"""ccost command line: turn Claude Code logs into a cost report."""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rich.console import Console

from . import __version__, blocks, html, maxx, report, schedule
from .parse import SOURCES, load_records

COMMANDS = ("summary", "maxx", "window", "calendar", "daily", "monthly",
            "projects", "models", "sources", "html", "json", "schedule")


def _load_pricing(path: str | None) -> dict | None:
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"ccost: could not read pricing file {path!r}: {e}")
    valid = isinstance(data, dict) and all(
        isinstance(model, str)
        and model
        and isinstance(rates, dict)
        and all(
            isinstance(rates.get(key), (int, float))
            and not isinstance(rates.get(key), bool)
            and math.isfinite(rates[key])
            and rates[key] >= 0
            for key in ("input", "output")
        )
        for model, rates in data.items()
    )
    if not valid:
        sys.exit(f"ccost: invalid pricing file {path!r}: expected nonnegative input and output rates")
    return data


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _since(days: int | None) -> datetime | None:
    if not days:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ccost", description="See what Claude Code actually costs you.")
    p.add_argument("command", nargs="?", default="summary", choices=COMMANDS,
                   help="report to show (default: summary)")
    p.add_argument("--source", choices=(*SOURCES, "all"), default="all",
                   help="which agent's logs to read (default: all)")
    p.add_argument("--dir", type=Path, help="Claude projects dir (default: ~/.claude/projects)")
    p.add_argument("--days", type=_positive_int, help="only include the last N days")
    p.add_argument("--limit", type=_positive_int, help="your token budget per 5-hour window (for `window`)")
    p.add_argument("--pricing", help="JSON file overriding model prices")
    p.add_argument("-o", "--out", help="output file for the html command (default: ccost-report.html)")
    p.add_argument("-v", "--version", action="version", version=f"ccost {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    raw = sys.argv[1:] if argv is None else argv
    if raw and raw[0] == "schedule":
        return schedule.main(raw[1:])
    args = build_parser().parse_args(raw)
    overrides = _load_pricing(args.pricing)
    sources = SOURCES if args.source == "all" else (args.source,)
    records = load_records(sources=sources, since=_since(args.days), claude_root=args.dir)
    console = Console()

    if args.command == "json":
        print(json.dumps({
            "count": len(records),
            "records": [
                {
                    "ts": r.ts.isoformat(), "source": r.source, "model": r.model,
                    "project": r.project, "session": r.session,
                    "input": r.input, "output": r.output, "cache_read": r.cache_read,
                    "cache_write_5m": r.cache_write_5m, "cache_write_1h": r.cache_write_1h,
                }
                for r in records
            ],
        }, indent=2))
        return 0

    if args.command == "html":
        out = Path(args.out or "ccost-report.html")
        try:
            out.write_text(html.render(records, overrides))
        except OSError as e:
            sys.exit(f"ccost: could not write HTML report {str(out)!r}: {e}")
        console.print(f"[green]Wrote[/] {out}  ({len(records):,} records)")
        return 0

    if args.command == "window":
        blocks.print_window(console, records, overrides, limit=args.limit)
        return 0
    if args.command == "calendar":
        blocks.print_calendar(console, records)
        return 0

    dispatch = {
        "summary": report.print_summary,
        "daily": report.print_daily,
        "monthly": report.print_monthly,
        "projects": report.print_projects,
        "models": report.print_models,
        "sources": report.print_sources,
        "maxx": maxx.print_maxx,
    }
    dispatch[args.command](console, records, overrides)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
