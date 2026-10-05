"""CLI for the data-schema migrations. Stop the app before upgrade/downgrade/restore.

    python -m uvalu.migrations status
    python -m uvalu.migrations upgrade [--to N]
    python -m uvalu.migrations downgrade --to N
    python -m uvalu.migrations snapshots
    python -m uvalu.migrations restore-snapshot <id> --yes
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")   # ENCRYPTION_KEY for migrations that read data

from uvalu.migrations import runner  # noqa: E402


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m uvalu.migrations", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("upgrade")
    p.add_argument("--to", type=int)
    p = sub.add_parser("downgrade")
    p.add_argument("--to", type=int, required=True)
    sub.add_parser("snapshots")
    p = sub.add_parser("restore-snapshot")
    p.add_argument("snapshot_id")
    p.add_argument("--yes", action="store_true", help="confirm: overwrites the current data files")
    args = ap.parse_args(argv)

    try:
        if args.cmd == "status":
            state = runner.read_state()
            expected = runner.expected_version()
            on_disk = state["schema_version"] if state else None
            print(f"data schema:     {on_disk if on_disk is not None else 'not recorded yet'}")
            print(f"code expects:    {expected}")
            for m in runner.discover():
                mark = "applied" if on_disk is not None and m.NUMBER <= on_disk else "pending"
                rev = "" if runner.is_reversible(m) else "  (irreversible)"
                print(f"  {m.NUMBER:>4}  {mark:<8} {m.DESCRIPTION}{rev}")
            for h in (state or {}).get("history", [])[-10:]:
                print(f"  history: {h.get('at')}  {h.get('direction'):<13} #{h.get('number')}  "
                      f"{h.get('app_version')}  snapshot={h.get('snapshot')}")
            return 0 if on_disk in (None, expected) else 2
        if args.cmd == "upgrade":
            done = runner.upgrade(target=args.to)
            print(f"applied: {done}" if done else "nothing to apply")
            print(f"data schema is now {runner.current_version()}")
        elif args.cmd == "downgrade":
            done = runner.downgrade(args.to)
            print(f"reverted: {done}; data schema is now {runner.current_version()}")
        elif args.cmd == "snapshots":
            for sid in runner.list_snapshots():
                print(sid)
        elif args.cmd == "restore-snapshot":
            if not args.yes:
                print("This overwrites the current data files with the snapshot. Stop the app, "
                      "then run again with --yes.", file=sys.stderr)
                return 1
            n = runner.restore_snapshot(args.snapshot_id)
            print(f"restored {n} files; data schema is now {runner.current_version()}")
    except runner.MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
