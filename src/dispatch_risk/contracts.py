from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    """One delivered shipment event before it is normalized by the engine.

    Attributes:
        event_id: Stable identity for a real-world measurement or status update.
            Multiple deliveries with the same event ID may appear when a message
            is duplicated or corrected.
        revision: Monotonic revision for the same event ID. Higher revisions
            supersede lower revisions once they have actually arrived.
        shipment_id: Shipment that owns this event. The same event ID is not
            allowed to move between shipments.
        device_time: Time when the measurement was taken by the device.
        received_at: Time when this revision arrived at the risk service.
        kind: Type of event. The current feature set uses numeric
            ``temperature_c`` events.
        value: Raw event value. Temperature values must be finite numbers.
        source: Producer or feed name used for audit slices.
        payload: Extra JSON-compatible fields retained for traceability.
    """

    event_id: str
    revision: int
    shipment_id: str
    device_time: datetime
    received_at: datetime
    kind: str
    value: float | str | None
    source: str
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TrainingRow:
    """Point-in-time supervised example used by offline training.

    Attributes:
        shipment_id: Shipment being scored.
        decision_time: Prediction checkpoint. Features must only use events
            received at or before this time.
        features: Model-ready values extracted from the known shipment state.
        label: Binary target, where 1 means an incident occurred inside the
            configured prediction horizon.
        metadata: Audit information about the horizon, split boundaries,
            source feed, and label-completeness assumption.
    """

    shipment_id: str
    decision_time: datetime
    features: Mapping[str, float | int | str | None]
    label: int
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Prediction:
    """Canonical prediction returned by the online risk engine.

    Attributes:
        shipment_id: Shipment that was scored.
        as_of: Decision time used for feature extraction.
        probability: Incident probability in the six-hour prediction horizon.
        model_version: Content hash of the portable model artifact.
        feature_digest: Hash of the exact features used for the score.
        degraded: True when the score is still returned but should be treated
            with extra caution because of missing, stale, or truncated context.
        reasons: Stable machine-readable reasons for degraded scoring.
    """

    shipment_id: str
    as_of: datetime
    probability: float
    model_version: str
    feature_digest: str
    degraded: bool
    reasons: tuple[str, ...]

    def to_wire(self) -> bytes:
        """Return deterministic JSON bytes for audit and replay checks.

        Returns:
            UTF-8 encoded JSON with sorted keys and no non-deterministic
            whitespace. Replaying the same retained state should produce
            identical bytes, which makes equality checks meaningful.
        """
        import json

        value = {
            "as_of": self.as_of.isoformat(),
            "degraded": self.degraded,
            "feature_digest": self.feature_digest,
            "model_version": self.model_version,
            "probability": self.probability,
            "reasons": list(self.reasons),
            "shipment_id": self.shipment_id,
        }
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
