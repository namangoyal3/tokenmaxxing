"""Discover and parse Claude Code session logs into flat usage records.

Claude Code writes one JSONL file per session under
`~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. Each assistant turn
carries a `message.usage` block. We extract those, dedupe repeated requests
(resumed sessions replay earlier turns), and hand back plain dataclasses.
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


def _codex_record(file_path: Path) -> Record | None:
    """One record per Codex rollout: its final (cumulative) token totals.

    Codex writes a running `total_token_usage` on every turn, so we keep the
    largest one — the session total — rather than summing turns.
    """
    try:
        text = file_path.read_text(errors="replace")
    except OSError:
        return None
    meta_ts = meta_cwd = session_id = None
    model = "unknown"
    best = None  # the total_token_usage dict with the most total_tokens
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
        t = obj.get("type")
        if t == "session_meta":
            meta_ts = payload.get("timestamp") or obj.get("timestamp")
            meta_cwd = payload.get("cwd")
            session_id = payload.get("id")
        elif t == "turn_context" and payload.get("model"):
            model = payload["model"]
        info = payload.get("info") if isinstance(payload, dict) else None
        if isinstance(info, dict):
            tu = info.get("total_token_usage")
            if isinstance(tu, dict):
                if best is None or tu.get("total_tokens", 0) > best.get("total_tokens", 0):
                    best = tu
    if not best:
        return None
    ts = _parse_ts(meta_ts) or _parse_ts(None)
    if ts is None:
        return None
    cached = int(best.get("cached_input_tokens", 0) or 0)
    total_in = int(best.get("input_tokens", 0) or 0)
    return Record(
        ts=ts,
        model=model,
        project=(Path(meta_cwd).name if meta_cwd else "unknown"),
        session=session_id or file_path.stem,
        branch="",
        input=max(total_in - cached, 0),  # OpenAI input_tokens includes cached
        output=int(best.get("output_tokens", 0) or 0),
        cache_read=cached,
        cache_write_5m=0,  # OpenAI implicit caching has no write premium
        cache_write_1h=0,
        source="codex",
    )


def _load_codex(root: Path, since: datetime | None) -> list[Record]:
    out: list[Record] = []
    if not root.exists():
        return out
    for file_path in root.rglob("rollout-*.jsonl"):
        rec = _codex_record(file_path)
        if rec is None:
            continue
        if since and rec.ts < since:
            continue
        out.append(rec)
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
