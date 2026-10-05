"""Write the build metadata of this checkout (VM-04, VM-05).

Usage:
    python tools/stamp_build.py               # environment from UVALU_ENV / .env
    python tools/stamp_build.py --env test    # force the environment (CI)
    python tools/stamp_build.py --check       # validate an existing build_info.json, write nothing

Writes ``build_info.json`` (read by ``uvalu.buildinfo``) and
``static/version.json`` (served at ``/app/static/version.json``, VD-07). Both
are git-ignored and must never be edited by hand. ``run_app.py`` calls
:func:`stamp` on every start, so a deploy (``git pull`` + start) is stamped
automatically. Never fails a start-up: without git the commit is ``unknown``
and the build counts as a dev build.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from uvalu import buildinfo  # noqa: E402


def stamp(*, environment: "str | None" = None, root: Path = ROOT,
          schema_version: "int | None" = None) -> buildinfo.BuildInfo:
    if environment is None:
        try:
            from dotenv import load_dotenv
            load_dotenv(root / ".env")
        except Exception:
            pass
    info = buildinfo.compute(root, environment=environment)
    buildinfo.write(info, root / buildinfo.STAMP_FILE.name)
    buildinfo.write_public(info, schema_version=schema_version,
                           path=root / buildinfo.STATIC_DIR.name / buildinfo.VERSION_JSON.name)
    return info


def check(root: Path = ROOT) -> int:
    info = buildinfo.load(root / buildinfo.STAMP_FILE.name)
    if info is None:
        print("build_info.json missing or invalid", file=sys.stderr)
        return 1
    problems = []
    if not info.version or info.version == "0.0.0":
        problems.append("no version")
    if info.is_release and info.display_version != info.version:
        problems.append("release build with a dev display version")
    if not info.is_release and "-dev+" not in info.display_version:
        problems.append("dev build without a -dev+ marker")
    if not info.built_at.endswith("Z"):
        problems.append("built_at is not UTC")
    for p in problems:
        print(f"build_info.json: {p}", file=sys.stderr)
    return 1 if problems else 0


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--env", help="development | test | production (default: UVALU_ENV)")
    ap.add_argument("--check", action="store_true", help="validate build_info.json only")
    args = ap.parse_args(argv)
    if args.check:
        return check()
    info = stamp(environment=args.env)
    print(f"Stamped {info.display_version} ({info.commit}, {info.environment}, {info.built_at})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
