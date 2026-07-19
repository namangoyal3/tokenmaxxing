"""ccost command line: turn Claude Code logs into a cost report."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rich.console import Console

from . import __version__, html, report
from .parse import load_records

COMMANDS = ("summary", "daily", "monthly", "projects", "models", "html", "json")


def _load_pricing(path: str | None) -> dict | None:
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"ccost: could not read pricing file {path!r}: {e}")


def _since(days: int | None) -> datetime | None:
    if not days:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ccost", description="See what Claude Code actually costs you.")
    p.add_argument("command", nargs="?", default="summary", choices=COMMANDS,
                   help="report to show (default: summary)")
    p.add_argument("--dir", type=Path, help="Claude projects dir (default: ~/.claude/projects)")
    p.add_argument("--days", type=int, help="only include the last N days")
    p.add_argument("--pricing", help="JSON file overriding model prices")
    p.add_argument("-o", "--out", help="output file for the html command (default: ccost-report.html)")
    p.add_argument("-v", "--version", action="version", version=f"ccost {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    overrides = _load_pricing(args.pricing)
    records = load_records(args.dir, since=_since(args.days))
    console = Console()

    if args.command == "json":
        print(json.dumps({
            "count": len(records),
            "records": [
                {
                    "ts": r.ts.isoformat(), "model": r.model, "project": r.project,
                    "session": r.session, "input": r.input, "output": r.output,
                    "cache_read": r.cache_read, "cache_write_5m": r.cache_write_5m,
                    "cache_write_1h": r.cache_write_1h,
                }
                for r in records
            ],
        }, indent=2))
        return 0

    if args.command == "html":
        out = Path(args.out or "ccost-report.html")
        out.write_text(html.render(records, overrides))
        console.print(f"[green]Wrote[/] {out}  ({len(records):,} records)")
        return 0

    dispatch = {
        "summary": report.print_summary,
        "daily": report.print_daily,
        "monthly": report.print_monthly,
        "projects": report.print_projects,
        "models": report.print_models,
    }
    dispatch[args.command](console, records, overrides)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
