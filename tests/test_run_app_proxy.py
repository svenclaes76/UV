"""run_app.py's production mode behind the reverse proxy (SR2,
docs/deployment.md)."""

import run_app


def test_behind_proxy_listens_on_localhost_over_plain_http():
    args = run_app._streamlit_args("8501", behind_proxy=True)
    joined = " ".join(args)
    assert "--server.address 127.0.0.1" in joined
    i = args.index("--server.sslCertFile")
    assert args[i + 1] == ""          # TLS is Caddy's job
    assert "--server.enableXsrfProtection true" in joined


def test_local_launch_keeps_the_defaults():
    args = run_app._streamlit_args("8501", behind_proxy=False)
    assert "--server.address" not in args
    assert "--server.sslCertFile" not in args
