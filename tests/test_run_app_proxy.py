"""run_app.py's production mode behind the reverse proxy (SR2,
docs/deployment.md)."""

import run_app


def test_behind_proxy_listens_on_localhost_over_plain_http():
    args = run_app._streamlit_args("8501", behind_proxy=True)
    joined = " ".join(args)
    assert "--server.address 127.0.0.1" in joined
    assert "--server.sslCertFile" not in args       # TLS is Caddy's job
    assert "--server.enableXsrfProtection true" in joined


def test_local_launch_serves_the_self_signed_cert():
    args = run_app._streamlit_args("8501", behind_proxy=False)
    assert "--server.address" not in args
    i = args.index("--server.sslCertFile")
    assert args[i + 1] == str(run_app.CERT_FILE)
    assert args[args.index("--server.sslKeyFile") + 1] == str(run_app.KEY_FILE)


def test_committed_config_starts_without_a_certificate():
    """DM-6: Community Cloud runs the committed config and has no .ssl/."""
    import tomllib
    cfg = tomllib.loads((run_app.ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    server = cfg.get("server", {})
    assert "sslCertFile" not in server and "sslKeyFile" not in server
    assert cfg.get("browser", {}).get("gatherUsageStats") is False
