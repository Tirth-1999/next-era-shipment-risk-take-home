# Local shipment walkthrough

## Browser presentation

The same server serves the nine-slide interview deck at `http://127.0.0.1:8765/presentation` (a trailing slash also works). Use the sidebar's **Presentation** link or enter the URL in Chrome. No additional server or dependency is required.

Use arrow keys or Previous/Next to navigate, the slide picker to jump, **F** for fullscreen, and **N** for speaker notes. Notes appear below the slide on the same page; hide them before sharing the screen. A slide URL such as `/presentation#slide-6` can be bookmarked. **Live demo** returns to `/`.

Text, tables, colors and speaker notes are exported from `personal/outputs/presentation/Shipment_Risk_Interview.pptx`. After updating that deck, run `python personal/tools/export_presentation.py` to regenerate `personal/demo/presentation.html` and `personal/demo/presentation-slides.css`. The exporter supports the text boxes and tables in this deck and rejects unsupported shapes; it is not a general PowerPoint converter. Fonts are supplied by the browser, so line wrapping can differ slightly from PowerPoint.

## Start the server

Run from the repository root after installing the project and generating the model:

```bash
PYTHONPATH=src .venv/bin/python -m personal.demo.server
```

Open http://127.0.0.1:8765. Use `--port`, `--artifact` or `--data` to choose another local port, model directory or dataset. The default model is `outputs/final_model`; create it with `python -m dispatch_risk train` if missing.

The page has three demo tabs and a presentation link:

- **Start here:** four steps showing a reading, a duplicate, a late correction, and a noon prediction.
- **System checks:** one button at a time checks shipment capacity, snapshot restore, and failed reload. Each check starts from a known small example and uses the real engine. These are demonstrations, not load tests.
- **Model results:** caught, missed, and false-alarm counts; the full report is expandable.
- **Presentation:** the nine-slide deck in the browser.

The right sidebar can be collapsed. The previous dataset selector and manual playback dashboard were removed because they obscured the purpose of the demo. Use RUNBOOK.md for full-stream replay and stress-test commands. Guided prediction and system checks use separate sessions. Restarting the server clears in-memory sessions.

This is optional interview practice. The assessed engine works without the UI.

## FastAPI interview workbench

Install the optional API dependencies and start from the repository root:

```bash
python -m pip install -e '.[dev,demo]'
PYTHONPATH=src .venv/bin/python -m uvicorn personal.demo.api:app --host 127.0.0.1 --port 8765
```

For a uv-managed environment: `uv sync --extra dev --extra notebook --extra demo`.
Stop the old `demo.server` process first if it occupies port 8765. The original standard-library server supports the teaching views; the **New stream** actions require FastAPI.

Open `/` for the demo, `/docs` for interactive API requests, `/openapi.json` for the schema, and `/presentation` for slides. Swagger's default docs load assets from a CDN and require internet; the demo and API execution run locally after installation.

**New stream** calls `POST /api/interview/stream` with seed, shipment count and capacity. The backend calls the supplied deterministic generator, then replays delivery order twice through the saved model. It writes raw data, both prediction streams, snapshots and `report.json` under a unique `personal/outputs/interview/` folder. Files are retained for inspection; remove unwanted run folders manually. It compares prediction and snapshot hashes and checks shipment capacity after every delivery. It reports the first capacity violation if one occurs. A replay mismatch requires comparing the two saved files; no failure is fabricated.

Use the same seed with a different memory limit to demonstrate a requirement change. For a code change, edit the implementation and its test locally; **Run repository tests** starts pytest in a fresh process. Restart the API before replaying changed engine code. The UI does not edit source automatically. Repeated generation tests robustness, not accuracy on independent real data. The original held-out report remains separate.
