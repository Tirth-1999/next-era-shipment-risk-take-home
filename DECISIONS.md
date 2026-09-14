# Decisions

These are my decisions for the submission. I rejected all ten customer suggestions as written. For each one, I explain why and identify the rule I implemented.

## 1. Use a random 80/20 row split

**My decision: I reject this suggestion. Split shipments by time into training, validation and test groups.**

A random row split can put checkpoints from the same shipment on both sides and mix earlier and later examples. That weakens the estimate of future performance.

Order shipments by their first decision time and use approximately 60/20/20 groups. Keep each shipment and equal start times together. Check results by sensor source separately; do not force every source into every time period. Learn missing value replacements and scaling values only from fitting rows.

**Implemented in:** [training.py](src/dispatch_risk/training.py).

## 2. Always apply the newest event revision

**My decision: I reject this suggestion. Use the highest revision that had arrived by the requested decision time.**

A correction received at noon was unavailable to an 11 AM prediction. Applying it would use future information.

Filter revisions by `received_at <= as_of` before choosing the highest revision. Keep older revisions while their history remains stored so earlier predictions can be reconstructed.

**Implemented in:** `known_revisions` in [features.py](src/dispatch_risk/features.py).

## 3. Sort everything by device time before replay

**My decision: I reject this suggestion. Process messages in their supplied delivery order.**

Sorting by device time changes when the engine sees a message and can also change which shipment histories are removed from memory. Device clocks can be wrong.

Use receipt time to decide whether a reading was available. Use device time to calculate reading age and temperature windows after that check. Exclude readings whose device time is later than their receipt time and return an explanation. An unusable correction does not bring back its older reading.

**Implemented in:** [__main__.py](src/dispatch_risk/__main__.py) and [features.py](src/dispatch_risk/features.py).

## 4. Deduplicate on shipment ID

**My decision: I reject this suggestion. Identify a repeated message by event ID and revision.**

One shipment has many valid readings. Deduplicating by shipment would discard them.

An exact repeated delivery has no extra effect. Reject different contents for the same event ID and revision, or an event ID moving to another shipment. These checks apply while the identifying history remains in memory.

**Implemented in:** `ingest` in [engine.py](src/dispatch_risk/engine.py).

## 5. Rely on Kafka for snapshot consistency

**My decision: I reject this suggestion. The application must save a consistent copy of its own history.**

A messaging system's delivery guarantees do not make changes to this engine's memory and local files one transaction. This submission does not use Kafka.

Hold the engine lock while capturing history, ordering, counters and model version. Write a temporary file, flush it to disk, then replace the destination. Restore checks the snapshot contents and requires the matching model version. Saving broker positions together with engine history is not implemented.

**Implemented in:** `snapshot` and `restore` in [engine.py](src/dispatch_risk/engine.py), and `atomic_write` in [model.py](src/dispatch_risk/model.py).

## 6. Return zero risk when a model cannot load

**My decision: I reject this suggestion. Keep the previous valid model after a failed reload. Stop startup if no valid model can be loaded.**

Zero is a prediction of no incident risk. A model loading error provides no evidence for that prediction.

`reload_model` returns `False` on failure and leaves the current model and shipment history intact. The constructor raises an error if the initial model is invalid.

**Implemented in:** [engine.py](src/dispatch_risk/engine.py) and [model.py](src/dispatch_risk/model.py).

## 7. Use the full incident table to generate features

**My decision: I reject this suggestion. Use incident reports to build training answers only.**

An incident report can arrive after the prediction. Putting it into the model inputs would reveal the outcome being predicted.

Build features from shipment messages available at the checkpoint. Build labels from incidents in `(decision_time, decision_time + 6 hours]`, using only reports available by the relevant training or evaluation cutoff. Apply the reporting wait described below.

**Implemented in:** `build_training_rows` and `_label` in [training.py](src/dispatch_risk/training.py).

## 8. Treat AUC above 0.90 as sufficient for launch

**My decision: I reject this suggestion. These synthetic test results do not justify a production launch.**

One ranking score does not establish probability accuracy, acceptable false alarms, or performance across operational groups.

Report average precision, Brier score, log loss, a constant baseline, and results by source, reading age and missing trend. The final test has 309 checkpoints and 25 positives: average precision 0.981277 and Brier 0.003760, against baseline values of 0.080906 and 0.074380. At the demonstration cutoff of 20%, the model catches 24 positive checkpoints, misses one and raises no false alarms.

Real deployment requires confirmed report coverage, evaluation on real shipments, and an alert cutoff based on incident costs and response capacity. No production cutoff has been selected.

**Evidence:** [evaluation.json](outputs/final_model/evaluation.json). Notebook 13 adds calibration plots and uncertainty estimates by resampling whole shipments.

## 9. Keep every shipment in memory

**My decision: I reject this suggestion. Enforce the shipment limit and limits on each shipment's records.**

Unlimited history violates the required memory contract. One busy shipment can also grow indefinitely unless its records are capped.

Keep at most `max_shipments` histories and 128 revision records per shipment. Limit each stored event to 16 KiB and each ID to 256 characters. Remove the shipment updated longest ago when capacity is reached, including its event ID lookup entries. Accepted new messages update that order; scores and exact duplicates do not.

When trimming one shipment, remove all revisions of the selected event together. Remember the latest removed receipt time and reject arrivals at or before it. Return `history_truncated` for shortened histories and `retention_coverage_unverified` for new histories after a shipment removal. Exact duplicate recognition and historical reconstruction are limited by the history still stored. Unknown shipments receive the fitted prior incident rate with reasons explaining the missing history.

These limits bound stored data. They do not enforce an exact process RAM ceiling.

**Implemented in:** [engine.py](src/dispatch_risk/engine.py). [Engine tests](tests/test_engine.py) cover capacity, record trimming and lookup cleanup.

## 10. Allow model reload to clear history

**My decision: I reject this suggestion. Replace the model while preserving all shipment history.**

Even during low traffic, clearing history removes the readings needed by the next prediction.

Read and check the candidate model before taking the lock. Hold the lock briefly to replace the model reference. Each score uses one model and a consistent view of history. A failed reload leaves both unchanged.

**Implemented in:** `reload_model` and `score` in [engine.py](src/dispatch_risk/engine.py). Tests cover overlapping ingestion, scoring and reload calls.

## Label policy and the known contract gap

**My decision: I wait six hours for the prediction window and another 48 hours for reports. Leave examples with unknown outcomes out of training.**

The wait applies to both classes. After it passes, a matching incident gives label 1; no matching report gives label 0 under an explicit completeness assumption. Checks with 48, 72 and 96 hour waits found no later contradictions in those examples. They do not prove reporting completeness.

The builder has no observation cutoff input, so it uses the latest supplied decision time as the assumed end of observation. Training labels must be ready before validation starts, validation labels before test starts, and test labels before observation ends. Report availability is checked again at each cutoff.

**Unmet requirement:** the README requests a binary label at every checkpoint. The implementation omits checkpoints still waiting for reports and records requested and excluded counts. A single recent checkpoint can return no rows; `train([])` raises an error. This gap is not fixed. Resolving it requires an agreed representation of unknown outcomes and a confirmed observation cutoff. External `TrainingRow` callers without incident details take responsibility for label completeness; the waiting rule still applies.

## Model and input choices

**My decision: I use shared temperature features and the logistic regression family selected on validation data.**

The nine inputs cover latest temperature, age, delay, missing temperature, and the count, average, maximum, trend and time span in `(as_of - 3 hours, as_of]`. Trend fits a straight line using actual times; it needs two distinct times. Each reading has equal weight in the average. Training and prediction share the same functions. Fill missing numbers with training medians, add nine missing value flags, and use fitted scaling values for logistic regression.

Validation compared constant, logistic regression, a small tree, random forest and gradient boosting. Require better average precision and Brier than constant, then choose the simplest model within 0.002 Brier of the best qualifying model. Logistic regression met that rule. Public training fits this fixed family on earlier eligible data; final test answers do not select the model. Too little fitting data or one answer class produces a constant model. Unavailable test metrics stay empty. With no training group, the validation fallback is fixed at 0.5.

Save weights, input preparation settings, feature definitions, training details and version information in JSON. Check exported probabilities against sklearn within 1e-12. Replay comparisons require the same runtime, model, settings and delivery sequence. Different math libraries can produce tiny numeric differences. Content fingerprints detect changed files but do not authenticate their publisher.

## Work I did not implement within the timebox

- Kafka integration or coordinated saving of broker positions and engine history.
- Distributed storage or coordination between multiple processes.
- Measured response time, load targets or an exact process RAM ceiling.
- Model signing, automatic retraining or a separate probability calibration model.
- Features from door, compressor or location data, or prediction of incident severity.
- Validation on real shipment data or a production alert cutoff.
- A complete resolution of the per-checkpoint training-row contract above.
- Separate testing on Python 3.11; verification used Python 3.14.

The implemented package trains and scores offline after dependencies are installed. The UI and notebooks are optional preparation materials. Run commands are in [personal/README.md](personal/README.md).
