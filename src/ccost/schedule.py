"""Run one prompt when an exhausted Claude or Codex limit resets."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rich.console import Console

from .parse import _parse_ts, codex_dir, default_dir

RESET_RE = re.compile(r"resets\s+(\d{1,2}:\d{2}\s*[ap]m)\s+\(([^)]+)\)", re.IGNORECASE)


def _latest_codex_limits(root: Path) -> dict | None:
    latest: tuple[datetime, dict] | None = None
    if not root.exists():
        return None
    for path in root.rglob("rollout-*.jsonl"):
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or not isinstance(obj.get("payload"), dict):
                continue
            limits = obj["payload"].get("rate_limits")
            ts = _parse_ts(obj.get("timestamp"))
            if isinstance(limits, dict) and ts is not None:
                if latest is None or ts > latest[0]:
                    latest = ts, limits
                break
    return latest[1] if latest else None


def codex_reset(root: Path | None = None, now: datetime | None = None) -> datetime | None:
    """Return the reset that clears all currently exhausted Codex limits."""
    now = now or datetime.now(timezone.utc)
    limits = _latest_codex_limits(root or codex_dir())
    if not limits:
        return None
    reached = str(limits.get("rate_limit_reached_type") or "").lower()
    resets: list[datetime] = []
    available: list[datetime] = []
    for name in ("primary", "secondary"):
        limit = limits.get(name)
        if not isinstance(limit, dict):
            continue
        try:
            reset = datetime.fromtimestamp(float(limit["resets_at"]), timezone.utc)
            used = float(limit.get("used_percent", 0))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if reset <= now:
            continue
        available.append(reset)
        if used >= 100 or reached in (name, "both", "all"):
            resets.append(reset)
    if reached and not resets:
        resets = available
    return max(resets, default=None)


def _claude_error(path: Path) -> tuple[datetime, str] | None:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("error") != "rate_limit" and obj.get("apiErrorStatus") != 429:
            continue
        ts = _parse_ts(obj.get("timestamp"))
        message = obj.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        text = " ".join(
            part.get("text", "") for part in content or [] if isinstance(part, dict)
        )
        if ts is not None:
            return ts, text
    return None


def claude_reset(root: Path | None = None, now: datetime | None = None) -> datetime | None:
    """Return the reset from the newest still-active Claude 429 response."""
    now = now or datetime.now(timezone.utc)
    root = root or default_dir()
    latest: tuple[datetime, str] | None = None
    if not root.exists():
        return None
    for path in root.rglob("*.jsonl"):
        error = _claude_error(path)
        if error and (latest is None or error[0] > latest[0]):
            latest = error
    if latest is None:
        return None
    match = RESET_RE.search(latest[1])
    if not match:
        return None
    try:
        zone = ZoneInfo(match.group(2))
        reset_time = datetime.strptime(match.group(1).replace(" ", ""), "%I:%M%p").time()
    except (ValueError, ZoneInfoNotFoundError):
        return None
    error_local = latest[0].astimezone(zone)
    reset = datetime.combine(error_local.date(), reset_time, zone)
    if reset <= error_local:
        reset += timedelta(days=1)
    reset = reset.astimezone(timezone.utc)
    return reset if reset > now else None


def _nonnegative_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError("must be a finite nonnegative number")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="schedule",
        description="Run one prompt when the active agent's limit resets.",
    )
    parser.add_argument("prompt", help="quoted prompt, or - to read standard input")
    parser.add_argument("--grace", type=_nonnegative_float, default=5,
                        help="seconds to wait after the reset (default: 5)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prompt = sys.stdin.read() if args.prompt == "-" else args.prompt
    if not prompt.strip():
        build_parser().error("the prompt cannot be empty")

    now = datetime.now(timezone.utc)
    current = "claude" if os.environ.get("CLAUDECODE") else (
        "codex" if os.environ.get("CODEX_THREAD_ID") else None
    )
    if current:
        agent = current
        reset = claude_reset(now=now) if agent == "claude" else codex_reset(now=now)
    else:
        active = [
            (reset, agent)
            for agent, reset in (
                ("claude", claude_reset(now=now)),
                ("codex", codex_reset(now=now)),
            )
            if reset is not None
        ]
        reset, agent = min(active, default=(None, None))
    if reset is None:
        print("schedule: no active Claude or Codex limit found", file=sys.stderr)
        return 1

    executable = shutil.which(agent)
    if executable is None:
        print(f"schedule: {agent} is not installed or not on PATH", file=sys.stderr)
        return 127

    run_at = reset + timedelta(seconds=args.grace)
    Console().print(
        f"[cyan]Scheduled for {agent}[/] at {run_at.astimezone():%Y-%m-%d %H:%M:%S %Z}. "
        "Keep this process running; press Ctrl-C to cancel."
    )
    try:
        time.sleep(max((run_at - datetime.now(timezone.utc)).total_seconds(), 0))
    except KeyboardInterrupt:
        print("\nschedule: prompt cancelled", file=sys.stderr)
        return 130

    command = [executable, "-p", prompt] if agent == "claude" else [executable, "exec", prompt]
    return subprocess.run(command, check=False).returncode
