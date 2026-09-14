from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    """One shipment message before the engine checks and stores it.

    Attributes:
        event_id: ID for one measurement or status update.
            Multiple deliveries with the same event ID may appear when a message
            is duplicated or corrected.
        revision: Version number for the same event ID. A higher version replaces
            a lower one for predictions made after the higher version arrived.
        shipment_id: Shipment that owns this event. The same event ID is not
            allowed to move between shipments.
        device_time: Time when the measurement was taken by the device.
        received_at: Time when this revision arrived at the risk service.
        kind: Type of event. The current feature set uses numeric
            ``temperature_c`` events.
        value: Raw event value. Temperature values must be finite numbers.
        source: Name of the source, used to compare results across data feeds.
        payload: Extra JSON fields saved so we can inspect the original message.
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
    """One training example with the inputs known at its prediction time.

    Attributes:
        shipment_id: Shipment being scored.
        decision_time: Prediction checkpoint. Features must only use events
            received at or before this time.
        features: Input values calculated from the shipment information known then.
        label: Answer used to train the model: 1 means an incident occurred in
            the prediction window; 0 means no incident under the reporting rule.
        metadata: Details about the prediction window, data split, source feed,
            and the assumption about when incident reports are complete.
    """

    shipment_id: str
    decision_time: datetime
    features: Mapping[str, float | int | str | None]
    label: int
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Prediction:
    """The result returned when the engine predicts shipment risk.

    Attributes:
        shipment_id: Shipment that was scored.
        as_of: Decision time used for feature extraction.
        probability: Estimated chance of an incident in the next six hours.
        model_version: Fingerprint of the saved model settings.
        feature_digest: Fingerprint of the exact input values used for this prediction.
        degraded: True when the score is still returned but should be treated
            with extra caution because of missing readings, old readings, or history removed to save memory.
        reasons: Reason codes that explain why the prediction has limited information.
    """

    shipment_id: str
    as_of: datetime
    probability: float
    model_version: str
    feature_digest: str
    degraded: bool
    reasons: tuple[str, ...]

    def to_wire(self) -> bytes:
        """Write the prediction as JSON bytes in a repeatable format.

        Returns:
            UTF-8 JSON bytes with sorted keys and fixed spacing. The same
            prediction produces the same bytes, so tests can compare them exactly.
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
