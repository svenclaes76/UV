---
name: run-uvalu
description: >-
  Build, launch, smoke-test, screenshot, or interactively drive the uvalu
  Streamlit app (European stock value screener + portfolio manager). Use when
  asked to run / start / serve / preview the app, take a screenshot of a
  screen, verify a change renders, or drive the Dashboard / Risk / Analysis /
  Portfolio / Screener pages.
---

# Run uvalu

`uvalu` is a single-process **Streamlit web app** (`app.py`). It's driven
headless in two layers:

- **Liveness** — `.claude/skills/run-uvalu/smoke.py` launches it and checks
  the routes respond. No browser, no extra deps. ~15 s.
- **Interactive** — launch `_dev_entry.py` with Streamlit, then drive it with
  the in-app **Browser pane** (`preview_start` / `mcp__Claude_Browser__*`):
  `navigate` by URL, read with `get_page_text`, screenshot with `computer`.

Two project-specific hurdles, both already handled by the scripts here:

1. `.streamlit/config.toml` forces a **self-signed TLS cert** the preview
   browser rejects — every launch passes `--server.sslCertFile "" --server.sslKeyFile ""` to fall back to plain HTTP.
2. Every screen except the login wall is **behind auth**, and an agent can't
   type a password. `_dev_entry.py` runs `app.py` unmodified but first signs a
   2-hour session token for the already-registered account.

All paths below are relative to the repo root. This is a **Windows** checkout
— the venv is `.venv/Scripts/`, not `.venv/bin/`.

## Prerequisites

The repo ships a populated `.venv/`. If it's missing or stale:

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

An account must already exist in `.cache/users.json` (encrypted). If it's a
fresh machine with no account, create one (any values — it's local, and the
first account is auto-promoted to Admin):

```bash
.venv/Scripts/python.exe -c "import auth; print(auth.register('dev@local', 'devpass12345'))"
```

## Build

None. Pure Python; Streamlit serves `app.py` directly.

## Run — liveness smoke (fastest)

```bash
.venv/Scripts/python.exe .claude/skills/run-uvalu/smoke.py
```

Exit 0 = the server came up and `/`, `/risk`, `/analysis`, `/portfolio`,
`/screener` all return 200. It tears the server down on exit. `--keep` leaves
it running; `--port N` changes the port (default 8521).

Streamlit renders client-side over a websocket, so a 200 means "route exists",
**not** "screen rendered". For that, use the interactive path.

## Run — interactive (drive real screens)

1. Launch the app (background). SSL off; `_dev_entry.py` handles auth:

   ```bash
   nohup .venv/Scripts/streamlit.exe run .claude/skills/run-uvalu/_dev_entry.py \
     --server.port 8520 --server.headless true \
     --server.sslCertFile "" --server.sslKeyFile "" > /tmp/uvalu_run.log 2>&1 &
   ```

2. Wait ~12 s, then confirm it's up:

   ```bash
   .venv/Scripts/python.exe -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8520/_stcore/health', timeout=10).read())"
   ```

   Expect `b'ok'`.

3. Open it in the Browser pane and drive it:
   - `mcp__Claude_Browser__navigate` → `http://localhost:8520/` (Dashboard).
   - **Navigate to other pages by URL**, not by clicking the top nav:
     `http://localhost:8520/risk`, `/analysis`, `/portfolio`, `/screener`,
     `/watchlist`, `/settings`, `/admin`. (Top-bar `st.page_link` clicks do
     **not** register through the pane — see Gotchas.)
   - After each navigate, `sleep 8-10` before reading — first render of a
     page is slow.
   - Verify with `mcp__Claude_Browser__get_page_text` (exact numbers, labels).
     Use `computer {action:"screenshot"}` for layout, but prefer text.

4. Stop when done:

   ```bash
   powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8520 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id \$_ -Force }"
   ```

## Run — human path

```bash
.venv/Scripts/python.exe run_app.py
```

Generates a localhost TLS cert and serves `https://localhost:8502` with the
real login wall. Useless headless (needs a human to log in), and the
self-signed cert blocks the preview browser — hence `_dev_entry.py` for
agents.

## Test

```bash
.venv/Scripts/python.exe -m pytest -q
```

~900 tests, ~2 min. AppTest-based; no browser needed.

## Gotchas

- **Self-signed TLS.** `.streamlit/config.toml` sets `sslCertFile`/`sslKeyFile`.
  `streamlit run` then serves **https** and the preview browser silently
  refuses the cert (`navigation … denied or failed`, nothing renders). Always
  pass `--server.sslCertFile "" --server.sslKeyFile ""`. `.claude/launch.json`
  carries these too, so `preview_start name:uvalu` also works — but it does
  **not** set the auth shim, so it lands on the login wall.
- **Auth wall.** `app.py` → `authgate.auth_wall()` `st.stop()`s without a valid
  JWT. `_dev_entry.py` signs one from `.cache/users.json` + `auth._JWT_SECRET`
  before `runpy`-ing `app.py`. It also pre-seeds `st.session_state["user_email"]`
  / `["user_role"]` — `app.py` calls `set_user(current_user().email)` *before*
  `auth_wall()` populates it, so without the seed the first render points at
  the empty default bucket and shows **"No portfolio yet"**.
- **Top-nav clicks don't work through the Browser pane.** Clicking the
  Dashboard/Risk/… `st.page_link`s (by coordinate or by `ref`) does nothing.
  Navigate by URL path instead (`/risk`, `/analysis`, …).
- **Screenshot coordinates are scaled.** The pane returns an ~800px-wide image
  even at a 1440px emulated viewport, so `computer` clicks by raw coordinate
  miss. Use `ref` from `find`/`read_page`, or `resize_window {preset:"desktop"}`.
- **Row → drawer clicks are flaky.** The Holdings / risk-table rows open a
  detail drawer via an invisible full-row overlay button; clicking it through
  the pane often doesn't fire. To inspect the drawer / Analysis page, set the
  ticker directly: navigate to `/analysis` after the app has stored
  `_analysis_ticker` — or just read the table via `get_page_text`, which
  carries every number.
- **First page render ≈ 8-12 s.** Streamlit boots, then the page does its own
  background price/fundamentals fetches. Reading too early gets a half-page.
- **Log noise.** `$COFB.BR: possibly delisted` / `ROG.SW … Quote not found` in
  the launch log are stale tickers in the universe — harmless, not a failure.
- **`.venv/Scripts/python.exe -m pytest`**, not bare `pytest` / `python` — the
  system Python (3.14) has none of the deps; only the venv does.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `navigation to https://localhost:… denied or failed`, blank pane | You launched with TLS. Relaunch with `--server.sslCertFile "" --server.sslKeyFile ""`. |
| App renders but shows **"No portfolio yet"** despite a real account | Using bare `app.py` / `launch.json` (login wall) instead of `_dev_entry.py`, or the session seed didn't take — relaunch via `_dev_entry.py`. |
| `_dev_entry.py` shows "No account registered" | Run the `auth.register(...)` line from Prerequisites, then relaunch. |
| `smoke.py` → `FAIL: /_stcore/health never came up` | Check `/tmp/uvalu_run.log` (or run streamlit in the foreground). Usually a missing dep — `pip install -r requirements.txt`. |
| `ModuleNotFoundError` on launch | Wrong Python. Use `.venv/Scripts/python.exe` / `.venv/Scripts/streamlit.exe`. |
| Port already in use | Kill it: `powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8520 -State Listen | %{ Stop-Process -Id $_.OwningProcess -Force }"` |
