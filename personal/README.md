# Tirth's interview preparation

For interview practice, use [WALKTHROUGH.md](WALKTHROUGH.md). Commands are collected below. The plan and learning journal are development history; you do not need to read them before each presentation.

| Folder or file | Use |
| --- | --- |
| `notebooks/` | Learning checkpoints 1–14; open in order |
| `MY_LEARNINGS.md` | What each checkpoint taught us |
| `plan.md` | Development plan and history |
| `demo/` | Optional browser demo and FastAPI interview tools |
| `tests/` | Optional demo/API tests |
| `data/tables/` | Tables exported during exploration |
| `outputs/` | Notebook results, experimental model, presentation and local run evidence |
| `tools/` | Presentation exporter and notebook-artifact verifier |

Run commands from the **repository root**, not this folder:

```bash
python -m pip install -e '.[dev,demo,notebook]'
PYTHONPATH=src .venv/bin/python -m uvicorn personal.demo.api:app --host 127.0.0.1 --port 8765
```

For uv: `uv sync --extra dev --extra demo --extra notebook`.

- Demo: http://127.0.0.1:8765/
- API requests: http://127.0.0.1:8765/docs
- Presentation: http://127.0.0.1:8765/presentation

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests personal/tests
python personal/tools/export_presentation.py
```

The default `pytest` command runs only the submission tests. Optional materials remain in GitHub but are grouped here; this is organization, not privacy protection. Omit this whole folder from a reviewer-only copy if desired. The original assignment text remains in the root README. The first Git commit already contained the completed implementation, so Git cannot reconstruct the untouched starter repository; separation follows the assignment requirements and development record.

## Demo behavior

Restart the API after code changes; restarting clears in-memory sessions. API docs at `/docs` load Swagger assets from a CDN.

**New stream** calls `POST /api/interview/stream` with seed, shipment count and capacity. The backend calls the supplied deterministic generator, then replays delivery order twice through the saved model. It writes raw data, both prediction streams, snapshots and `report.json` under a unique `personal/outputs/interview/` folder. Files are retained for inspection; remove unwanted run folders manually. It compares prediction and snapshot hashes and checks shipment capacity after every delivery. It reports the first capacity violation if one occurs. A replay mismatch requires comparing the two saved files; no failure is fabricated.

Use the same seed with a different memory limit to demonstrate a requirement change. For a code change, edit the implementation and its test locally; **Run repository tests** starts pytest in a fresh process. Restart the API before replaying changed engine code. The UI does not edit source automatically. Repeated generation tests robustness, not accuracy on independent real data. The original held-out report remains separate.

## Page purposes

- **Start here:** demonstrate a duplicate and a late correction.
- **System checks:** exercise memory capacity, recovery and rejected model reload.
- **Model results:** compare incident detection and probability quality against the baseline.
- **New stream:** generate inputs and check deterministic replay.

## CLI replay and recovery

See the [submission README](../README.md#run-the-submission) for core setup, training and tests. Run commands below from the repository root. With the existing virtual environment, use `PYTHONPATH=src .venv/bin/python` in place of `python`.

`train` writes `model.json` and `evaluation.json`. The CLI prints validation, held-out model/baseline metrics and operational slices. The model family was selected in the validation notebook. This command fits that family without selecting again on test results. `replay` preserves input delivery order, writes one canonical prediction per accepted delivery at that delivery's `received_at`, writes `snapshot.json`, and prints memory counters. Scoring an old received timestamp after eviction may intentionally produce a degraded result.

To reproduce another stream without replacing the original data:

```bash
python tools/generate_dataset.py --seed 1927 --shipments 700 --output /tmp/dispatch-unseen
python -m dispatch_risk replay --data /tmp/dispatch-unseen --artifact outputs/final_model --max-shipments 32 --output /tmp/dispatch-unseen-replay
```

This checks input robustness with the existing model; it is not a new estimate of predictive quality. To compare deterministic replays, run `replay` twice into separate directories and compare `predictions.jsonl` and `snapshot.json` with `cmp`.

First create the replay snapshot:

```bash
python -m dispatch_risk replay --artifact outputs/final_model --max-shipments 32 --output outputs/replay
```

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

## Browser presentation

The same server serves the nine-slide interview deck at `http://127.0.0.1:8765/presentation` (a trailing slash also works). Use the sidebar's **Presentation** link or enter the URL in Chrome. No additional server or dependency is required.

Use arrow keys or Previous/Next to navigate, the slide picker to jump, **F** for fullscreen, and **N** for speaker notes. Notes appear below the slide on the same page; hide them before sharing the screen. A slide URL such as `/presentation#slide-6` can be bookmarked. **Live demo** returns to `/`.

Text, tables, colors and speaker notes are exported from `personal/outputs/presentation/Shipment_Risk_Interview.pptx`. After updating that deck, run `python personal/tools/export_presentation.py` to regenerate `personal/demo/presentation.html` and `personal/demo/presentation-slides.css`. The exporter supports the text boxes and tables in this deck and rejects unsupported shapes; it is not a general PowerPoint converter. Fonts are supplied by the browser, so line wrapping can differ slightly from PowerPoint.

## Run the notebooks

Install the notebook dependencies with `uv sync --extra dev --extra notebook --extra demo`. Open notebooks under `personal/notebooks/` in numerical order. In your editor's kernel picker, choose the Python interpreter at this repository's `.venv/bin/python`; the displayed kernel label alone does not confirm the interpreter. Check `import sys; print(sys.executable)` in a cell if unsure.

For an external Jupyter installation, register the project interpreter once:

```bash
.venv/bin/python -m ipykernel install --user --name dispatch-risk --display-name "Shipment risk (.venv)"
```

Then select **Shipment risk (.venv)**. Repeat registration if the repository or environment moves. Notebooks locate the repository from the current folder's ancestors. Raw inputs remain in `data/`; tables and learning artifacts go under `personal/`. Later notebooks explicitly import `src/` and the moved support folder.

To check every notebook with this environment in a temporary copy:

```bash
.venv/bin/python personal/tools/check_notebooks.py
```

The checker runs all 14 notebooks in order with fresh kernels and stops on the first error. It leaves the saved notebooks, tables and model artifacts unchanged. Allow roughly a minute locally; runtime depends on the machine.
