import polars as pl

from bluenexus.ingestion.sanitizer import IngestionResult


def ratio(numerator: str | pl.Expr, denominator: str | pl.Expr) -> pl.Expr:
    n = pl.col(numerator) if isinstance(numerator, str) else numerator
    d = pl.col(denominator) if isinstance(denominator, str) else denominator
    return pl.when(n.is_not_null() & (d > 0)).then(n / d).otherwise(None)


def build_features(data: IngestionResult) -> pl.DataFrame:
    """Same-date daily joins only; no interpolation or monthly-dose propagation."""
    frame = data.performance.join(
        data.equipment, on=["plant", "date"], how="left", validate="1:1"
    ).sort(["plant", "date"])
    frame = frame.with_columns(
        ratio("daily_electricity_kwh", "effluent_volume_m3").alias("sec_kwh_m3"),
        ratio("effluent_volume_m3", "influent_volume_m3").alias("recovery_calculated"),
        ratio("effluent_conductivity_us_cm", "influent_conductivity_us_cm").alias(
            "salt_passage_proxy"
        ),
        ratio("effluent_volume_m3", "planned_reclaimed_supply_m3").alias(
            "throughput_vs_supply_plan"
        ),
        (pl.col("reclaimed_supply_volume_m3") - pl.col("customer_end_volume_m3")).alias(
            "delivery_gap_m3"
        ),
        ratio("actual_naoh_dose_reported", "planned_naoh_dose_reported")
        .sub(1)
        .alias("naoh_deviation"),
        (pl.col("rohsl") / 100).alias("equipment_ro_recovery"),
        pl.when(pl.col("plant") == "Plant A")
        .then(pl.lit("FIXED_REPORTED_NOT_INDEPENDENTLY_VERIFIED"))
        .otherwise(pl.lit("CALCULATED_FROM_REPORTED_VOLUMES"))
        .alias("recovery_provenance"),
    ).with_columns(
        ratio("sec_kwh_m3", "planned_specific_energy_kwh_m3").sub(1).alias("sec_deviation"),
        (1 - pl.col("salt_passage_proxy")).alias("salt_rejection_proxy"),
        ratio("delivery_gap_m3", "reclaimed_supply_volume_m3").alias("delivery_gap_fraction"),
        (pl.col("recovery_calculated") - pl.col("reported_recovery_rate")).alias(
            "recovery_reporting_difference"
        ),
        (pl.col("recovery_calculated") - pl.col("equipment_ro_recovery")).alias(
            "recovery_cross_source_difference"
        ),
        pl.when(pl.col("plant") == "Plant B")
        .then(pl.col("recovery_calculated"))
        .otherwise(None)
        .alias("recovery_for_monitoring"),
        (
            pl.col("daily_electricity_kwh")
            - pl.col("effluent_volume_m3") * pl.col("planned_specific_energy_kwh_m3")
        )
        .clip(lower_bound=0)
        .alias("excess_energy_vs_plan_kwh"),
        pl.col("salt_passage_proxy").is_not_null().alias("conductivity_available"),
        pl.col("actual_naoh_dose_reported").is_not_null().alias("naoh_available"),
    )
    return build_equipment_features(frame)


def build_equipment_features(frame: pl.DataFrame) -> pl.DataFrame:
    axes = [f"c4_m4_ro1_high_pressure_pump_{c}" for c in ("xsd", "ysd", "zsd")]
    displacement = [f"c4_m4_ro1_high_pressure_pump_{c}" for c in ("xwy", "ywy", "zwy")]
    for columns, name in [
        (axes, "vibration_resultant_reported"),
        (displacement, "displacement_resultant_reported"),
    ]:
        complete = pl.all_horizontal([pl.col(c).is_not_null() for c in columns])
        frame = frame.with_columns(
            pl.when(complete)
            .then(pl.sum_horizontal([pl.col(c).pow(2) for c in columns]).sqrt())
            .otherwise(None)
            .alias(name)
        )
    frame = frame.with_columns(
        pl.col("c4_m4_ro1_high_pressure_pump_wd").alias("motor_temperature_reported"),
        pl.col("c_m_ro1_high_pressure_pump_fre_out").alias("ro1_frequency_hz"),
        pl.col("c_m_ro1_high_pressure_pump_a_out").alias("ro1_current_reported"),
        pl.col("c_m_ro_tt_zjs_out").alias("feed_temperature_candidate"),
        # Unsupported quantities stay unavailable rather than using invented inputs.
        pl.lit(None, dtype=pl.Float64).alias("hydraulic_resistance"),
        pl.lit(None, dtype=pl.Float64).alias("normalized_membrane_flow"),
        pl.lit(None, dtype=pl.Float64).alias("current_unbalance"),
        pl.lit(None, dtype=pl.Float64).alias("thermal_dissipation_ratio"),
    )
    return frame


def feature_registry() -> list[dict]:
    """Human-readable measurement contract for every derived diagnostic feature."""
    entries = [
        (
            "sec_kwh_m3",
            "kWh/m3",
            "electricity / effluent volume",
            "SUPPORTED",
            "Daily reported electricity and effluent boundaries assumed consistent.",
        ),
        (
            "sec_deviation",
            "fraction",
            "SEC / planned SEC - 1",
            "SUPPORTED",
            "Plan comparison, not demonstrated savings.",
        ),
        (
            "salt_passage_proxy",
            "fraction",
            "effluent / influent conductivity",
            "PROXY",
            "Plant-level sampling points; not confirmed RO membrane feed/permeate.",
        ),
        (
            "recovery_calculated",
            "fraction",
            "effluent / influent volume",
            "PROXY",
            "Plant A fixed 75% is excluded from independent recovery alerts.",
        ),
        (
            "equipment_ro_recovery",
            "fraction",
            "rohsl / 100",
            "REPORTED",
            "RO-specific signal kept separate from whole-plant volumetric recovery.",
        ),
        (
            "delivery_gap_m3",
            "m3/day",
            "reclaimed supply - customer-end",
            "SUPPORTED",
            "Storage changes, timing and different meter boundaries are possible explanations.",
        ),
        (
            "naoh_deviation",
            "fraction",
            "actual reported dose / planned reported dose - 1",
            "SUPPORTED",
            "Plant A has 2 records; Plant B has 62. Dose units are unverified.",
        ),
        (
            "throughput_vs_supply_plan",
            "fraction",
            "effluent / planned reclaimed supply",
            "PROXY",
            "Supply plan is not certified rated capacity.",
        ),
        (
            "excess_energy_vs_plan_kwh",
            "kWh",
            "max(electricity - effluent * planned SEC, 0)",
            "REFERENCE",
            "Positive daily deviations summed; not net excess or attainable savings.",
        ),
        (
            "vibration_resultant_reported",
            "reported sensor units",
            "sqrt(xsd^2 + ysd^2 + zsd^2)",
            "PROXY",
            "Vector resultant, not waveform RMS or vibration spectrum.",
        ),
        (
            "displacement_resultant_reported",
            "reported sensor units",
            "sqrt(xwy^2+ywy^2+zwy^2)",
            "PROXY",
            "Axis measurement convention and units are unverified.",
        ),
        (
            "motor_temperature_reported",
            "reported sensor units",
            "wd",
            "REPORTED",
            "Plant B RO1 only; compare historical load-conditioned trends.",
        ),
        (
            "hydraulic_resistance",
            "unavailable",
            "pressure / flow",
            "UNAVAILABLE",
            "No confirmed pressure mapping in supplied CSVs.",
        ),
        (
            "normalized_membrane_flow",
            "unavailable",
            "vendor-specific normalization",
            "UNAVAILABLE",
            "Pressure, membrane metadata and verified feed temperature unavailable.",
        ),
        (
            "current_unbalance",
            "unavailable",
            "abs(Ia-Ic)/mean(Ia,Ic)",
            "UNAVAILABLE",
            "Plant A Pump 2 phase C is fixed zero; do not diagnose electrical imbalance.",
        ),
        (
            "thermal_dissipation_ratio",
            "unavailable",
            "temperature / frequency",
            "UNAVAILABLE",
            "Not a verified physical diagnostic; do not assign a failure threshold.",
        ),
    ]
    return [
        dict(zip(("feature", "unit", "formula", "status", "limitation"), row)) for row in entries
    ]
