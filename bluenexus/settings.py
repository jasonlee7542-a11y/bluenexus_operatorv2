from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Settings:
    """Provisional challenge thresholds, not certified plant operating limits."""

    recovery_low: float = 0.70
    recovery_high: float = 0.76
    recovery_change: float = 0.10
    recovery_reporting_tolerance: float = 0.005
    recovery_cross_source_tolerance: float = 0.05
    energy_deviation: float = 0.20
    delivery_gap_fraction: float = 0.10
    delivery_gap_critical: float = 0.50
    naoh_deviation: float = 0.30
    ph_low: float = 6.5
    ph_high: float = 8.5
    flatline_window: int = 5
    flatline_variance: float = 1e-6
    warmup: int = 14
    ewma_alpha: float = 0.15
    ensemble_min_history: int = 28
    ensemble_refit_every: int = 7
    baseline_min_history: int = 7
    model_features: tuple[str, ...] = (
        "effluent_volume_m3",
        "sec_kwh_m3",
        "salt_passage_proxy",
        "effluent_ph",
    )
    random_seed: int = 42
    equipment_baseline_days: int = 14
    equipment_iqr_multiplier: float = 1.5
    equipment_persistence_days: int = 3
    assumed_temperature_high: float = 120.0
    peer_lookback_days: int = 60
    peer_output_tolerance: float = 0.20
    peer_minimum: int = 5

    def to_dict(self) -> dict:
        return asdict(self)
