# My shipment risk project plan

## My goal

I want to explain and demonstrate a system that predicts the chance of a shipment incident in the next six hours. I need to show which information was available at each prediction time, how I turned it into model inputs, and how I checked the predictions later.

My implementation, fourteen notebooks and local demo are complete. My current focus is interview practice and understanding the limits of the solution. The latest checks passed 27 tests and all 14 notebooks. The saved evaluation has 309 checkpoints and 25 positives, with average precision 0.981277 and Brier score 0.003760. These results come from synthetic data.

## How I worked through the project

| Stage | What I worked on | What I took into the next stage |
| --- | --- | --- |
| Notebooks 1–2 | Read the data and followed duplicates and corrections | I must select the version available at the checkpoint |
| Notebooks 3–4 | Compared the two clocks and calculated temperature features | Reading age, arrival delay and recent trend answer different questions |
| Notebook 5 | Converted JSON into tables | I can inspect the data while preserving delivery order |
| Notebooks 6–7 | Studied incident reports and reporting delays | An absent report can mean the outcome is still unknown |
| Notebooks 8–9 | Built examples and measured a constant baseline | I need a clear target and a simple comparison |
| Notebook 10 | Studied how logistic regression learns | Weights and the starting score change during fitting |
| Notebooks 11–12 | Split shipments by time and compared models | I choose the model on validation data |
| Notebooks 13–14 | Evaluated the chosen model and checked saved files | I can load the model in a separate process and repeat predictions |
| Python package | Added shared features, memory limits, recovery and reload | I can test the required engine behavior |
| Demo and CLI practice | Built examples for explaining and exercising the engine | I can show evidence for each claim during the interview |

The detailed history stays in [my learning journal](MY_LEARNINGS.md). I use this plan for my current priorities.

## The decisions I need to explain

I use information received by the prediction time. I keep earlier revisions while their history is stored. I identify duplicates by event ID and revision.

I use a three hour temperature window and a six hour incident window. I allow another 48 hours for reports before using a training example. That wait assumes older reports are complete; it is not proof of completeness.

I split shipments into groups ordered by time. I fit input preparation on fitting rows and choose the model on validation results. Logistic regression met the declared selection rule. The final test does not select another model.

I limit stored shipment histories and records. When history is removed, I explain the missing coverage in the prediction. I save history consistently and keep it during model reload. If reload fails, the current model stays active.

My full responses to the customer suggestions are in [DECISIONS.md](../DECISIONS.md).

## My remaining work

1. I will rehearse the opening and follow one message through the code using [my walkthrough](WALKTHROUGH.md).
2. I will run the five CLI exercises: a new stream, a failed rule, a changed requirement, evaluation questions, and a small code edit.
3. I will practise explaining the failed test before describing the fix. I will compare saved replay outputs after the change.
4. I will review the label contract gap. My builder leaves out checkpoints still waiting for reports, while the assignment asks for a binary label at every checkpoint. I must state this clearly.
5. I will explain the remaining deployment work: confirmed report coverage, real data evaluation, measured resource use and an alert cutoff based on operating costs.

I do not need to add model complexity or more demo controls to complete this rehearsal. If the interviewer changes a requirement, I will clarify the expected result, edit the responsible code and test that change.

## How I want my notes to read

I use plain English, short explanations and concrete examples. I keep technical names when they help me find the code, then explain what they mean. I want to understand an answer well enough to say it in my own words.

I record what was tested and what remains uncertain. I keep results from real work separate from rehearsal examples. After each checkpoint, I add what I tried, what happened, why I chose the approach and what I still need to understand to my learning journal.

## Where I start each practice session

I use [personal/README.md](README.md) for setup and commands. I select the repository's `.venv/bin/python` kernel for notebooks. I run the notebook checker when I change notebook paths or shared helpers.

I use [walkthrough section 7](WALKTHROUGH.md#7-cli-rehearsal-for-the-five-follow-up-tasks) for terminal practice. I save new inputs and replay evidence in a separate folder so I keep the original model and evaluation intact.
