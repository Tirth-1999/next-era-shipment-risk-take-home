"""Retain bounded shipment history and score it safely across threads."""
from __future__ import annotations
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from threading import RLock
import hashlib
import json
from .contracts import Prediction, TelemetryEvent
from .features import (FEATURE_VERSION, MAX_EVENT_BYTES, aware, canonical,
                       event_from_mapping, extract_features, identifier,
                       known_revisions, normalize_event, utc)
from .model import atomic_write, load_model

MAX_RECORDS_PER_SHIPMENT = 128


class RiskEngine:
    def __init__(self, artifact_dir: Path, max_shipments: int = 10_000):
        if type(max_shipments) is not int or max_shipments <= 0:
            raise ValueError("max_shipments must be a positive integer")
        self._model = load_model(artifact_dir)
        self._max_shipments = max_shipments
        self._ships = OrderedDict()
        self._owners = {}
        self._lock = RLock()
        self._accepted = self._evictions = self._trimmed = 0

    def ingest(self, event: TelemetryEvent) -> bool:
        record = normalize_event(event)
        sid, eid = record['shipment_id'], record['event_id']
        key = (eid, record['revision'])
        with self._lock:
            if eid in self._owners and self._owners[eid] != sid:
                raise ValueError('Event ID cannot change shipment')
            state = self._ships.get(sid)
            if state is not None:
                previous = state['records'].get(key)
                if previous is not None:
                    if previous != record:
                        raise ValueError('Conflicting duplicate delivery')
                    return False
                if state['discarded_through'] is not None and utc(record['received_at']) <= utc(state['discarded_through']):
                    return False
            else:
                if len(self._ships) == self._max_shipments:
                    _, evicted = self._ships.popitem(last=False)
                    for old in evicted['records'].values():
                        self._owners.pop(old['event_id'], None)
                    self._evictions += 1
                # Without unbounded tombstones a returning shipment cannot be identified.
                state = {'records': {}, 'discarded_through': None,
                         'coverage_unverified': self._evictions > 0}
                self._ships[sid] = state
            state['records'][key] = record
            self._owners[eid] = sid
            self._ships.move_to_end(sid)
            self._accepted += 1
            if len(state['records']) > MAX_RECORDS_PER_SHIPMENT:
                # Remove all revisions of the oldest event together; never resurrect
                # a lower revision simply by removing its correcting revision.
                latest_arrival = {}
                for r in state['records'].values():
                    latest_arrival[r['event_id']] = max(latest_arrival.get(r['event_id'], utc(r['received_at'])), utc(r['received_at']))
                oldest = min(latest_arrival, key=lambda e: (latest_arrival[e], e))
                removed = [k for k in state['records'] if k[0] == oldest]
                for k in removed:
                    del state['records'][k]
                self._owners.pop(oldest, None)
                boundary = latest_arrival[oldest]
                if state['discarded_through'] is not None:
                    boundary = max(boundary, utc(state['discarded_through']))
                state['discarded_through'] = boundary.isoformat()
                self._trimmed += len(removed)
            return True

    def score(self, shipment_id: str, as_of: datetime) -> Prediction:
        sid = identifier(shipment_id, 'shipment_id')
        checkpoint = aware(as_of)
        with self._lock:
            state = self._ships.get(sid)
            records = list(state['records'].values()) if state else []
            features = extract_features(records, sid, checkpoint)
            reasons = []
            if state is None:
                reasons.append('shipment_not_retained')
            elif state['coverage_unverified']:
                reasons.append('retention_coverage_unverified')
            if state and state['discarded_through'] is not None:
                reasons.append('history_truncated')
            if features['temperature_missing']:
                reasons.append('no_usable_temperature')
            elif features['measurement_age_minutes'] > 180:
                reasons.append('stale_temperature')
            selected = known_revisions(records, checkpoint)
            if any(utc(r['device_time']) > utc(r['received_at']) for r in selected):
                reasons.append('future_device_clock_excluded')
            digest = hashlib.sha256(canonical({'feature_version': FEATURE_VERSION, 'features': features})).hexdigest()
            probability = self._model.prior if state is None else self._model.predict(features)
            return Prediction(sid, checkpoint, probability, self._model.version,
                              digest, bool(reasons), tuple(sorted(reasons)))

    def snapshot(self, destination: Path) -> None:
        with self._lock:
            body = {'schema_version': 1, 'feature_version': FEATURE_VERSION,
                    'model_version': self._model.version,
                    'max_shipments': self._max_shipments,
                    'record_cap': MAX_RECORDS_PER_SHIPMENT,
                    'accepted': self._accepted, 'evictions': self._evictions,
                    'trimmed': self._trimmed,
                    'shipments': [{'shipment_id': sid,
                                   'discarded_through': st['discarded_through'],
                                   'coverage_unverified': st['coverage_unverified'],
                                   'records': [st['records'][k] for k in sorted(st['records'])]}
                                  for sid, st in self._ships.items()]}
            # Hold the lock until the full snapshot has been encoded.
            encoded = canonical(body)
            wrapper = canonical({'sha256': hashlib.sha256(encoded).hexdigest(), 'state': body})
        atomic_write(destination, wrapper)

    @classmethod
    def restore(cls, artifact_dir: Path, snapshot: Path) -> 'RiskEngine':
        wrapper = json.loads(Path(snapshot).read_bytes())
        body = wrapper['state']
        if hashlib.sha256(canonical(body)).hexdigest() != wrapper['sha256']:
            raise ValueError('Snapshot checksum mismatch')
        if body['schema_version'] != 1 or body['feature_version'] != FEATURE_VERSION or body['record_cap'] != MAX_RECORDS_PER_SHIPMENT:
            raise ValueError('Incompatible snapshot schema')
        result = cls(artifact_dir, body['max_shipments'])
        if result._model.version != body['model_version']:
            raise ValueError('Restore requires the snapshot model version')
        if len(body['shipments']) > result._max_shipments:
            raise ValueError('Snapshot exceeds shipment cap')
        for field in ('accepted', 'evictions', 'trimmed'):
            if type(body[field]) is not int or body[field] < 0:
                raise ValueError('Invalid snapshot counter')
            setattr(result, '_' + field, body[field])
        for item in body['shipments']:
            sid = identifier(item['shipment_id'], 'shipment_id')
            if sid in result._ships or len(item['records']) > MAX_RECORDS_PER_SHIPMENT:
                raise ValueError('Invalid snapshot shipment or history cap')
            boundary = item['discarded_through']
            if boundary is not None:
                boundary = utc(boundary).isoformat()
            if type(item['coverage_unverified']) is not bool:
                raise ValueError('Invalid snapshot coverage flag')
            records = {}
            for raw in item['records']:
                record = normalize_event(event_from_mapping(raw))
                eid = record['event_id']; key = (eid, record['revision'])
                if record['shipment_id'] != sid or key in records or result._owners.get(eid, sid) != sid:
                    raise ValueError('Invalid snapshot identity')
                records[key] = record
                result._owners[eid] = sid
            result._ships[sid] = {'records': records, 'discarded_through': boundary,
                                  'coverage_unverified': item['coverage_unverified']}
        return result

    def reload_model(self, artifact_dir: Path) -> bool:
        try:
            candidate = load_model(artifact_dir)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
            return False
        with self._lock:
            self._model = candidate
        return True

    def stats(self):
        with self._lock:
            records = sum(len(s['records']) for s in self._ships.values())
            return {'shipments': len(self._ships), 'max_shipments': self._max_shipments,
                    'retained_records': records, 'event_id_index': len(self._owners),
                    'max_records_per_shipment': MAX_RECORDS_PER_SHIPMENT,
                    'max_event_bytes': MAX_EVENT_BYTES,
                    'accepted': self._accepted, 'evictions': self._evictions,
                    'trimmed': self._trimmed, 'model_version': self._model.version}
