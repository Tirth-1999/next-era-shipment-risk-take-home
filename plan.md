# Shipment risk: work plan

## Where the project stands

The fourteen notebooks and the Python engine are complete. The engine builds training rows, fits the selected model, scores incoming telemetry, limits retained history, saves and restores snapshots, and reloads models without clearing shipment state.

The last implementation check passed 20 tests. Two replays produced identical predictions and snapshots. A separate stream with 12,881 deliveries stayed within a 32-shipment limit. The held-out model results were AP 0.981277 and Brier 0.003760, based on 309 examples and 25 incidents. Those figures describe synthetic data under an assumed reporting-completeness policy; they are not a deployment claim.

The optional local interview demo is now implemented in `demo/`. Run it using the instructions in `demo/README.md`, then use the walkthrough to review the finished code and practise explaining a change to one requirement.

## What we are trying to build

For one shipment at one decision time, estimate the chance of a temperature incident in the following six hours. Use only telemetry available by that decision time. Later incident reports can provide training labels, but cannot become prediction inputs.

[README.md](README.md) is the original assignment. [DECISIONS.md](DECISIONS.md) records the implemented choices and their limits. [RUNBOOK.md](RUNBOOK.md) has commands to run the solution. [MY_LEARNINGS.md](MY_LEARNINGS.md) follows the experiments and discussions in order.

## How to work through the remaining concepts

Start with one shipment and a concrete question. Explain the idea before introducing terminology, show the relevant readings or code, and check the result. Discuss alternatives where they change behavior, such as how much history to retain or when to trust a negative label.

Keep a separate notebook for each learning checkpoint. Inspect its outputs before moving to the next experiment. The source modules now contain the maintained feature and engine code; a future experiment should reuse them where possible. Do not select another model using the final test results.

After a checkpoint, add the result, reason for the choice, remaining limitation, and next question to the learning journal. Record actual explanations from the discussion separately from material that still needs review. Running code does not establish understanding by itself.

## Writing conventions

Use the plain-language rules from the resume memory: lead with the point, describe concrete actions, vary sentence length, and remove filler. Keep technical terms when they explain the decision. Write notebook explanations and comments in English. Comments should explain a rule or an unexpected case, rather than narrate every line.

Keep numerical results, uncertainty, and the distinction between experiments and deployed systems intact. Interview notes should sound natural when spoken aloud. Avoid generic praise, tool lists without context, repeated warnings, and notes about the writing process in technical explanations.

The reference is `career_records/applications/resume_automation/RESUME_MEMORY.md` in the portfolio project, especially its “Humanized Writing Rules” section. Its resume formatting and bullet-length rules do not apply to this repository.

## Checkpoints completed

| Notebook | Question | Result used in the next step |
|---|---|---|
| 01: Learning lab | What does one training example represent? | One shipment at a decision time; distinguish events, features and outcomes. |
| 02: Duplicates and revisions | Which reading was available then? | Select the highest available revision and collapse duplicates. |
| 03: Clocks and first features | How old is the reading, and when did it arrive? | Separate temperature, measurement age, arrival delay and missingness. |
| 04: Windows and trends | What happened over the recent past? | Three-hour summaries; slope uses elapsed time and can be missing. |
| 05: Tables | How can the raw files be inspected more easily? | Save separate tables in `data/tables/`, preserving delivery order and original JSON. |
| 06: Outcome availability | Does no report mean no incident? | Report delay leaves some outcomes unknown. |
| 07: Maturity | When can a row enter training? | Use a 48-hour reporting allowance after the six-hour window; inspect 72/96-hour alternatives. |
| 08: Training table | How do features and labels fit together? | Nine feature columns, separate labels and audit metadata. |
| 09: Baseline | What must a useful model improve on? | Compare with the training incident rate; accuracy alone can hide zero recall. |
| 10: Model mechanics | What changes during training? | Logistic weights and intercept; a conceptual comparison with trees. |
| 11: Evaluation setup | How do we estimate future performance? | Chronological shipment groups and preprocessing fitted on training data. |
| 12: Model comparison | Which candidate meets the declared rule? | Logistic regression selected from five validation candidates. |
| 13: Final evaluation | How does the selected model perform on held-out data? | Model/baseline metrics, operational slices, reliability bins and uncertainty. |
| 14: Saved model | Can another process reproduce the predictions? | Model loading and input checks before implementing the stateful engine. |

Checkpoint 15 moved the tested behavior into Python and added memory limits, snapshots, concurrency, reload and a CLI. Checkpoint 16 reviews wording and plans an optional demonstration. Earlier journal entries describe what was known at that stage, not the current completion status.

## Choices to explain in the interview

- **Two clocks:** receipt determines what was knowable; device time describes when a measurement claims to have happened.
- **Outcome labels:** the six-hour horizon and 48-hour allowance apply to both classes. Mature negatives are assumed complete, not certified by the dataset.
- **Model choice:** logistic regression met the validation rule. Higher AP alone did not make boosting the selected model.
- **Memory:** cap shipments and records per shipment. Removing history limits historical reconstruction, so predictions report incomplete coverage.
- **Reload:** validate a new model before swapping it. A failed reload retains the old model and all telemetry.
- **Replay:** retain the same delivery order, state rules, feature version and model to reproduce serialized results.

## Assignment constraints

The README specifies Python 3.11+, offline evaluation, declared dependencies, concurrent calls, and streams exceeding 10,000 events with capacity 32. Compressed generated data must be below 5 MB; the current data files total about 0.40 MB when individually gzip-compressed.

It also states a seven-hour maximum and says: “Do not spend time on UI, infrastructure-as-code, or presentation slides.” This is stronger than saying UI receives no points. No claim is made that the full learning process stayed within that timebox. The optional demo below is for separate interview preparation and should stay outside the assessed submission unless the interviewer invites it.

## Optional interview UI: implemented walkthrough

**Purpose:** make one prediction easy to explain. The demo should show which readings the engine used, why other readings were excluded, and what changes when another delivery arrives. It should help tell a five-minute story without adding a second implementation of the model.

**Status:** implemented after approval to build. It uses Python’s standard library, the existing engine and local HTML/CSS/JavaScript. No new dependencies were added. The design below records the agreed scope; `demo/README.md` describes the working controls.

### First version: one local page

Use a small Python launcher and a browser page that runs locally. Reuse `RiskEngine`, the shared feature functions, and the saved model. Keep it in a separate `demo/` folder with no imports from the core package back into the demo. Start with the existing data and a few small examples whose answers can be checked by hand.

The page would have three sections:

1. **Shipment and delivery controls.** Choose a shipment, inspect the next delivery, step forward, or reset. Show UTC throughout. Keep “delivery position” separate from “score as of”: they answer different questions.
2. **What was known.** Show a table of event IDs, revisions, device times, receipt times and temperatures. Mark duplicates, revisions unavailable at the checkpoint, superseded readings and excluded device clocks. Include a simple temperature timeline with the three-hour lookback shaded.
3. **Prediction and retained state.** Show six-hour incident probability, model version, feature values and degraded reasons. Explain a missing trend as insufficient distinct measurement times. Show retained shipments/records and eviction counts alongside their limits.

A later incident report can appear in a separate “Outcome, revealed later” section. It must not enter the feature panel or imply that the prediction knew the answer.

### Walkthrough to support

Begin with the 8°C reading received at 9:05 AM. Score at 11 AM. Deliver its noon correction to 5°C and score at 11 AM again: the result should stay the same while history is retained. Then score at noon and show the eligible revision changing.

Next, use a small shipment cap to show eviction and its degraded reason. Save a snapshot, restore it, and compare the serialized prediction. Finally, try an invalid model reload and show that the previous model still serves. A valid reload example needs a separately identified valid artifact; it should not suggest that a demonstration model has better performance.

### Evaluation view, if the first version is useful

Read the existing evaluation report to show the selected model beside the constant baseline, with row/incident counts, AP, Brier and precision/recall at the illustrative 20% threshold. Include the source and freshness slices. Explain that the dataset is synthetic and the threshold is not an operating recommendation. Do not retrain or tune from the UI.

### How to check the demo

For each displayed prediction, compare its probability, model version and feature digest with a direct engine call. Check the delayed-correction example, duplicate handling, eviction, restore and failed reload. Reset must recreate the same starting state and delivery sequence. Empty data and missing artifacts need readable errors rather than a blank page or a zero-risk result.

Keep the command-line walkthrough as the fallback. The UI should be removable without changing package installation, tests, training or scoring. No hosting, login, branding work or slide deck is needed for this proposal.

### Next review

Start the local demo and follow the late-correction example. Delivery playback, the prediction and feature panels, memory counters, snapshot/restore, reload checks and the saved evaluation view are implemented. The next task is to practise the explanation and compare it with the notebook and CLI walkthroughs.

## Checkpoint 17: local UI

Built the optional demo with separate playback sessions per tab. Every displayed feature set is checked against the engine’s feature digest. Automated tests cover duplicates, late corrections, eviction, restore, reload, source-data playback and tab isolation. Browser checks cover the controls and saved evaluation view. The engine code and model artifact are unchanged.

## Checkpoint 19: repository handoff documentation

### Browser presentation

The existing nine-slide PowerPoint is also available as HTML at `/presentation` on the demo server. A standard-library exporter preserves the deck's text, tables and notes; the viewer adds keyboard navigation, fullscreen, slide links and a return to the live demo. Re-export after changing the PowerPoint. The presentation remains optional interview preparation and does not change model or engine behavior.

Added main README navigation, environment setup, server startup, retraining and replay commands, saved evaluation metrics, operational slices, and a requirement-to-evidence map. Keep the original assignment available below the submission guide. The handoff must make the immature-row contract difference and synthetic-data limits visible alongside the results. Updated the GitHub About description with the project scope. Next: rehearse the runbook against a new stream and explain the documented tradeoffs.

## Checkpoint 18: improvement review and presentation

Reviewed the implementation against the README and recorded priorities in IMPROVEMENTS.md. The main submission concern is the documented omission of immature training rows from a contract that requests every checkpoint. Further priorities are explicit observation coverage, measured memory/latency, bounded snapshot parsing, minimum-version testing and validation on real data. No model or engine policy was changed during this review.

Created a nine-slide interview presentation in the UI’s green-and-cream theme, with editable evidence tables and speaker notes. It covers timing, features, labels, model selection, evaluation, engine behavior, remaining work and the live walkthrough. It is optional interview preparation alongside the demo. Next: review the contract concern, then rehearse the presentation and demonstration.
