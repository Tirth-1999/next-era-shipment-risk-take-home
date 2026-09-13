"""Calculate the same shipment features during training and scoring."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from statistics import mean
from collections.abc import Mapping
import json
import math
from .contracts import TelemetryEvent

FEATURE_VERSION = "temperature-v1"
FEATURES = ["latest_temperature_c", "measurement_age_minutes", "arrival_delay_minutes", "temperature_missing", "temperature_count", "temperature_mean_c", "temperature_max_c", "temperature_trend_c_per_hour", "temperature_span_hours"]
LOOKBACK_HOURS = 3
MAX_EVENT_BYTES = 16384

def canonical(value):
    """Serialize JSON-compatible data into deterministic bytes.

    Args:
        value: Data structure made from JSON-compatible primitives.

    Returns:
        UTF-8 JSON bytes with sorted keys and compact separators.

    Raises:
        ValueError: If ``value`` contains unsupported values such as NaN.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def aware(value):
    """Validate and normalize a datetime to UTC.

    Args:
        value: Datetime expected to include timezone information.

    Returns:
        The same instant converted to UTC.

    Raises:
        ValueError: If the input is not timezone-aware.
    """
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A timezone-aware datetime is required")
    return value.astimezone(timezone.utc)

def identifier(value, field):
    """Validate a stable identifier used in events and labels.

    Args:
        value: Candidate string identifier.
        field: Field name used in the validation error.

    Returns:
        The original identifier when it is nonempty and within the size limit.

    Raises:
        ValueError: If the identifier is missing, not a string, or too long.
    """
    if not isinstance(value,str) or not value or len(value)>256:
        raise ValueError(field + " must be a nonempty string of at most 256 characters")
    return value

def normalize_event(event):
    """Convert a ``TelemetryEvent`` into retained canonical JSON data.

    Args:
        event: Raw telemetry event supplied by callers, tests, or replay.

    Returns:
        A plain dictionary with UTC ISO timestamps and copied payload data.

    Raises:
        TypeError: If ``event`` is not a ``TelemetryEvent``.
        ValueError: If identifiers, revision, timestamps, value, payload, or
            encoded size violate the online retention contract.
    """
    if not isinstance(event,TelemetryEvent):
        raise TypeError("Expected TelemetryEvent")
    if type(event.revision) is not int or not 0 <= event.revision < 2**63:
        raise ValueError("Revision must be a nonnegative 64-bit integer")
    value=event.value
    if isinstance(value,bool) or (value is not None and not isinstance(value,(float,int,str))):
        raise ValueError("Invalid event value")
    if isinstance(value,(float,int)) and not math.isfinite(value):
        raise ValueError("Event value must be finite")
    if not isinstance(event.payload,Mapping):
        raise ValueError("Payload must be a JSON object")
    result={"event_id":identifier(event.event_id,"event_id"),"revision":event.revision,
            "shipment_id":identifier(event.shipment_id,"shipment_id"),
            "device_time":aware(event.device_time).isoformat(),"received_at":aware(event.received_at).isoformat(),
            "kind":identifier(event.kind,"kind"),"source":identifier(event.source,"source"),
            "value":value,"payload":dict(event.payload)}
    encoded=canonical(result)
    if len(encoded)>MAX_EVENT_BYTES:
        raise ValueError("Event exceeds 16 KiB retention budget")
    return json.loads(encoded)  # Copy nested values so caller changes cannot alter retained events.

def event_from_mapping(row):
    """Build a ``TelemetryEvent`` from a JSON dictionary.

    Args:
        row: Mapping with the same fields used by ``TelemetryEvent``. Timestamp
            fields may be ISO strings.

    Returns:
        A ``TelemetryEvent`` with parsed UTC-aware datetimes.
    """
    return TelemetryEvent(**{**row,"device_time":utc(row["device_time"]),"received_at":utc(row["received_at"])})

def utc(text):
    """Parse an ISO timestamp and return it in UTC.

    Args:
        text: ISO-8601 timestamp. A trailing ``Z`` is accepted.

    Returns:
        Timezone-aware UTC datetime.

    Raises:
        ValueError: If the timestamp has no explicit timezone.
    """
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("An explicit timezone is required.")
    return value.astimezone(timezone.utc)

def known_revisions(records, checkpoint):
    """Select the latest known revision for each event at a decision time.

    Args:
        records: Retained normalized event dictionaries.
        checkpoint: Decision time. Events received after this time are ignored,
            even if their device time is older.

    Returns:
        One dictionary per event ID, using the highest revision that had
        arrived by ``checkpoint``. Results are sorted by event ID for stable
        downstream hashing.

    Raises:
        ValueError: If the checkpoint has no timezone, duplicate deliveries
            disagree, or an event ID changes shipment.
    """
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
    """Extract latest-temperature freshness features for one shipment.

    Args:
        records: Normalized events retained for the shipment history.
        shipment: Shipment ID being scored.
        checkpoint: Decision time used to decide which revisions are known.

    Returns:
        Latest numeric temperature, measurement age, arrival delay, and a
        missing-temperature flag. When no usable reading is available, numeric
        values are ``None`` and ``temperature_missing`` is 1.
    """
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
        if measured > received:  # Exclude measurements whose clocks run ahead of receipt.
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
    """Summarize recent temperature behavior inside a lookback window.

    Args:
        records: Normalized retained events.
        shipment: Shipment ID being scored.
        checkpoint: Right edge of the lookback window.
        window_hours: Positive number of hours to look backward.

    Returns:
        Count, mean, max, linear trend, and span of usable temperature readings
        whose measurement time falls in ``(checkpoint - window, checkpoint]``.
        Trend is ``None`` when fewer than two distinct measurement times are
        available, because the slope is unknown rather than flat.

    Raises:
        ValueError: If the checkpoint is naive or the window is invalid.
    """
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
        # Use the same clock rule as the latest-temperature feature.
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

def extract_features(records, shipment, checkpoint):
    """Create the full model feature vector for a shipment checkpoint.

    Args:
        records: Iterable of normalized events available to the caller.
        shipment: Shipment ID to score.
        checkpoint: Decision time. Only revisions received by this instant may
            contribute to the features.

    Returns:
        Dictionary ordered by ``FEATURES`` containing the exact training and
        serving feature contract.
    """
    checkpoint=aware(checkpoint)
    records=list(records)
    result=first_features(records,shipment,checkpoint)
    result.update(window_features(records,shipment,checkpoint,LOOKBACK_HOURS))
    return {name:result[name] for name in FEATURES}
