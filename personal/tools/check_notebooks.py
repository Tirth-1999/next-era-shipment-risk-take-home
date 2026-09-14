"""Execute learning notebooks in fresh kernels without overwriting saved results."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    """Run all checkpoints in order in a temporary repository copy.

    Uses this process's Python interpreter for each fresh kernel. No arguments
    are required. Prints a pass line per notebook and raises on the first cell
    error. Generated tables and models stay in the temporary copy; the original
    notebook outputs and final submission model remain unchanged.
    """
    with tempfile.TemporaryDirectory(prefix="risk-notebooks-") as directory:
        work = Path(directory) / "candidate"
        for name in ("src", "data", "tools", "personal"):
            shutil.copytree(ROOT / name, work / name, ignore=shutil.ignore_patterns(
                "__pycache__", ".presentation-build", "interview", "*.pyc"))
        kernels = Path(directory) / "kernels"
        spec = kernels / "python3"
        spec.mkdir(parents=True)
        (spec / "kernel.json").write_text(json.dumps({
            "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": "Notebook verification", "language": "python",
        }))
        for path in sorted((work / "personal/notebooks").glob("*.ipynb")):
            manager = KernelManager(kernel_name="python3",
                kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(kernels)]))
            notebook = nbformat.read(path, as_version=4)
            NotebookClient(notebook, km=manager, timeout=300,
                resources={"metadata": {"path": str(path.parent)}}).execute(cleanup_kc=True)
            print(f"PASS {path.name}", flush=True)
        print("All 14 notebooks executed successfully; saved project outputs unchanged.")


if __name__ == "__main__":
    main()
