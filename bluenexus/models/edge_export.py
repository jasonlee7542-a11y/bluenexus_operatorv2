import json
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from bluenexus.settings import Settings


def export_edge_models(
    frame: pl.DataFrame, output_dir: Path, settings: Settings = Settings()
) -> list[dict]:
    """Export a next-observation model, never reuse it for historical backtesting.

    Historical dashboard scores retain their separate prequential models. Feature
    generation, EWMA, diagnostics and score calibration remain outside this ONNX graph.
    """
    try:
        import onnxruntime as ort
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType
    except ImportError as exc:
        raise RuntimeError(
            "Install the optional edge dependencies: pip install -e '.[edge]'"
        ) from exc
    from bluenexus.pipeline import safe_output_directory

    output_dir = safe_output_directory(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = []
    names = list(settings.model_features)
    for plant in frame.sort(["plant", "date"]).partition_by("plant", maintain_order=True):
        eligible = plant.filter(pl.col("operating_state") != "STANDBY_INDICATED")
        x = eligible.select(names).to_numpy().astype(np.float32)
        x = x[np.isfinite(x).sum(axis=1) >= 3]
        if len(x) < settings.ensemble_min_history:
            continue
        if not np.all(np.isfinite(x).sum(axis=0) >= settings.baseline_min_history):
            raise ValueError("Insufficient historical coverage for the fixed ONNX input contract")
        model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", RobustScaler()),
                (
                    "forest",
                    IsolationForest(
                        n_estimators=100,
                        random_state=settings.random_seed,
                        contamination="auto",
                        n_jobs=1,
                    ),
                ),
            ]
        ).fit(x)
        forest = model.named_steps["forest"]
        converted = convert_sklearn(
            model,
            initial_types=[("features", FloatTensorType([None, len(names)]))],
            target_opset={"": 17, "ai.onnx.ml": 3},
            options={id(forest): {"score_samples": True}},
        )
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(
            converted.SerializeToString(), sess_options=options, providers=["CPUExecutionProvider"]
        )
        outputs = dict(
            zip([o.name for o in session.get_outputs()], session.run(None, {"features": x}))
        )
        score_name = next((k for k in outputs if "score_samples" in k), None)
        if score_name is None:
            raise RuntimeError(f"ONNX score_samples output missing: {list(outputs)}")
        sklearn_scores = model.score_samples(x)
        onnx_scores = outputs[score_name].ravel()
        error = float(np.max(abs(sklearn_scores - onnx_scores)))
        if error > 1e-5:
            raise RuntimeError(f"ONNX parity failed: max absolute error {error}")
        slug = plant["plant"][0].lower().replace(" ", "_")
        path = output_dir / f"{slug}_isolation_forest.onnx"
        path.write_bytes(converted.SerializeToString())
        metadata.append(
            {
                "plant": plant["plant"][0],
                "file": path.name,
                "training_rows": len(x),
                "observed_through": str(plant["date"].max()),
                "intended_use": (
                    "Observations after observed_through; not historical dashboard scoring"
                ),
                "input": {
                    "name": "features",
                    "dtype": "float32",
                    "columns": names,
                    "missing": "NaN; median imputation from historical training data",
                },
                "score_samples_output": score_name,
                "higher_score_means": "more normal",
                "maximum_absolute_score_error": error,
                "parity_tolerance": 1e-5,
                "graph_scope": "Median imputation, robust scaling and Isolation Forest only",
                "deployment": "Local CPU inference verified; AquaX Hub deployment untested",
            }
        )
    (output_dir / "manifest.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return metadata
