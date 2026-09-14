# Shipment Risk Engine

A local Python engine for six-hour refrigerated-shipment incident risk. It reconstructs what was known at each decision time, trains a model, and serves deterministic predictions with bounded history.

## Run the submission

Use Python 3.11 or newer, from the repository root:

```bash
python -m pip install -e '.[dev]'
python -m pytest
python -m dispatch_risk train --artifact outputs/final_model
python -m dispatch_risk replay --artifact outputs/final_model --max-shipments 32 --output outputs/replay
```

The sample data and portable model are included. To regenerate sample data, run `python tools/generate_dataset.py`. Training and scoring run offline after dependencies are installed. See [run instructions](personal/README.md) for fresh-stream and recovery commands, and [DECISIONS.md](DECISIONS.md) for policies and limitations.

## Repository layout

| Location | Purpose |
| --- | --- |
| `src/dispatch_risk/` | Public implementation |
| `tests/` | Submission tests |
| `tools/generate_dataset.py` | Supplied deterministic generator |
| `data/` | Source sample records |
| `outputs/final_model/` | Portable model, evaluation and verification evidence |
| `personal/` | Optional notebooks, learning notes, UI and interview preparation |

The assessed package and core tests do not depend on `personal/`. That folder can be omitted from a submission copy. [Personal preparation index](personal/README.md).

## Evaluation results

These results come from the saved [evaluation report](outputs/final_model/evaluation.json) on synthetic data: **309 held-out decision rows, including 25 positives**.

**Split rule:** order shipments by their first decision timestamp and form approximately 60% training, 20% validation, and 20% test cohorts. Shipments do not overlap between partitions, and timestamp ties stay together. Training outcomes must mature by validation start, validation outcomes by test start, and test outcomes by the observation cutoff. Maturity requires the six-hour outcome window plus a 48-hour reporting allowance. Label availability is checked at each fit cutoff; preprocessing is fitted only on the fitting partition.

For the saved run, validation starts on February 15, 2026 at 08:00 UTC; test starts on March 2 at 08:00 UTC; observation ends on March 17 at 11:00 UTC. These boundaries are derived from the supplied data, not hard-coded dates.

Constant, logistic regression, shallow tree, random forest, and gradient boosting were compared on validation data. The selection rule required better average precision and Brier score than the constant baseline, then selected the simplest model within 0.002 Brier of the best eligible model. Logistic regression was selected before test evaluation and refitted on mature development data available at test start.


| Held-out metric                                    | Logistic regression | Constant baseline |
| -------------------------------------------------- | ------------------- | ----------------- |
| Average precision (higher is better)               | 0.981277            | 0.080906          |
| Brier score (lower is better)                      | 0.003760            | 0.074380          |
| Log loss (lower is better)                         | 0.020847            | 0.281113          |
| Recall at illustrative 20% threshold               | 96%                 | 0%                |
| True positives / false negatives / false positives | 24 / 1 / 0          | 0 / 25 / 0        |


The constant baseline gives every example the incident prevalence learned from mature development rows. Average precision measures how well incidents rank above non-incidents. Brier score measures squared probability error; it assesses probability quality but does not by itself prove calibration.

Operational slices check whether performance changes across sensor sources, stale measurements, or missing trend evidence:


| Slice                             | Rows | Positives | Average precision | Brier score | Recall at 20% |
| --------------------------------- | ---- | --------- | ----------------- | ----------- | ------------- |
| Sensor central                    | 103  | 3         | 1.000000          | 0.000301    | 100%          |
| Sensor coast                      | 102  | 14        | 0.981203          | 0.009918    | 92.9%         |
| Sensor north                      | 104  | 8         | 1.000000          | 0.001147    | 100%          |
| Measurement older than 30 minutes | 256  | 22        | 0.978936          | 0.004330    | 95.5%         |
| Measurement within 30 minutes     | 53   | 3         | 1.000000          | 0.001010    | 100%          |
| Temperature trend missing         | 77   | 9         | 1.000000          | 0.002004    | 100%          |
| Temperature trend present         | 232  | 16        | 0.980978          | 0.004343    | 93.8%         |


Slices within each dimension partition the test rows; dimensions overlap. Small positive counts make slice estimates uncertain. [Notebook 13](personal/notebooks/13_final_evaluation_and_model_artifact.ipynb) also contains reliability bins and shipment-bootstrap uncertainty.

Chronological evaluation estimates performance on later shipment cohorts more credibly than a random row split. It does not establish production readiness: these are synthetic examples, reporting completeness after 48 hours is an assumption, and the latest decision time is an assumed observation boundary. The 20% threshold illustrates behavior; selecting a launch threshold requires operational costs and real-data validation.

## Requirement coverage


| Assignment requirement                                       | Implementation and evidence                                                                                                                                                                                                                                                                         |
| ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Point-in-time training rows and correction policy            | [training.py](src/dispatch_risk/training.py) and [features.py](src/dispatch_risk/features.py) use only revisions received by the decision time. Label policy and the immature-row exception are documented in [DECISIONS.md](DECISIONS.md).                                                         |
| Training, portable artifact, and required evaluation         | [model.py](src/dispatch_risk/model.py), [training.py](src/dispatch_risk/training.py), and [evaluation.json](outputs/final_model/evaluation.json). The JSON model includes feature interpretation metadata and fitted preprocessing; the installed package supplies the versioned feature functions. |
| Duplicate, late, corrected, and out-of-order input           | [engine.py](src/dispatch_risk/engine.py) preserves delivery order and deduplicates event ID plus revision within retained history.                                                                                                                                                                  |
| UTC outputs, model version, and deterministic feature digest | [contracts.py](src/dispatch_risk/contracts.py), shared features, and canonical serialization.                                                                                                                                                                                                       |
| Snapshot/restore and deterministic replay                    | Engine state capture, integrity validation, atomic file replacement, and replay/continuation checks in [test_engine.py](tests/test_engine.py). Exact byte identity applies within the same runtime and artifact.                                                                                    |
| Bounded state                                                | Shipment capacity, per-shipment record limits, bounded record size and lookup indexes; eviction and truncation are exposed in prediction reasons and counters.                                                                                                                                      |
| Concurrent scoring and safe reload                           | Engine locking, candidate validation before swap, and retention of the previous model after a failed reload.                                                                                                                                                                                        |
| Dangerous failure-mode tests                                 | [tests](tests) covers temporal correctness, repeated replay, retention, snapshot corruption, reload, and concurrency. Run `python -m pytest`.                                                                                                                                                       |
| Customer notes and timebox exclusions                        | [DECISIONS.md](DECISIONS.md) answers all ten customer notes with the safer contract and lists omitted work.                                                                                                                                                                                         |
| Follow-up interview                                          | [run instructions](personal/README.md) covers a new stream, failed-invariant investigation, and how to verify a requirement change.                                                                                                                                                                               |


**Known contract difference:** the training builder excludes immature checkpoints instead of returning a binary label for every requested decision. Unknown outcomes cannot safely be assigned zero. Requested/censored counts are recorded in metadata. [DECISIONS.md](DECISIONS.md) explains this choice; [improvement priorities](personal/WALKTHROUGH.md#10-improvement-priorities) records the need for an explicit censored-row or observation-boundary contract. Historical reconstruction is also limited by retained state, with degraded reasons after evidence is discarded.

The original assignment follows for reference.

---



# Take-Home: Point-in-Time Risk Engine

**Role:** Senior Machine Learning Software Engineer  
**Expected effort:** 7 hours maximum  
**Language:** Python 3.11+  

Do not spend time on UI, infrastructure-as-code, or presentation slides. We assess the repository, executable behavior, tests, and technical decisions.

## Scenario

You own an online risk engine for refrigerated shipments. A device stream reports temperature, door, compressor, and location events. The engine must estimate whether a shipment will suffer a temperature excursion in the next six hours.

Events are delivered at least once. They can arrive late, be corrected, or carry a bad device clock. Operations wants a prediction after every accepted event. Labels arrive later from audited incident records.

You are given a deterministic data generator and a small starter interface. Build a thin training-and-serving implementation that is correct under replay and usable under concurrent scoring and model reload.

## Input records

Telemetry is JSON Lines. Every event contains:

```json
{
  "event_id": "evt-123",
  "revision": 2,
  "shipment_id": "s-17",
  "device_time": "2026-01-12T10:03:00-05:00",
  "received_at": "2026-01-12T15:07:13Z",
  "kind": "temperature_c",
  "value": 9.4,
  "source": "sensor-v2",
  "payload": {"firmware": "4.8.1"}
}
```

Labels are also JSON Lines:

```json
{
  "incident_id": "inc-88",
  "shipment_id": "s-17",
  "incident_at": "2026-01-12T20:15:00Z",
  "label_available_at": "2026-01-14T09:00:00Z",
  "severity": 2
}
```

Important semantics:

- `(event_id, revision)` identifies a delivered record.
- A higher revision supersedes lower revisions with the same `event_id`.
- `device_time` is when the device claims the measurement occurred.
- `received_at` is when the platform could first use that revision.
- Input order is delivery order and is not guaranteed to be chronological.
- All public outputs must use UTC-aware timestamps.
- An incident is positive for an `as_of` time if it occurs in `(as_of, as_of + 6 hours]`.



## Required implementation

Implement the functions and class in `src/dispatch_risk/solution.py`. You may change other starter files while keeping the public contract stable.

### 1. Point-in-time training set

Implement:

```python
build_training_rows(events, labels, decision_times)
```

For each `(shipment_id, decision_time)`, produce features, a binary label, and metadata. A feature may use only information that would have been available to the platform at that decision time.

You must make and document a policy for corrected events whose latest revision arrives after a decision time.

### 2. Model training and artifact

Implement:

```python
train(rows, artifact_dir)
```

The artifact must be loadable in a fresh Python process and include everything required to reproduce feature interpretation and scoring.

Report at least:

- the evaluation split rule;
- PR-AUC or average precision;
- one probability-quality metric;
- performance against a constant or simple rule baseline;
- results for at least two operationally meaningful slices.

Do not optimize for a leaderboard. We care more about whether the evaluation estimates future behavior.

### 3. Online engine

Implement `RiskEngine` with the contract in `contracts.py`.

It must:

- accept duplicate, late, out-of-order, and corrected events;
- make repeated delivery of the same record idempotent;
- score a shipment as of an explicit UTC timestamp;
- return the model version and a deterministic feature digest;
- snapshot and restore its state;
- enforce `max_shipments` without unbounded auxiliary structures;
- reload a valid model while scoring requests are active;
- keep serving the previous model if a reload fails.

Two identical replays from an empty state must produce byte-identical serialized predictions and snapshots.

### 4. Tests

Add tests for the failure modes you think are most dangerous. We will run public and private tests, including generated streams not present in this repository.

### 5. Decision record

Complete `DECISIONS.md`. Keep it concise and concrete. Explicitly state anything you chose not to implement within the timebox.

## Customer-provided implementation notes

The following notes came from different customer engineers. Treat them as requirements unless you believe one is unsafe or technically invalid. If you reject or reinterpret one, do so explicitly in `DECISIONS.md` and implement the safer contract.

1. “Use a random 80/20 row split; we need every carrier represented in both sets.”
2. “Always apply the newest revision of an event, even when replaying an old decision.”
3. “Sort everything by device time before replay so the model sees the real sequence.”
4. “Deduplicate on `shipment_id`; downstream only needs one current prediction.”
5. “Kafka is exactly-once, so snapshot consistency does not need application logic.”
6. “If the model cannot load, return probability `0.0` to preserve the API SLO.”
7. “Use the full incident table during feature generation; it is the authoritative source.”
8. “AUC above 0.90 is sufficient for launch.”
9. “Keep every shipment in memory because historical corrections can arrive at any time.”
10. “Model reload may briefly clear in-memory state; deploys occur during low traffic.”

No clarification is available during the exercise. Make reasonable assumptions and record them.

## Constraints

- The private evaluator has no network access.
- Tests may call the engine from several threads.
- The evaluator may set `max_shipments=32` and replay more than 10,000 events.
- Do not key logic to sample IDs, fixed row counts, or dates in the generated data.
- Avoid hosted APIs and external model services.
- Dependencies must be declared in `pyproject.toml`.



## Run instructions

Generate the sample data:

```bash
python tools/generate_dataset.py
```

Install and run:

```bash
python -m pip install -e '.[dev]'
pytest
```

Your submission should include generated data only if its total compressed size is below 5 MB.

## Follow-up

In a 60-minute technical interview, you will:

- run your solution against a new event stream;
- investigate one failed invariant;
- modify one requirement;
- defend the statistical validity of your evaluation;
- make a small code change while preserving replay determinism.
