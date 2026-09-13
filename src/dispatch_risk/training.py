"""Point-in-time examples and chronological evaluation of the selected model family."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from pathlib import Path
import hashlib
import math

from .contracts import TrainingRow
from .features import (
    FEATURES,
    FEATURE_VERSION,
    LOOKBACK_HOURS,
    aware,
    canonical,
    extract_features,
    identifier,
    normalize_event,
    utc,
)
from .model import atomic_write, write_model

HORIZON = timedelta(hours=6)
GRACE = timedelta(hours=48)


def build_training_rows(events, labels, decision_times):
    """Create mature point-in-time examples from events, labels, and checkpoints.

    Args:
        events: Iterable of ``TelemetryEvent`` objects in delivery order.
            Duplicate deliveries are allowed only when their content matches.
        labels: Iterable of incident-report mappings with ``incident_at`` and
            ``label_available_at`` timestamps.
        decision_times: Iterable of ``(shipment_id, decision_time)`` pairs at
            which the model would have been asked to predict.

    Returns:
        List of ``TrainingRow`` objects. Rows whose six-hour outcome window plus
        48-hour reporting grace has not completed by the observation cutoff are
        excluded rather than silently labeled negative.

    Raises:
        ValueError: If event or incident identities conflict, timestamps are
            invalid, or identifiers fail validation.
    """
    decisions = sorted(
        {(identifier(shipment_id, "shipment_id"), aware(decision_time))
         for shipment_id, decision_time in decision_times},
        key=lambda item: (item[1], item[0]),
    )
    if not decisions:
        return []

    cutoff = max(decision_time for _, decision_time in decisions)
    first = {}
    for shipment_id, decision_time in decisions:
        first.setdefault(shipment_id, decision_time)

    cohorts = sorted(first, key=lambda shipment_id: (first[shipment_id], shipment_id))
    validation_start = first[cohorts[min(int(len(cohorts) * 0.6), len(cohorts) - 1)]]
    test_start = first[cohorts[min(int(len(cohorts) * 0.8), len(cohorts) - 1)]]

    histories = defaultdict(list)
    identities = {}
    owners = {}

    for event in events:
        normalized = normalize_event(event)
        event_id = normalized["event_id"]
        key = (event_id, normalized["revision"])

        if event_id in owners and owners[event_id] != normalized["shipment_id"]:
            raise ValueError("Event ID cannot change shipment")
        owners[event_id] = normalized["shipment_id"]

        if key in identities:
            if identities[key] != normalized:
                raise ValueError("Conflicting duplicate event")
            continue

        identities[key] = normalized
        histories[normalized["shipment_id"]].append(normalized)

    incidents = defaultdict(list)
    seen = {}

    for raw in labels:
        row = dict(raw)
        incident_id = identifier(row["incident_id"], "incident_id")
        shipment_id = identifier(row["shipment_id"], "shipment_id")
        incident_at = (
            aware(row["incident_at"])
            if not isinstance(row["incident_at"], str)
            else utc(row["incident_at"])
        )
        available_at = (
            aware(row["label_available_at"])
            if not isinstance(row["label_available_at"], str)
            else utc(row["label_available_at"])
        )

        if available_at < incident_at:
            raise ValueError("Incident report cannot precede incident")

        item = {
            "incident_id": incident_id,
            "shipment_id": shipment_id,
            "incident_at": incident_at.isoformat(),
            "label_available_at": available_at.isoformat(),
        }
        if incident_id in seen:
            if item != seen[incident_id]:
                raise ValueError("Conflicting incident identity")
            continue

        seen[incident_id] = item
        if available_at <= cutoff:
            incidents[shipment_id].append(item)

    rows = []
    censored = sum(
        decision_time + HORIZON + GRACE > cutoff for _, decision_time in decisions
    )

    for shipment_id, decision_time in decisions:
        # Do not turn "not yet knowable" into label 0. The row becomes usable
        # only after the outcome horizon and reporting allowance have both passed.
        eligible_at = decision_time + HORIZON + GRACE
        if eligible_at > cutoff:
            continue

        relevant = sorted(
            [
                incident
                for incident in incidents[shipment_id]
                if decision_time < utc(incident["incident_at"]) <= decision_time + HORIZON
            ],
            key=lambda incident: (incident["incident_at"], incident["incident_id"]),
        )
        features = extract_features(histories[shipment_id], shipment_id, decision_time)

        source_events = [
            event
            for event in histories[shipment_id]
            if utc(event["received_at"]) <= decision_time
        ]
        source = (
            max(
                source_events,
                key=lambda event: (
                    event["received_at"],
                    event["event_id"],
                    event["revision"],
                ),
            )["source"]
            if source_events
            else "unknown"
        )

        metadata = {
            "feature_version": FEATURE_VERSION,
            "source": source,
            "horizon_end": (decision_time + HORIZON).isoformat(),
            "eligible_at": eligible_at.isoformat(),
            "observation_cutoff": cutoff.isoformat(),
            "validation_start": validation_start.isoformat(),
            "test_start": test_start.isoformat(),
            "cohort_first_decision": first[shipment_id].isoformat(),
            "outcome_incidents": relevant,
            "negative_policy": "assumed complete after 48h reporting allowance",
            "censored_decisions": censored,
            "requested_decisions": len(decisions),
        }
        rows.append(
            TrainingRow(
                shipment_id,
                decision_time,
                features,
                int(bool(relevant)),
                metadata,
            )
        )

    return rows


def _label(row, cutoff):
    """Resolve a row label as of a training or evaluation cutoff.

    Args:
        row: Candidate training row.
        cutoff: Time by which outcome reports are assumed observable.

    Returns:
        ``1`` for an incident inside the horizon, ``0`` for an eligible
        no-incident row, or ``None`` when the row is still immature at the
        supplied cutoff.
    """
    if row.decision_time + HORIZON + GRACE > cutoff:
        return None

    incidents = row.metadata.get("outcome_incidents")
    if incidents is not None:
        return int(
            any(
                utc(incident["label_available_at"]) <= cutoff
                and row.decision_time
                < utc(incident["incident_at"])
                <= row.decision_time + HORIZON
                for incident in incidents
            )
        )

    available = row.metadata.get("label_available_at")
    if available is not None and utc(available) > cutoff:
        return None

    # External TrainingRows: caller asserts label completeness, with default 48h maturity.
    return row.label


def train(rows, artifact_dir):
    """Train the portable model artifact and write evaluation output.

    Args:
        rows: Mature ``TrainingRow`` examples. Rows are split by chronological
            shipment cohort into train, validation, development, and test
            groups.
        artifact_dir: Directory where ``model.json`` and ``evaluation.json``
            will be written.

    Returns:
        Evaluation report dictionary containing split boundaries, validation
        metrics, held-out metrics, slice metrics, limitations, model kind, and
        model version.

    Raises:
        ValueError: If no usable rows are supplied, duplicate checkpoints are
            present, labels/features are invalid, dataset cutoffs are mixed, or
            the portable scorer disagrees with the fitted sklearn pipeline.
    """
    import numpy as np
    import pandas as pd
    import sklearn
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import MissingIndicator, SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (
        average_precision_score,
        brier_score_loss,
        confusion_matrix,
        log_loss,
    )
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from threadpoolctl import threadpool_limits

    rows = sorted(rows, key=lambda row: (aware(row.decision_time), row.shipment_id))
    if not rows:
        raise ValueError("No mature training rows; provide a longer observed time span")
    if len({(row.shipment_id, row.decision_time) for row in rows}) != len(rows):
        raise ValueError("Duplicate training checkpoint")

    for row in rows:
        if type(row.label) is not int or row.label not in (0, 1):
            raise ValueError("Labels must be binary integers")
        if row.metadata.get("feature_version", FEATURE_VERSION) != FEATURE_VERSION:
            raise ValueError("Training feature version mismatch")
        for name in FEATURES:
            value = row.features.get(name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError("Features must be finite numeric values or None")

    first = {}
    for row in rows:
        first_decision = (
            utc(row.metadata["cohort_first_decision"])
            if "cohort_first_decision" in row.metadata
            else row.decision_time
        )
        first.setdefault(row.shipment_id, first_decision)

    ordered = sorted(first, key=lambda shipment_id: (first[shipment_id], shipment_id))

    def consistent(field, default):
        """Read one shared timestamp metadata field across all rows."""
        values = {row.metadata[field] for row in rows if field in row.metadata}
        if len(values) > 1:
            raise ValueError("Mixed dataset cutoffs")
        return utc(next(iter(values))) if values else default

    validation_start = consistent(
        "validation_start",
        first[ordered[min(int(len(ordered) * 0.6), len(ordered) - 1)]],
    )
    test_start = consistent(
        "test_start",
        first[ordered[min(int(len(ordered) * 0.8), len(ordered) - 1)]],
    )
    observation_cutoff = consistent(
        "observation_cutoff",
        max(row.decision_time for row in rows) + HORIZON + GRACE,
    )

    def subset(group, cutoff):
        """Select rows and labels for a named chronological cohort."""
        selected = []
        labels = []

        for row in rows:
            first_time = first[row.shipment_id]
            if group == "train":
                belongs = first_time < validation_start
            elif group == "validation":
                belongs = validation_start <= first_time < test_start
            elif group == "development":
                belongs = first_time < test_start
            else:
                belongs = first_time >= test_start

            label = _label(row, cutoff)
            if belongs and label is not None:
                selected.append(row)
                labels.append(label)

        return selected, np.array(labels, dtype=int)

    train_rows, train_y = subset("train", validation_start)
    validation_rows, validation_y = subset("validation", test_start)
    development_rows, development_y = subset("development", test_start)
    test_rows, test_y = subset("test", observation_cutoff)

    def X(selected_rows):
        """Convert training rows into a pandas feature matrix."""
        return pd.DataFrame(
            [
                {name: row.features.get(name) for name in FEATURES}
                for row in selected_rows
            ],
            columns=FEATURES,
            dtype=float,
        )

    def fit(selected_rows, labels):
        """Fit the sklearn logistic pipeline or return ``None`` for one class."""
        if len(np.unique(labels)) < 2:
            return None

        # Numeric feature values and missingness indicators are both exported
        # into the portable JSON model artifact after fitting.
        preprocessing = ColumnTransformer(
            [
                (
                    "values",
                    Pipeline(
                        [
                            (
                                "impute",
                                SimpleImputer(
                                    strategy="median",
                                    keep_empty_features=True,
                                ),
                            ),
                            ("scale", StandardScaler()),
                        ]
                    ),
                    FEATURES,
                ),
                ("missing", MissingIndicator(features="all"), FEATURES),
            ],
            sparse_threshold=0,
        )
        model = Pipeline(
            [
                ("prepare", preprocessing),
                (
                    "model",
                    LogisticRegression(C=1, max_iter=2000, random_state=1729),
                ),
            ]
        )
        with threadpool_limits(limits=1):
            model.fit(X(selected_rows), labels)
        return model

    def measure(labels, probabilities):
        """Calculate probability and threshold metrics for one evaluation set."""
        if not len(labels):
            return {
                "rows": 0,
                "positives": 0,
                "average_precision": None,
                "brier": None,
                "log_loss": None,
                "recall_at_0_2": None,
                "precision_at_0_2": None,
            }

        _, false_positive, false_negative, true_positive = confusion_matrix(
            labels,
            probabilities >= 0.2,
            labels=[0, 1],
        ).ravel()
        has_both_classes = len(np.unique(labels)) == 2

        return {
            "rows": len(labels),
            "positives": int(labels.sum()),
            "average_precision": (
                min(1.0, float(average_precision_score(labels, probabilities)))
                if has_both_classes
                else None
            ),
            "brier": float(brier_score_loss(labels, probabilities)),
            "log_loss": float(
                log_loss(
                    labels,
                    np.clip(probabilities, 1e-15, 1 - 1e-15),
                    labels=[0, 1],
                )
            ),
            "recall_at_0_2": (
                float(true_positive / (true_positive + false_negative))
                if true_positive + false_negative
                else None
            ),
            "precision_at_0_2": (
                float(true_positive / (true_positive + false_positive))
                if true_positive + false_positive
                else None
            ),
            "true_positive": int(true_positive),
            "false_positive": int(false_positive),
            "false_negative": int(false_negative),
        }

    fitted = fit(train_rows, train_y) if train_rows else None
    training_prior = float(train_y.mean()) if len(train_y) else 0.5
    validation_probabilities = (
        fitted.predict_proba(X(validation_rows))[:, 1]
        if fitted is not None and validation_rows
        else np.full(len(validation_rows), training_prior)
    )
    validation = {
        "logistic_or_fallback": measure(validation_y, validation_probabilities),
        "constant": measure(
            validation_y,
            np.full(len(validation_rows), training_prior),
        ),
    }
    report = {
        "schema_version": 1,
        "configuration": (
            "Regularized logistic fixed from notebook validation; "
            "no test-based reselection"
        ),
        "split": {
            "validation_start": validation_start.isoformat(),
            "test_start": test_start.isoformat(),
            "observation_cutoff": observation_cutoff.isoformat(),
            "rule": "chronological shipment cohorts 60/20/20; horizon+48h maturity",
        },
        "validation": validation,
        "limitations": [
            "Synthetic data; 48h mature-record completeness is an assumption",
            "Latest decision time is an assumed observation snapshot, not certified audit coverage",
            "20% threshold is illustrative, not a launch decision",
        ],
    }

    if not development_rows:
        # With too little history to split, save a constant and omit held-out metrics.
        development_rows = rows
        development_y = np.array([row.label for row in rows])
        test_rows = []
        test_y = np.array([], dtype=int)
        report["limitations"].append(
            "Insufficient chronological development span: fit constant on supplied "
            "mature rows; no held-out estimate"
        )
        final = None
    else:
        final = fit(development_rows, development_y)

    prior = float(development_y.mean())
    probabilities = (
        final.predict_proba(X(test_rows))[:, 1]
        if final is not None and test_rows
        else np.full(len(test_rows), prior)
    )

    report["test"] = measure(test_y, probabilities)
    report["constant_test"] = measure(test_y, np.full(len(test_rows), prior))
    report["development_rows"] = len(development_rows)
    report["slices"] = []

    for dimension in ("source", "freshness", "trend"):
        groups = {}
        for idx, row in enumerate(test_rows):
            if dimension == "source":
                value = row.metadata.get("source", "unknown")
            elif dimension == "freshness":
                age = row.features.get("measurement_age_minutes")
                value = (
                    "missing"
                    if age is None
                    else "older_than_30_minutes"
                    if age > 30
                    else "within_30_minutes"
                )
            else:
                value = (
                    "missing"
                    if row.features.get("temperature_trend_c_per_hour") is None
                    else "present"
                )
            groups.setdefault(value, []).append(idx)

        for value, index in sorted(groups.items()):
            report["slices"].append(
                {
                    "dimension": dimension,
                    "value": value,
                    **measure(test_y[index], probabilities[index]),
                }
            )

    training_digest_rows = [
        {
            "shipment_id": row.shipment_id,
            "decision_time": row.decision_time.isoformat(),
            "features": dict(row.features),
            "label": int(label),
        }
        for row, label in zip(development_rows, development_y)
    ]
    training_cutoff = (
        observation_cutoff
        if (
            not report["test"]["rows"]
            and "Insufficient chronological" in " ".join(report["limitations"])
        )
        else test_start
    )

    body = {
        "schema_version": 1,
        "feature_version": FEATURE_VERSION,
        "feature_order": FEATURES,
        "lookback_hours": LOOKBACK_HOURS,
        "kind": "constant" if final is None else "logistic_regression",
        "prior": prior,
        "medians": [0.0] * 9,
        "means": [0.0] * 9,
        "scales": [1.0] * 9,
        "weights": [0.0] * 18,
        "intercept": 0.0,
        "training_cutoff": training_cutoff.isoformat(),
        "grace_hours": 48,
        "training_library_version": sklearn.__version__,
        "training_rows_digest": hashlib.sha256(
            canonical(training_digest_rows)
        ).hexdigest(),
    }

    if final is not None:
        preprocessing = final.named_steps["prepare"].named_transformers_["values"]
        body.update(
            medians=preprocessing.named_steps["impute"].statistics_.tolist(),
            means=preprocessing.named_steps["scale"].mean_.tolist(),
            scales=preprocessing.named_steps["scale"].scale_.tolist(),
            weights=final.named_steps["model"].coef_[0].tolist(),
            intercept=float(final.named_steps["model"].intercept_[0]),
        )

    model = write_model(artifact_dir, body)

    if final is not None:
        expected = final.predict_proba(X(development_rows))[:, 1]
        actual = np.array([model.predict(row.features) for row in development_rows])
        if not np.allclose(expected, actual, atol=1e-12, rtol=1e-12):
            raise ValueError("Portable scoring differs from trained pipeline")

    report["model_version"] = model.version
    report["model_kind"] = model.kind
    atomic_write(Path(artifact_dir) / "evaluation.json", canonical(report))
    return report
