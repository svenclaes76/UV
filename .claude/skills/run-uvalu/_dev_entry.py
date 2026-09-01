"""Dev launch shim for the uvalu Streamlit app — used by the /run-uvalu skill.

`streamlit run app.py` drops you on a login wall, and an agent can't type a
password into a form. This entry file runs the real app.py unmodified, but
first mints a short-lived session token for whatever account is already
registered, so the authenticated screens (Dashboard / Risk / Analysis /
Portfolio) render straight away.

Nothing on disk is patched. This file is dev-only and is never imported by
app.py or shipped in a deployment. To run WITH the login wall, just launch
app.py directly instead of this file.

    .venv/Scripts/streamlit.exe run .claude/skills/run-uvalu/_dev_entry.py \
        --server.port 8520 --server.headless true \
        --server.sslCertFile "" --server.sslKeyFile ""

The empty sslCertFile / sslKeyFile args override .streamlit/config.toml,
which otherwise forces a self-signed cert the in-app preview browser rejects.
"""
from __future__ import annotations

import os
import runpy
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# `streamlit run` puts THIS file's directory on sys.path[0], not the repo
# root, so `import auth` / `import uvalu` would fail. Fix the path and the CWD
# before touching anything else (the app resolves .streamlit/, .cache/ and
# data/ relative to the process CWD).
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

import streamlit as st  # noqa: E402
import auth as _auth  # noqa: E402
import jwt as _jwt  # noqa: E402

# Sign a 2h session token for the first registered account (the bootstrap
# user is an Admin). app.py's auth_wall() then validates this JWT through its
# normal code path and lets the request through — no source patch, no
# password entry.
if not st.session_state.get("jwt_token"):
    _users = _auth._load_users()
    if _users:
        _email = next(iter(_users))
        _role = _users[_email].get("role", "Analyst")
        st.session_state["jwt_token"] = _jwt.encode(
            {
                "sub": _email,
                "role": _role,
                "exp": datetime.now(timezone.utc) + timedelta(hours=2),
                "iat": datetime.now(timezone.utc),
            },
            _auth._JWT_SECRET,
            algorithm=_auth._JWT_ALGO,
        )
        # app.py calls set_user(current_user().email) BEFORE auth_wall()
        # populates it from the token, so seed these now or the first render
        # points the data layer at the empty default bucket ("No portfolio
        # yet") until the next rerun.
        st.session_state["user_email"] = _email
        st.session_state["user_role"] = _role
    else:
        st.error(
            "No account registered. Create one first, then relaunch:\n\n"
            "    .venv/Scripts/python.exe -c \"import auth; "
            "print(auth.register('dev@local', 'devpass12345'))\""
        )
        st.stop()

runpy.run_path(str(_ROOT / "app.py"), run_name="__main__")
