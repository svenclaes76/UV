"""tools/rollback.py + release.schema_of — rolling back to a release tag with
its data schema (VM-10)."""
import shutil
import subprocess
import types
from pathlib import Path

import pytest

from tools import release, rollback
from uvalu.migrations import runner

HAS_GIT = shutil.which("git") is not None


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """v2026.10.1 = baseline only; v2026.10.2 adds migration 2."""
    if not HAS_GIT:
        pytest.skip("git not installed")
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "master")
    for k, v in (("user.email", "t@example.com"), ("user.name", "t"),
                 ("commit.gpgsign", "false"), ("tag.gpgsign", "false")):
        _git(r, "config", k, v)
    mig = r / "uvalu" / "migrations"
    mig.mkdir(parents=True)
    (mig / "__init__.py").write_text("")
    (mig / "m0001_baseline.py").write_text("NUMBER = 1\n")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "one")
    _git(r, "tag", "-a", "v2026.10.1", "-m", "one")
    (mig / "m0002_rename.py").write_text("NUMBER = 2\n")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "two")
    _git(r, "tag", "-a", "v2026.10.2", "-m", "two")
    return r


@pytest.fixture
def ctx(tmp_path):
    c = runner.MigrationContext(tmp_path / "data", tmp_path / "cache")
    c.data_dir.mkdir()
    c.cache_dir.mkdir()
    (c.cache_dir / "users.json").write_text("existing install")
    return c


def _mods(monkeypatch, *, reversible=True):
    def up2(c): (c.data_dir / "m2").write_text("2")
    def down2(c): (c.data_dir / "m2").unlink()
    m1 = types.SimpleNamespace(NUMBER=1, DESCRIPTION="baseline", up=lambda c: None, down=lambda c: None)
    m2 = types.SimpleNamespace(NUMBER=2, DESCRIPTION="rename", up=up2)
    if reversible:
        m2.down = down2
    monkeypatch.setattr(runner, "discover", lambda: [m1, m2])


def test_schema_of_reads_migrations_at_the_tag(repo):
    assert release.schema_of("v2026.10.1", root=repo) == 1
    assert release.schema_of("v2026.10.2", root=repo) == 2


def test_schema_of_release_without_migrations_is_baseline(repo):
    _git(repo, "rm", "-rq", "uvalu")
    _git(repo, "commit", "-q", "-m", "none")
    assert release.schema_of("HEAD", root=repo) == 1


def test_schema_of_unknown_ref(repo):
    with pytest.raises(release.ReleaseError):
        release.schema_of("v1999.01.1", root=repo)


def test_plan_downgrades_then_checks_out(repo, ctx, monkeypatch):
    _mods(monkeypatch)
    runner.upgrade(ctx)
    plan = rollback.make_plan("v2026.10.1", root=repo, ctx=ctx)
    assert (plan.current_schema, plan.target_schema, plan.blocked) == (2, 1, [])
    text = "\n".join(plan.lines())
    assert "downgrade --to 1" in text and "git checkout --detach v2026.10.1" in text
    assert text.index("downgrade") < text.index("git checkout")


def test_plan_without_downgrade(repo, ctx, monkeypatch):
    _mods(monkeypatch)
    runner.upgrade(ctx, target=1)
    plan = rollback.make_plan("v2026.10.1", root=repo, ctx=ctx)
    assert not plan.needs_downgrade
    assert "downgrade" not in "\n".join(plan.lines())


def test_irreversible_migration_blocks_and_names_snapshot(repo, ctx, monkeypatch):
    _mods(monkeypatch, reversible=False)
    runner.upgrade(ctx)
    snap = runner.read_state(ctx)["history"][-1]["snapshot"]
    plan = rollback.make_plan("v2026.10.1", root=repo, ctx=ctx)
    assert plan.blocked == ["2 (rename)"] and plan.snapshot_hint == snap
    assert f"restore-snapshot {snap}" in "\n".join(plan.lines())
    with pytest.raises(release.ReleaseError, match="blocked"):
        rollback.execute(plan, root=repo, ctx=ctx)


def test_execute_downgrades_data_and_checks_out_tag(repo, ctx, monkeypatch):
    _mods(monkeypatch)
    runner.upgrade(ctx)
    rollback.execute(rollback.make_plan("v2026.10.1", root=repo, ctx=ctx), root=repo, ctx=ctx)
    assert runner.current_version(ctx) == 1
    assert not (ctx.data_dir / "m2").exists()
    assert _git(repo, "rev-parse", "HEAD") == _git(repo, "rev-parse", "v2026.10.1^{commit}")


def test_execute_refuses_dirty_tree(repo, ctx, monkeypatch):
    _mods(monkeypatch)
    runner.upgrade(ctx)
    (repo / "uvalu" / "migrations" / "m0001_baseline.py").write_text("NUMBER = 1\n# edit\n")
    with pytest.raises(release.ReleaseError, match="uncommitted"):
        rollback.execute(rollback.make_plan("v2026.10.1", root=repo, ctx=ctx), root=repo, ctx=ctx)
    assert runner.current_version(ctx) == 2           # nothing touched
