"""Load and check the notebook model bundle in a separate Python process."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def score(artifact: Path, probe: dict) -> dict:
    import joblib
    import numpy as np
    import pandas as pd
    import sklearn
    from threadpoolctl import threadpool_limits
    manifest = json.loads((artifact / "manifest.json").read_text())
    if manifest["schema_version"] != 1:
        raise ValueError("Unsupported notebook artifact schema")
    for name in ("model.joblib", "feature_runtime.py"):
        actual = hashlib.sha256((artifact / name).read_bytes()).hexdigest()
        if actual != manifest["checksums"][name]:
            raise ValueError("Artifact checksum mismatch: " + name)
    if manifest["dependencies"]["sklearn"] != sklearn.__version__:
        raise ValueError("Artifact requires its recorded sklearn version")
    spec = importlib.util.spec_from_file_location("notebook_feature_runtime", artifact / "feature_runtime.py")
    runtime = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(runtime)
    # Only locally created/trusted joblib artifacts are supported.
    model = joblib.load(artifact / "model.joblib")
    rows = []
    for checkpoint in probe["checkpoints"]:
        when = runtime.utc(checkpoint["decision_time"])
        history = [e for e in probe["events"] if e["shipment_id"] == checkpoint["shipment_id"]]
        row = runtime.first_features(history, checkpoint["shipment_id"], when)
        row.update(runtime.window_features(history, checkpoint["shipment_id"], when, manifest["lookback_hours"]))
        rows.append(row)
    X = pd.DataFrame(rows,columns=manifest["feature_order"])
    with threadpool_limits(limits=1):
        probabilities = model.predict_proba(X)[:,1]
    if not np.isfinite(probabilities).all() or not ((probabilities >= 0)&(probabilities <= 1)).all():
        raise ValueError("Invalid probabilities")
    digests = [hashlib.sha256(json.dumps(row, sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest() for row in rows]
    return {"model_version":manifest["model_version"],"feature_digests":digests,"probabilities":probabilities.tolist()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact",type=Path,required=True)
    parser.add_argument("--probe",type=Path,required=True)
    args = parser.parse_args()
    result = score(args.artifact.resolve(),json.loads(args.probe.read_text()))
    print(json.dumps(result,sort_keys=True,separators=(",",":"),allow_nan=False))

if __name__ == "__main__":
    main()
