"""uvalu.buildinfo + tools/stamp_build.py — the version/build metadata single
source (VM-01..VM-06, VD-07, VD-10)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from uvalu import buildinfo

ROOT = Path(__file__).resolve().parents[1]
HAS_GIT = shutil.which("git") is not None


# ── CalVer + naming ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("v", ["2026.10.1", "2026.1.1", "2026.01.3", "2027.12.12"])
def test_calver_accepts(v):
    assert buildinfo.is_calver(v)


@pytest.mark.parametrize("v", ["2.1.1", "2026.13.1", "2026.10.0", "2026.00.1", "26.10.1",
                               "2026.10", "2026.10.1-dev", "v2026.10.1", ""])
def test_calver_rejects(v):
    assert not buildinfo.is_calver(v)


def test_display_version_release_and_dev():
    assert buildinfo.display_version("2026.10.2", is_release=True, commit="a1b2c3d", dirty=False) == "2026.10.2"
    assert buildinfo.display_version("2026.10.2", is_release=False, commit="a1b2c3d", dirty=False) \
        == "2026.10.2-dev+a1b2c3d"
    assert buildinfo.display_version("2026.10.2", is_release=False, commit="a1b2c3d", dirty=True) \
        == "2026.10.2-dev+a1b2c3d.dirty"
    assert buildinfo.display_version("2026.10.2", is_release=False, commit="unknown", dirty=False) \
        == "2026.10.2-dev+unknown"


@pytest.mark.parametrize("raw,want", [
    (None, "development"), ("", "development"), ("dev", "development"), ("Development", "development"),
    ("test", "test"), ("staging", "test"), ("PROD", "production"), ("production", "production"),
    ("qa", "qa"),
])
def test_normalize_environment(raw, want):
    assert buildinfo.normalize_environment(raw) == want


def test_environment_labels():
    assert buildinfo.environment_label("development") == "DEV"
    assert buildinfo.environment_label("test") == "TEST"
    assert buildinfo.environment_label("production") == "PROD"
    assert buildinfo.environment_label("qa") == "QA"


# ── compute() against throw-away git repos ──────────────────────────────────

def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    if not HAS_GIT:
        pytest.skip("git not installed")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "config", "tag.gpgsign", "false")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "2026.10.1"\n')
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_untagged_commit_is_dev_build(repo):
    info = buildinfo.compute(repo, environment="test", now=0)
    sha = _git(repo, "rev-parse", "--short=7", "HEAD")
    assert info.version == "2026.10.1"
    assert info.commit == sha and len(info.commit) == 7
    assert not info.is_release and not info.dirty
    assert info.display_version == f"2026.10.1-dev+{sha}"
    assert info.environment == "test"
    assert info.built_at == "1970-01-01T00:00:00Z"
    assert info.source == "runtime"


def test_annotated_tag_on_head_is_release(repo):
    _git(repo, "tag", "-a", "v2026.10.1", "-m", "release")
    info = buildinfo.compute(repo, environment="production")
    assert info.is_release and info.display_version == "2026.10.1"
    assert info.is_production


def test_lightweight_tag_is_not_a_release(repo):
    _git(repo, "tag", "v2026.10.1")
    assert not buildinfo.compute(repo, environment="test").is_release


def test_tag_for_other_version_is_not_a_release(repo):
    _git(repo, "tag", "-a", "v2026.9.4", "-m", "older")
    assert not buildinfo.compute(repo, environment="test").is_release


def test_commit_after_tag_is_dev(repo):
    _git(repo, "tag", "-a", "v2026.10.1", "-m", "release")
    (repo / "f.txt").write_text("x")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "after")
    info = buildinfo.compute(repo, environment="test")
    assert not info.is_release and "-dev+" in info.display_version


def test_dirty_tree_at_tag_is_dev_dirty(repo):
    _git(repo, "tag", "-a", "v2026.10.1", "-m", "release")
    (repo / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "2026.10.1"\n# edit\n')
    info = buildinfo.compute(repo, environment="test")
    assert info.dirty and not info.is_release
    assert info.display_version.endswith(".dirty")


def test_no_git_degrades_to_unknown(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "2026.10.1"\n')
    monkeypatch.setattr(buildinfo, "_git", lambda *a, **k: None)
    info = buildinfo.compute(tmp_path, environment="development")
    assert info.commit == "unknown" and info.commit_full == "unknown"
    assert info.display_version == "2026.10.1-dev+unknown"
    assert not info.is_release


# ── stamp / load / current ───────────────────────────────────────────────────

def test_write_then_load_round_trip(tmp_path):
    info = buildinfo.compute(ROOT, environment="test")
    path = tmp_path / "build_info.json"
    buildinfo.write(info, path)
    raw = json.loads(path.read_text())
    assert "source" not in raw
    loaded = buildinfo.load(path)
    assert loaded.source == "stamp"
    assert {k: v for k, v in loaded.to_dict().items() if k != "source"} == \
        {k: v for k, v in info.to_dict().items() if k != "source"}


def test_load_rejects_garbage(tmp_path):
    p = tmp_path / "b.json"
    p.write_text("{not json")
    assert buildinfo.load(p) is None
    p.write_text('{"version": "2026.10.1"}')
    assert buildinfo.load(p) is None
    assert buildinfo.load(tmp_path / "missing.json") is None


def test_current_prefers_stamp_and_uses_runtime_environment(tmp_path, monkeypatch):
    stamp = tmp_path / "build_info.json"
    info = buildinfo.compute(ROOT, environment="production")
    buildinfo.write(info, stamp)
    monkeypatch.setattr(buildinfo, "STAMP_FILE", stamp)
    monkeypatch.setattr(buildinfo, "_runtime_environment", lambda: "test")
    buildinfo.reset()
    try:
        cur = buildinfo.current()
        assert cur.source == "stamp"
        assert cur.commit == info.commit and cur.built_at == info.built_at
        assert cur.environment == "test"       # the running process decides the environment
        assert buildinfo.current() is cur      # cached per process
    finally:
        buildinfo.reset()


def test_current_falls_back_to_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(buildinfo, "STAMP_FILE", tmp_path / "absent.json")
    buildinfo.reset()
    try:
        assert buildinfo.current().source == "runtime"
    finally:
        buildinfo.reset()


def test_build_id_combines_version_and_time():
    info = buildinfo.compute(ROOT, environment="test", now=0)
    assert buildinfo.build_id(info) == f"{info.display_version}@1970-01-01T00:00:00Z"


def test_public_dict_shape():
    info = buildinfo.compute(ROOT, environment="test")
    d = buildinfo.public_dict(info, schema_version=3)
    assert set(d) == {"service", "version", "display_version", "commit", "built_at",
                      "environment", "is_release", "schema_version"}
    assert d["schema_version"] == 3
    assert "commit_full" not in d


def test_stamp_tool_writes_both_files_and_check_passes(tmp_path, repo):
    from tools import stamp_build
    info = stamp_build.stamp(environment="test", root=repo, schema_version=1)
    assert (repo / "build_info.json").exists()
    pub = json.loads((repo / "static" / "version.json").read_text())
    assert pub["display_version"] == info.display_version and pub["schema_version"] == 1
    assert stamp_build.check(repo) == 0


def test_stamp_check_fails_without_file(tmp_path):
    from tools import stamp_build
    assert stamp_build.check(tmp_path) == 1


# ── VM-05 / VD-10 guards ─────────────────────────────────────────────────────

@pytest.mark.skipif(not HAS_GIT, reason="git not installed")
def test_build_metadata_files_are_not_tracked():
    tracked = _git(ROOT, "ls-files", "build_info.json", "static/version.json")
    assert tracked == ""
    ignored = subprocess.run(["git", "check-ignore", "build_info.json", "static/version.json"],
                             cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert set(ignored) == {"build_info.json", "static/version.json"}


_LITERAL = re.compile(r"""["']v?\d{4}\.\d{1,2}\.\d+["']""")


def test_no_hard_coded_app_version_in_ui_code():
    """VD-10: the UI never hard-codes a CalVer version — it reads uvalu.buildinfo."""
    files = [ROOT / "app.py", *ROOT.joinpath("uvalu").rglob("*.py")]
    offenders = [f"{p.relative_to(ROOT)}:{i}"
                 for p in files if p.name != "buildinfo.py"
                 for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if _LITERAL.search(line)]
    assert offenders == []
