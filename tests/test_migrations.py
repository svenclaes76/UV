"""uvalu/migrations — data-schema version, migration runner, start-up check
(VM-08, VM-09) and the snapshot/downgrade path behind rollbacks (VM-10).

conftest's autouse ``_migrations_isolated`` already points the runner at an
empty tmp data dir; tests here build their own MigrationContext on top."""
from __future__ import annotations

import json
import os
import time
import types
import zipfile
from pathlib import Path

import pytest

from uvalu import migrations
from uvalu.migrations import runner

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ctx(tmp_path):
    c = runner.MigrationContext(tmp_path / "data", tmp_path / "cache")
    c.data_dir.mkdir()
    c.cache_dir.mkdir()
    return c


def _seed_existing_install(ctx):
    (ctx.data_dir / "portfolio" / "abc123").mkdir(parents=True)
    (ctx.data_dir / "portfolio" / "abc123" / "portfolio.json").write_text("enc-portfolio")
    (ctx.cache_dir / "users.json").write_text("enc-users")


def _mod(number, *, up=None, down=None, desc=None):
    m = types.ModuleType(f"m{number:04d}_fake")
    m.NUMBER = number
    m.DESCRIPTION = desc or f"fake step {number}"
    m.up = up or (lambda ctx: None)
    if down is not None:
        m.down = down
    return m


@pytest.fixture
def fake_chain(monkeypatch, ctx):
    """Baseline + two reversible steps that write/remove marker files."""
    def up2(c): (c.data_dir / "m2").write_text("2")
    def down2(c): (c.data_dir / "m2").unlink()
    def up3(c): (c.data_dir / "m3").write_text("3")
    def down3(c): (c.data_dir / "m3").unlink()
    mods = [_mod(1, down=lambda c: None), _mod(2, up=up2, down=down2), _mod(3, up=up3, down=down3)]
    monkeypatch.setattr(runner, "discover", lambda: mods)
    return mods


# ── discovery ────────────────────────────────────────────────────────────────

def test_real_migrations_are_numbered_from_one():
    mods = runner.discover()
    assert [m.NUMBER for m in mods] == list(range(1, len(mods) + 1))
    assert mods[0].__name__.endswith("m0001_baseline")
    assert runner.expected_version() == mods[-1].NUMBER


def test_real_migrations_define_down_or_say_irreversible():
    for m in runner.discover():
        assert m.DESCRIPTION and callable(m.up)


# ── baseline ─────────────────────────────────────────────────────────────────

def test_existing_install_is_recorded_at_baseline(ctx, fake_chain):
    _seed_existing_install(ctx)
    applied = runner.upgrade(ctx)
    state = runner.read_state(ctx)
    assert applied == [2, 3]
    assert [h["direction"] for h in state["history"]] == ["baseline", "up", "up"]
    assert state["schema_version"] == 3
    assert (ctx.data_dir / "m2").exists() and (ctx.data_dir / "m3").exists()


def test_fresh_install_starts_at_newest_without_running_steps(ctx, fake_chain):
    assert runner.upgrade(ctx) == []
    state = runner.read_state(ctx)
    assert state["schema_version"] == 3
    assert state["history"][0]["direction"] == "fresh-install"
    assert not (ctx.data_dir / "m2").exists()


def test_history_records_build(ctx, fake_chain):
    from uvalu import buildinfo
    _seed_existing_install(ctx)
    runner.upgrade(ctx)
    h = runner.read_state(ctx)["history"][-1]
    assert h["app_version"] == buildinfo.current().display_version
    assert h["commit"] == buildinfo.current().commit
    assert h["at"].endswith("Z") and h["snapshot"]


# ── upgrade ──────────────────────────────────────────────────────────────────

def test_upgrade_to_target_then_rest(ctx, fake_chain):
    _seed_existing_install(ctx)
    assert runner.upgrade(ctx, target=2) == [2]
    assert runner.current_version(ctx) == 2
    assert runner.upgrade(ctx) == [3]
    assert runner.upgrade(ctx) == []


def test_upgrade_snapshots_first(ctx, fake_chain):
    _seed_existing_install(ctx)
    runner.upgrade(ctx)
    snaps = runner.list_snapshots(ctx)
    assert len(snaps) == 1 and "before-up-1-to-3" in snaps[0]
    with zipfile.ZipFile(ctx.snapshot_dir / f"{snaps[0]}.zip") as zf:
        names = set(zf.namelist())
    assert "data/portfolio/abc123/portfolio.json" in names
    assert "cache/users.json" in names
    assert "data/m2" not in names          # taken before the steps ran


def test_crash_mid_chain_leaves_accurate_version(ctx, monkeypatch):
    def boom(c): raise RuntimeError("disk full")
    mods = [_mod(1), _mod(2, up=lambda c: (c.data_dir / "m2").write_text("2")), _mod(3, up=boom)]
    monkeypatch.setattr(runner, "discover", lambda: mods)
    _seed_existing_install(ctx)
    with pytest.raises(runner.MigrationError) as ei:
        runner.upgrade(ctx)
    assert runner.current_version(ctx) == 2
    assert "migration 3" in str(ei.value) and "restore-snapshot" in str(ei.value)
    assert not (ctx.data_dir / runner.LOCK_NAME).exists()      # lock released


def test_upgrade_refuses_data_from_newer_code(ctx, fake_chain):
    runner._write_state(ctx, {"schema_version": 7, "history": []})
    with pytest.raises(runner.SchemaMismatch):
        runner.upgrade(ctx)


def test_upgrade_from_version_reruns_idempotent_steps(ctx, fake_chain):
    runner.upgrade(ctx)                                  # fresh → 3, nothing ran
    assert runner.upgrade(ctx, from_version=1) == [2, 3]  # restoring a schema-1 backup
    assert (ctx.data_dir / "m3").exists()
    assert runner.current_version(ctx) == 3


# ── downgrade ────────────────────────────────────────────────────────────────

def test_downgrade_reverses_steps_newest_first(ctx, fake_chain):
    _seed_existing_install(ctx)
    runner.upgrade(ctx)
    assert runner.downgrade(1, ctx) == [3, 2]
    assert runner.current_version(ctx) == 1
    assert not (ctx.data_dir / "m2").exists()
    assert [h["direction"] for h in runner.read_state(ctx)["history"]][-2:] == ["down", "down"]


def test_downgrade_refuses_irreversible_and_names_snapshot(ctx, monkeypatch):
    mods = [_mod(1, down=lambda c: None), _mod(2)]       # step 2 has no down()
    monkeypatch.setattr(runner, "discover", lambda: mods)
    _seed_existing_install(ctx)
    runner.upgrade(ctx)
    snap = runner.read_state(ctx)["history"][-1]["snapshot"]
    with pytest.raises(runner.MigrationError, match="irreversible") as ei:
        runner.downgrade(1, ctx)
    assert snap in str(ei.value)
    assert runner.current_version(ctx) == 2


def test_downgrade_needs_the_newer_code(ctx, fake_chain):
    runner._write_state(ctx, {"schema_version": 9, "history": []})
    with pytest.raises(runner.MigrationError, match="newer code"):
        runner.downgrade(1, ctx)


@pytest.mark.parametrize("to", [0, 3, 4])
def test_downgrade_target_bounds(ctx, fake_chain, to):
    _seed_existing_install(ctx)
    runner.upgrade(ctx)
    with pytest.raises(runner.MigrationError):
        runner.downgrade(to, ctx)


def test_round_trip_restores_identical_files(ctx, fake_chain):
    """VM-10 rehearsal: upgrade → downgrade → upgrade leaves the data as it was."""
    _seed_existing_install(ctx)

    def files():
        return {p.relative_to(ctx.data_dir).as_posix(): p.read_bytes()
                for p in ctx.data_dir.rglob("*") if p.is_file()
                and runner.SNAPSHOT_DIRNAME not in p.parts and p.name != runner.STATE_NAME}

    runner.upgrade(ctx)
    after_up = files()
    runner.downgrade(1, ctx)
    runner.upgrade(ctx)
    assert files() == after_up


# ── lock ─────────────────────────────────────────────────────────────────────

def test_concurrent_run_is_refused(ctx, fake_chain):
    (ctx.data_dir / runner.LOCK_NAME).write_text("123")
    with pytest.raises(runner.MigrationError, match="another migration"):
        runner.upgrade(ctx)


def test_stale_lock_is_broken(ctx, fake_chain):
    lock = ctx.data_dir / runner.LOCK_NAME
    lock.write_text("123")
    old = time.time() - runner._LOCK_STALE_S - 60
    os.utime(lock, (old, old))
    runner.upgrade(ctx)
    assert not lock.exists()


# ── snapshots ────────────────────────────────────────────────────────────────

def test_snapshot_skips_backups_and_snapshots(ctx):
    _seed_existing_install(ctx)
    (ctx.data_dir / "backups").mkdir()
    (ctx.data_dir / "backups" / "x.zip").write_text("b")
    runner.snapshot(ctx, "one")
    second = runner.snapshot(ctx, "two")
    with zipfile.ZipFile(ctx.snapshot_dir / f"{second}.zip") as zf:
        names = zf.namelist()
    assert "data/portfolio/abc123/portfolio.json" in names
    assert not any(n.startswith("data/backups/") or runner.SNAPSHOT_DIRNAME in n for n in names)


def test_snapshots_are_pruned(ctx, monkeypatch):
    monkeypatch.setattr(runner, "KEEP_SNAPSHOTS", 2)
    ctx.snapshot_dir.mkdir(parents=True)
    for i in range(4):
        (ctx.snapshot_dir / f"2026010{i}T000000Z-x.zip").write_bytes(b"z")
    runner._prune_snapshots(ctx)
    assert runner.list_snapshots(ctx) == ["20260103T000000Z-x", "20260102T000000Z-x"]


def test_restore_snapshot_puts_data_and_schema_back(ctx, fake_chain):
    _seed_existing_install(ctx)
    runner.upgrade(ctx, target=2)
    (ctx.cache_dir / "users.json").write_text("changed")
    runner.upgrade(ctx)                                  # snapshot at schema 2, then → 3
    snap = runner.read_state(ctx)["history"][-1]["snapshot"]
    (ctx.cache_dir / "users.json").write_text("changed again")
    n = runner.restore_snapshot(snap, ctx)
    assert n >= 3
    assert runner.current_version(ctx) == 2
    assert (ctx.cache_dir / "users.json").read_text() == "changed"


def test_restore_unknown_snapshot(ctx):
    with pytest.raises(runner.MigrationError, match="no snapshot"):
        runner.restore_snapshot("nope", ctx)


# ── start-up check (VM-09) ───────────────────────────────────────────────────

def test_check_records_baseline_when_missing(ctx, fake_chain):
    assert runner.ensure_compatible(ctx) == 3            # fresh install
    assert runner.read_state(ctx)["schema_version"] == 3


def test_check_refuses_existing_install_before_upgrade(ctx, fake_chain, caplog):
    _seed_existing_install(ctx)
    with pytest.raises(runner.SchemaMismatch) as ei:
        runner.ensure_compatible(ctx)
    assert (ei.value.on_disk, ei.value.expected) == (1, 3)
    assert "python -m uvalu.migrations upgrade" in str(ei.value)
    rec = [r for r in caplog.records if getattr(r, "event", None) == "startup.schema_mismatch"]
    assert rec and rec[0].levelname == "CRITICAL"


def test_check_refuses_newer_data(ctx, fake_chain):
    runner._write_state(ctx, {"schema_version": 4, "history": []})
    with pytest.raises(runner.SchemaMismatch, match="downgrade --to 3"):
        runner.ensure_compatible(ctx)


def test_check_refuses_corrupt_state(ctx, fake_chain):
    ctx.state_file.write_text("{oops")
    with pytest.raises(runner.SchemaMismatch) as ei:
        runner.ensure_compatible(ctx)
    assert ei.value.on_disk is None


def test_check_message_names_version_and_commit(ctx, fake_chain):
    from uvalu import buildinfo
    runner._write_state(ctx, {"schema_version": 2, "history": []})
    with pytest.raises(runner.SchemaMismatch) as ei:
        runner.ensure_compatible(ctx)
    info = buildinfo.current()
    assert info.display_version in str(ei.value) and info.commit in str(ei.value)


def test_check_success_is_cached_mismatch_is_not(ctx, fake_chain):
    runner._write_state(ctx, {"schema_version": 2, "history": []})
    with pytest.raises(runner.SchemaMismatch):
        runner.ensure_compatible(ctx)
    runner._write_state(ctx, {"schema_version": 3, "history": []})
    assert runner.ensure_compatible(ctx) == 3            # fixed without a restart
    ctx.state_file.write_text("{oops")
    assert runner.ensure_compatible(ctx) == 3            # success remembered


# ── backups carry the schema ─────────────────────────────────────────────────

def test_backup_records_and_checks_schema(isolated_data, monkeypatch):
    import backup
    email = "test@example.com"
    meta = json.loads(zipfile.ZipFile(__import__("io").BytesIO(backup.export_zip(email))).read("meta.json"))
    assert meta["schema_version"] == runner.expected_version()

    newer = __import__("io").BytesIO()
    with zipfile.ZipFile(newer, "w") as zf:
        zf.writestr("data/watchlist.json", "x")
        zf.writestr("meta.json", json.dumps({"schema_version": 99}))
    with pytest.raises(ValueError, match="newer Uvalu version"):
        backup.import_zip(newer.getvalue(), email)


def test_older_backup_reruns_migrations(isolated_data, monkeypatch):
    import backup
    calls = []
    monkeypatch.setattr(migrations, "expected_version", lambda: 3)
    monkeypatch.setattr(migrations, "upgrade", lambda **kw: calls.append(kw) or [])
    legacy = __import__("io").BytesIO()
    with zipfile.ZipFile(legacy, "w") as zf:            # no meta.json → schema 1
        zf.writestr("data/watchlist.json", "x")
    assert backup.import_zip(legacy.getvalue(), "test@example.com") == ["watchlist.json"]
    assert calls == [{"from_version": 1}]


# ── CLI ──────────────────────────────────────────────────────────────────────

def test_cli_status_and_upgrade(capsys):
    from uvalu.migrations import __main__ as cli
    assert cli.main(["status"]) == 0
    assert "not recorded yet" in capsys.readouterr().out
    assert cli.main(["upgrade"]) == 0
    assert cli.main(["status"]) == 0
    assert "applied" in capsys.readouterr().out


def test_cli_restore_needs_yes(capsys):
    from uvalu.migrations import __main__ as cli
    assert cli.main(["restore-snapshot", "x"]) == 1


# ── app.py refuses to serve on a mismatch ────────────────────────────────────

def test_app_shows_maintenance_screen_on_mismatch():
    from streamlit.testing.v1 import AppTest
    c = runner.default_context()
    runner._write_state(c, {"schema_version": runner.expected_version() + 1, "history": []})
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "Uvalu is being updated" in text
    assert not at.text_input                                # the sign-in form never rendered


# ── m0002: drop unused fields, fill dividend currency ────────────────────────

def test_m0002_drops_unused_fields_and_fills_currency(ctx, monkeypatch):
    from uvalu.migrations import m0002_drop_unused_fields as m2
    monkeypatch.setenv("ENCRYPTION_KEY", "unit-test-key-123")
    udir = ctx.data_dir / "portfolio" / "abc123"
    udir.mkdir(parents=True)
    ctx.write_json(udir / "portfolio.json", [{"ticker": "AED.BR", "google_ticker": "EBR:AED",
                                              "target_price": 100, "account": "", "shares": 30}])
    ctx.write_json(udir / "sold.json", [{"ticker": "KIN.BR", "google_ticker": "EBR:KIN", "shares": 60}])
    ctx.write_json(udir / "dividends_history.json", [
        {"ticker": "ROG.SW", "google_ticker": "SWX:ROG", "amount": 76.8, "currency": None, "declaration_date": None,
         "record_date": None, "reinvested": False, "reinvested_shares": None},
        {"ticker": "ABI.BR", "amount": 32.8},
        {"ticker": "NESN.SW", "amount": 10, "currency": "EUR"},
    ])
    m2.up(ctx)
    m2.up(ctx)   # idempotent
    assert ctx.read_json(udir / "portfolio.json") == [{"ticker": "AED.BR", "shares": 30}]
    assert ctx.read_json(udir / "sold.json") == [{"ticker": "KIN.BR", "shares": 60}]
    assert ctx.read_json(udir / "dividends_history.json") == [
        {"ticker": "ROG.SW", "amount": 76.8, "currency": "CHF"},
        {"ticker": "ABI.BR", "amount": 32.8, "currency": "EUR"},
        {"ticker": "NESN.SW", "amount": 10, "currency": "EUR"},
    ]
