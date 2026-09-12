# Decision record

## Event time and knowledge time

Preserve delivery order at ingest. At scoring time, select the highest revision **available by `as_of`**, then interpret device time. A later correction never replaces an earlier decision's inputs before its `received_at`. Duplicate identity is `(event_id, revision)`; conflicting contents and changing an event's shipment are rejected atomically. IDs belong to one shipment while retained. Lower revisions can add historical information even after a higher revision has arrived.

Timestamps must have explicit timezones and are normalized to UTC. A measurement claiming a time later than its own receipt is excluded, with a degraded reason. This conservative policy can discard genuine clock-skewed data. An invalid correcting measurement does not resurrect the older revision. Finite numeric temperatures are used; other kinds remain in bounded history but are not model features. Latest measurement may be older than three hours; scoring then flags staleness.

## Labels and evaluation

We allow 48 hours for reports after the six-hour outcome window ends. The same waiting rule applies to positive and negative examples. Reports must have `label_available_at <= cutoff`; positives require an incident in `(decision_time, decision_time + 6 hours]`. Absence of an incident becomes an **assumed negative**, not a certified negative. The 48/72/96-hour exploration found no observed later-report contradictions; that does not prove completeness.

The public builder has no observation-cutoff argument. It uses the latest supplied decision timestamp as the assumed end of observation. The builder returns only mature checkpoints. This departs from the README’s request for a binary label at every checkpoint because recent outcomes may still be unknown. Metadata reports requested/censored counts. A single recent checkpoint can therefore return no rows; `train([])` raises a clear error. Production use needs a certified observation boundary or a separate censored-row contract. Caller-supplied `TrainingRow`s without incident metadata assert the supplied labels are complete; they still receive a maturity gate.

Split by shipment's first decision timestamp into approximately 60/20/20 chronological cohorts, without shared shipments. Timestamp ties stay together. Train labels mature by validation start, validation labels by test start, test labels by the assumed observation cutoff. Report availability is rechecked at each fit cutoff. Training-only median imputation, scaling, and missing indicators prevent preprocessing leakage. Sparse or one-class development data produces a constant model; insufficient holdout data is reported with unavailable metrics left empty. With no training partition, the validation fallback is a fixed 0.5, never a prevalence learned from future rows.

## Features, model, artifact

Nine features: latest temperature, measurement age, arrival delay, missing-temperature indicator, and count/mean/max/trend/span within `(as_of - 3 hours, as_of]`. Trend is an ordinary least-squares slope in degrees/hour using actual timestamps; fewer than two distinct times means missing, not zero. Mean is observation-weighted. Training and scoring use the same functions in `features.py`. Missing numerical values receive fitted medians and explicit indicators; logistic values are standardized. All nine indicators are retained even if redundant.

Notebooks compared constant, logistic, shallow tree, forest and gradient boosting. The declared selection rule required improvements in validation AP and Brier over constant, then picked the simplest within 0.002 Brier of the best eligible model. Logistic was selected before test evaluation. Public `train` fits that fixed family and refits mature development data at test start. It does not reselect using test outcomes.

Public training reproduces the notebook test results: 309 rows, 25 positives; AP 0.981277, Brier 0.003760, log loss 0.020847. Constant AP 0.080906 and Brier 0.074380. At illustrative threshold 0.2: 24 true positives, one false negative, zero false positives. Source, measurement freshness, and missing trend slices are reported. Notebook 13 also includes reliability bins and shipment-bootstrap uncertainty. The results come from synthetic data. We have not chosen an operating threshold or fitted a separate probability calibrator.

Serving uses a small JSON artifact, not executable pickle. It stores the feature version/order/window, fitted imputation/scaling parameters, coefficients, prior, training cutoff, training-data digest and library version. Canonical content SHA-256 is the model version. The installed `dispatch_risk` package supplies the versioned feature interpreter; incompatible artifacts fail validation. The exported model’s probabilities are checked against the fitted sklearn pipeline to 1e-12. Exact replay guarantees apply to the same runtime/artifact; different math libraries or platforms can introduce floating-point differences. Hashes detect accidental damage, not malicious replacement.

## Memory, eviction, and idempotency

A lock protects an insertion-ordered map of at most `max_shipments` shipment states. Successful ingest refreshes recency; score and exact duplicate deliveries do not. Evict the least recently updated shipment, including its event-ID index entries. Each shipment retains at most 128 revision records; each normalized record is at most 16 KiB, IDs at most 256 characters. The cap covers both records and the event-ID lookup index. These rules bound stored data; they do not impose an exact process-memory limit: worst-case stored JSON is about 64 MiB for 32 shipments, plus Python object overhead.

If a shipment exceeds its record budget, remove all revisions of the event whose latest receipt is oldest, with event ID as a tie breaker. Keep one discard-time watermark per shipment; deliveries at or before it cannot resurrect forgotten records. Whole-event trimming can discard many revisions at once. A prediction from truncated history always carries `history_truncated`, even if a particular recent window might be complete.

The engine does not keep a growing list of every evicted shipment. If one returns, it starts with a new history. This means duplicate recognition and event-ID ownership checks cannot extend across eviction. New shipment states after any eviction conservatively carry `retention_coverage_unverified`. Unknown shipments receive the fitted prior and degraded reasons. Exact historical reconstruction is supported while the relevant history is retained; degraded predictions expose the limitation afterward. Finite memory means some very late deliveries can no longer be matched against their full history. `stats()` exposes caps, retained/index counts, accepted deliveries, evictions and trimming.

## Concurrency, snapshots, reload

An `RLock` serializes ingest, score, snapshot capture and stats. Each score uses one model and a consistent view of the retained readings. Reload reads, validates and smoke-tests a candidate outside the lock, then swaps one reference under the lock. Failure returns false without changing model or state. If the initial model cannot load, startup fails rather than returning an unsupported zero-risk result.

Snapshots encode canonical JSON under the lock, including LRU order, records, discard watermarks, coverage flags, counters and model version. Writing uses a temporary file, flush/fsync and atomic rename. Restore checks integrity, schema, bounds and identities before returning an engine, and requires the same model version. The model artifact is supplied separately. Concurrent snapshots each capture a consistent state, although last rename wins when writers target the same path. This is single-process file replacement; broker offsets, multi-process coordination and filesystem power-loss guarantees beyond file fsync are not implemented.

## Responses to the customer notes

1. **Random row split:** rejected; chronological, shipment-disjoint cohorts better estimate future use.
2. **Always newest revision:** rejected; only revisions available by the decision are eligible.
3. **Sort replay by device time:** rejected; preserve delivery order, use device time only inside eligible feature calculations.
4. **Deduplicate shipment ID:** rejected; deduplicate event ID plus revision within retained history.
5. **Kafka guarantees snapshot consistency:** rejected; application state capture and atomic replacement are implemented independently of a broker.
6. **Load failure means zero risk:** rejected; retain the last valid model, or fail initial startup.
7. **Full incident table in features:** rejected; incidents are outcomes only, restricted by label availability.
8. **AUC > 0.90 sufficient for launch:** rejected; AP, probability error, baseline, slices and uncertainty matter; real-data validation and operational costs remain necessary.
9. **Keep every shipment:** rejected; enforce shipment and record caps with explicit retention limitations.
10. **Reload clears state:** rejected; only the immutable model reference changes.

## Scope and reproduction

Implemented the public builder, training, engine, CLI, snapshots/restore, bounded retention, model reload, and focused invariant tests. See `RUNBOOK.md` for exact commands. Not implemented: broker offset transactions, real-time SLA/load testing, distributed state, authenticated model signing, automatic drift retraining, or features from door/compressor/location. The implementation is intended for the local exercise; these remain outside its scope.

Generated files in `data/` total approximately 0.40 MB when individually gzip-compressed, below the 5 MB requirement. Notebook learning artifacts are retained separately from the portable serving artifact. No network is required for training/scoring after declared dependencies are installed. Verification here used Python 3.14; the declared minimum is 3.11 but that version was not separately tested.
