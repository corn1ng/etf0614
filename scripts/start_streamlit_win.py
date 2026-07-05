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
    "app.py",
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
CREATE_BREAKAWAY_FROM_JOB = 0x01000000

stdout_path = LOG_DIR / "streamlit.out.log"
stderr_path = LOG_DIR / "streamlit.err.log"
launcher_path = LOG_DIR / "streamlit.launcher.log"
stdout = stdout_path.open("ab", buffering=0)
stderr = stderr_path.open("ab", buffering=0)

with launcher_path.open("a", encoding="utf-8") as launcher:
    try:
        process = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB,
        )
    except Exception as exc:
        launcher.write(f"failed: {exc!r}\n")
        raise
    launcher.write(f"started pid={process.pid}\n")
