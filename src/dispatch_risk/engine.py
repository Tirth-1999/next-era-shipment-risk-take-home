"""Keep shipment history within limits and protect it when calls overlap."""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from threading import RLock
import hashlib
import json

from .contracts import Prediction, TelemetryEvent
from .features import (
    FEATURE_VERSION,
    MAX_EVENT_BYTES,
    aware,
    canonical,
    event_from_mapping,
    extract_features,
    identifier,
    known_revisions,
    normalize_event,
    utc,
)
from .model import atomic_write, load_model

MAX_RECORDS_PER_SHIPMENT = 128


class RiskEngine:
    """Store shipment updates and predict risk using the information known then.

    The engine limits how much history it keeps. A lock stops overlapping calls
    from changing that history while another call reads it. Repeated messages,
    late corrections, recovery and model changes follow explicit rules.
    """

    def __init__(self, artifact_dir: Path, max_shipments: int = 10_000):
        """Load a model and start with no shipment history.

        Args:
            artifact_dir: Directory containing ``model.json``.
            max_shipments: Maximum number of shipment histories retained in
                memory. When full, remove the shipment updated longest ago.

        Raises:
            ValueError: If ``max_shipments`` is not a positive integer or the
                model artifact is invalid.
        """
        if type(max_shipments) is not int or max_shipments <= 0:
            raise ValueError("max_shipments must be a positive integer")
        self._model = load_model(artifact_dir)
        self._max_shipments = max_shipments
        self._ships = OrderedDict()
        self._owners = {}
        self._lock = RLock()
        self._accepted = self._evictions = self._trimmed = 0

    def ingest(self, event: TelemetryEvent) -> bool:
        """Check one incoming message and update the stored shipment history.

        Args:
            event: The shipment message that just arrived.

        Returns:
            ``True`` when the message added information to the stored history. ``False`` when
            the delivery was an exact duplicate or older than already discarded
            history.

        Raises:
            ValueError: If a duplicate delivery conflicts, an event ID changes
                shipment, or the event fails the input checks.
        """
        record = normalize_event(event)
        sid = record["shipment_id"]
        eid = record["event_id"]
        key = (eid, record["revision"])

        with self._lock:
            if eid in self._owners and self._owners[eid] != sid:
                raise ValueError("Event ID cannot change shipment")
            state = self._ships.get(sid)

            if state is not None:
                previous = state["records"].get(key)
                if previous is not None:
                    if previous != record:
                        raise ValueError("Conflicting duplicate delivery")
                    return False

                discarded_through = state["discarded_through"]
                if discarded_through is not None and utc(record["received_at"]) <= utc(
                    discarded_through
                ):
                    return False
            else:
                if len(self._ships) == self._max_shipments:
                    _, evicted = self._ships.popitem(last=False)
                    for old in evicted["records"].values():
                        self._owners.pop(old["event_id"], None)
                    self._evictions += 1

                # We do not remember every shipment removed from memory.
                # If one returns, explain that its earlier readings may be missing.
                state = {
                    "records": {},
                    "discarded_through": None,
                    "coverage_unverified": self._evictions > 0,
                }
                self._ships[sid] = state

            state["records"][key] = record
            self._owners[eid] = sid
            self._ships.move_to_end(sid)
            self._accepted += 1

            if len(state["records"]) > MAX_RECORDS_PER_SHIPMENT:
                # Remove an event and all its corrections together.
                # This stops an old reading returning when its correction is removed.
                latest_arrival = {}
                for retained in state["records"].values():
                    event_id = retained["event_id"]
                    received_at = utc(retained["received_at"])
                    latest_arrival[event_id] = max(
                        latest_arrival.get(event_id, received_at),
                        received_at,
                    )

                oldest = min(latest_arrival, key=lambda e: (latest_arrival[e], e))
                removed = [key for key in state["records"] if key[0] == oldest]
                for key in removed:
                    del state["records"][key]
                self._owners.pop(oldest, None)

                boundary = latest_arrival[oldest]
                if state["discarded_through"] is not None:
                    boundary = max(boundary, utc(state["discarded_through"]))
                state["discarded_through"] = boundary.isoformat()
                self._trimmed += len(removed)

            return True

    def score(self, shipment_id: str, as_of: datetime) -> Prediction:
        """Score incident risk for one shipment at one decision time.

        Args:
            shipment_id: Shipment to score.
            as_of: Decision time. The feature extractor only uses revisions
                whose ``received_at`` timestamp is at or before this instant.

        Returns:
            ``Prediction`` containing probability, feature fingerprint, model
            version, and reasons why the available information is incomplete.

        Raises:
            ValueError: If the shipment ID or decision time is invalid.
        """
        sid = identifier(shipment_id, "shipment_id")
        checkpoint = aware(as_of)

        with self._lock:
            state = self._ships.get(sid)
            records = list(state["records"].values()) if state else []
            features = extract_features(records, sid, checkpoint)
            reasons = []

            if state is None:
                reasons.append("shipment_not_retained")
            elif state["coverage_unverified"]:
                reasons.append("retention_coverage_unverified")

            if state and state["discarded_through"] is not None:
                reasons.append("history_truncated")
            if features["temperature_missing"]:
                reasons.append("no_usable_temperature")
            elif features["measurement_age_minutes"] > 180:
                reasons.append("stale_temperature")

            selected = known_revisions(records, checkpoint)
            if any(utc(r["device_time"]) > utc(r["received_at"]) for r in selected):
                reasons.append("future_device_clock_excluded")

            digest = hashlib.sha256(
                canonical({"feature_version": FEATURE_VERSION, "features": features})
            ).hexdigest()
            probability = self._model.prior if state is None else self._model.predict(features)
            return Prediction(
                sid,
                checkpoint,
                probability,
                self._model.version,
                digest,
                bool(reasons),
                tuple(sorted(reasons)),
            )

    def snapshot(self, destination: Path) -> None:
        """Save the stored shipment history with a fingerprint to detect file changes.

        Args:
            destination: File path where the history will be saved as repeatable JSON.

        Returns:
            ``None``. Other calls cannot change the history while it is converted
            to JSON. The finished file then replaces the old one.
        """
        with self._lock:
            body = {
                "schema_version": 1,
                "feature_version": FEATURE_VERSION,
                "model_version": self._model.version,
                "max_shipments": self._max_shipments,
                "record_cap": MAX_RECORDS_PER_SHIPMENT,
                "accepted": self._accepted,
                "evictions": self._evictions,
                "trimmed": self._trimmed,
                "shipments": [
                    {
                        "shipment_id": sid,
                        "discarded_through": state["discarded_through"],
                        "coverage_unverified": state["coverage_unverified"],
                        "records": [
                            state["records"][key] for key in sorted(state["records"])
                        ],
                    }
                    for sid, state in self._ships.items()
                ],
            }
            # Keep other calls from changing history until the JSON is complete.
            encoded = canonical(body)
            wrapper = canonical(
                {"sha256": hashlib.sha256(encoded).hexdigest(), "state": body}
            )
        atomic_write(destination, wrapper)

    @classmethod
    def restore(cls, artifact_dir: Path, snapshot: Path) -> "RiskEngine":
        """Restore an engine from a previously written snapshot.

        Args:
            artifact_dir: Directory containing the same model version used by
                the snapshot.
            snapshot: Snapshot file created by ``snapshot``.

        Returns:
            A new ``RiskEngine`` with retained shipments, counters, and event
            ownership rebuilt from the snapshot.

        Raises:
            ValueError: If the checksum, schema, model version, retention caps,
                counters, or event identities are invalid.
        """
        wrapper = json.loads(Path(snapshot).read_bytes())
        body = wrapper["state"]

        if hashlib.sha256(canonical(body)).hexdigest() != wrapper["sha256"]:
            raise ValueError("Snapshot checksum mismatch")

        compatible_schema = (
            body["schema_version"] == 1
            and body["feature_version"] == FEATURE_VERSION
            and body["record_cap"] == MAX_RECORDS_PER_SHIPMENT
        )
        if not compatible_schema:
            raise ValueError("Incompatible snapshot schema")

        result = cls(artifact_dir, body["max_shipments"])
        if result._model.version != body["model_version"]:
            raise ValueError("Restore requires the snapshot model version")
        if len(body["shipments"]) > result._max_shipments:
            raise ValueError("Snapshot exceeds shipment cap")

        for field in ("accepted", "evictions", "trimmed"):
            if type(body[field]) is not int or body[field] < 0:
                raise ValueError("Invalid snapshot counter")
            setattr(result, "_" + field, body[field])

        for item in body["shipments"]:
            sid = identifier(item["shipment_id"], "shipment_id")
            if sid in result._ships or len(item["records"]) > MAX_RECORDS_PER_SHIPMENT:
                raise ValueError("Invalid snapshot shipment or history cap")

            boundary = item["discarded_through"]
            if boundary is not None:
                boundary = utc(boundary).isoformat()
            if type(item["coverage_unverified"]) is not bool:
                raise ValueError("Invalid snapshot coverage flag")

            records = {}
            for raw in item["records"]:
                record = normalize_event(event_from_mapping(raw))
                eid = record["event_id"]
                key = (eid, record["revision"])
                if (
                    record["shipment_id"] != sid
                    or key in records
                    or result._owners.get(eid, sid) != sid
                ):
                    raise ValueError("Invalid snapshot identity")
                records[key] = record
                result._owners[eid] = sid

            result._ships[sid] = {
                "records": records,
                "discarded_through": boundary,
                "coverage_unverified": item["coverage_unverified"],
            }

        return result

    def reload_model(self, artifact_dir: Path) -> bool:
        """Check a new model, then switch to it while protecting ongoing calls.

        Args:
            artifact_dir: Directory containing the new ``model.json``.

        Returns:
            ``True`` when the new model loads and replaces the current
            model. ``False`` when loading or validation fails; in that case the
            previous model remains active.
        """
        try:
            candidate = load_model(artifact_dir)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
            return False

        with self._lock:
            self._model = candidate
        return True

    def stats(self):
        """Show how much history is stored and which limits apply.

        Returns:
            Dictionary with retained shipment count, record count, capacity
            settings, maximum stored size of one event, accepted deliveries, evictions,
            trimmed records, and active model version.
        """
        with self._lock:
            records = sum(len(state["records"]) for state in self._ships.values())
            return {
                "shipments": len(self._ships),
                "max_shipments": self._max_shipments,
                "retained_records": records,
                "event_id_index": len(self._owners),
                "max_records_per_shipment": MAX_RECORDS_PER_SHIPMENT,
                "max_event_bytes": MAX_EVENT_BYTES,
                "accepted": self._accepted,
                "evictions": self._evictions,
                "trimmed": self._trimmed,
                "model_version": self._model.version,
            }
