# My interview walkthrough

I use this guide to rehearse my explanation. I explain one decision, show the relevant code and pause for questions. I use the demo to support the engine walkthrough.

## 1. Opening: the problem in 30 seconds

> “This system estimates the chance of a shipment having a temperature incident in the next six hours. The difficult part is that readings can arrive late, repeat, or be corrected. I made sure each prediction uses only what was available at its decision time, then evaluated the model on later shipments.”

I give one example: a 9 AM reading says 8°C and arrives at 9:05. A correction to 5°C arrives at noon. Reconstructing the 11 AM prediction must still use 8°C, provided that history is retained.

I start with the shipment problem before showing code or scores.

## 2. Where development started

I began with the supplied interface, event records, decision checkpoints, incident reports and generator. I explored in notebooks before transferring the behavior into the Python package.

| Stage | What I learned or decided | Why it came first |
| --- | --- | --- |
| Notebooks 1–2 | Record shapes, duplicates, revisions | Understand which messages represent the same event |
| 3–4 | Two clocks, measurement age, delay, three-hour features | Make inputs valid at the decision time |
| 5 | Flatten JSON into tables, preserve raw order | Make inspection easier without silently cleaning away hazards |
| 6–7 | Late reports and waiting long enough for incident reports | An absent report does not establish a negative |
| 8–9 | Training examples and constant comparison model | Establish a trustworthy target and reference performance |
| 10 | Logistic regression learning on teaching examples | Understand weights and intercept before comparisons |
| 11–12 | Split by time, preparing model inputs and candidate comparison | Choose on validation, without opening test results |
| 13–14 | Final evaluation, artifact export, separate process checks | Verify the fixed choice and how live predictions use the saved model |
| Python implementation | Shared features, limited stored history, recovery, overlapping calls | Convert the experiment into the required engine |
| Optional preparation | UI, presentation, API workbench | Help explain and exercise the completed implementation |

For the interview, I follow the code sequence below.

## 3. Follow one message through the code

When a code name uses a technical term, explain it like this:

| Code term | What to say aloud |
| --- | --- |
| Feature | A value the model uses, such as temperature or reading age |
| Revision | A newer version of the same message |
| Digest or hash | A fingerprint that changes when the data changes |
| Snapshot | A saved copy of the engine's history and settings |
| Eviction | Removing old shipment history to stay within the memory limit |
| Invariant | A rule that must keep holding, such as duplicates having no extra effect |
| Calibration | Whether predicted risks match how often incidents actually happen |


At each stop, I explain what the function does, what I pass in, why the rule exists, what comes back, and how I tested it.

### Stop A: the public contract

I open [solution.py](../src/dispatch_risk/solution.py), then [contracts.py](../src/dispatch_risk/contracts.py).

`solution.py` gives callers the three required names: `RiskEngine`, `build_training_rows`, and `train`. Their code lives in separate files so each file has one clear job.

The three containers are:

- `TelemetryEvent`: a delivered event, including event ID, revision, shipment, device time and receipt time.
- `TrainingRow`: inputs at a checkpoint, a 0 or 1 answer, and details of how the example was built.
- `Prediction`: probability, decision time, model version, input fingerprint and reasons why information is missing or old.

My answer: “The two clocks are separate because measurement time and availability time answer different questions.”

`Prediction.to_wire()` uses sorted JSON keys, fixed separators and rejects infinity and NaN. This fixed format lets us compare saved predictions exactly. The data classes stop callers from assigning a new value to a field. A dictionary inside a field can still change, so ingest checks and copies incoming data.

### Stop B: receive a message

I open [engine.py](../src/dispatch_risk/engine.py), `RiskEngine.__init__` and `ingest`.

Startup loads a valid model, starts an ordered list of shipment histories and lookup of which shipment owns each event, and creates a lock. An invalid initial artifact fails startup; no unsupported zero-risk fallback is invented.

`ingest` checks and copies the record, checks its identity, and updates stored history under the lock. Messages with the same event ID, revision and contents return false. Conflicting duplicates or event IDs moving between shipments raise an error. Lower revisions can still be useful for historical scoring.

My answer: “A retry must not become another temperature measurement. I deduplicate by event plus revision, not by shipment.”

Capacity removes the least recently updated shipment and its index entries. Scores and duplicates do not change the last updated order. Each shipment also has a record cap, so one busy shipment cannot grow forever. Trimming removes whole event histories and keeps a latest receipt time removed from history. These limits control stored data. I have not measured an exact RAM ceiling.

Evidence: [test_engine.py](../tests/test_engine.py). Explain the memory tradeoff: forgotten history cannot always be reconstructed, and duplicate identity does not persist across removal of shipment history.

### Stop C: choose what was known

I open [features.py](../src/dispatch_risk/features.py), `known_revisions`.

First exclude revisions received after the checkpoint. Then choose the highest eligible revision per event. Selecting the newest revision first would let a future correction overwrite an earlier prediction.

Device time determines measurement age and window membership only after availability is established. Measurements claiming a time after their own receipt are excluded conservatively. An invalid correction does not bring its replaced reading back.

My answer: “Receipt time decides whether I could know it; device time tells us when it was measured.”

### Stop D: turn readings into features

I continue to `first_features`, `window_features`, and `extract_features`.

Nine features describe latest temperature, age, arrival delay, missing temperature, and the three-hour count, mean, maximum, trend and span. The same functions serve training and live prediction paths.

The window is `(as_of - 3 hours, as_of]`: the left boundary is excluded and the decision time is included. This is an explicit boundary convention, not a claim that sliding windows never overlap. Latest temperature can lie outside the summary window.

Trend is a slope of the best fitting straight line using actual elapsed hours. It needs two distinct times. Missing trend means unknown; zero means a measured flat slope. The mean weights readings equally, not elapsed time. Three hours is a feature assumption, not a proven optimum.

My answer: “Shared feature code prevents training and serving from interpreting the same reading differently.”

### Stop E: score and return the result

I open `RiskEngine.score`, then [model.py](../src/dispatch_risk/model.py), `Model.predict`.

Scoring protects the stored readings while it calculates the inputs and their fingerprint. It then fills missing values, scales the inputs and applies the saved model weights. The output includes reasons when evidence is missing, stale or lost. Shipments with no stored history receive the incident rate learned during training with reasons why information is missing or old.

The exported JSON contains feature version/order, saved values for filling and scaling inputs and model parameters. Serving does not need to execute a pickle. Version hashes detect accidental artifact changes; they are not cryptographic proof of a trusted publisher.

My answer: “I return the probability plus enough identity and quality information to investigate how it was produced.”

## 4. Explain how the model was trained

I open [training.py](../src/dispatch_risk/training.py).

### Build examples

`build_training_rows` reconstructs features at each decision time. A positive incident falls inside `(decision, decision + 6 hours]`. Reports must be available by the relevant label cutoff. Both classes wait the six hour horizon plus a 48 hour reporting grace.

After the reporting wait, no matching incident gives an **assumed negative**. The latest supplied decision time is an assumed end of observation because the public interface has no explicit coverage argument.

I disclose the contract difference: decisions still waiting for reports are excluded instead of returning a row with a 0 or 1 answer for every requested decision. This avoids pretending unknown outcomes are zero, but does not exactly meet that wording in the assignment. I will not claim complete compliance without qualification.

### Split and preprocess

Shipments are ordered by first decision timestamp into approximately 60/20/20 groups of shipments. Each shipment stays in one group. Shipments with the same first decision time stay together. The reporting wait must finish before the cutoff for each group. Missing value replacements and scaling settings are learned only from the fitting data.

My answer: “A random row split could let the same shipment appear on both sides and would not estimate later shipment behavior as directly.”

### Select, then test

Validation compared constant, logistic regression, shallow tree, random forest and gradient boosting. Require better validation AP and Brier than constant, then choose the simplest within 0.002 Brier of the best eligible candidate. Logistic regression won this declared rule. The public training function fits that fixed family; it does not repeat candidate selection on test data.

The final model is fitted again on earlier data whose reporting wait has passed before the test period. The test result is evaluated after selection, not used to choose a winner.

| Saved test evidence | Model | Constant |
| --- | ---: | ---: |
| Average precision | 0.981277 | 0.080906 |
| Brier score | 0.003760 | 0.074380 |
| At 20%: caught / missed / false alarms | 24 / 1 / 0 | 0 / 25 / 0 |

There are 309 test checkpoints and 25 positives. AP measures ranking; Brier measures squared probability error. Neither a high score nor Brier alone proves calibration or launch readiness. Results for useful groups of shipments cover sensor source, freshness and missing trend. Small positive counts limit conclusions. Open [evaluation.json](../outputs/final_model/evaluation.json) for exact results, and notebook 13 for groups comparing predicted risk with the observed incident rate and uncertainty estimated by repeatedly resampling whole shipments.

My answer: “The results are strong on synthetic data. The threshold is illustrative, and real-world performance is untested.”

## 5. Explain recovery and concurrent use

I return to `snapshot`, `restore`, and `reload_model` in the engine.

- Snapshot captures consistent stored history, order, counters and model identity under the lock. The finished temporary file replaces the old saved file.
- Restore validates the snapshot before returning an engine and requires the corresponding model version.
- Reload validates and runs a few basic checks on a candidate before swapping its reference under the lock. Failure keeps the current model and shipment data.
- A single lock makes the rules easier to enforce. Calls may wait for each other. I have not measured response time or requests per second under load.

My answer: “Updating a model should change the model, not erase shipment history.”

Exact replay applies to the same runtime, artifact, settings and delivery sequence. Different computers or math libraries may produce tiny numeric differences. I have not added distributed storage or saved broker positions together with engine history.

## 6. Map the README's eight engine rules to evidence

| Required behavior | Show |
| --- | --- |
| Duplicate, late, unordered, corrected events | `ingest` and `known_revisions` |
| Repeated delivery has no extra effect | Exact event/revision comparison and duplicate tests |
| Explicit UTC scoring | Timestamp normalization and `score(as_of)` |
| Model version and repeatable fingerprint | `score`, model fingerprint, `Prediction.to_wire` |
| Snapshot/restore | State capture, validation, continuation tests |
| Bounded memory and supporting lookup tables | Shipment map, record cap, cleaning the event ID lookup |
| Reload while scoring | Validation outside lock, switching models inside the lock |
| Failed reload preserves service | Rejected candidate leaves current model intact |

The final replay requirement is tested by feeding identical deliveries into empty engines and comparing prediction and snapshot bytes.

## 7. CLI rehearsal for the five follow-up tasks

The README names five tasks. The exact failing input and requested change are unknown. The exercises below are preparation examples. Ask the interviewer for the expected behavior before editing code.

### Before the interview: prepare the terminal

I open a terminal at the repository root. Run these commands in the same terminal session:

```bash
pwd
git status --short
git rev-parse --short HEAD
export PYTHONPATH="$PWD/src:$PWD"
export PYTHONDONTWRITEBYTECODE=1
.venv/bin/python -c 'import sys, dispatch_risk; print(sys.executable); print(dispatch_risk.__file__)'
.venv/bin/python -m dispatch_risk --help
.venv/bin/python -m pytest tests
rehearsal_dir=$(mktemp -d /tmp/shipment-rehearsal.XXXXXX)
export REHEARSAL_DIR="$rehearsal_dir"
printf '%s\n' "$REHEARSAL_DIR"
```

The printed Python path should end in this repository's `.venv/bin/python`; the package should resolve inside this repository's `src/`. If dependencies are missing, run `uv sync --extra dev --extra notebook --extra demo`. Keep the printed temporary directory path; it contains the rehearsal evidence. If I open a new terminal, I restore both environment variables and that directory path.

I keep my working tree clean before the interview. For an actual requested edit, create a branch with `git switch -c codex/interview-rehearsal` (or choose a fresh name if it exists). Do not reset or overwrite unrelated work.

The CLI has two commands: `train` and `replay`. There is no CLI `score`, `restore`, `reload`, or `evaluate` subcommand. Use the Python snippets below or the named tests for those behaviors.

### Task 1: run against a new event stream

**Question I may be asked:** “Here is a new dataset. Show me your engine processing it.”

My answer: “I'll load the saved model, preserve delivery order, and save the predictions and final state. Then I'll repeat the run to check the outputs match.”

For practice, generate another dataset:

```bash
.venv/bin/python tools/generate_dataset.py --seed 1927 --shipments 80 --output "$REHEARSAL_DIR/input"
.venv/bin/python -m dispatch_risk replay --data "$REHEARSAL_DIR/input" --artifact outputs/final_model --max-shipments 32 --output "$REHEARSAL_DIR/replay-a"
.venv/bin/python -m dispatch_risk replay --data "$REHEARSAL_DIR/input" --artifact outputs/final_model --max-shipments 32 --output "$REHEARSAL_DIR/replay-b"
cmp "$REHEARSAL_DIR/replay-a/predictions.jsonl" "$REHEARSAL_DIR/replay-b/predictions.jsonl" && echo "Prediction bytes match"
cmp "$REHEARSAL_DIR/replay-a/snapshot.json" "$REHEARSAL_DIR/replay-b/snapshot.json" && echo "Snapshot bytes match"
head -n 1 "$REHEARSAL_DIR/replay-a/predictions.jsonl" | .venv/bin/python -m json.tool
wc -l "$REHEARSAL_DIR/input/events.jsonl" "$REHEARSAL_DIR/replay-a/predictions.jsonl"
```

`cmp` returns zero when files match. A difference returns nonzero; do not continue claiming success. The prediction count can be smaller because exact duplicate deliveries are rejected while their identities remain retained. Removal of shipment history can remove that duplicate knowledge.

If the interviewer supplies a folder, substitute its quoted path for `--data`; do not generate replacement inputs. Replay needs `events.jsonl`. Training additionally needs `labels.jsonl` and `decision_times.jsonl`. Check the schema against the README. Preserve malformed input and report validation errors; do not silently remove troublesome rows.

The replay CLI scores after each accepted delivery at that event's receipt timestamp. It does not score the separate decision-times file. The training builder uses those decision checkpoints.

**Verified practice result:** seed 1927 with 80 shipments produced 1,469 deliveries, 1,309 accepted predictions, 32 retained shipments and 48 shipments removed from memory at capacity 32. Both comparisons matched. Different inputs or configurations can change these counts.

**Completion:** both outputs saved, repeat bytes equal, counts explained. This establishes repeatability for this sequence. It does not establish predictive accuracy on new real data.

### Task 2: investigate one failed invariant

**Question I may be asked:** “A late correction changed an earlier prediction. Find out why.”

An invariant is a property that must remain true, such as an exact duplicate having no additional effect. Start by identifying the exact failing property and the first input that breaks it.

1. I preserve the input directory, artifact, settings and commit ID. Save the failing output before rerunning anything into that directory.
2. I run the smallest relevant test with a useful traceback:

```bash
.venv/bin/python -m pytest tests/test_engine.py::test_late_correction_does_not_change_past -vv --tb=short
.venv/bin/python -m pytest tests/test_engine.py::test_duplicate_and_conflict_are_transactional -vv --tb=short
rg -n 'def ingest|def score|def known_revisions' src/dispatch_risk
```

3. For two differing replay files, locate their first differing prediction:

```bash
.venv/bin/python - <<'PY'
import json, os
from itertools import zip_longest
from pathlib import Path
root = Path(os.environ['REHEARSAL_DIR'])
with (root/'replay-a/predictions.jsonl').open() as a, (root/'replay-b/predictions.jsonl').open() as b:
    for row, (left, right) in enumerate(zip_longest(a, b), 1):
        if left != right:
            print('First differing prediction row:', row)
            print('A:', json.loads(left) if left else 'missing')
            print('B:', json.loads(right) if right else 'missing')
            break
    else:
        print('No prediction differences')
PY
```

Prediction row numbers are not raw delivery row numbers because rejected duplicates produce no prediction. Trace the shipment and decision time back to the deliveries; add temporary diagnostic prints of delivery index and event ID if necessary. Remove diagnostic prints after the fix.

4. I inspect `as_of`, `model_version`, `feature_digest`, probability and reasons why information is missing or old. Different model versions mean I am comparing different models. A different digest points toward selected readings or feature calculation. An unchanged digest with a different probability points toward model loading or scoring. Retention differences can also explain changed reasons.
5. I reduce the input to one shipment and the original message, correction and checkpoint. Confirm the small sequence still reproduces the failure before changing the implementation.
6. I add that sequence as a regression test in `tests/test_engine.py`. Use the existing `event()` helper and `engine` fixture when adding to that file. For historical correction behavior, capture `score(...).to_wire()` before ingesting the later revision, then assert equality at the old timestamp afterward. Also assert that the later timestamp uses a changed feature fingerprint. A constant test model may produce equal probabilities despite changed features, so checking probability alone can miss a bug.
7. I inspect `known_revisions` in `features.py`: filter by receipt time before selecting the highest eligible revision. Preserve legitimate older revisions in `ingest`. Check whether removal of shipment history makes the requested historical reconstruction impossible.
8. I run the new test, the full core suite, and both replay comparisons from Task 1 using fresh output folders.

**Other failure routes:** duplicate effects → `ingest`; memory growth → removal of shipment history/owner cleanup and record trimming; restore differences → snapshot order and model version; failed reload interrupting service → candidate validation and reference swap.

My answer: “The failure starts at this delivery. This smaller test reproduces it. I'll change the responsible function and verify both the regression and full replay.”

If all checks pass, say that no failure was reproduced with the available input. Ask for the failing sequence. I will not invent a discovered defect.

### Task 3: modify one requirement

**Question I may be asked:** “Now keep only eight shipments in memory.”

I clarify whether the limit refers to retained shipment histories or exact RAM consumption. The current parameter bounds histories. It does not promise a process-RSS ceiling.

```bash
.venv/bin/python -m dispatch_risk replay --data "$REHEARSAL_DIR/input" --artifact outputs/final_model --max-shipments 8 --output "$REHEARSAL_DIR/capacity-8-a"
.venv/bin/python -m dispatch_risk replay --data "$REHEARSAL_DIR/input" --artifact outputs/final_model --max-shipments 8 --output "$REHEARSAL_DIR/capacity-8-b"
cmp "$REHEARSAL_DIR/capacity-8-a/predictions.jsonl" "$REHEARSAL_DIR/capacity-8-b/predictions.jsonl"
cmp "$REHEARSAL_DIR/capacity-8-a/snapshot.json" "$REHEARSAL_DIR/capacity-8-b/snapshot.json"
.venv/bin/python -m pytest tests/test_engine.py -k 'capacity or hot_shipment or revision_flood' -vv
```

I read `shipments`, `max_shipments`, `retained_records`, `event_id_index`, `evictions` and `trimmed`. The record bound is retained shipments × 128; the event ID lookup must not exceed the retained record count. A final snapshot checks the end state; to claim a bound throughout ingestion, check `stats()` after every delivery:

```bash
.venv/bin/python - <<'PY'
import json, os
from pathlib import Path
from dispatch_risk import RiskEngine
from dispatch_risk.features import event_from_mapping
engine = RiskEngine(Path('outputs/final_model'), max_shipments=8)
with (Path(os.environ['REHEARSAL_DIR'])/'input/events.jsonl').open() as handle:
    for line_number, line in enumerate(handle, 1):
        if not line.strip():
            continue
        engine.ingest(event_from_mapping(json.loads(line)))
        state = engine.stats()
        assert state['shipments'] <= 8, (line_number, state)
        assert state['retained_records'] <= 8 * state['max_records_per_shipment'], (line_number, state)
        assert state['event_id_index'] <= state['retained_records'], (line_number, state)
print('Capacity and index bounds passed after every delivery')
PY
```

I compare repeated runs at capacity 8 with each other. Predictions at capacity 8 can legitimately differ from capacity 32 because stored history differs. The configuration is part of the replay contract.

My answer: “This requirement is already configurable. With eight histories, the engine removes old shipment histories sooner and may report incomplete history.”

**If they ask for a different change:**

| Request | Where to change | What else must be checked |
| --- | --- | --- |
| Six-hour feature past period | `features.py` and model compatibility checks | Feature version, fitted artifact, boundary tests, training and live prediction agreement |
| Different future period being predicted | `training.py` plus artifact/output semantics and docs | Labels, maturity, splits, retraining, evaluation; this changes the prediction target |
| Different record cap | `engine.py` | Trimming tests and snapshot compatibility; snapshots record the cap |
| Exact RAM ceiling | New resource policy and measurements | Existing shipment counts are insufficient evidence |
| Return every requested training checkpoint | Public row contract and builder | Agree how to represent unknown outcomes before changing binary labels |

For feature or label changes, save experimental training under a new directory:

```bash
.venv/bin/python -m dispatch_risk train --data data --artifact "$REHEARSAL_DIR/changed-model" > "$REHEARSAL_DIR/changed-evaluation.json"
```

I use a separate validation experiment to choose the change. Repeatedly inspecting the existing final test group while tuning weakens its role as a final evaluation. I will not overwrite `outputs/final_model` during practice.

### Task 4: defend the statistical validity

**Question I may be asked:** “Why should these scores estimate future behavior?”

I open the recorded evidence directly:

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('outputs/final_model/evaluation.json').read_text())
for key in ('split', 'test', 'constant_test', 'limitations'):
    print(key)
    print(json.dumps(report[key], indent=2))
for row in report['slices']:
    print(row['dimension'], row['value'], 'rows=', row['rows'],
          'positives=', row['positives'], 'AP=', row['average_precision'], 'Brier=', row['brier'])
PY
.venv/bin/python -m pytest tests/test_training.py::test_generated_training_artifact_and_reproducibility tests/test_training.py::test_fit_cutoff_cannot_use_later_report -vv
```

Narrow the discussion to these six questions:

| Question | My answer | Code or evidence |
| --- | --- | --- |
| Why this split? | “I ordered shipment groups by their first checkpoint. Older groups train the model, later groups validate it, and the last group evaluates the fixed choice.” | `build_training_rows`, `train`, report `split` |
| Can one shipment appear on both sides? | “Each shipment belongs to one shipment group. Repeated checkpoints stay together.” | Cohort assignment in `training.py` |
| Could future information enter training? | “Features use eligible receipts at each checkpoint. The reporting wait must finish before the fitting cutoff, and input preparation settings are learned from the fitting rows.” | `known_revisions`, `_label`, `train` |
| Why 48 hours? | “I assume reports have arrived after that wait. My comparisons with longer waits found no contradictions in this dataset. Real use needs confirmation of report coverage.” | Notebook 7, `GRACE`, decision record |
| Why this model? | “The validation comparison used a declared probability error and simplicity rule. Logistic regression met that rule. The public trainer fits that selected family.” | Notebook 12, `validation_selection.json` |
| What does the result establish? | “It performed well on later synthetic shipments under my label assumptions. Real shipment performance is still untested.” | Report limitations |

Know these values: test has 309 checkpoints and 25 positive checkpoints; AP 0.981277, Brier 0.003760. Constant baseline AP 0.080906, Brier 0.074380. At the illustrative 20% alert cutoff: 24 true positives, one false negative, zero false positives. Checkpoints are not independent incident counts: overlapping windows can refer to the same incident.

I show at least two useful slice dimensions. Source distinguishes sensor feeds; freshness separates readings older than 30 minutes. The coast-source slice has 14 positives and Brier about 0.009918. Fresh readings have only three positives, so their perfect ranking provides limited evidence. I will not claim one source causes worse performance from this comparison.

I explain AP as ranking quality and Brier as average squared probability error. Recall counts the positive checkpoints caught at a threshold. Brier alone does not establish calibration. Notebook 13 holds groups comparing predicted risk with the observed incident rate and shipment-level bootstrap uncertainty; bootstrap intervals do not remove synthetic-data or completeness assumptions.

The test above verifies that changing test labels does not change the fitted saved model files. It supports one leakage safeguard. It does not prove all possible leakage is absent.

### Task 5: make a small code change and preserve repeatable results

**Practice request:** “Reject an invalid shipment limit in the CLI with a clear usage error.” This is a proposed rehearsal change, not a missing engine validation: the engine already rejects invalid limits. Get agreement on the requested behavior first.

**Expected behavior:** positive integers continue working; `0`, negative numbers and non-integers fail during argument parsing with exit code 2 and an actionable message.

1. I create my practice branch. Open `src/dispatch_risk/__main__.py` and `tests/test_cli.py` (new test file).
2. I add this regression test to `tests/test_cli.py`:

```python
import subprocess
import sys
import pytest


@pytest.mark.parametrize('value', ['0', '-1', 'abc'])
def test_cli_rejects_invalid_capacity(value):
    result = subprocess.run(
        [sys.executable, '-m', 'dispatch_risk', 'replay',
         '--max-shipments', value],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert 'max-shipments must be a positive integer' in result.stderr
    assert 'Traceback' not in result.stderr
```

3. I run `.venv/bin/python -m pytest tests/test_cli.py -vv`. Confirm the intended assertion fails before editing the implementation. An unrelated import failure is not the expected failure.
4. I add this helper above `main()` in `__main__.py`:

```python
def positive_shipments(value: str) -> int:
    """Parse the CLI shipment capacity.

    Args:
        value: Command-line text supplied for --max-shipments.

    Returns:
        The positive integer capacity.

    Raises:
        argparse.ArgumentTypeError: If the value is not a positive integer.
    """
    try:
        capacity = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            'max-shipments must be a positive integer'
        ) from None
    if capacity <= 0:
        raise argparse.ArgumentTypeError(
            'max-shipments must be a positive integer'
        )
    return capacity
```

5. I replace the capacity argument declaration with:

```python
parser.add_argument('--max-shipments', type=positive_shipments, default=10000)
```

I keep the engine constructor validation: Python callers do not pass through argparse.
6. I run the tests and valid replay:

```bash
.venv/bin/python -m pytest tests/test_cli.py -vv
.venv/bin/python -m pytest tests
.venv/bin/python -m dispatch_risk replay --data "$REHEARSAL_DIR/input" --artifact outputs/final_model --max-shipments 32 --output "$REHEARSAL_DIR/after-change-a"
.venv/bin/python -m dispatch_risk replay --data "$REHEARSAL_DIR/input" --artifact outputs/final_model --max-shipments 32 --output "$REHEARSAL_DIR/after-change-b"
cmp "$REHEARSAL_DIR/after-change-a/predictions.jsonl" "$REHEARSAL_DIR/after-change-b/predictions.jsonl"
cmp "$REHEARSAL_DIR/after-change-a/snapshot.json" "$REHEARSAL_DIR/after-change-b/snapshot.json"
cmp "$REHEARSAL_DIR/replay-a/predictions.jsonl" "$REHEARSAL_DIR/after-change-a/predictions.jsonl"
cmp "$REHEARSAL_DIR/replay-a/snapshot.json" "$REHEARSAL_DIR/after-change-a/snapshot.json"
git diff --check
git diff -- src/dispatch_risk/__main__.py
git status --short
```

A new untracked test does not appear in ordinary `git diff`; open it explicitly or stage only the intended files before inspecting the staged diff. Commit or push only when requested.

Here, unchanged valid-input outputs are expected because only CLI validation changed. A feature change can legitimately change predictions; compare two runs of the new implementation for repeatable results and explain the intended before/after difference.

My answer: “Invalid limits now fail at the command boundary. The engine validation still protects Python callers. Valid inputs produced identical predictions and snapshots before and after the change.”

This worked example has been checked in a temporary copy; it is not applied to the submitted implementation. If the interviewer requests another edit, follow the same reproduce, test, change, verify sequence.

### Recovery demonstration if asked

There is no need to start the UI. Restore the state and compare its serialized representation:

```bash
.venv/bin/python - <<'PY'
import os
from pathlib import Path
from dispatch_risk import RiskEngine
root = Path(os.environ['REHEARSAL_DIR'])
model = Path('outputs/final_model')
original = root/'replay-a/snapshot.json'
engine = RiskEngine.restore(model, original)
engine.snapshot(root/'restored.json')
assert original.read_bytes() == (root/'restored.json').read_bytes()
before = engine.stats()
assert engine.reload_model(model)
assert not engine.reload_model(root/'missing-model')
assert engine.stats() == before
print('Restore bytes match; rejected reload preserved model and state counters')
PY
.venv/bin/python -m pytest tests/test_engine.py::test_replay_snapshot_restore_and_continuation tests/test_engine.py::test_reload_atomic_with_concurrent_calls -vv
```

The snippet verifies restored bytes and unchanged counters/version. The tests add continuation and overlapping prediction calls evidence. Restore requires the artifact version recorded in the snapshot.

### Suggested use of the 60 minutes

I treat this as a flexible rehearsal budget: 5 minutes for setup, 10 for the new stream, 15 for failure investigation, 10 for the changed requirement, 10 for evaluation, and 10 for the code edit. The interviewer may combine tasks or change the order. Narrate my next check briefly, run it, then explain the result. Do not spend the interview reading every command in this guide.


## 8. Questions and concise answers

| Question | Answer |
| --- | --- |
| Why not always use the correction? | It was not available to the earlier prediction. |
| Why keep two clocks? | One measures event time; one establishes knowledge time. |
| Why is missing trend not zero? | Unknown slope is different from observed flat readings. |
| Why not train on every decision? | Recent outcomes may be unknown; my exclusion is a documented contract difference. |
| Why logistic regression? | It met the predeclared validation rule and is straightforward to inspect and export. |
| Why memory limits? | Explicit README requirement; unlimited shipment or extra stored history would violate it. |
| What happens after removal of shipment history? | Lost history limits reconstruction and duplicate identity; the prediction discloses incomplete history. |
| Why reject customer notes? | Their suggested mechanisms conflict with temporal correctness, limited memory or safe serving; DECISIONS records each alternative. |
| What would you improve first? | Explicit observation coverage and agreed way to represent unknown outcomes, then realistic load and real data validation. |

## 9. Suggested presentation order

I spend about one minute on the problem and two-clock example, then five minutes following one message through contract, ingest, features and score. Use another three minutes for labels, split, baseline and model choice. Finish with recovery, limits and tests. Adjust to the interviewer's questions; the 60-minute follow-up includes live work, not a 60-minute speech.

Optional demo order: Start here for the correction example; Model results for evaluation; System checks for reliability; New stream for live input/configuration changes. Open API docs only when demonstrating the backend request. Every button should support a claim already explained.

Close with: “The main guarantees are inputs known at the prediction time, reproducible scoring and explicit limits when information is missing. The strongest remaining uncertainty is real-world label coverage and predictive performance.”

## 10. Improvement priorities

These are remaining gaps, not completed upgrades.

### 1. Resolve the training-row contract before submission

`build_training_rows` omits checkpoints whose six hour prediction window and 48 hour wait for reports have not finished. The README asks for features, a binary label and metadata at every requested checkpoint. This is a real contract difference, already disclosed in DECISIONS.md. A single requested decision produces no rows under the current observation cutoff rule.

The reason is valid: an unknown outcome cannot honestly become label zero. The interface needs an agreed way to represent it. If the interface can change, return an eligibility status with every requested checkpoint and keep rows with outcomes still unknown out of fitting. If the interface must stay fixed, defend the omission explicitly and retain counts. Do not quietly label recent rows negative just to match a row count.

The builder also infers its observation cutoff from the latest decision time. A future revision should accept a separately supplied time when observation is assumed to end or certified audit coverage. The prediction schedule is not evidence that all incident reports are complete.

Evidence: README required implementation section, `src/dispatch_risk/training.py`, `tests/test_engine.py::test_label_boundary_availability_and_maturity`, DECISIONS.md.

### 2. Measure resource use and strengthen boundary checks

Shipment, record and event-size limits bound retained structures. They do not impose an exact process-memory ceiling. Scoring runs feature extraction under the engine lock, so long histories can delay other callers. Measure actual memory, scoring latency and snapshot pauses while ingestion and reload are active. Choose service targets before deciding whether finer locking or cached features are worthwhile.

Restore currently reads an entire snapshot before validating its structural bounds. Add a byte-size limit before parsing if snapshots may come from untrusted or oversized sources. Exercise extreme valid numeric values and malformed artifacts as part of that hardening. Test the declared minimum Python 3.11 environment separately from the verified Python 3.14 environment.

Evidence: `src/dispatch_risk/engine.py`, `src/dispatch_risk/features.py`, `pyproject.toml`, outputs/final_model/verification.json.

### 3. Establish evidence for real use

The final test result has 25 incidents from synthetic data. The 48 hour allowance assumes mature outcome records are complete. Before operational use, confirm reporting coverage, evaluate several later time periods with real shipments, and check probability calibration within useful operational groups.

I select an alert threshold using the costs of missed incidents, false alarms and available response capacity. The demonstration threshold of 20% does not establish that decision. If a calibration model becomes necessary, fit it on a separate calibration or validation group rather than the existing final test data.

Only then assess whether extra sensor features or a more complex model improve performance. The current evidence does not justify adding model complexity solely because it is available.

Evidence: outputs/final_model/evaluation.json, notebooks 11–13, DECISIONS.md.
