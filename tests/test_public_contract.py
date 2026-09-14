from __future__ import annotations

from datetime import datetime, timezone

from dispatch_risk.contracts import Prediction


def test_prediction_wire_format_is_canonical() -> None:
    prediction = Prediction(
        shipment_id="s-1",
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        probability=0.25,
        model_version="m-1",
        feature_digest="abc",
        degraded=False,
        reasons=("temperature_high",),
    )
    assert prediction.to_wire() == (
        b'{"as_of":"2026-01-01T00:00:00+00:00","degraded":false,'
        b'"feature_digest":"abc","model_version":"m-1","probability":0.25,'
        b'"reasons":["temperature_high"],"shipment_id":"s-1"}'
    )
