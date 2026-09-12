# Local shipment walkthrough

Run from the repository root after installing the project and generating the model:

```bash
PYTHONPATH=src .venv/bin/python -m demo.server
```

Open http://127.0.0.1:8765. Use `--port`, `--artifact` or `--data` to choose another local port, model directory or dataset. The default model is `outputs/final_model`; create it with `python -m dispatch_risk train` if missing.

The page has three views:

- **Replay a shipment:** step through the small correction example or the supplied event stream, choose a UTC prediction time, inspect features and delivery eligibility, and test snapshot/restore and reload.
- **Review the model:** read the saved evaluation report, baseline and operational slices. No fitting or model selection happens in the browser.
- **Walkthrough notes:** follow the example in order, with prompts for explaining each decision.

The small example is invented teaching data. It uses the saved model to show engine behavior; its individual probabilities are not an evaluation. The supplied-data mode preserves file delivery order. Turn on “Follow each delivery’s shipment and receipt time” when moving through large batches. Shipment capacity takes effect on reset.

Each tab gets its own playback session. Refreshing keeps that tab’s session; resetting clears its saved snapshot. The server keeps at most eight tab sessions; opening more can discard the oldest session. Restarting the server clears them all. Snapshots live in temporary local directories. This demo loads the finite source dataset for inspection; its process-memory usage is separate from the engine’s retention counters.

Predictions come directly from `RiskEngine`. The feature panel reads retained events through a public snapshot, calls the shared feature functions, and verifies that its digest matches the prediction. The table marks raw duplicate deliveries, unavailable revisions, discarded history and excluded device clocks. Only the most recent 200 deliveries for the selected shipment are displayed; the table reports its displayed/total count.

“Reload same valid model” reloads the existing artifact. “Try invalid reload” passes a missing artifact and verifies that the original prediction remains unchanged. These controls demonstrate the reload contract without claiming to compare two trained models. Restore rewinds both the engine and the demo’s playback position and compares the saved prediction bytes.

The server binds to loopback and uses only Python’s standard library plus the installed engine. There are no external scripts, fonts, hosted services or new dependencies. This is a local demonstration, not a multi-user service.

The assignment explicitly says not to spend time on UI. This optional folder was added for interview practice after the engine was completed and can be omitted from the submission. The engine and its package installation do not import the demo. If omitting it, omit `tests/test_demo.py` as well; the remaining tests cover the assessed implementation.
