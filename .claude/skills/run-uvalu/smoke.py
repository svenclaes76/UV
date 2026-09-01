"""Fast liveness smoke for the uvalu Streamlit app — no browser, no extra deps.

Launches the app through _dev_entry.py (SSL off + an auto-signed session so
the auth wall is passed), waits for /_stcore/health, checks that the page
routes respond 200, prints a PASS/FAIL line, and always tears the server
down.

NOTE: Streamlit renders client-side over a websocket, so a 200 here means
"the server is up and the route exists", NOT "the screen rendered
correctly". For that, drive it with the in-app Browser pane — see SKILL.md.

    .venv/Scripts/python.exe .claude/skills/run-uvalu/smoke.py
    echo $?     # 0 = pass

Optional: --port N (default 8521), --keep (leave the server running).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENTRY = Path(__file__).with_name("_dev_entry.py")
STREAMLIT = ROOT / ".venv" / "Scripts" / "streamlit.exe"
ROUTES = ("/", "/risk", "/analysis", "/portfolio", "/screener")


def _get(url: str, timeout: float = 10.0) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
        return r.status, r.read(64)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8521)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    base = f"http://localhost:{args.port}"

    proc = subprocess.Popen(
        [str(STREAMLIT), "run", str(ENTRY),
         "--server.port", str(args.port), "--server.headless", "true",
         "--server.sslCertFile", "", "--server.sslKeyFile", ""],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        # Wait up to 40s for the health endpoint.
        deadline = time.time() + 40
        while time.time() < deadline:
            try:
                if _get(f"{base}/_stcore/health")[1].strip() == b"ok":
                    break
            except Exception:
                time.sleep(1)
        else:
            print("FAIL: /_stcore/health never came up")
            return 1

        failures = []
        for route in ROUTES:
            try:
                status, _ = _get(base + route)
                mark = "ok" if status == 200 else f"HTTP {status}"
                if status != 200:
                    failures.append(route)
            except Exception as e:  # noqa: BLE001
                mark, _ = f"ERR {e}", failures.append(route)
            print(f"  {route:<12} {mark}")

        if failures:
            print(f"FAIL: {', '.join(failures)}")
            return 1
        print(f"PASS: uvalu up on {base} ({len(ROUTES)} routes 200)")
        if args.keep:
            print(f"--keep: server left running (pid {proc.pid}); Ctrl-C to stop")
            proc.wait()
        return 0
    finally:
        if not args.keep:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
