# My learning journal

These notes explain what we tried, what the results showed, and why we made each choice. The entries follow the order of the work: a limitation marked open in an early checkpoint may be resolved later. Checkpoint 15 records the completed engine. Interview notes are prompts to review, not claims that every concept has already been discussed.

## How to use this journal
After every completed learning checkpoint, experiment, evaluation, or implementation milestone, add an entry before moving on. Record failed experiments and revised choices too. Do not claim a model is better without measured evidence. Use personal/plan.md for the roadmap and DECISIONS.md for the final engineering decisions.

## Checkpoint 0 — Establish the notebook-first workflow

**Status:** Setup complete. Notebook concepts demonstrated; discussion pending.

**Question:** How will we build the assignment while understanding the reasons behind each decision?

**Concepts introduced:** A raw event is a delivered update; a feature describes eligible information; a label is the eventual outcome. One training example represents one shipment at one decision time. Measurement time and information availability are different.

**Work:** Read the assignment, contracts, starter implementation, tests, and generator. Created personal/plan.md and personal/notebooks/01_learning_lab.ipynb. Executed the notebook's six code cells in order and saved their outputs.

**Evidence:** The notebook loaded the supplied data and inspected identities, revisions, a shipment timeline, availability at a checkpoint, and incident windows. All six code cells executed successfully using Python. This verifies the exploratory cells, not a trained model or production engine. The production functions had not been implemented at this stage.

**Options considered:** Implement immediately in solution.py, or first explore examples and decisions in a notebook.

**Why this approach:** Use the notebook first, as requested, so intermediate data and reasoning are visible before moving the tested logic into Python modules.

**Limits:** Exploration consumes the assignment's seven-hour effort budget. Notebook experiments are not the final deliverable. We must later extract shared, tested feature logic so training and serving do not drift apart. No model or final feature set has been selected.

**Interview notes:** “I first examined individual shipment timelines to understand what information was available at each prediction time. This helped me establish temporal policies before implementing the reusable pipeline.”

**Discussion notes:** Pending review; running the cells is separate from explaining the result.

**Open questions:** How should we resolve revisions and bad clocks? What makes a negative label sufficiently observed? Which features add useful information?

**Next step:** Review notebook sections 1–2 together, then work through one checkpoint manually.

**References:** [Plan](plan.md), [Learning notebook](notebooks/01_learning_lab.ipynb), [Assignment](../README.md).

---

## What to record at each checkpoint

### Checkpoint N — Descriptive title
- **Date / status:**
- **Question or goal:**
- **Concepts explained in plain English:**
- **What we tried or changed:**
- **Observed result and evidence:** Include metrics, split, sample counts, and baseline for evaluations; link actual outputs.
- **Alternatives considered:**
- **Decision and why:** State whether provisional or final.
- **Tradeoffs, failure cases, and limitations:**
- **Interview notes:** A short answer in my own voice, for review.
- **Discussion notes:** Record my explanation or leave pending.
- **Remaining questions and next step:**
- **References:** Notebook section, code, tests, or artifacts.

## Checkpoint 1 — Repair the notebook environment

**Status:** Environment repair verified; discussion pending.

**Question:** Why did selecting .venv not let the notebook execute?

**Concept:** A virtual environment provides an isolated Python interpreter and packages. A notebook also needs ipykernel to communicate with that interpreter. A working Python executable alone does not establish notebook readiness.

**Evidence:** The environment ran Python 3.14.6, but ipykernel and jupyter_client were absent. After installing notebook dependencies, the full notebook executed through an actual .venv Jupyter kernel from the notebooks directory. Earlier setup had only executed cell code as Python; that had not verified Jupyter startup.

**Choice and alternatives:** Added a notebook optional dependency group (ipykernel and nbclient) rather than installing packages globally or making them production scorer dependencies. Updated uv.lock. Removed the stale uv workspace member venv, which was not a project workspace member.

**Reproduction:** From the repository root, run `uv sync --extra dev --extra notebook`. Select the project .venv interpreter in the notebook editor and restart its kernel.

**Limitations:** Programmatic kernel execution is verified; the notebook editor selection still needs to be refreshed. No ML model or production engine was changed.

**Interview notes:** “I kept notebook tooling in an optional development dependency group and verified the notebook with the same interpreter used for development.”

**Next step:** Resume the first learning example after selecting/restarting the repaired kernel.

## Checkpoint 2 — Select the revision known at prediction time

**Status:** Notebook experiment implemented and verified; discussion pending.

**Concepts:** Duplicate delivery repeats an event/revision; correction supplies a higher revision. Select the highest revision available by the checkpoint, not the final revision in the whole file.

**Work/evidence:** Notebook section 8 adds a teaching helper and invented timeline. At 9 AM there is no reading; at 10 AM revision 1 reports 8°C; at noon revision 2 reports 5°C. Assertions cover repeated deliveries, out-of-order revision inputs in historical reconstruction, exact arrival boundary, exclusion of future corrections, and conflicting duplicate rejection. The actual sample event s-00000-temp-08 selects revision 1 (3.908°C) just before 7 PM and revision 2 (1.658°C) at 7 PM. All eight notebook code cells executed sequentially with .venv Python and notebook schema validation passed. This checkpoint used sequential Python execution, not a new frontend kernel run.

**Decision/reason:** Filter by received time before selecting the highest revision; otherwise future corrections leak into historical features. Collapse exact duplicates so retries do not change reading counts.

**Alternatives:** Always using newest truth leaks future knowledge; counting revisions independently double-counts a measurement. Silently choosing the first conflicting duplicate depends on file ordering; explicit rejection is the provisional notebook policy.

**Limits:** Helper is for historical reconstruction with full input available, not online ingestion. It does not solve bounded retention, clock validity, outcome completeness, or production rejection behavior. No ML model has been selected or trained.

**Interview notes:** “I choose the latest revision known at the decision time and collapse exact duplicates, so late corrections cannot rewrite earlier knowledge and delivery retries cannot add measurements.”

**Discussion notes:** a reconstructed 11 AM prediction uses the original 8°C reading, available from 9:05 AM, because the 5°C correction arrived at noon. Clarification: 9 AM is the measurement time; 9:05 AM is the platform availability time. The original reading is eligible at 11 AM; the noon correction is not.

**Next:** Clock validity and first temperature/freshness features. Reference: notebook section 8.

## Organization checkpoint — separate notebooks

**Change and reason:** Moved revision experiments to personal/notebooks/02_duplicates_and_revisions.ipynb with independent imports and data loading. Notebook 1 retains the introductory exploration and links forward. Each substantive checkpoint will have its own notebook to make review and reproduction easier. Earlier references to section 8 refer to notebook 2.

**Verification:** Notebook schemas validated; notebook 1's six code cells and notebook 2's three code cells executed sequentially in separate namespaces with .venv Python. Outputs saved. This check did not launch a frontend Jupyter kernel.

**Tradeoff:** Small setup helpers are repeated for independent exploration; final reviewed production feature logic will be shared. No model or production source changes.

## Checkpoint 3 — First feature-engineering experiment

**Status:** Implemented and verified in notebook 03; discussion pending.

**Concepts:** Features are calculated descriptions of eligible data. Latest temperature, measurement age, and selected revision arrival delay describe different aspects of the same observation. Missing is not zero.

**Decision and alternatives:** Start with interpretable features before window summaries or models. Select latest by device time after availability/revision checks. Provisional experiment excludes device times later than received times rather than silently replacing them; tolerance/fallback alternatives remain open. No stale-data cutoff yet.

**Evidence:** Teaching example at 11 AM yields 8°C, age 120 minutes, delay 5 minutes. At noon the correction yields 5°C, age/delay 180 minutes; correction delay includes revision processing, not just transport. Four code cells executed sequentially using .venv Python and notebook schema validated. Assertions passed for hand calculations, duplicates, historical order independence, future corrections, future clocks, and missing versus zero. Actual earliest shipment checkpoints produced 3.798°C/60-minute age/35-minute delay; 5.386°C/60/2; and 9.857°C/0/0. These are descriptive sample results, not predictive evaluation.

**Limitations:** No trained model, final clock tolerance, window policy, label completeness, or bounded online state. Old device clocks may still be misleading. Notebook execution used sequential Python, not a newly launched Jupyter kernel.

**Interview notes:** “I engineered the latest eligible temperature and explicit freshness features, keeping missing information separate from actual zero readings.”

**Discussion notes:** measurement age as 60 minutes and arrival delay as 50 minutes for a 10 AM measurement received at 10:50 and scored at 11. Purpose clarification provided: age/delay describe freshness and availability lag; they do not alone determine eligibility or automatically discard readings. A separate missing indicator distinguishes absence from an actual 0°C measurement. Understanding of this distinction remains to be confirmed.

**Next:** Review notebook 03, then trailing summaries and trend.

## Checkpoint 4 — Temperature windows and trends

**Status:** Notebook experiment verified; discussion pending.

**Concepts:** Historical lookback differs from the future six-hour outcome horizon. Mean describes observed level, maximum describes peak, slope describes change per hour. Count and actual observation span describe available evidence. Missing slope is not zero slope.

**Choices and alternatives:** Half-open historical window (checkpoint minus width, checkpoint]; observation-weighted mean; least-squares slope on elapsed hours rather than row numbers. Endpoint slope is simpler but ignores interior data; time-weighted means or robust slopes merit consideration if bursts/outliers matter. Three hours is illustrative, not selected via evaluation.

**Evidence:** Independent notebook 04 has four code cells, executed sequentially with .venv Python; schema validated and outputs saved. Teaching readings 4/5/8°C at 9/10/11 AM give a three-hour mean of 5.667°C, maximum 8°C, and slope +2°C/hour. Two-hour window gives mean 6.5°C and slope +3°C/hour; one-hour window has only one reading and missing slope. Assertions cover arithmetic, duplicates, ordering, window boundaries, sparse/flat trends, irregular times, late telemetry and corrections. No new Jupyter frontend run was performed.

**Limitations:** Observation weighting overweights bursts of distinct events. Outliers affect peak/slope. Strict clock exclusion is provisional; old bad clocks remain possible. No predictive comparison establishes a best window or feature.

**Interview notes:** “I summarized available, revision-resolved readings in explicit historical windows, used elapsed hours for trend, and kept count and time span visible so sparse evidence was not disguised.”

**Discussion notes:** Pending explanation of left boundary and missing versus zero slope.

**Next:** After review, label eligibility and evaluation cutoffs before a training table or model selection. Reference: personal/notebooks/04_temperature_windows_and_trends.ipynb.

### Checkpoint 4 clarification — average versus trend
The question was why the two-hour trend is +3°C/hour when expanding from a one-hour to two-hour window lowers the mean from 8°C to 6.5°C. Explanation: these are summaries of different sets at the same decision time, not temperature observations at successive times. The actual two included readings are 5°C at 10 AM and 8°C at 11 AM. Their mean is (5+8)/2 = 6.5°C; their two-point slope is (8-5)/(11-10) = +3°C/hour. Divide by the actual one-hour observation separation, not the two-hour window width. Understanding pending confirmation.

### Checkpoint 4 clarification — three-hour trend
Explained the +2°C/hour example: readings 4, 5, 8°C at 9, 10, 11 AM span two actual hours. Net change is 4°C over two hours. Here the least-squares fit through all three equally spaced points also has slope +2°C/hour. Individual hourly increases are +1 and +3, so the fitted rate is a summary, not a constant change each hour. Endpoint division is an intuition for this specific example, not the general algorithm; notebook uses all readings in least-squares fitting. Discussion pending confirmation.

## Checkpoint 5 — Normalize JSON into analysis tables

**Status:** Notebook created and verified. Discussion pending.

**Goal/concept:** A DataFrame presents records as rows and named columns for inspection and analysis. In this checkpoint, normalization means expanding JSON structures into tabular columns, not scaling numeric features or performing database normalization.

**Work:** Added pandas to the notebook optional dependency group and updated the lockfile/environment. Created personal/notebooks/05_tabular_data_exploration.ipynb in English. Loaded events, decision times, labels, and manifest into separate tables. Added one-based file-row tracking, flattened payload columns, and UTC analysis timestamps while retaining original payloads and timestamp strings. Included previews, column/missingness audits, duplicate/revision inspection, delays, and a shipment view.

**Evidence:** Five notebook code cells executed sequentially using .venv Python; notebook schema validated. Table shapes: events 11,019 rows × 14 columns; decision times 1,800 × 4; labels 133 × 8; manifest 1 × 5. Assertions verified row counts, event order, revisions, preserved payloads, file-row sequence, and UTC timestamps. Execution was programmatic Python, not an editor kernel session.

**Decision/alternatives:** Use independent in-memory tables instead of replacing the JSON source or joining everything into a single table. This improves exploration while preserving replay evidence and avoids premature joins that could leak outcomes or multiply observations.

**Limits:** Tabular conversion alone does not clean the data or produce a training set. Availability, revision, clock, and label-completeness rules still apply. No model or predictive evaluation has been run.

**Interview notes:** “I created tabular analysis views while retaining raw delivery order and revision identities. I kept audited outcomes separate until constructing time-valid training labels.”

**Discussion notes:** Pending review.

**Preference recorded:** All notebook content and written learning material in English.

**Next:** Review table columns, then label eligibility and evaluation cutoffs. Original assignment README and JSON files remain unchanged.

### Checkpoint 5 follow-up — Persist analysis tables
Saved four CSV exports in personal/data/tables/: events, decision_times, labels, and manifest. Notebook 05 section 6 regenerates the files. Original JSON data remains authoritative. CSV drops pandas type metadata and can conflate null/empty text, so UTC parsing and missing-value policy must be explicit when reloading. Nested payloads are saved as JSON strings. All six notebook code cells executed with .venv Python; CSV round-trip checks verified headers, row counts, file-row order, event identities/revisions, and payloads.

### Checkpoint 4 discussion
Review answer: trend is unknown without observations at two distinct times. Boundary reasoning was requested and explained below; understanding of this explanation is not yet confirmed.

## Clarification — window boundaries and missing trend

`(start, end]` excludes the lower boundary and includes the upper boundary. This is our historical-window convention, not an ML requirement. At 11 AM a two-hour window `(9 AM, 11 AM]` excludes exactly 9 AM and includes exactly 11 AM if already received.

Why choose it? It includes the current observation and assigns a shared boundary to just one interval when considering adjacent, non-overlapping intervals. Rolling windows can still overlap and reuse readings. We could use `[start, end]` for historical features instead, with consistent implementation and tests. The README separately mandates `(as_of, as_of + 6 hours]` for future labels; that is a fixed requirement, not this optional feature convention.

Missing trend means insufficient observations at distinct measurement times. Zero trend means an estimated slope of zero from usable observations. Two records at the same timestamp do not suffice. A fitted zero slope can also arise when increases and decreases balance; it does not prove every reading was constant.

Next learning step: future labels, outcome completeness, and label availability before training.

## Checkpoint 6 — Labels and outcome availability

**Status:** English notebook 06 created and verified; discussion pending.

**Concepts:** Decision time, future incident time, audited-label availability, and model training cutoff are different. Positive means an incident in the specified future horizon; negative requires sufficiently complete follow-up; unknown means training eligibility is unresolved, not a third prediction class.

**Experiment:** Teaching decision at 11 AM, incident at 3 PM, report next day at 9 AM. At same-day 6 PM the window has ended but report is unavailable; next morning the positive is known. A hypothetical audit-complete-through guarantee illustrates what could support a negative. That field is not supplied by this dataset.

**Verification:** Four code cells executed sequentially with .venv Python, outputs saved, schema validated. Boundary and positive/negative/unknown assertions passed. Actual data has 140 checkpoint horizons containing listed incidents and 1,660 without; the latter are not automatically verified negatives. Observed report delays range from 18 to 28 hours; these descriptive observations are not a guaranteed bound for unseen data.

**Choices/alternatives:** The teaching helper waits for the full horizon before admitting either class and uses only available reports. A final completeness/grace policy remains open. Explicit audit coverage would be strongest but is absent. Closed-world mature-data assumptions could enable training if documented with limitations; treating all unverified negatives as unknown alone leaves no usable two-class dataset.

**Limits:** No production labels constructed, fixed grace selected, model fit, or new Jupyter frontend execution. The public builder has no training-cutoff argument; final design must address this explicitly.

**Interview notes:** “I separated incident occurrence from report availability and documented what supports negative labels, rather than treating missing reports as proof of no incident.”

**Discussion notes:** Pending answer about why no report at 6 PM is not automatically label zero.

**Next:** Review notebook 06, choose completeness assumptions and temporal evaluation design, then create training examples.

### Checkpoint 6 discussion and policy discussion
The discussion established that absent confirmation does not establish whether an incident occurred and that predictions/temperature movement cannot substitute for audited outcomes. The observed mean reporting delay was correctly read as approximately 22.9 hours. Clarification: this mean covers supplied incident reports, not a guaranteed reporting deadline or completeness evidence for all shipments.

Options explained in plain English: obtain an explicit complete-audit guarantee (not available in this exercise); adopt a documented reporting-wait and complete-records assumption with sensitivity checks; or retain unverified negatives as unknown, which alone cannot support useful binary training here. Recommended direction is an explicit assumption for this constrained exercise, not a claim of real-world certainty. No waiting-period value is selected yet; a grace period alone cannot prove completeness. The same maturity gate should be applied to potential positives and negatives to avoid admitting only quickly reported positives near the cutoff.

### Checkpoint 6 clarification — three input roles
We needed to separate telemetry events, prediction checkpoints and audited outcomes: events are readings/updates, not suspected incidents; decision_times lists when to predict, not actual outcomes or actions; labels lists audited incidents. Construct targets for each shipment/checkpoint by searching for an incident in the following six hours. Absence from decision_times is never evidence of a negative. No matching incident can be a negative only under the documented completeness/maturity policy. These file roles still need another walkthrough.

### Checkpoint 6 decision — proceed with option two
We chose to assume that sufficiently old outcome records are complete (option two). Clarified that this is an explicit assumption, not abandonment of all assumptions. Initial engineering allowance: 48 hours after the six-hour outcome window closes. Same maturity rule for positives and negatives; only reports available by the training cutoff can supply training labels. Immature rows stay excluded. The initial 48-hour proposal was an experiment, not a reporting SLA or a proven completeness bound. It was later selected as the working allowance in checkpoint 8. Plan sensitivity comparisons at 48, 72, and 96 hours. No policy comparison or model evaluation has yet been run. The final public-interface cutoff/metadata design remains open.

### Checkpoint 6 confirmed reasoning
Review answer: an unavailable report does not establish label zero: an incident may have occurred and its report may arrive late. Terminology clarified: missing audited outcome evidence, not a missing decision; decision_times are prediction checkpoints.

## Checkpoint 7 — Maturity and historical training cutoff
**Status:** Independent notebook 07 created; five code cells executed sequentially with .venv Python and schema validated. Discussion pending.

**Work:** Apply a 48-hour allowance after the six-hour horizon, equally to both classes, using only reports available by the training cutoff. Demonstration cutoff selected at approximately 70% of distinct decision timestamps without consulting incident outcomes; not a final split or observation-end guarantee.

**Evidence:** At the demonstration cutoff, 48 hours yields 1,209 eligible rows (96 positive, 1,113 assumed negative), 51 immature rows, and 540 at/after the cutoff. At 72 hours: 1,185 eligible (94 positive). At 96 hours: 1,161 eligible (93 positive). No later-report contradictions occur among assumed negatives in the supplied table at these settings; completeness is still not proven. Teaching test deliberately shows a report later than the allowance can contradict an assumed negative. Maturity boundary, symmetric waiting, and future-report exclusion checks passed.

**Limits:** Eligibility comparison only; no model metrics, joined features, final split, final grace selection, or new frontend Jupyter execution.

**Interview notes:** “I applied a symmetric outcome-maturity gate and limited training labels to information available at fit time, then audited later-report contradictions.”

**Next:** Review notebook 07; subsequently combine features and eligible outcomes, establish temporal evaluation details, and teach model fitting.

### Checkpoint 7 discussion — maturity and zero contradictions
Review answer: an immature checkpoint should remain out of training. Clarification: exclusion follows our symmetric waiting rule; it can apply even when a positive is already known, not only when the outcome is unknown.

Discussion: zero later-report contradictions for all three allowances. Interpretation: at this demonstration cutoff, no negative assigned under any of these policies is overturned by a later incident report present in the supplied table. The sample's observed incident reporting delays are at most 28 hours, shorter than even the smallest 48-hour allowance. Therefore zero contradictions are expected for mature windows in this sample and do not distinguish 48/72/96 hours on this measure. Longer allowances reduce eligible rows (1,209/1,185/1,161) and positives (96/94/93) because a different recent subset is excluded, not because incidents are relabeled away. This is not model-quality evidence or proof of unreported-incident absence. Keep 48 hours provisional; further checks can cover more cutoffs and deliberately longer synthetic reporting delays. No new tests were run for this explanation.

## Checkpoint 8 — First training table
**Status:** Notebook created and six code cells verified with .venv Python; discussion pending.

**Accepted choice:** Selected 48 hours as the working reporting allowance. It remains an assumed completeness policy, not a demonstrated SLA.

**Work:** Combined previously explored features with eligible labels, preserving decision time versus training cutoff. Copied helper definitions unchanged into the independent notebook; final production extraction remains pending. Explicitly selected nine X columns and kept y and metadata separate. Exported personal/data/tables/checkpoint08_training_rows.csv.

**Evidence:** 1,209 rows: 96 positive, 1,113 assumed negative; positive fraction about 7.94%. Nine candidate features; 316 missing slopes and 19 empty-window summaries. Tests checked maturity, row uniqueness, separation of label/metadata from X, and invariance to unavailable future data/reports. CSV reload verified counts, shipment sequence, and labels. Notebook schema validated; execution was sequential Python rather than a new frontend kernel session.

**Decisions/limits:** Three-hour feature window and 70% timestamp cutoff remain demonstration settings, not final selections. No model trained; no missing-value imputation fit. Current features include potentially redundant and constant columns, to review before fitting. No predictive performance claims. Final split and held-out outcome coverage remain open.

**Interview notes:** “I built one row per decision checkpoint, froze its features to information available then, and attached only mature labels known at the training cutoff. I explicitly excluded audit metadata and the label from model inputs.”

**Next:** Review X versus y, then baseline/model concepts and a valid temporal evaluation design.

### Checkpoint 8 discussion — label versus input features
The discussion correctly placed training before prediction. Clarification provided: exclude the label from X because it is the target answer, unavailable for a new prediction. Including it as a feature leaks the answer and produces misleading training/evaluation behavior. We do not discard labels during training: fit uses X as inputs and y as the separate target. Predict uses new X without its unknown y. Understanding of this specific reason is pending confirmation.

## Checkpoint 9 — Baseline and probability errors
**Status:** Independent notebook 09 created; six code cells executed with .venv Python and schema validated. Discussion pending.

**Concepts:** Baseline, class imbalance, accuracy versus incident recall, training-frequency probability, and Brier score. A constant baseline ignores X and learns one number from y. New prediction labels are not needed to produce scores.

**Evidence:** On the 1,209-row demonstration training subset, always-negative classification has 92.06% accuracy and 0% recall. Constant probability learned from training is 96/1209 = 7.9404%. Training Brier score is 0.073099 for the constant versus 0.079404 for zero probability. These are in-sample illustrations, not held-out model-quality claims. Hand-calculated Brier and constant-rate assertions passed.

**Choice and limits:** Establish an interpretable constant baseline before a feature-based model. Lower training Brier is expected because the mean minimizes squared error among constants. No ranking capability, final temporal split, imputation, or feature-based model has been established. Notebook recomputes reviewed training rows without relying on another notebook's state.

**Interview notes:** “I compared against a training-frequency probability baseline and examined incident recall, since always predicting no incident can appear accurate with imbalanced outcomes.”

**Discussion notes:** Pending answer about high accuracy with zero incident detection.

**Next:** Model concepts: feature weights and logistic probability mapping versus decision-tree questions; temporal evaluation and preprocessing before fitting candidate models.

### Checkpoint 9 discussion
Review answer: high accuracy with no incident recall is insufficient for a successful risk engine. Clarification: recall alone is also insufficient; always alerting can give full recall with many false positives. Evaluate precision, probability quality, and operational tradeoffs on later data.

## Checkpoint 10 — How models learn
**Status:** Independent English notebook 10 created; four code cells executed with .venv Python, outputs saved and schema validated. Discussion pending.

**Concepts:** Feature weight, intercept, score, sigmoid probability mapping, scaling, log loss, gradient descent, regularization, and decision-tree contrasts. Features versus learned parameters distinguished.

**Experiment/evidence:** Fit a one-feature logistic model on eight invented teaching rows, not the actual shipment dataset. Penalized training objective decreases from 0.693147 to 0.420919; repeated fits identical; finite-difference gradient check passed. These figures illustrate learning only, not generalization or shipment risk. No tree fitted.

**Approach:** Baseline remains reference; regularized logistic regression is first candidate for real evaluation; shallow tree is a possible nonlinear comparison. Neither is declared best. Temporal train/validation/test design, outcome coverage, missing-value handling and scaling must precede actual fitting. Training preprocessing must be reused unchanged at scoring.

**Interview notes:** “I used the constant baseline to establish a reference, then considered a compact regularized logistic model and a shallow tree, selecting with time-valid evaluation rather than training accuracy.”

**Discussion notes:** Pending explanation of what changes during training.

**Next:** Notebook 11, temporal evaluation and preprocessing, then actual model comparisons. Source references are included in notebook 10. No production implementation changed.

### Checkpoint 10 discussion — learned parameters
Review answer: logistic-regression training changes the model's weights and intercept. The original readings and target labels remain fixed; preprocessing can create transformed input representations separately. Clarification provided: learned parameters produce a probability; a chosen threshold can convert it into a class. This task requires the probability output, and an operational threshold is a separate decision. No threshold selected.

## Checkpoint 11 — Temporal split and preprocessing
Verified three code cells. Prior missingness and imbalance results drove training-only median imputation, explicit missing indicators, and model-appropriate scaling. 60/20/20 shipment cohorts by first decision timestamp; exact time boundaries ignore labels. Maturity removes 54 rows each from train/validation, leaving 1,026 training rows (77 positives) and 306 validation rows (21 positives). Shipments are disjoint. 264 training trends are missing. The latest checkpoint is an assumed snapshot cutoff, not audited coverage; 48-hour completeness assumption remains. Test labels were not examined. Shared notebook helpers replace further duplicated implementations; public source unchanged.

## Checkpoint 12 — Validation comparison
Verified two code cells. All five fixed candidates used the checkpoint 11 data/preprocessing. Validation AP/Brier: constant .068627/.063959; logistic .963370/.005328; shallow tree .936989/.006474; forest .951940/.008833; boosting .981793/.005789. Predeclared selection: beat baseline on AP and Brier, choose simplest within .002 Brier of best eligible. Logistic selected, with 20/21 incidents detected and one false positive at illustrative .2 threshold. Boosting ranks slightly better but did not win the declared rule. No test outcomes used. Only 21 validation positives and synthetic temperature signal limit interpretation. Next: freeze selection, refit on mature development rows at test start, evaluate test once against constant, inspect slices/uncertainty. Discussion pending.

Workflow preference confirmed: inspect each notebook's actual outputs before authoring the next checkpoint, and record how results change the next step.

## Checkpoint 13 — Frozen-choice test evaluation and artifact
**Starting point:** validation selected logistic regression; selection was frozen before test evaluation. Refit on 1,386 eligible development rows at test start, with no test shipments.
**Evidence:** Four code cells verified. 309 mature held-out rows from 104 shipments, 25 positives. Logistic AP 0.981277, Brier 0.003760, log loss 0.020847; constant AP 0.080906, Brier 0.074380. At illustrative 20% threshold: 24 true positives, one false negative, zero false positives. Seven slices cover source, freshness, and trend missingness. Reliability bins and 300 shipment-bootstrap replicates recorded. Approximate AP interval .9392 to 1 (floating-point rounding can yield a tiny excess above one); Brier interval .000286 to .010140. Small synthetic period and assumed label completeness limit conclusions. No test-driven reselection or calibration.
**Artifacts:** Saved fitted preprocessing/model pipeline, exact experimental feature runtime, feature order, dependencies, policy, checksums, and evaluation outputs. Notebook bundle is not yet the public training/serving contract. Discussion pending.

## Checkpoint 14 — Fresh-process and artifact checks
**Starting point:** the selected model and artifact from checkpoint 13. No model changes or repeated final selection based on test outcomes. Three code cells verified. Two fresh processes from unrelated working directories exactly matched parent-process canonical JSON for twelve probes, including feature digests and probabilities. Duplicate deliveries, historical input permutation, and unavailable future correction left results unchanged. A damaged checksum was rejected. A different generated stream (seed 1730, 80 shipments, 1,467 deliveries) produced 240 valid predictions without retraining. This is input robustness evidence, not new predictive validation.
**Limits:** These checks covered the notebook model only. The public engine, eviction, snapshots and concurrent reload were added in checkpoint 15. Shared helpers remain under personal/notebooks/support. Notebook phase is ready for review and subsequent Python implementation. Discussion pending.

## Checkpoint 15 — From notebook experiment to executable risk engine

**Starting point:** notebooks 11–14 fixed the model family and verified its predictions. Operational guarantees still needed implementation; good model metrics alone do not provide bounded memory, recoverable state or safe reload.

**Implementation choices:** offline and online paths share feature definitions. Serving uses validated JSON coefficients and preprocessing rather than loading executable pickle. Shipment capacity and a per-shipment record cap bound history and its lookup index. Eviction means some old evidence is gone, so predictions disclose missing coverage. One lock gives each score a consistent state/model view; reload validates first and swaps the model without clearing telemetry. Snapshots preserve replay-relevant state and ordering, then replace the destination atomically.

**Why these choices:** a shipment limit alone does not bound a single busy shipment. Keeping tombstones for every past shipment would defeat the cap. A successful model reload must not erase the readings needed for the next prediction. A failed load must retain the previous model rather than invent zero risk. An unknown outcome must remain excluded from training until the documented maturity assumption applies.

**Evidence:** public training matches the notebook held-out AP 0.981277 and Brier 0.003760. Retained state stayed within 32 shipments in a 10,050-event test. Repeated delivery-order replays produced byte-identical predictions and snapshots. Snapshot restore and continuation, concurrent operations, corruption rejection, and fixed-model training consistency checks have executable tests. The environment required a `PYTHONPATH=src` workaround for Python skipping hidden editable-install path files; this was a packaging/runtime issue rather than a modeling issue.

**Next discussion:** walk through the completed implementation. Read DECISIONS.md for explicit limits on historical reconstruction, assumed negative completeness, synthetic-data evaluation and cross-platform floating-point identity. Next learning discussion should start with one shipment entering the engine, then eviction, snapshot recovery, and model replacement.

**Final verification:** 20 tests passed. A different generated stream (seed 1927, 700 shipments, 12,881 deliveries) completed with 32 retained shipments, 527 records and 523 indexed event IDs. The portable model restored and scored in a fresh Python process with site-packages disabled. Exact replay hashes and environment limitations are saved in `outputs/final_model/verification.json`.

## Checkpoint 16: clearer writing and a proposed interview demo

The documentation now uses shorter explanations and concrete wording, following the writing preferences in the resume memory. The notebook examples, reported metrics and limitations are preserved. The plan describes the current implementation; earlier entries remain a history of how it was developed.

The optional UI proposal follows one shipment through delivery, feature calculation and prediction. It also includes examples of a late correction, eviction, restore and failed model reload. It would call the existing engine rather than duplicate its rules. No UI has been built yet.

The assignment explicitly says not to spend time on UI. The proposed page is therefore a separate interview-practice aid, outside the assessed submission unless invited. The next discussion is whether this page would explain the two clocks more clearly than the notebook and CLI.

Verification after the wording pass: 20 tests passed. Structural comparisons found no executable-code changes in 14 Python files or the 14 notebooks. Notebook schemas are valid and saved outputs are unchanged. The review covered 76 notebook markdown cells, the plan, decisions, runbook and this journal.

## Checkpoint 17: a local interface for explaining the engine

The demo follows one shipment through delivery, eligibility checks and prediction. It calls the existing engine and checks that the feature panel matches the prediction digest. Inspecting a snapshot keeps the display consistent with retained history after eviction. Audit outcomes are revealed separately and do not enter the feature calculation.

The small example makes the two clocks visible: a duplicate adds no evidence, and a correction received at noon cannot change an 11 AM prediction while the required history is retained. Snapshot restore compares the saved prediction bytes. Invalid reload checks confirm that the old model continues to serve. The evaluation view reads saved metrics without fitting another model.

Separate tab sessions prevent one walkthrough from moving another tab’s playback. The demo holds a finite dataset for inspection; its memory use must not be confused with the engine counters. The UI remains optional interview preparation, as the README excludes UI work from the assignment. Concept review is next.

Verification: all 27 tests passed, including seven demo-specific tests. Browser checks confirmed the duplicate/correction example, snapshot restore, both reload controls, and evaluation metrics. The narrow layout was inspected at a 380-pixel viewport with no page-level horizontal overflow. The core engine, training logic and saved model were not changed for the UI.

## Checkpoint 19: making the submission reviewable

The presentation and live demo now share one local server. Keeping the PowerPoint as the source for HTML slides avoids maintaining two separate copies of the results and explanations. The exporter retains slide text, table values and speaker notes. Notes are visible on the same page when expanded, so they should be hidden while presenting to the panel.

A reviewer needs a working startup command, an explanation of the evaluation split, comparison with a simple baseline, and evidence for each required behavior. The main README now puts those together. Average precision measures ranking; Brier score measures probability error. Slice counts matter: perfect recall on three incidents provides much less evidence than the same result on a large sample. Strong synthetic-data results do not settle reporting completeness or production performance. We should explain the immature-row contract difference directly rather than imply every original requirement is met exactly.

## Checkpoint 18: what is still worth improving

The system passes 27 tests, but passing tests and meeting every interpretation of the assignment are different questions. The builder currently leaves immature checkpoints out because their outcomes are unknown. The README asks for a binary-labeled row at each checkpoint. This needs an explicit contract discussion rather than silently treating unknown as negative.

The other priorities concern evidence: a certified observation boundary, measurements of memory and latency under load, and real-data evaluation before selecting an operating threshold. A more complicated model is not the first improvement supported by the current results. The detailed review is in personal/WALKTHROUGH.md (Improvement priorities).

The presentation follows the same visual theme as the UI and includes notes for explaining each choice. It retains the synthetic-data and outcome-completeness limitations. No new model experiment was performed, and no claim is made that the proposed upgrades are complete. Discussion and rehearsal remain next.


## Checkpoint 20: a simpler demo

The default view now explains one shipment in four steps: original reading, duplicate, late correction, and a noon prediction. Each step uses the real engine and includes a sentence to say aloud. Guided playback has its own session so it does not reset manual exploration. Technical controls and exact evaluation metrics remain available on demand. The sidebar can be collapsed and remembers its setting for the tab. Small positive probabilities are shown as less than 0.1% rather than rounded to zero.

The exploration tab now opens with only the usable temperature, estimated risk, and next/reset buttons. Model results open with caught, missed, and false-alarm counts. Explanations and full diagnostic controls are collapsed to keep the initial view short.

Replaced the manual playback dashboard with System checks. Each click demonstrates a specific guarantee using a small live example: bounded shipment count, exact snapshot recovery, and continued scoring after a rejected model reload. Full-stream replay remains a CLI task in personal/README.md.

Navigation now has three distinct demo purposes: prediction timing, system reliability, and model evaluation. Removed the separate speaking-notes tab because the guided walkthrough already provides those prompts. The footer stays at the bottom of short pages and follows content on longer pages.

## Checkpoint 21: demonstrating a changed input or requirement

A new seed creates another synthetic stream. Replaying it twice checks deterministic behavior; it does not prove accuracy on real data. Holding the seed fixed while changing capacity isolates the configuration change. Saved inputs, source fingerprints, predictions and snapshots let us investigate failures. Running tests in a fresh process checks local code edits; the API itself must restart to load edited engine modules.

The first three demo pages now emphasize visible state: eligible reading cards, memory/recovery status, and an interactive model-versus-baseline incident display. Supporting explanations stay collapsed. The new-stream API remains available separately for interview exercises.

## Checkpoint 22: repository organization and interview walkthrough

Development order and presentation order serve different purposes. We learned through notebooks, but an interviewer can follow one message through the contract, ingest, time filtering, features and prediction before discussing training and evaluation. Each explanation should identify the choice, reason and test evidence. Personal materials now live under `personal/`; required deliverables remain at the root. The walkthrough also calls out limits, including assumed label completeness and exclusion of immature checkpoints.

The added runbook also belongs to personal preparation and now lives at `personal/README.md`. Essential setup, training, testing and replay commands remain in the root README.

## Checkpoint 23: remove repository clutter

Removed generated Python caches and installation metadata from Git tracking; these are recreated locally. Consolidated improvement priorities into the walkthrough and made FastAPI the single documented full-demo startup. Retained notebooks, exported tables and saved experiment results because they preserve the learning and reproducibility record.

Documentation consolidation: combined the runbook and demo guide into `personal/README.md`. Use it for commands and `WALKTHROUGH.md` for rehearsal; this journal and the plan retain development history.

## Checkpoint 24: verify notebooks after relocation

Audited paths after the move to `personal/`. Notebooks 11–14 now add repository `src/` explicitly before importing shared helpers. A kernel's display label does not establish its Python executable; use the project `.venv` interpreter. Added a temporary-copy checker that executes every notebook in a fresh kernel, including training and fresh-process artifact checks. All 14 notebooks and 28 core/demo tests passed. Saved submission artifacts were not regenerated.
