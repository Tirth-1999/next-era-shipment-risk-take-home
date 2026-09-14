# Improvements worth prioritizing

The implementation and demo pass the current 27 tests. That supports the tested behavior, but does not prove compliance with every private test or readiness for real operations. This review identifies changes to consider without changing the agreed policies or the trained model.

## 1. Resolve the training-row contract before submission

`build_training_rows` omits checkpoints whose six-hour outcome window and 48-hour reporting allowance have not finished. The README asks for features, a binary label and metadata at every requested checkpoint. This is a real contract difference, already disclosed in DECISIONS.md. A single requested decision produces no rows under the current observation-cutoff rule.

The reason is valid: an unknown outcome cannot honestly become label zero. The interface needs an agreed way to represent it. If the interface can change, return an eligibility status with every requested checkpoint and keep censored rows out of fitting. If the interface must stay fixed, defend the omission explicitly and retain counts. Do not quietly label recent rows negative just to match a row count.

The builder also infers its observation cutoff from the latest decision time. A future revision should accept a separately supplied observation boundary or certified audit coverage. The prediction schedule is not evidence that all incident reports are complete.

Evidence: README required implementation section, `src/dispatch_risk/training.py`, `tests/test_engine.py::test_label_boundary_availability_and_maturity`, DECISIONS.md.

## 2. Measure resource use and strengthen boundary checks

Shipment, record and event-size limits bound retained structures. They do not impose an exact process-memory ceiling. Scoring runs feature extraction under the engine lock, so long histories can delay other callers. Measure actual memory, scoring latency and snapshot pauses while ingestion and reload are active. Choose service targets before deciding whether finer locking or cached features are worthwhile.

Restore currently reads an entire snapshot before validating its structural bounds. Add a byte-size limit before parsing if snapshots may come from untrusted or oversized sources. Exercise extreme finite numeric values and malformed artifacts as part of that hardening. Test the declared minimum Python 3.11 environment separately from the verified Python 3.14 environment.

Evidence: `src/dispatch_risk/engine.py`, `src/dispatch_risk/features.py`, `pyproject.toml`, outputs/final_model/verification.json.

## 3. Establish evidence for real use

The held-out result has 25 incidents from synthetic data. The 48-hour allowance assumes mature outcome records are complete. Before operational use, confirm reporting coverage, evaluate several later time periods with real shipments, and check probability calibration within useful operational groups.

Select an alert threshold using the costs of missed incidents, false alarms and available response capacity. The demonstration threshold of 20% does not establish that decision. If a calibration model becomes necessary, fit it on a separate calibration or validation partition rather than the existing final test data.

Only then assess whether extra sensor features or a more complex model improve performance. The current evidence does not justify adding model complexity solely because it is available.

Evidence: outputs/final_model/evaluation.json, notebooks 11–13, DECISIONS.md.

## Interview priority

The first item deserves attention before submission. The resource and real-data work belongs in the next-steps discussion unless the panel asks for a specific change. The presentation records these limits rather than claiming they have been fixed.
