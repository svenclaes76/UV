"""Demo-mode launch shim for the /run-uvalu skill (docs/demo-mode-plan.md).

Runs the real app.py unmodified with UVALU_DATA_MODE=demo: no sign-in, a
temporary workspace built from demo-data/, no network for market data. Your
own data in data/ and .cache/ is never read or written.

    .venv/Scripts/streamlit.exe run .claude/skills/run-uvalu/_demo_entry.py \\
        --server.port 8530 --server.headless true \\
        --server.sslCertFile "" --server.sslKeyFile ""
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)
os.environ["UVALU_DATA_MODE"] = "demo"

runpy.run_path(str(_ROOT / "app.py"), run_name="__main__")
