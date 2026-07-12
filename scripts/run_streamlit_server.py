from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

python = ROOT / ".venv-win" / "Scripts" / "python.exe"
cmd = [
    str(python),
    "-m",
    "streamlit",
    "run",
    str(ROOT / "app.py"),
    "--server.address",
    "127.0.0.1",
    "--server.port",
    "8501",
    "--server.headless",
    "true",
    "--browser.gatherUsageStats",
    "false",
]

env = os.environ.copy()
env["PYTHONUNBUFFERED"] = "1"

with (LOG_DIR / "streamlit.out.log").open("ab", buffering=0) as stdout:
    with (LOG_DIR / "streamlit.err.log").open("ab", buffering=0) as stderr:
        subprocess.call(cmd, cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
