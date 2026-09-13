"""Run with PYTHONPATH=src .venv/bin/python -m demo.server."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from collections import OrderedDict
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock
from urllib.parse import urlsplit

from dispatch_risk import RiskEngine
from dispatch_risk.features import (
    FEATURE_VERSION, canonical, event_from_mapping, extract_features,
    known_revisions, normalize_event, utc,
)

ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path):
    """Read a small JSON Lines file into memory for the local demo.

    Args:
        path: JSONL file path.

    Returns:
        List of decoded JSON objects, skipping blank lines.
    """
    with path.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def lesson():
    """Build the hand-crafted teaching stream used by the UI.

    Returns:
        List of JSON-compatible event dictionaries that demonstrate duplicate
        delivery, late correction, separate shipments, and a device-clock error.
    """
    def reading(eid, sid, device, received, value, revision=1):
        """Create one temperature reading for the teaching stream."""
        return dict(event_id=eid, revision=revision, shipment_id=sid,
                    device_time=f'2026-01-01T{device}:00+00:00',
                    received_at=f'2026-01-01T{received}:00+00:00',
                    kind='temperature_c', value=value, source='teaching-example', payload={})
    original = reading('reading-1', 'shipment-A', '09:00', '09:05', 8)
    return [original, dict(original),
            reading('reading-1', 'shipment-A', '09:00', '12:00', 5, 2),
            reading('reading-2', 'shipment-B', '10:00', '10:05', 6),
            reading('reading-3', 'shipment-C', '10:30', '10:35', 7),
            reading('reading-4', 'shipment-A', '11:00', '12:15', 9),
            reading('clock-error', 'shipment-A', '15:00', '12:20', 20)]


class Demo:
    """A single local walkthrough, protected from overlapping browser requests."""
    def __init__(self, artifact=ROOT/'outputs/final_model', data=ROOT/'data'):
        """Create a demo session and load the first teaching event.

        Args:
            artifact: Model artifact directory used by ``RiskEngine``.
            data: Data directory used by the sample-dataset scenario.
        """
        self.artifact = Path(artifact)
        self.data = Path(data)
        self.temporary = TemporaryDirectory(prefix='dispatch-demo-')
        self.work = Path(self.temporary.name)
        self.lock = RLock()
        self.saved = None
        self.scenario = 'lesson'
        self.capacity = 2
        self.reset('lesson', 2)

    def reset(self, scenario, capacity):
        """Reset the walkthrough to a scenario and shipment capacity.

        Args:
            scenario: ``lesson`` for the hand-crafted stream or ``sample`` for
                the supplied dataset.
            capacity: Maximum number of shipments retained by the engine.

        Raises:
            ValueError: If the scenario, capacity, or source data is invalid.
        """
        if scenario not in ('lesson', 'sample'):
            raise ValueError('Choose the lesson or the supplied dataset.')
        if type(capacity) is not int or not 1 <= capacity <= 10000:
            raise ValueError('Shipment capacity must be between 1 and 10,000.')
        raw = lesson() if scenario == 'lesson' else read_jsonl(self.data/'events.jsonl')
        if not raw:
            raise ValueError('The dataset contains no deliveries.')
        events = [normalize_event(event_from_mapping(r)) for r in raw]
        engine = RiskEngine(self.artifact, capacity)
        self.events, self.engine = events, engine
        self.scenario, self.capacity = scenario, capacity
        self.position = 0
        self.accepted = []
        self.saved = None
        self.shipment = events[0]['shipment_id']
        self.as_of = utc('2026-01-01T11:00:00Z') if scenario == 'lesson' else utc(events[0]['received_at'])
        self.message = 'First delivery loaded. Step forward to see what changes.'
        self.advance(1)

    def advance(self, count):
        """Ingest the next deliveries in file order.

        Args:
            count: Number of deliveries to process, capped by remaining events.

        Raises:
            ValueError: If the requested step size is outside the demo limit.
        """
        if type(count) is not int or not 1 <= count <= 1000:
            raise ValueError('Advance between 1 and 1,000 deliveries at a time.')
        for _ in range(min(count, len(self.events)-self.position)):
            self.accepted.append(self.engine.ingest(event_from_mapping(self.events[self.position])))
            self.position += 1

    def act(self, request):
        """Apply one browser action and return the updated view model.

        Args:
            request: Action object from ``/api/action``. Supported actions are
                ``view``, ``step``, ``save``, ``restore``, ``reload_valid``,
                ``reload_invalid``, and ``reset``.

        Returns:
            Dictionary returned by ``view``.

        Raises:
            ValueError: If the action or selected shipment/time is invalid.
            RuntimeError: If a restore or reload invariant fails.
        """
        with self.lock:
            action = request.get('action', 'view')
            if action == 'reset':
                self.reset(request.get('scenario', self.scenario), request.get('capacity', self.capacity))
            else:
                sid = request.get('shipment', self.shipment)
                if sid not in {e['shipment_id'] for e in self.events}:
                    raise ValueError('Choose a shipment from this stream.')
                checkpoint = utc(request.get('as_of', self.as_of.isoformat()))
                self.shipment, self.as_of = sid, checkpoint
                if action == 'step':
                    self.advance(request.get('count', 1))
                    if request.get('follow_time') and self.position:
                        self.as_of = utc(self.events[self.position-1]['received_at'])
                        self.shipment = self.events[self.position-1]['shipment_id']
                    self.message = f'Processed {self.position:,} of {len(self.events):,} deliveries in file order.'
                elif action == 'save':
                    self.engine.snapshot(self.work/'saved.json')
                    self.saved = dict(position=self.position, accepted=self.accepted[:], shipment=self.shipment,
                                      as_of=self.as_of, wire=self.engine.score(self.shipment, self.as_of).to_wire())
                    self.message = 'Snapshot saved. Advance the stream, then restore to return to this point.'
                elif action == 'restore':
                    if self.saved is None:
                        raise ValueError('Save a snapshot before restoring.')
                    self.engine = RiskEngine.restore(self.artifact, self.work/'saved.json')
                    self.position = self.saved['position']
                    self.accepted = self.saved['accepted'][:]
                    self.shipment, self.as_of = self.saved['shipment'], self.saved['as_of']
                    same = self.engine.score(self.shipment, self.as_of).to_wire() == self.saved['wire']
                    if not same:
                        raise RuntimeError('Restored prediction differs from the saved prediction.')
                    self.message = 'Restored. The serialized prediction matches the saved prediction byte for byte.'
                elif action in ('reload_valid', 'reload_invalid'):
                    before = self.engine.score(self.shipment, self.as_of).to_wire()
                    target = self.artifact if action == 'reload_valid' else self.work/'missing-model'
                    success = self.engine.reload_model(target)
                    unchanged = before == self.engine.score(self.shipment, self.as_of).to_wire()
                    if success != (action == 'reload_valid') or not unchanged:
                        raise RuntimeError('Reload check failed.')
                    self.message = ('Same valid artifact reloaded. Prediction and telemetry are unchanged.' if success else
                                    'Invalid reload rejected. The previous model still serves the identical prediction.')
                elif action == 'view':
                    self.message = 'Prediction updated for the selected shipment and UTC time.'
                else:
                    raise ValueError('Unknown action.')
            return self.view()

    def view(self):
        """Build the JSON state shown by the browser UI.

        Returns:
            Dictionary containing the selected shipment, decision time,
            prediction, feature values, retained deliveries, engine stats, and
            explanatory status text.

        Raises:
            RuntimeError: If displayed features do not match the prediction
                digest produced by the engine.
        """
        # Inspect a public snapshot rather than reaching into private engine fields.
        self.engine.snapshot(self.work/'inspect.json')
        state = json.loads((self.work/'inspect.json').read_text())['state']
        retained = next((s['records'] for s in state['shipments'] if s['shipment_id']==self.shipment), [])
        features = extract_features(retained, self.shipment, self.as_of)
        prediction = json.loads(self.engine.score(self.shipment, self.as_of).to_wire())
        digest = hashlib.sha256(canonical({'feature_version':FEATURE_VERSION, 'features':features})).hexdigest()
        if digest != prediction['feature_digest']:
            raise RuntimeError('Displayed features do not match the engine prediction.')
        latest = {r['event_id']:r['revision'] for r in known_revisions(retained, self.as_of)}
        kept = {(r['event_id'], r['revision']) for r in retained}
        deliveries, seen = [], set()
        for i, e in enumerate(self.events[:self.position]):
            if e['shipment_id'] != self.shipment:
                continue
            key = (e['event_id'], e['revision'])
            if key in seen:
                status = 'Duplicate delivery'
            elif key not in kept:
                status = 'Not retained'
            elif utc(e['received_at']) > self.as_of:
                status = 'Not yet available'
            elif latest.get(e['event_id']) != e['revision']:
                status = 'Superseded revision'
            elif utc(e['device_time']) > utc(e['received_at']):
                status = 'Device clock excluded'
            elif e['kind'] != 'temperature_c' or not isinstance(e['value'], (float,int)):
                status = 'Not a numeric temperature'
            elif utc(e['device_time']) <= self.as_of-timedelta(hours=3):
                status = 'Outside lookback; may supply latest'
            else:
                status = 'In temperature window'
            seen.add(key)
            deliveries.append(dict(e, status=status, file_row=i+1, accepted=self.accepted[i]))
        return dict(scenario=self.scenario, capacity=self.capacity, position=self.position,
                    total=len(self.events), shipments=list(dict.fromkeys(e['shipment_id'] for e in self.events)),
                    shipment=self.shipment, as_of=self.as_of.isoformat(),
                    horizon_end=(self.as_of+timedelta(hours=6)).isoformat(),
                    lookback_start=(self.as_of-timedelta(hours=3)).isoformat(),
                    next_event=self.events[self.position] if self.position<len(self.events) else None,
                    last_event=self.events[self.position-1] if self.position else None,
                    deliveries=deliveries[-200:], displayed_deliveries=min(len(deliveries),200),
                    shipment_deliveries=len(deliveries), prediction=prediction, features=features,
                    stats=self.engine.stats(), retained_shipments=[s['shipment_id'] for s in state['shipments']],
                    has_snapshot=self.saved is not None, message=self.message)

    def outcomes(self):
        """Return retrospective reports for the currently selected shipment.

        Returns:
            Dictionary with explanatory note text and the available incident
            reports. These reports are shown for teaching only and are not used
            to score the current prediction.
        """
        with self.lock:
            if self.scenario == 'lesson':
                return dict(note='Invented incident for the teaching example; not used by the model.', reports=[
                    dict(shipment_id='shipment-A', incident_at='2026-01-01T13:00:00+00:00',
                         label_available_at='2026-01-02T09:00:00+00:00')
                ] if self.shipment=='shipment-A' else [])
            return dict(note='Retrospective audit reports from the supplied dataset. No report does not establish a negative.',
                        reports=[r for r in read_jsonl(self.data/'labels.jsonl') if r['shipment_id']==self.shipment])


class Sessions:
    """Keep tab playbacks separate and bound the number of local demo sessions."""
    def __init__(self, default):
        """Create a manager around the default demo session.

        Args:
            default: Shared session used when the browser sends no session ID.
        """
        self.default = default
        self.sessions = OrderedDict()
        self.lock = RLock()

    def get(self, token):
        """Return the demo session associated with a browser token.

        Args:
            token: Optional UUID-like browser session token.

        Returns:
            Existing or newly created ``Demo`` instance. At most eight custom
            sessions are retained.

        Raises:
            ValueError: If the token format is invalid.
        """
        if not token:
            return self.default
        if not re.fullmatch(r'[a-f0-9-]{36}', token):
            raise ValueError('Invalid demo session.')
        with self.lock:
            if token not in self.sessions:
                if len(self.sessions) >= 8:
                    _, old = self.sessions.popitem(last=False)
                    with old.lock:
                        old.temporary.cleanup()
                self.sessions[token] = Demo(self.default.artifact, self.default.data)
            self.sessions.move_to_end(token)
            return self.sessions[token]


def make_handler(demo):
    """Create the HTTP request handler bound to a demo manager.

    Args:
        demo: Default ``Demo`` instance.

    Returns:
        ``BaseHTTPRequestHandler`` subclass serving static files and JSON API
        routes for the local walkthrough.
    """
    sessions = Sessions(demo)
    class Handler(BaseHTTPRequestHandler):
        """HTTP adapter for the browser-based shipment-risk walkthrough."""

        def send(self, code, body, content_type='application/json'):
            """Send a JSON or static-file response with defensive headers."""
            data = canonical(body) if content_type == 'application/json' else body
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            """Serve static assets and read-only demo API routes."""
            route = urlsplit(self.path).path
            try:
                if route == '/api/state':
                    current=sessions.get(self.headers.get('X-Demo-Session'))
                    with current.lock: self.send(200, current.view())
                elif route == '/api/evaluation':
                    self.send(200, json.loads((demo.artifact/'evaluation.json').read_text()))
                elif route == '/api/outcomes':
                    self.send(200, sessions.get(self.headers.get('X-Demo-Session')).outcomes())
                elif route in ('/', '/app.js', '/style.css'):
                    name = 'index.html' if route=='/' else route[1:]
                    kind = {'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8'}[name]
                    self.send(200, (Path(__file__).parent/name).read_bytes(), kind)
                else: self.send(404, {'error':'Not found.'})
            except (ValueError, OSError, KeyError, RuntimeError) as exc:
                self.send(400, {'error':str(exc)})

        def do_POST(self):
            """Apply one local demo action after basic origin and size checks."""
            # The demo controls a local process; reject cross-origin browser writes.
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                self.send(403, {'error':'Use the demo from its own local page.'});return
            if urlsplit(self.path).path != '/api/action':
                self.send(404, {'error':'Not found.'});return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=8192:raise ValueError('Invalid request size.')
                request=json.loads(self.rfile.read(length))
                if not isinstance(request,dict):raise ValueError('Expected an action object.')
                self.send(200,sessions.get(self.headers.get('X-Demo-Session')).act(request))
            except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
                self.send(400,{'error':str(exc)})

        def log_message(self, *_):
            """Silence default HTTP request logging for a cleaner demo terminal."""
            pass
    return Handler


def main():
    """Start the local threaded HTTP server for the walkthrough UI."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--artifact', type=Path, default=ROOT/'outputs/final_model')
    parser.add_argument('--data', type=Path, default=ROOT/'data')
    args=parser.parse_args()
    try:
        demo=Demo(args.artifact,args.data)
        server=ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(demo))
    except (OSError,ValueError,KeyError) as exc:
        parser.exit(1,f'Could not start the demo: {exc}\nTrain an artifact with python -m dispatch_risk train if needed.\n')
    print(f'Local shipment demo: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();demo.temporary.cleanup()


if __name__=='__main__':main()
