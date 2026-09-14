# Run the shipment risk engine

Use Python 3.11 or newer. Run commands from the repository root. Install dependencies once; subsequent training and scoring are offline.

```bash
python -m pip install -e '.[dev]'
python -m pytest
python -m dispatch_risk train --artifact outputs/final_model
python -m dispatch_risk replay --artifact outputs/final_model --max-shipments 32 --output outputs/replay
```

For this project's existing virtual environment, replace `python` with `.venv/bin/python`. On this macOS workspace, Python 3.14 sometimes skips editable-install `.pth` files because they carry a hidden filesystem flag. The verified local workaround is to prefix commands with `PYTHONPATH=src`, for example:

```bash
PYTHONPATH=src .venv/bin/python -m pytest
PYTHONPATH=src .venv/bin/python -m dispatch_risk train
PYTHONPATH=src .venv/bin/python -m dispatch_risk replay --max-shipments 32
```

`train` writes `model.json` and `evaluation.json`. The CLI prints validation, held-out model/baseline metrics and operational slices. The model family was selected in the validation notebook. This command fits that family without selecting again on test results. `replay` preserves input delivery order, writes one canonical prediction per accepted delivery at that delivery's `received_at`, writes `snapshot.json`, and prints memory counters. Scoring an old received timestamp after eviction may intentionally produce a degraded result.

To reproduce another stream without replacing the original data:

```bash
python tools/generate_dataset.py --seed 1927 --shipments 700 --output /tmp/dispatch-unseen
python -m dispatch_risk replay --data /tmp/dispatch-unseen --artifact outputs/final_model --max-shipments 32 --output /tmp/dispatch-unseen-replay
```

This checks input robustness with the existing model; it is not a new estimate of predictive quality. To compare deterministic replays, run `replay` twice into separate directories and compare `predictions.jsonl` and `snapshot.json` with `cmp`.

Restore and reload example:

```python
from pathlib import Path
from dispatch_risk import RiskEngine

engine = RiskEngine.restore(Path('outputs/final_model'), Path('outputs/replay/snapshot.json'))
print(engine.stats())
assert engine.reload_model(Path('outputs/final_model'))
assert not engine.reload_model(Path('missing-model'))  # Previous model still active.
```

Restore requires the snapshot's model version. Keep the corresponding model directory alongside the snapshot. See `DECISIONS.md` for retention, label-censoring and initial-load failure policies.

## Where to look during the follow-up

- `src/dispatch_risk/features.py`: which readings were available, revision selection, windows, trend.
- `src/dispatch_risk/training.py`: mature labels, time split, fitted preprocessing, portable export.
- `src/dispatch_risk/model.py`: artifact validation and standard-library probability calculation.
- `src/dispatch_risk/engine.py`: lock boundaries, retention, snapshots and reload.
- `tests/test_engine.py` and `tests/test_training.py`: tests to extend when a requirement changes.
- `outputs/final_model/evaluation.json`: actual public implementation results.

A useful debugging sequence is to inspect one failed prediction's reasons and feature digest, reconstruct eligible revisions at its timestamp, check retention counters, then check its model version. Change one rule, add a test for the changed behavior, and rerun the replay comparison. Changes to feature interpretation require a new feature version and retraining.

## Optional interview preparation

The demo, notebooks and speaking walkthrough live in [this folder](README.md). They are not required to run the submission.
