# Tirth's interview preparation

Start with [WALKTHROUGH.md](WALKTHROUGH.md). It gives the opening explanation, code order, decision rationale, and follow-up practice.

| Folder or file | Use |
| --- | --- |
| `RUNBOOK.md` | Commands for running, replaying and rehearsing recovery |
| `notebooks/` | Learning checkpoints 1–14; open in order |
| `MY_LEARNINGS.md` | What each checkpoint taught us |
| `plan.md` | Development plan and history |
| `IMPROVEMENTS.md` | Known gaps and improvement priorities |
| `demo/` | Optional browser demo and FastAPI interview tools |
| `tests/` | Optional demo/API tests |
| `data/tables/` | Tables exported during exploration |
| `outputs/` | Notebook results, experimental model, presentation and local run evidence |
| `tools/` | Presentation exporter and notebook-artifact verifier |

Run commands from the **repository root**, not this folder:

```bash
python -m pip install -e '.[dev,demo,notebook]'
PYTHONPATH=src .venv/bin/python -m uvicorn personal.demo.api:app --host 127.0.0.1 --port 8765
```

For uv: `uv sync --extra dev --extra demo --extra notebook`.

- Demo: http://127.0.0.1:8765/
- API requests: http://127.0.0.1:8765/docs
- Presentation: http://127.0.0.1:8765/presentation

```bash
PYTHONPATH=src:. .venv/bin/python -m pytest tests personal/tests
python personal/tools/export_presentation.py
```

The default `pytest` command runs only the submission tests. Optional materials remain in GitHub but are grouped here; this is organization, not privacy protection. Omit this whole folder from a reviewer-only copy if desired. The original assignment text remains in the root README. The first Git commit already contained the completed implementation, so Git cannot reconstruct the untouched starter repository; separation follows the assignment requirements and development record.
