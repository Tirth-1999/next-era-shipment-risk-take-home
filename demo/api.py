"""Optional interview API. Run: python -m uvicorn demo.api:app --port 8765."""
from pathlib import Path
from threading import Lock
from uuid import uuid4
import hashlib
import json
import subprocess
import sys

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from demo.server import Demo, Sessions, ROOT
from dispatch_risk import RiskEngine
from dispatch_risk.features import event_from_mapping
from tools.generate_dataset import generate, emit

app = FastAPI(title="Shipment Risk Interview", description="Generate a stream, verify replay, and inspect the live demo.")
sessions = Sessions(Demo())
run_lock = Lock()


class StreamRequest(BaseModel):
    """Reproducible stream seed, size, and engine shipment capacity."""
    seed: int = Field(default=1927, ge=0, le=2147483647)
    shipments: int = Field(default=80, ge=3, le=700)
    max_shipments: int = Field(default=32, ge=1, le=128)


@app.middleware("http")
async def local_requests(request: Request, call_next):
    """Reject cross-origin writes and prevent caching of local results."""
    if request.method == "POST":
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Use the local page or API docs."}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get('/api/state')
def state(x_demo_session: str | None = Header(default=None)):
    """Read the current tab's demonstration state."""
    current = sessions.get(x_demo_session)
    with current.lock:
        return current.view()


@app.post('/api/action')
def action(body: dict, x_demo_session: str | None = Header(default=None)):
    """Apply a small demo action through the existing engine adapter."""
    try:
        return sessions.get(x_demo_session).act(body)
    except (ValueError, RuntimeError, KeyError) as error:
        raise HTTPException(400, str(error)) from error


@app.get('/api/evaluation')
def evaluation():
    """Return the saved held-out evaluation; do not retrain on new streams."""
    return json.loads((ROOT / 'outputs/final_model/evaluation.json').read_text())


def replay(events, directory, capacity):
    """Replay delivery order, writing predictions and snapshot with invariant evidence.

    Args:
        events: Generated telemetry mappings in delivery order.
        directory: Unique output folder for this replay.
        capacity: Maximum retained shipments.

    Returns:
        Prediction digest, snapshot digest, counters, and first capacity failure.
    """
    directory.mkdir(parents=True)
    engine = RiskEngine(ROOT / 'outputs/final_model', capacity)
    digest = hashlib.sha256()
    failure = None
    peak = 0
    with (directory / 'predictions.jsonl').open('wb') as output:
        for number, raw in enumerate(events, 1):
            event = event_from_mapping(raw)
            if engine.ingest(event):
                wire = engine.score(event.shipment_id, event.received_at).to_wire() + b'\n'
                digest.update(wire)
                output.write(wire)
            stats = engine.stats()
            peak = max(peak, stats['shipments'])
            if stats['shipments'] > capacity and failure is None:
                failure = {'row': number, 'event': raw, 'stats': stats}
    snapshot = directory / 'snapshot.json'
    engine.snapshot(snapshot)
    return {'predictions_sha256': digest.hexdigest(), 'snapshot_sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest(), 'peak_shipments': peak, 'stats': engine.stats(), 'first_failure': failure}


@app.post('/api/interview/stream')
def new_stream(body: StreamRequest):
    """Generate new data and compare two independent replays of the fixed model.

    Saved outputs include seed, source code digests, raw records, predictions,
    snapshots and checks. This is software verification, not fresh model evaluation.
    """
    if not run_lock.acquire(blocking=False):
        raise HTTPException(409, 'Another verification is running.')
    try:
        folder = ROOT / 'outputs/interview' / uuid4().hex
        folder.mkdir(parents=True)
        events, labels, decisions = generate(body.seed, body.shipments)
        for name, rows in [('events', events), ('labels', labels), ('decision_times', decisions)]:
            emit(folder / f'{name}.jsonl', rows)
        first = replay(events, folder / 'replay-a', body.max_shipments)
        second = replay(events, folder / 'replay-b', body.max_shipments)
        checks = {
            'identical_predictions': first['predictions_sha256'] == second['predictions_sha256'],
            'identical_snapshots': first['snapshot_sha256'] == second['snapshot_sha256'],
            'shipment_limit': first['first_failure'] is None and second['first_failure'] is None,
        }
        report = {'request': body.model_dump(), 'events': len(events), 'checks': checks,
                  'first_replay': first, 'second_replay': second,
                  'output_directory': str(folder.relative_to(ROOT)),
                  'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / 'src/dispatch_risk').glob('*.py')},
                  'meaning': 'Fixed-model replay checks. These are not new accuracy results.'}
        (folder / 'report.json').write_text(json.dumps(report, indent=2))
        return report
    finally:
        run_lock.release()


@app.post('/api/interview/tests')
def run_tests():
    """Run the fixed repository test suite in a fresh process after a code edit.

    No caller-supplied command is executed. Return actual exit code and test output.
    """
    if not run_lock.acquire(blocking=False):
        raise HTTPException(409, 'Another verification is running.')
    try:
        import os
        environment = {**os.environ, 'PYTHONPATH': str(ROOT / 'src') + os.pathsep + str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'}
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q'], cwd=ROOT, env=environment, capture_output=True, text=True, timeout=90)
        return {'passed': result.returncode == 0, 'exit_code': result.returncode, 'output': (result.stdout + result.stderr)[-20000:]}
    except subprocess.TimeoutExpired as error:
        raise HTTPException(408, 'Tests exceeded 90 seconds.') from error
    finally:
        run_lock.release()


@app.get('/{path:path}', include_in_schema=False)
def page(path: str):
    """Serve only the explicitly allowed demo assets."""
    name = {'': 'index.html', 'presentation': 'presentation.html', 'presentation/': 'presentation.html'}.get(path, path)
    allowed = {'index.html', 'app.js', 'style.css', 'presentation.html', 'presentation.js', 'presentation.css', 'presentation-slides.css'}
    if name not in allowed:
        raise HTTPException(404)
    return FileResponse(Path(__file__).parent / name)
