import hashlib
import json
from dataclasses import dataclass

import polars as pl

from bluenexus.settings import Settings

ALERT_SCHEMA = {
    "event_id": pl.String,
    "date": pl.Date,
    "plant": pl.String,
    "code": pl.String,
    "subsystem": pl.String,
    "severity": pl.String,
    "event_type": pl.String,
    "message": pl.String,
    "next_action": pl.String,
    "evidence": pl.String,
    "persistence_steps": pl.Int32,
    "energy_reference_kwh": pl.Float64,
    "potential_savings": pl.Float64,
}


@dataclass
class Rule:
    code: str
    subsystem: str
    condition: pl.Expr
    message: str
    next_action: str
    signals: tuple[str, ...]
    persistence: int = 1
    severity: str = "warning"
    immediate: pl.Expr | None = None
    critical: pl.Expr | None = None


def evaluate_rule(frame: pl.DataFrame, rule: Rule) -> pl.DataFrame:
    """Emit at episode onset; missing values and calendar gaps reset persistence."""
    frame = frame.sort(["plant", "date"]).with_columns(
        rule.condition.fill_null(False).alias("__trigger")
    )
    if rule.persistence > 1:
        condition = (
            pl.col("__trigger")
            .cast(pl.Int32)
            .rolling_sum(window_size=rule.persistence, min_samples=rule.persistence)
            .over("plant")
            == rule.persistence
        ) & (
            (
                pl.col("date") - pl.col("date").shift(rule.persistence - 1).over("plant")
            ).dt.total_days()
            == rule.persistence - 1
        )
    else:
        condition = pl.col("__trigger")
    if rule.immediate is not None:
        condition = condition | rule.immediate.fill_null(False)
    frame = frame.with_columns(condition.fill_null(False).alias("__qualified"))
    previous = pl.col("__qualified").shift(1).over("plant").fill_null(False)
    consecutive = (pl.col("date").diff().over("plant").dt.total_days() == 1).fill_null(False)
    onset = pl.col("__qualified") & ~(previous & consecutive)
    # A critical escalation is emitted even inside an already active warning episode.
    critical = rule.critical.fill_null(False) if rule.critical is not None else pl.lit(False)
    frame = frame.with_columns(critical.alias("__critical"))
    escalation = pl.col("__critical") & ~pl.col("__critical").shift(1).over("plant").fill_null(
        False
    )
    # Preserve every qualifying day; the shared case layer groups consecutive days.
    selected = frame.with_columns(onset.alias("__onset"),escalation.alias("__escalation")).filter(pl.col("__qualified"))
    events = []
    for row in selected.iter_rows(named=True):
        evidence = {c: row.get(c) for c in rule.signals}
        # Explanatory serialization is outside the vectorized time-series calculations.
        event_id = hashlib.sha256(f"{row['plant']}|{row['date']}|{rule.code}".encode()).hexdigest()[
            :16
        ]
        events.append(
            {
                "event_id": event_id,
                "date": row["date"],
                "plant": row["plant"],
                "code": rule.code,
                "subsystem": rule.subsystem,
                "severity": "critical" if row["__critical"] else rule.severity,
                "event_type": "episode_onset" if row["__onset"] else "critical_escalation" if row["__escalation"] else "continuation",
                "message": rule.message,
                "next_action": rule.next_action,
                "evidence": json.dumps(evidence, default=str, allow_nan=False),
                "persistence_steps": 1
                if rule.immediate is not None and row["__critical"]
                else rule.persistence,
                "energy_reference_kwh": row.get("excess_energy_vs_plan_kwh")
                if rule.subsystem == "Energy"
                else None,
                "potential_savings": None,
            }
        )
    return pl.DataFrame(events, schema=ALERT_SCHEMA)


def diagnose_process(frame: pl.DataFrame, settings: Settings = Settings()) -> pl.DataFrame:
    f = pl.col
    recovery = f("recovery_for_monitoring")
    recovery_extreme = (recovery > 0.85) | (recovery < 0.65)
    low_throughput = f("throughput_vs_supply_plan") < 0.4
    rules = [
        Rule(
            "RECOVERY_CORRIDOR",
            "Recovery",
            (recovery < settings.recovery_low) | (recovery > settings.recovery_high),
            "Calculated recovery is outside the provisional challenge corridor.",
            "Compare daily volume reporting and RO recovery. Scaling or flushing is unconfirmed.",
            (
                "recovery_calculated",
                "reported_recovery_rate",
                "equipment_ro_recovery",
                "recovery_cross_source_difference",
            ),
            persistence=2,
            immediate=recovery_extreme,
            critical=recovery_extreme,
        ),
        Rule(
            "RECOVERY_STEP_CHANGE",
            "Recovery",
            recovery.diff().over("plant").abs() > settings.recovery_change,
            "Daily calculated recovery changed by more than 10 percentage points.",
            "Review adjacent daily records and conflicting recovery sources before attribution.",
            ("recovery_calculated", "equipment_ro_recovery", "recovery_cross_source_difference"),
        ),
        Rule(
            "RECOVERY_SOURCE_DISAGREEMENT",
            "Data quality",
            f("recovery_cross_source_difference").abs() > settings.recovery_cross_source_tolerance,
            "Whole-plant calculated recovery and reported RO recovery disagree.",
            "Keep both series separate; check measurement boundaries and export aggregation.",
            ("recovery_calculated", "equipment_ro_recovery", "recovery_cross_source_difference"),
        ),
        Rule(
            "RECOVERY_REPORT_MISMATCH",
            "Data quality",
            f("recovery_reporting_difference").abs() > settings.recovery_reporting_tolerance,
            "Reported recovery differs from the same row's effluent/influent ratio.",
            "Review the reporting formula; retain reported and independently calculated values.",
            ("reported_recovery_rate", "recovery_calculated", "recovery_reporting_difference"),
        ),
        Rule(
            "DELIVERY_DISCREPANCY",
            "Water distribution",
            f("delivery_gap_fraction").abs() > settings.delivery_gap_fraction,
            "Reclaimed supply and customer-end daily volume differ materially.",
            "Review timing, storage and meter boundaries. This does not establish leakage.",
            (
                "reclaimed_supply_volume_m3",
                "customer_end_volume_m3",
                "delivery_gap_m3",
                "delivery_gap_fraction",
            ),
            persistence=2,
            immediate=f("delivery_gap_fraction").abs() > settings.delivery_gap_critical,
            critical=f("delivery_gap_fraction").abs() > settings.delivery_gap_critical,
        ),
        Rule(
            "LOW_THROUGHPUT_ENERGY",
            "Energy",
            (f("sec_deviation") > settings.energy_deviation) & low_throughput,
            "High specific energy coincides with low throughput relative to the supply plan.",
            "Compare the historical load baseline before treating this as equipment degradation.",
            (
                "effluent_volume_m3",
                "throughput_vs_supply_plan",
                "sec_kwh_m3",
                "sec_deviation",
                "energy_load_residual_fraction",
            ),
        ),
        Rule(
            "ENERGY_ABOVE_PLAN",
            "Energy",
            (f("sec_deviation") > settings.energy_deviation) & ~low_throughput,
            "Specific energy remains more than 20% above the reported plan.",
            "Review throughput, daily energy boundaries and the load-adjusted residual.",
            (
                "sec_kwh_m3",
                "planned_specific_energy_kwh_m3",
                "sec_deviation",
                "energy_load_residual_fraction",
            ),
            persistence=2,
        ),
        Rule(
            "ENERGY_LOAD_RESIDUAL",
            "Energy",
            f("energy_load_residual_fraction") > settings.energy_deviation,
            "Electricity exceeds the historical throughput-conditioned estimate.",
            "Investigate operating changes; the observational baseline does not prove a fault.",
            ("daily_electricity_kwh", "expected_energy_kwh", "energy_load_residual_fraction"),
            persistence=2,
        ),
        Rule(
            "NAOH_REPORTED_DEVIATION",
            "Chemicals",
            f("naoh_deviation").abs() > settings.naoh_deviation,
            "Recorded NaOH dose differs from its reported plan by more than 30%.",
            "Review this recorded dose and effluent pH. Plant A has only two dose records.",
            (
                "actual_naoh_dose_reported",
                "planned_naoh_dose_reported",
                "naoh_deviation",
                "effluent_ph",
            ),
        ),
        Rule(
            "EFFLUENT_PH",
            "Water quality",
            (f("effluent_ph") < settings.ph_low) | (f("effluent_ph") > settings.ph_high),
            "Effluent pH is outside the provisional challenge interval of 6.5 to 8.5.",
            "Review the reported pH and available dosing records; dosing causality is unconfirmed.",
            ("effluent_ph", "actual_naoh_dose_reported", "naoh_deviation"),
        ),
        Rule(
            "MULTIVARIATE_NOVELTY",
            "Process pattern",
            (f("ensemble_score") > 0.85) & (f("available_detectors") == 3),
            "Multiple historical detectors indicate a persistent unusual process pattern.",
            "Review scores and physical evidence. A high score does not establish failure.",
            (
                "statistical_score",
                "pca_score",
                "isolation_score",
                "ensemble_score",
                "multivariate_train_through",
            ),
            persistence=2,
        ),
    ]
    return pl.concat([evaluate_rule(frame, r) for r in rules]).sort(["date", "plant", "code"])


def diagnose_equipment(frame: pl.DataFrame) -> pl.DataFrame:
    active = pl.col("operating_state") == "ACTIVE_INDICATED"
    rules = [
        Rule(
            "VIBRATION_TREND",
            "Mechanical",
            (pl.col("vibration_z") > 3) & active,
            "Reported RO1 vibration resultant remains above its historical trend band.",
            "Review the daily axis readings. Waveforms and verified units are unavailable.",
            ("vibration_resultant_reported", "vibration_mean", "vibration_z", "ro1_frequency_hz"),
            persistence=2,
        ),
        Rule(
            "MOTOR_TEMPERATURE_TREND",
            "Mechanical",
            (pl.col("motor_temperature_z") > 3) & active,
            "Reported RO1 motor temperature remains above its historical trend band.",
            "Compare load and frequency. Thermal images and ambient temperature are unavailable.",
            (
                "motor_temperature_reported",
                "motor_temperature_mean",
                "motor_temperature_z",
                "ro1_frequency_hz",
            ),
            persistence=2,
        ),
    ]
    return pl.concat([evaluate_rule(frame, r) for r in rules]).sort(["date", "plant", "code"])
