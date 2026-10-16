from dataclasses import dataclass

import numpy as np
import polars as pl
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import RobustScaler

from bluenexus.settings import Settings


@dataclass
class ModelResult:
    scored: pl.DataFrame
    training_runs: list[dict]


def statistical_baseline(
    frame: pl.DataFrame, column: str, prefix: str, settings: Settings
) -> pl.DataFrame:
    """Score t against a lagged EWMA and lagged trailing population stddev."""
    frame = frame.sort(["plant", "date"])
    x = pl.col(column)
    window = max(14, settings.baseline_min_history)
    frame = frame.with_columns(
        x.ewm_mean(
            alpha=settings.ewma_alpha,
            adjust=False,
            min_samples=settings.baseline_min_history,
            ignore_nulls=True,
        )
        .shift(1)
        .over("plant")
        .alias(prefix + "_mean"),
        x.rolling_std(window_size=window, min_samples=settings.baseline_min_history, ddof=0)
        .shift(1)
        .over("plant")
        .alias(prefix + "_std"),
    )
    floor = (pl.col(prefix + "_mean").abs() * 0.02).clip(lower_bound=1e-6)
    std = pl.max_horizontal(pl.col(prefix + "_std"), floor)
    return frame.with_columns(
        pl.when(pl.col(prefix + "_std").is_not_null())
        .then((x - pl.col(prefix + "_mean")) / std)
        .otherwise(None)
        .alias(prefix + "_z"),
        (pl.col(prefix + "_mean") - 3 * std).alias(prefix + "_lower"),
        (pl.col(prefix + "_mean") + 3 * std).alias(prefix + "_upper"),
    )


def _percentile(reference: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Reference contains historical training scores only, never evaluation rows."""
    return np.searchsorted(np.sort(reference), values, side="right") / len(reference)


def score_process(frame: pl.DataFrame, settings: Settings = Settings()) -> ModelResult:
    """Weekly historical refits; vectorized scoring within each chronological batch."""
    frame = statistical_baseline(frame, "sec_kwh_m3", "sec_baseline", settings)
    frame = statistical_baseline(frame, "recovery_for_monitoring", "recovery_baseline", settings)
    frame = frame.with_columns(
        pl.max_horizontal(pl.col("sec_baseline_z").abs(), pl.col("recovery_baseline_z").abs())
        .truediv(6)
        .clip(0, 1)
        .alias("statistical_score")
    )
    pieces, runs = [], []
    for plant_frame in frame.partition_by("plant", maintain_order=True):
        plant = plant_frame["plant"][0]
        n = plant_frame.height
        pca_score = np.full(n, np.nan)
        isolation_score = np.full(n, np.nan)
        expected_energy = np.full(n, np.nan)
        model_cutoffs = [None] * n
        feature_names = list(settings.model_features)
        x = plant_frame.select(feature_names).to_numpy().astype(float)
        energy = plant_frame["daily_electricity_kwh"].to_numpy().astype(float)
        volume = plant_frame["effluent_volume_m3"].to_numpy().astype(float)
        eligible = np.array(plant_frame["operating_state"].to_list()) != "STANDBY_INDICATED"
        energy_valid = eligible & np.isfinite(energy) & np.isfinite(volume) & (volume > 0)
        # Stateful refits are intentionally sequential. Rows within a batch are scored together.
        for start in range(settings.warmup, n, settings.ensemble_refit_every):
            stop = min(start + settings.ensemble_refit_every, n)
            history = np.flatnonzero(energy_valid[:start])
            if len(history) < settings.warmup:
                continue
            design = np.column_stack([np.ones(len(history)), volume[history] / 1000])
            energy_model = LinearRegression(positive=True, fit_intercept=False).fit(
                design, energy[history]
            )
            batch_valid = np.isfinite(volume[start:stop]) & (volume[start:stop] > 0)
            batch_design = np.column_stack([np.ones(stop - start), volume[start:stop] / 1000])
            batch_design[~np.isfinite(batch_design)] = 0
            prediction = energy_model.predict(batch_design)
            expected_energy[start:stop] = np.where(batch_valid, prediction, np.nan)
            runs.append(
                {
                    "plant": plant,
                    "model": "nonnegative_energy_load_baseline",
                    "train_through": str(plant_frame["date"][start - 1]),
                    "score_from": str(plant_frame["date"][start]),
                    "training_rows": len(history),
                    "baseload_kwh_day": float(energy_model.coef_[0]),
                    "marginal_kwh_m3": float(energy_model.coef_[1] / 1000),
                }
            )
        for start in range(settings.ensemble_min_history, n, settings.ensemble_refit_every):
            stop = min(start + settings.ensemble_refit_every, n)
            complete = np.sum(np.isfinite(x[:start]), axis=1) >= 3
            history = x[:start][complete & eligible[:start]]
            if len(history) < settings.ensemble_min_history:
                continue
            # Select usable columns from historical data only.
            usable = np.sum(np.isfinite(history), axis=0) >= settings.baseline_min_history
            if usable.sum() < 2:
                continue
            imputer = SimpleImputer(strategy="median")
            train = imputer.fit_transform(history[:, usable])
            scaler = RobustScaler().fit(train)
            train = scaler.transform(train)
            batch = scaler.transform(imputer.transform(x[start:stop, usable]))
            pca = PCA(n_components=min(2, train.shape[1] - 1), svd_solver="full").fit(train)
            train_error = np.sum((train - pca.inverse_transform(pca.transform(train))) ** 2, axis=1)
            batch_error = np.sum((batch - pca.inverse_transform(pca.transform(batch))) ** 2, axis=1)
            forest = IsolationForest(
                n_estimators=100,
                max_samples=min(256, len(train)),
                contamination="auto",
                random_state=settings.random_seed,
                n_jobs=1,
            ).fit(train)
            pca_score[start:stop] = _percentile(train_error, batch_error)
            isolation_score[start:stop] = _percentile(
                -forest.score_samples(train), -forest.score_samples(batch)
            )
            valid = (np.sum(np.isfinite(x[start:stop]), axis=1) >= 3) & eligible[start:stop]
            pca_score[start:stop] = np.where(valid, pca_score[start:stop], np.nan)
            isolation_score[start:stop] = np.where(valid, isolation_score[start:stop], np.nan)
            cutoff = str(plant_frame["date"][start - 1])
            model_cutoffs[start:stop] = [cutoff] * (stop - start)
            runs.append(
                {
                    "plant": plant,
                    "model": "PCA_and_IsolationForest",
                    "train_through": cutoff,
                    "score_from": str(plant_frame["date"][start]),
                    "training_rows": len(history),
                    "features": [name for name, use in zip(feature_names, usable) if use],
                    "calibration": "empirical historical training-score percentile",
                }
            )
        pieces.append(
            plant_frame.with_columns(
                pl.Series("pca_score", pca_score, nan_to_null=True),
                pl.Series("isolation_score", isolation_score, nan_to_null=True),
                pl.Series("expected_energy_kwh", expected_energy, nan_to_null=True),
                pl.Series("multivariate_train_through", model_cutoffs, dtype=pl.String),
            )
        )
    scored = (
        pl.concat(pieces)
        .with_columns(
            pl.when(pl.col("expected_energy_kwh") > 0)
            .then(pl.col("daily_electricity_kwh") / pl.col("expected_energy_kwh") - 1)
            .otherwise(None)
            .alias("energy_load_residual_fraction"),
            pl.mean_horizontal("statistical_score", "pca_score", "isolation_score").alias(
                "ensemble_score"
            ),
            pl.sum_horizontal(
                [
                    pl.col(c).is_not_null().cast(pl.Int32)
                    for c in ("statistical_score", "pca_score", "isolation_score")
                ]
            ).alias("available_detectors"),
        )
        .with_columns(
            (1 - pl.col("ensemble_score")).alias("relative_health_index"),
            pl.when(pl.col("available_detectors") == 0)
            .then(pl.lit("WARMUP"))
            .when(pl.col("available_detectors") < 3)
            .then(pl.lit("PARTIAL"))
            .otherwise(pl.lit("ENSEMBLE"))
            .alias("model_status"),
        )
    )
    return ModelResult(scored.sort(["plant", "date"]), runs)


def score_equipment(frame: pl.DataFrame, settings: Settings = Settings()) -> pl.DataFrame:
    frame = statistical_baseline(frame, "vibration_resultant_reported", "vibration", settings)
    return statistical_baseline(frame, "motor_temperature_reported", "motor_temperature", settings)
