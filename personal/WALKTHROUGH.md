# Interview walkthrough

Use this to rehearse, not as a script to read word for word. Explain one decision, show the relevant code, then pause. The UI is optional supporting evidence; the engine is the submission.

## 1. Opening: the problem in 30 seconds

> “This system estimates the chance of a shipment having a temperature incident in the next six hours. The difficult part is that readings can arrive late, repeat, or be corrected. I made sure each prediction uses only what was available at its decision time, then evaluated the model on later shipments.”

Give one example: a 9 AM reading says 8°C and arrives at 9:05. A correction to 5°C arrives at noon. Reconstructing the 11 AM prediction must still use 8°C, provided that history is retained.

Do not begin with notebook history, UI buttons, or model scores. Establish the problem first.

## 2. Where development started

We began with the supplied interface, event records, decision checkpoints, incident reports and generator. We explored in notebooks before transferring the behavior into the Python package.

| Stage | What we learned or decided | Why it came first |
| --- | --- | --- |
| Notebooks 1–2 | Record shapes, duplicates, revisions | Understand which messages represent the same event |
| 3–4 | Two clocks, measurement age, delay, three-hour features | Make inputs valid at the decision time |
| 5 | Flatten JSON into tables, preserve raw order | Make inspection easier without silently cleaning away hazards |
| 6–7 | Late reports and label maturity | An absent report does not establish a negative |
| 8–9 | Training examples and constant baseline | Establish a trustworthy target and reference performance |
| 10 | Logistic regression learning on teaching examples | Understand weights and intercept before comparisons |
| 11–12 | Chronological split, preprocessing and candidate comparison | Choose on validation, without opening test results |
| 13–14 | Final evaluation, artifact export, fresh-process checks | Verify the fixed choice and serving interpretation |
| Python implementation | Shared features, bounded state, recovery, concurrency | Convert the experiment into the required engine |
| Optional preparation | UI, presentation, API workbench | Help explain and exercise the completed implementation |

The learning history is not the interview order. Use the code sequence below when presenting.

## 3. Follow one message through the code

For each stop, explain **purpose → inputs → decision → output → evidence**.

### Stop A: the public contract

Open [solution.py](../src/dispatch_risk/solution.py), then [contracts.py](../src/dispatch_risk/contracts.py).

`solution.py` exposes `RiskEngine`, `build_training_rows`, and `train`. It delegates to focused modules so callers retain the requested interface.

The three containers are:

- `TelemetryEvent`: a delivered event, including event ID, revision, shipment, device time and receipt time.
- `TrainingRow`: features at a checkpoint, binary outcome and audit metadata.
- `Prediction`: probability, decision time, model version, input digest and degraded reasons.

Say: “The two clocks are separate because measurement time and availability time answer different questions.”

`Prediction.to_wire()` uses sorted JSON keys, fixed separators and rejects non-finite numbers. Stable serialization is necessary for byte-for-byte replay comparisons. Frozen dataclasses prevent field reassignment, but nested mappings are not deeply immutable; ingest normalizes/copies its input.

### Stop B: receive a message

Open [engine.py](../src/dispatch_risk/engine.py), `RiskEngine.__init__` and `ingest`.

Startup loads a valid model, initializes an ordered shipment map and event-owner index, and creates a lock. An invalid initial artifact fails startup; no unsupported zero-risk fallback is invented.

`ingest` normalizes the record, checks its identity, and updates retained state under the lock. Exact event-ID/revision duplicates return false. Conflicting duplicates or event IDs moving between shipments raise an error. Lower revisions can still be useful for historical scoring.

Say: “A retry must not become another temperature measurement. I deduplicate by event plus revision, not by shipment.”

Capacity removes the least recently updated shipment and its index entries. Scores and duplicates do not refresh recency. Each shipment also has a record cap, so one busy shipment cannot grow forever. Trimming removes whole event histories and keeps a discard watermark. These are bounded structures, not a measured exact RAM limit.

Evidence: [test_engine.py](../tests/test_engine.py). Explain the memory tradeoff: forgotten history cannot always be reconstructed, and duplicate identity does not persist across eviction.

### Stop C: choose what was known

Open [features.py](../src/dispatch_risk/features.py), `known_revisions`.

First exclude revisions received after the checkpoint. Then choose the highest eligible revision per event. Selecting the newest revision first would let a future correction overwrite an earlier prediction.

Device time determines measurement age and window membership only after availability is established. Measurements claiming a time after their own receipt are excluded conservatively. An invalid correction does not bring its superseded reading back.

Say: “Receipt time decides whether we could know it; device time tells us when it was measured.”

### Stop D: turn readings into features

Continue to `first_features`, `window_features`, and `extract_features`.

Nine features describe latest temperature, age, arrival delay, missing temperature, and the three-hour count, mean, maximum, trend and span. The same functions serve offline and online paths.

The window is `(as_of - 3 hours, as_of]`: the left boundary is excluded and the decision time is included. This is an explicit boundary convention, not a claim that sliding windows never overlap. Latest temperature can lie outside the summary window.

Trend is a least-squares slope using actual elapsed hours. It needs two distinct times. Missing trend means unknown; zero means a measured flat slope. The mean weights readings equally, not elapsed time. Three hours is a feature assumption, not a proven optimum.

Say: “Shared feature code prevents training and serving from interpreting the same reading differently.”

### Stop E: score and return the result

Open `RiskEngine.score`, then [model.py](../src/dispatch_risk/model.py), `Model.predict`.

Scoring holds a consistent state/model view, extracts features, computes their deterministic digest, and applies fitted preprocessing and the loaded coefficients. The output includes reasons when evidence is missing, stale or lost. Unknown shipments receive the learned prior with degraded reasons.

The exported JSON contains feature version/order, preprocessing values and model parameters. Serving does not need to execute a pickle. Version hashes detect accidental artifact changes; they are not cryptographic proof of a trusted publisher.

Say: “I return the probability plus enough identity and quality information to investigate how it was produced.”

## 4. Explain how the model was trained

Open [training.py](../src/dispatch_risk/training.py).

### Build examples

`build_training_rows` reconstructs features at each decision time. A positive incident falls inside `(decision, decision + 6 hours]`. Reports must be available by the relevant label cutoff. Both classes wait the six-hour horizon plus a 48-hour reporting grace.

No matching incident after maturity is an **assumed negative**. The latest supplied decision time is an assumed observation boundary because the public interface has no explicit coverage argument.

Disclose the contract difference: immature decisions are excluded instead of returning a binary-labeled row for every requested decision. This avoids pretending unknown outcomes are zero, but does not exactly meet that wording in the assignment. Do not claim complete compliance without qualification.

### Split and preprocess

Shipments are ordered by first decision timestamp into approximately 60/20/20 cohorts. No shipment overlaps; ties stay together. Labels mature by the appropriate validation, test or observation boundary. Imputation and scaling are fitted only on fitting data.

Say: “A random row split could let the same shipment appear on both sides and would not estimate later-shipment behavior as directly.”

### Select, then test

Validation compared constant, logistic regression, shallow tree, random forest and gradient boosting. Require better validation AP and Brier than constant, then choose the simplest within 0.002 Brier of the best eligible candidate. Logistic regression won this declared rule. The public training function fits that fixed family; it does not repeat candidate selection on test data.

The final model refits mature development data before the test period. The test result is evaluated after selection, not used to choose a winner.

| Saved test evidence | Model | Constant |
| --- | ---: | ---: |
| Average precision | 0.981277 | 0.080906 |
| Brier score | 0.003760 | 0.074380 |
| At 20%: caught / missed / false alarms | 24 / 1 / 0 | 0 / 25 / 0 |

There are 309 test checkpoints and 25 positives. AP measures ranking; Brier measures squared probability error. Neither a high score nor Brier alone proves calibration or launch readiness. Operational slices cover sensor source, freshness and missing trend. Small positive counts limit conclusions. Open [evaluation.json](../outputs/final_model/evaluation.json) for exact results, and notebook 13 for reliability bins and shipment-bootstrap uncertainty.

Say: “The results are strong on synthetic data. The threshold is illustrative, and real-world performance is untested.”

## 5. Explain recovery and concurrent use

Return to `snapshot`, `restore`, and `reload_model` in the engine.

- Snapshot captures consistent retained state, order, counters and model identity under the lock. Atomic file replacement avoids partially replacing the saved file.
- Restore validates the snapshot before returning an engine and requires the corresponding model version.
- Reload validates and smoke-tests a candidate before swapping its reference under the lock. Failure keeps the current model and shipment data.
- A single lock favors simple correctness over maximum parallel throughput. Do not claim latency or throughput targets were benchmarked.

Say: “Updating a model should change the model, not erase shipment history.”

Exact replay applies to the same runtime, artifact, settings and delivery sequence. Cross-platform floating-point identity is not guaranteed. Broker-offset transactions and distributed state are outside scope.

## 6. Map the README's eight engine rules to evidence

| Required behavior | Show |
| --- | --- |
| Duplicate, late, unordered, corrected events | `ingest` and `known_revisions` |
| Idempotent redelivery | Exact event/revision comparison and duplicate tests |
| Explicit UTC scoring | Timestamp normalization and `score(as_of)` |
| Model version and deterministic digest | `score`, artifact identity, `Prediction.to_wire` |
| Snapshot/restore | State capture, validation, continuation tests |
| Bounded memory and auxiliary structures | Shipment map, record cap, owner-index cleanup |
| Reload while scoring | Validation outside lock, atomic reference swap inside lock |
| Failed reload preserves service | Rejected candidate leaves current model intact |

The final replay requirement is tested by feeding identical deliveries into empty engines and comparing prediction and snapshot bytes.

## 7. Rehearse the five follow-up tasks

### A new event stream

Use the browser's New stream page or the commands in [RUNBOOK.md](RUNBOOK.md). Set a new seed; record it. Inspect event count, capacity checks, prediction hashes and snapshot hashes. Generated data and replay evidence are saved under `personal/outputs/interview/`.

A different seed exercises robustness within the same generator. It does not establish accuracy on independently collected data. If the panel supplies its own directory, pass that directory to the CLI instead of replacing it with generated data.

### Investigate one failed invariant

1. State the expected property and the observed failure.
2. Preserve input, seed, configuration, model and code version.
3. Find the first differing prediction or failing delivery; reduce to the smallest sequence that still fails.
4. Compare receipt times, revisions, retained history, model version and feature digest.
5. Add a failing regression test before fixing the responsible logic.
6. Run that test, then the relevant suite and replay comparison.

A useful rehearsal case is a correction received at noon affecting an 11 AM score. Investigate revision selection before blaming the model. Do not fabricate a failed invariant and present it as a discovered production bug.

### Modify one requirement

Clarify the observable new behavior first. A capacity change is configurable: rerun the same seed with a new shipment limit and inspect retained state. Changing the feature lookback is different: update feature interpretation/version, retrain, export a compatible model, and update boundary tests. Do not silently mix old coefficients with a new feature definition.

### Defend evaluation validity

Expect: Why chronological? Why group shipments? When were labels known? Why 48 hours? Was test data used for selection? What does the baseline establish? What do small slices hide?

Answer from the split and label rules above. Mention that 48/72/96-hour experiments found no observed contradictions, but that cannot prove reporting completeness. Real deployment needs audited observation coverage, real data, and a threshold chosen from operational costs.

### Make a small code change

Open only the responsible function. State the expected change, write the regression test, edit the function, run tests, and replay deterministically. A fresh pytest process loads changed code; restart the API before replaying engine edits. API fingerprints read source from disk, so do not treat them as proof that an old server has reloaded edited modules.

Example rehearsal: tighten an input validation rule. Discuss compatibility, add accepted/rejected cases, implement the rule, and verify unchanged valid streams. Do not make arbitrary code changes merely for show.

## 8. Questions and concise answers

| Question | Answer |
| --- | --- |
| Why not always use the correction? | It was not available to the earlier prediction. |
| Why keep two clocks? | One measures event time; one establishes knowledge time. |
| Why is missing trend not zero? | Unknown slope is different from observed flat readings. |
| Why not train on every decision? | Recent outcomes may be unknown; our exclusion is a documented contract difference. |
| Why logistic regression? | It met the predeclared validation rule and is straightforward to inspect and export. |
| Why memory limits? | Explicit README requirement; unlimited shipment or auxiliary history would violate it. |
| What happens after eviction? | Lost history limits reconstruction and duplicate identity; the prediction discloses degraded coverage. |
| Why reject customer notes? | Their suggested mechanisms conflict with temporal correctness, bounded memory or safe serving; DECISIONS records each alternative. |
| What would you improve first? | Explicit observation coverage and censored-row contract, then realistic load and real-data validation. |

## 9. Suggested presentation order

Spend about one minute on the problem and two-clock example, then five minutes following one message through contract, ingest, features and score. Use another three minutes for labels, split, baseline and model choice. Finish with recovery, limits and tests. Adjust to the interviewer's questions; the 60-minute follow-up includes live work, not a 60-minute speech.

Optional demo order: Start here for the correction example; Model results for evaluation; System checks for reliability; New stream for live input/configuration changes. Open API docs only when demonstrating the backend request. Every button should support a claim already explained.

Close with: “The main guarantees are point-in-time inputs, reproducible scoring and explicit limits when information is missing. The strongest remaining uncertainty is real-world label coverage and predictive performance.”
