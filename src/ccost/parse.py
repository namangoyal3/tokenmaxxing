"""Discover and parse Claude Code and Codex logs into flat usage records.

Claude Code writes one JSONL file per session under
`~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. Each assistant turn
carries a `message.usage` block. We extract those, dedupe repeated requests
(resumed sessions replay earlier turns), and hand back plain dataclasses.

Codex writes cumulative usage snapshots. We convert each snapshot to a delta
so model changes and date filters remain accurate.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


@dataclass
class Record:
    ts: datetime
    model: str
    project: str
    session: str
    branch: str
    input: int
    output: int
    cache_read: int
    cache_write_5m: int
    cache_write_1h: int
    source: str = "claude"

    @property
    def total_tokens(self) -> int:
        return (
            self.input
            + self.output
            + self.cache_read
            + self.cache_write_5m
            + self.cache_write_1h
        )


SOURCES = ("claude", "codex")


def default_dir() -> Path:
    """Where Claude Code stores logs. Respects CLAUDE_CONFIG_DIR."""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(env) if env else Path.home() / ".claude"
    return base / "projects"


def codex_dir() -> Path:
    """Where the OpenAI Codex CLI stores session rollouts."""
    env = os.environ.get("CODEX_HOME")
    base = Path(env) if env else Path.home() / ".codex"
    return base / "sessions"


def _project_name(rec: dict, file_path: Path) -> str:
    cwd = rec.get("cwd")
    if cwd:
        return Path(cwd).name or cwd
    # Fall back to the encoded directory name: "-Users-me-myproj" -> "myproj".
    return file_path.parent.name.split("-")[-1] or "unknown"


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _iter_records(file_path: Path) -> Iterator[tuple[Record, str]]:
    """Yield (record, dedupe_key) for each assistant turn with usage."""
    try:
        text = file_path.read_text(errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "assistant":
            continue
        msg = obj.get("message") or {}
        usage = msg.get("usage") or {}
        if not usage:
            continue
        ts = _parse_ts(obj.get("timestamp"))
        if ts is None:
            continue
        cc = usage.get("cache_creation") or {}
        cache_5m = int(cc.get("ephemeral_5m_input_tokens", 0) or 0)
        cache_1h = int(cc.get("ephemeral_1h_input_tokens", 0) or 0)
        total_create = int(usage.get("cache_creation_input_tokens", 0) or 0)
        # If the breakdown is missing but a total exists, treat it as 5m writes.
        if cache_5m == 0 and cache_1h == 0 and total_create > 0:
            cache_5m = total_create
        rec = Record(
            ts=ts,
            model=msg.get("model") or "unknown",
            project=_project_name(obj, file_path),
            session=obj.get("sessionId") or file_path.stem,
            branch=obj.get("gitBranch") or "",
            input=int(usage.get("input_tokens", 0) or 0),
            output=int(usage.get("output_tokens", 0) or 0),
            cache_read=int(usage.get("cache_read_input_tokens", 0) or 0),
            cache_write_5m=cache_5m,
            cache_write_1h=cache_1h,
        )
        # Dedupe by (message id, request id); resumed sessions replay old turns.
        key = f"{msg.get('id', '')}:{obj.get('requestId', '')}"
        if key == ":":  # no ids at all -> fall back to uuid so we don't over-merge
            key = obj.get("uuid", "") or f"{file_path}:{ts.isoformat()}"
        yield rec, key


def _load_claude(root: Path, since: datetime | None) -> list[Record]:
    seen: set[str] = set()
    out: list[Record] = []
    if not root.exists():
        return out
    for file_path in root.rglob("*.jsonl"):
        for rec, key in _iter_records(file_path):
            if key in seen:
                continue
            seen.add(key)
            if since and rec.ts < since:
                continue
            out.append(rec)
    return out


def _codex_records(file_path: Path) -> list[Record]:
    """Convert Codex cumulative token snapshots into per-event deltas."""
    try:
        text = file_path.read_text(errors="replace")
    except OSError:
        return []
    meta_ts = meta_cwd = session_id = None
    model = "unknown"
    previous = (0, 0, 0)
    out: list[Record] = []
    leading: list[Record] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        payload = obj.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        t = obj.get("type")
        if t == "session_meta":
            meta_ts = payload.get("timestamp") or obj.get("timestamp")
            meta_cwd = payload.get("cwd")
            session_id = payload.get("id")
        elif t == "turn_context" and payload.get("model"):
            model = payload["model"]
            for rec in leading:
                rec.model = model
            leading.clear()
        info = payload.get("info")
        if isinstance(info, dict):
            tu = info.get("total_token_usage")
            if isinstance(tu, dict):
                try:
                    current = (
                        int(tu.get("input_tokens", 0) or 0),
                        int(tu.get("cached_input_tokens", 0) or 0),
                        int(tu.get("output_tokens", 0) or 0),
                    )
                except (TypeError, ValueError):
                    continue
                deltas = tuple(now - before for now, before in zip(current, previous))
                if any(delta < 0 for delta in deltas):
                    # ponytail: Codex counters should only rise. A reset becomes the new baseline.
                    previous = current
                    continue
                previous = current
                if not any(deltas):
                    continue
                ts = _parse_ts(obj.get("timestamp")) or _parse_ts(meta_ts)
                if ts is None:
                    continue
                total_in, cached, output = deltas
                rec = Record(
                    ts=ts,
                    model=model,
                    project=(Path(meta_cwd).name if meta_cwd else "unknown"),
                    session=session_id or file_path.stem,
                    branch="",
                    input=max(total_in - cached, 0),  # OpenAI input_tokens includes cached
                    output=output,
                    cache_read=cached,
                    cache_write_5m=0,  # Codex logs do not expose cache writes
                    cache_write_1h=0,
                    source="codex",
                )
                out.append(rec)
                if model == "unknown":
                    leading.append(rec)
    return out


def _load_codex(root: Path, since: datetime | None) -> list[Record]:
    out: list[Record] = []
    if not root.exists():
        return out
    for file_path in root.rglob("rollout-*.jsonl"):
        out.extend(rec for rec in _codex_records(file_path) if not since or rec.ts >= since)
    return out


def load_records(
    sources=SOURCES,
    since: datetime | None = None,
    claude_root: Path | None = None,
    codex_root: Path | None = None,
) -> list[Record]:
    """Load usage records from every requested source, sorted by time."""
    out: list[Record] = []
    if "claude" in sources:
        out += _load_claude(claude_root or default_dir(), since)
    if "codex" in sources:
        out += _load_codex(codex_root or codex_dir(), since)
    out.sort(key=lambda r: r.ts)
    return out
