"""Roll Uvalu back to an earlier release (VM-10). Runbook:
docs/operations/release-and-rollback.md.

Usage (stop the app first):
    python tools/rollback.py --to v2026.10.1          # dry run: prints the plan
    python tools/rollback.py --to v2026.10.1 --yes    # downgrade data, check out the tag

Order matters: the data is downgraded *with the current code*, because only
the newer code knows how to undo its own migrations. Then the tag is checked
out (detached). Start the app again with ``python run_app.py``.

An irreversible migration on the way down stops the rollback; the message
names the snapshot taken before that migration, to restore with
``python -m uvalu.migrations restore-snapshot <id> --yes`` instead.
Roll forward again with ``git checkout master`` + ``python run_app.py``.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.release import ReleaseError, _git, schema_of  # noqa: E402


@dataclass
class Plan:
    tag: str
    current_schema: "int | None"
    target_schema: int
    blocked: "list[str]"
    snapshot_hint: "str | None"

    @property
    def needs_downgrade(self) -> bool:
        return self.current_schema is not None and self.current_schema > self.target_schema

    def lines(self) -> "list[str]":
        out = [f"Roll back to {self.tag} (data schema {self.target_schema}; "
               f"now {self.current_schema if self.current_schema is not None else 'not recorded'})."]
        n = 1
        if self.needs_downgrade:
            if self.blocked:
                out.append(f"  BLOCKED: irreversible migration(s) {', '.join(self.blocked)}.")
                if self.snapshot_hint:
                    out.append(f"  Restore the snapshot instead: python -m uvalu.migrations "
                               f"restore-snapshot {self.snapshot_hint} --yes")
                return out
            out.append(f"  {n}. python -m uvalu.migrations downgrade --to {self.target_schema}   (current code)")
            n += 1
        out.append(f"  {n}. git checkout --detach {self.tag}")
        out.append(f"  {n + 1}. python run_app.py")
        return out


def make_plan(tag: str, *, root: Path = ROOT, ctx=None) -> Plan:
    from uvalu.migrations import runner
    target = schema_of(tag, root=root)
    current = runner.current_version(ctx)
    blocked: list[str] = []
    hint = None
    if current is not None and current > target:
        mods = {m.NUMBER: m for m in runner.discover()}
        if current > max(mods):
            raise ReleaseError(f"data is at schema {current}, newer than this code knows ({max(mods)}) — "
                               "run the rollback from the newest code")
        blocked = [f"{n} ({mods[n].DESCRIPTION})" for n in range(current, target, -1)
                   if not runner.is_reversible(mods[n])]
        if blocked:
            first = int(blocked[-1].split()[0])
            state = runner.read_state(ctx) or {}
            snaps = [h.get("snapshot") for h in state.get("history", [])
                     if h.get("direction") == "up" and h.get("number") == first and h.get("snapshot")]
            hint = snaps[-1] if snaps else None
    return Plan(tag, current, target, blocked, hint)


def execute(plan: Plan, *, root: Path = ROOT, ctx=None) -> None:
    from uvalu.migrations import runner
    if plan.blocked:
        raise ReleaseError("rollback blocked by an irreversible migration — see the plan")
    if _git("status", "--porcelain", "--untracked-files=no", root=root):
        raise ReleaseError("the working tree has uncommitted changes — commit or stash them first")
    if plan.needs_downgrade:
        runner.downgrade(plan.target_schema, ctx)
    _git("checkout", "--quiet", "--detach", plan.tag, root=root)


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="Roll Uvalu back to an earlier release tag")
    ap.add_argument("--to", required=True, help="release tag, e.g. v2026.10.1")
    ap.add_argument("--yes", action="store_true", help="carry out the plan (default: dry run)")
    args = ap.parse_args(argv)
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        plan = make_plan(args.to)
        print("\n".join(plan.lines()))
        if not args.yes:
            print("\nDry run — nothing changed. Stop the app, then run again with --yes.")
            return 1 if plan.blocked else 0
        execute(plan)
        print(f"\nRolled back to {args.to}. Start it with: python run_app.py")
    except Exception as exc:          # ReleaseError, MigrationError
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
