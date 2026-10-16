from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from io import BytesIO

import polars as pl

from bluenexus.settings import Settings

FILES = {
    "plant_daily_performance.csv": None,
    "plant_A_equipment_daily.csv": "Plant A",
    "plant_B_equipment_daily.csv": "Plant B",
}
KEYS = ["plant", "date"]
EVENT_SCHEMA = {
    "plant": pl.String,
    "date": pl.Date,
    "signal": pl.String,
    "code": pl.String,
    "severity": pl.String,
    "raw_value": pl.Float64,
    "message": pl.String,
}
REQUIRED_PERFORMANCE = {
    "plant",
    "date",
    "influent_volume_m3",
    "effluent_volume_m3",
    "daily_electricity_kwh",
    "planned_specific_energy_kwh_m3",
    "reported_recovery_rate",
    "reclaimed_supply_volume_m3",
    "customer_end_volume_m3",
    "influent_conductivity_us_cm",
    "effluent_conductivity_us_cm",
    "effluent_ph",
    "actual_naoh_dose_reported",
    "planned_naoh_dose_reported",
    "planned_reclaimed_supply_m3",
}


@dataclass
class IngestionResult:
    performance: pl.DataFrame
    equipment: pl.DataFrame
    quality_events: pl.DataFrame
    column_audit: pl.DataFrame
    source_manifest: list[dict]
    raw_dir: Path
    raw_equipment: pl.DataFrame | None = None
    parsing_log: list[dict] | None = None


def parse_frame(raw: pl.DataFrame, plant: str | None = None) -> pl.DataFrame:
    """Parse explicit date formats and nullable finite numbers without imputation."""
    if "date" not in raw.columns:
        raise ValueError("Missing date column")
    if plant is not None:
        if "plant" in raw.columns and raw.filter(pl.col("plant") != plant).height:
            raise ValueError(f"Equipment plant identifier conflicts with file: {plant}")
        raw = raw.with_columns(pl.lit(plant).alias("plant"))
    elif "plant" not in raw.columns:
        raise ValueError("Missing plant column")
    date = pl.col("date").cast(pl.String).str.strip_chars()
    numeric = [c for c in raw.columns if c not in KEYS]
    expressions = []
    for c in numeric:
        value = pl.col(c).cast(pl.String).str.strip_chars().cast(pl.Float64, strict=False)
        expressions.append(pl.when(value.is_finite()).then(value).otherwise(None).alias(c))
    frame = raw.with_columns(
        pl.coalesce(
            date.str.strptime(pl.Date, "%m/%d/%Y", strict=False),
            date.str.strptime(pl.Date, "%Y/%m/%d", strict=False),
            date.str.strptime(pl.Date, "%Y-%m-%d", strict=False),
        ).alias("date"),
        *expressions,
    ).sort(KEYS)
    if frame.select(pl.col("date").is_null().any()).item():
        raise ValueError("Unparseable date; expected MM/DD/YYYY, YYYY/MM/DD or YYYY-MM-DD")
    if frame.select(pl.col("plant").is_null().any()).item():
        raise ValueError("Plant identifier is missing")
    if frame.select(pl.struct(KEYS).is_duplicated().any()).item():
        raise ValueError("Duplicate plant/date key; aggregation must be explicit")
    return frame


def _event(
    frame: pl.DataFrame,
    signal: str,
    predicate: pl.Expr,
    code: str,
    message: str,
    severity: str = "warning",
) -> pl.DataFrame:
    return (
        frame.filter(predicate.fill_null(False))
        .select(
            *KEYS,
            pl.lit(signal).alias("signal"),
            pl.lit(code).alias("code"),
            pl.lit(severity).alias("severity"),
            pl.col(signal).alias("raw_value"),
            pl.lit(message).alias("message"),
        )
        .cast(EVENT_SCHEMA)
    )


def sanitize(frame: pl.DataFrame, settings: Settings = Settings()) -> tuple:
    """Quarantine known invalid ranges; retain ambiguous register scales unchanged."""
    events = []
    clean = frame.clone()
    numeric = [c for c, dtype in frame.schema.items() if dtype == pl.Float64]
    for c in numeric:
        bounds = None
        if c in ("influent_ph", "effluent_ph"):
            bounds = (0.0, 14.0)
        elif "frequency" in c or c.endswith("fre_out"):
            bounds = (0.0, float("inf"))
        elif c.endswith("volume_m3") or c == "daily_electricity_kwh":
            bounds = (0.0, float("inf"))
        elif "conductivity_us_cm" in c or "actual_" in c and "dose_reported" in c:
            bounds = (0.0, float("inf"))
        elif c in ("rohsl", "ufhsl"):
            bounds = (0.0, 100.0)
        elif c == "reported_recovery_rate":
            bounds = (0.0, 1.0)
        if bounds is not None:
            invalid = (pl.col(c) < bounds[0]) | (pl.col(c) > bounds[1])
            events.append(
                _event(
                    frame,
                    c,
                    invalid,
                    "PHYSICAL_RANGE",
                    "Outside the configured application range; excluded from calculations. Verify units and measurement boundaries.",
                )
            )
            clean = clean.with_columns(pl.when(invalid).then(None).otherwise(pl.col(c)).alias(c))
        if "costheta" in c:
            events.append(
                _event(
                    frame,
                    c,
                    (pl.col(c) < 0) | (pl.col(c) > 1),
                    "UNRESOLVED_SCALE",
                    "Power-factor register scale is unverified; no automatic rescaling.",
                )
            )
        # Flatline checks exclude performance plans and sparse reconciliation records.
        if c not in REQUIRED_PERFORMANCE and not c.startswith(("planned_", "actual_")):
            variance = (
                pl.col(c)
                .rolling_var(
                    window_size=settings.flatline_window, min_samples=settings.flatline_window
                )
                .over("plant")
            )
            events.append(
                _event(
                    frame,
                    c,
                    variance < settings.flatline_variance,
                    "FLATLINE_CANDIDATE",
                    "Five identical daily readings; steady operation or stale signal.",
                )
            )
        if c.endswith("runtime_cumulative") or c.endswith("_ep") or c.startswith("advancedtags"):
            delta = pl.col(c).diff().over("plant")
            events.append(
                _event(
                    frame,
                    c,
                    delta < 0,
                    "COUNTER_DECREASE",
                    "Counter decreased; reset, rollover or invalid reading is unresolved.",
                )
            )
            clean = clean.with_columns(
                pl.when(delta >= 0).then(delta).otherwise(None).alias(c + "__delta")
            )
    event_frame = pl.concat(events) if events else pl.DataFrame(schema=EVENT_SCHEMA)
    return clean, event_frame


def operating_state(equipment: pl.DataFrame) -> pl.DataFrame:
    """A daily export can indicate activity, but cannot establish CIP duration."""
    frequencies = [
        c for c in equipment.columns if "frequency_feedback_o" in c or c.endswith("fre_out")
    ]
    if not frequencies:
        return equipment.with_columns(pl.lit("UNKNOWN").alias("operating_state"))
    known = pl.sum_horizontal([pl.col(c).is_not_null().cast(pl.Int32) for c in frequencies])
    active = pl.any_horizontal([pl.col(c) > 5 for c in frequencies]).fill_null(False)
    idle = pl.all_horizontal([pl.col(c).is_null() | (pl.col(c) <= 1) for c in frequencies])
    return equipment.with_columns(
        pl.when(active)
        .then(pl.lit("ACTIVE_INDICATED"))
        .when((known > 0) & idle)
        .then(pl.lit("STANDBY_INDICATED"))
        .otherwise(pl.lit("UNKNOWN"))
        .alias("operating_state")
    )


def _audit(frame: pl.DataFrame, source: str) -> list[dict]:
    rows = []
    for c in frame.columns:
        if c in KEYS:
            continue
        summary = frame.select(
            pl.col(c).is_null().sum().alias("missing"),
            pl.col(c).drop_nulls().n_unique().alias("unique"),
            pl.col(c).min().alias("minimum"),
            pl.col(c).max().alias("maximum"),
        ).row(0, named=True)
        count = frame.height - summary["missing"]
        rows.append(
            {
                "source": source,
                "signal": c,
                "rows": frame.height,
                "available": count,
                "missing_fraction": summary["missing"] / frame.height if frame.height else None,
                "availability": "MISSING"
                if count == 0
                else "CONSTANT"
                if summary["unique"] == 1
                else "VARIABLE",
                **summary,
            }
        )
    return rows


def ingest(raw_dir: Path, settings: Settings = Settings(), blobs: dict | None = None) -> IngestionResult:
    """Read exactly the three challenge files. Extra CSVs are never consumed."""
    frames, audits, manifests, events, originals, parsing = {}, [], [], [], {}, []
    for filename, plant in FILES.items():
        path = raw_dir / filename
        payload = blobs[filename] if blobs is not None else path.read_bytes()
        raw = pl.read_csv(BytesIO(payload), infer_schema=False)
        original_rows = raw.height
        raw = raw.unique(maintain_order=True)
        parsing.append(dict(file=filename, action="Exact duplicate rows removed", count=original_rows-raw.height, column="", original=""))
        for col in raw.columns:
            raw = raw.with_columns(pl.col(col).str.strip_chars().alias(col))
            raw = raw.with_columns(pl.when(pl.col(col).str.to_uppercase().is_in(["", "NULL", "NAN", "NA", "N/A", "/"])).then(None).otherwise(pl.col(col)).alias(col))
            if col not in KEYS:
                numeric = pl.col(col).cast(pl.Float64, strict=False)
                bad = raw.filter(pl.col(col).is_not_null() & (numeric.is_null() | ~numeric.is_finite()))
                for item in bad.select("date",col).iter_rows(named=True):
                    parsing.append(dict(file=filename, date=item["date"], action="Invalid numeric token to missing", count=1, column=col, original=item[col]))
        if plant is None and not REQUIRED_PERFORMANCE.issubset(raw.columns):
            raise ValueError(
                f"Performance schema missing: {sorted(REQUIRED_PERFORMANCE - set(raw.columns))}"
            )
        parsed = parse_frame(raw, plant)
        if parsed.is_empty():
            raise ValueError(f"{filename}: no records")
        if plant is None and not set(parsed["plant"].unique()).issubset({"Plant A", "Plant B"}):
            raise ValueError("Unexpected plant identifier in challenge performance data")
        audits.extend(_audit(parsed, filename))
        originals[filename] = parsed
        clean, quality = sanitize(parsed, settings)
        frames[filename] = clean
        events.append(quality)
        manifests.append(
            {
                "file": filename,
                "sha256": sha256(payload).hexdigest(),
                "source_rows": original_rows,
                "rows": parsed.height,
                "columns": raw.width,
                "first_date": str(parsed["date"].min()),
                "last_date": str(parsed["date"].max()),
                "all_missing_columns": sum(
                    a["available"] == 0 for a in audits if a["source"] == filename
                ),
            }
        )
    equipment = pl.concat([frames[f] for f, plant in FILES.items() if plant], how="diagonal_relaxed").sort(KEYS)
    # Optional diagnostic inputs remain explicitly unavailable if absent in uploads.
    optional = [f"c4_m4_ro1_high_pressure_pump_{x}" for x in ["xsd", "ysd", "zsd", "xwy", "ywy", "zwy", "wd"]]
    optional += ["c_m_ro1_high_pressure_pump_fre_out", "c_m_ro1_high_pressure_pump_a_out", "c_m_ro_tt_zjs_out", "rohsl"]
    equipment = equipment.with_columns([pl.lit(None, dtype=pl.Float64).alias(c) for c in optional if c not in equipment.columns])
    equipment = operating_state(equipment)
    if set(frames["plant_daily_performance.csv"]["plant"].unique()) != {"Plant A", "Plant B"}:
        raise ValueError("Performance file must include both Plant A and Plant B")
    return IngestionResult(
        frames["plant_daily_performance.csv"],
        equipment,
        pl.concat(events).sort([*KEYS, "signal", "code"]),
        pl.DataFrame(audits),
        manifests,
        raw_dir.resolve(),
        pl.concat([originals[f] for f, plant in FILES.items() if plant], how="diagonal_relaxed").sort(KEYS),
        parsing,
    )
