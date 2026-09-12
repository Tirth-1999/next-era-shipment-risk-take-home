from datetime import datetime, timedelta, timezone
from statistics import mean
import math, json

def utc(text):
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("An explicit timezone is required.")
    return value.astimezone(timezone.utc)


def known_revisions(records, checkpoint):
    """Teaching helper: select highest available revision per event ID."""
    if checkpoint.tzinfo is None:
        raise ValueError("Checkpoint must include a timezone")
    checkpoint = checkpoint.astimezone(timezone.utc)
    delivered = {}
    latest = {}
    for event in records:
        if utc(event["received_at"]) > checkpoint:
            continue
        key = (event["event_id"], event["revision"])
        # Compare canonical timestamps so equivalent timezone notation agrees.
        normalized = dict(event)
        for field in ("device_time", "received_at"):
            normalized[field] = utc(event[field]).isoformat()
        signature = json.dumps(normalized, sort_keys=True, allow_nan=False)
        if key in delivered:
            if delivered[key] != signature:
                raise ValueError("Conflicting content for the same event/revision")
            continue
        delivered[key] = signature
        prior = latest.get(event["event_id"])
        if prior is not None and prior["shipment_id"] != event["shipment_id"]:
            raise ValueError("An event ID changed shipment")
        if prior is None or event["revision"] > prior["revision"]:
            latest[event["event_id"]] = dict(event)
    return [latest[event_id] for event_id in sorted(latest)]


def first_features(records, shipment, checkpoint):
    selected = known_revisions(records, checkpoint)
    usable = []
    for event in selected:
        if event["shipment_id"] != shipment or event["kind"] != "temperature_c":
            continue
        value = event["value"]
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            continue
        if not math.isfinite(value):
            continue
        measured = utc(event["device_time"])
        received = utc(event["received_at"])
        if measured > received:  # Provisional experiment policy; see explanation above.
            continue
        usable.append(event)
    if not usable:
        return {"latest_temperature_c": None, "measurement_age_minutes": None,
                "arrival_delay_minutes": None, "temperature_missing": 1}
    latest = max(usable, key=lambda e: (utc(e["device_time"]),
                                      utc(e["received_at"]), e["event_id"]))
    measured = utc(latest["device_time"])
    received = utc(latest["received_at"])
    return {
        "latest_temperature_c": float(latest["value"]),
        "measurement_age_minutes": (checkpoint - measured).total_seconds() / 60,
        "arrival_delay_minutes": (received - measured).total_seconds() / 60,
        "temperature_missing": 0,
    }


def window_features(records, shipment, checkpoint, window_hours=3):
    if checkpoint.tzinfo is None:
        raise ValueError("Checkpoint needs an explicit timezone")
    if not math.isfinite(window_hours) or window_hours <= 0:
        raise ValueError("Window must be finite and positive")
    left = checkpoint - timedelta(hours=window_hours)
    points = []
    for event in known_revisions(records, checkpoint):
        if event["shipment_id"] != shipment or event["kind"] != "temperature_c":
            continue
        value = event["value"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        measured, received = utc(event["device_time"]), utc(event["received_at"])
        # Reuse checkpoint 3's provisional strict future-clock exclusion.
        if measured > received or not left < measured <= checkpoint:
            continue
        points.append((measured, event["event_id"], float(value)))
    points.sort(key=lambda p: (p[0], p[1]))
    if not points:
        return {"temperature_count": 0, "temperature_mean_c": None,
                "temperature_max_c": None, "temperature_trend_c_per_hour": None,
                "temperature_span_hours": None}
    values = [p[2] for p in points]
    hours = [(p[0] - points[0][0]).total_seconds() / 3600 for p in points]
    x_mean, y_mean = mean(hours), mean(values)
    denominator = sum((x - x_mean)**2 for x in hours)
    slope = (sum((x - x_mean)*(y - y_mean) for x, y in zip(hours, values))
             / denominator) if denominator > 0 else None
    return {"temperature_count": len(points), "temperature_mean_c": y_mean,
            "temperature_max_c": max(values), "temperature_trend_c_per_hour": slope,
            "temperature_span_hours": hours[-1]}
