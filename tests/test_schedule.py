import json
from datetime import datetime, timezone

import pytest

from ccost import schedule
from ccost.schedule import build_parser, claude_reset, codex_reset


def test_provider_reset_times_come_from_limit_logs(tmp_path):
    now = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)

    codex = tmp_path / "codex"
    codex.mkdir()
    (codex / "rollout-test.jsonl").write_text(json.dumps({
        "timestamp": "2026-07-20T09:59:00Z",
        "payload": {"rate_limits": {
            "primary": {"used_percent": 100, "resets_at": 1784545200},
            "secondary": {"used_percent": 100, "resets_at": 1784548800},
        }},
    }))
    assert codex_reset(codex, now) == datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)

    claude = tmp_path / "claude"
    claude.mkdir()
    (claude / "session.jsonl").write_text(json.dumps({
        "timestamp": "2026-07-20T09:59:00Z",
        "error": "rate_limit",
        "message": {"content": [{
            "type": "text",
            "text": "You've hit your session limit · resets 4:30pm (Asia/Calcutta)",
        }]},
    }))
    assert claude_reset(claude, now) == datetime(2026, 7, 20, 11, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("value", ["-1", "nan", "inf"])
def test_grace_must_be_finite_and_nonnegative(value):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["prompt", "--grace", value])


def test_schedule_uses_the_current_agent(monkeypatch):
    calls = []
    monkeypatch.setenv("CODEX_THREAD_ID", "test")
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.setattr(schedule, "codex_reset", lambda now: now)
    monkeypatch.setattr(schedule, "claude_reset", lambda now: None)
    monkeypatch.setattr(schedule.shutil, "which", lambda agent: f"/bin/{agent}")
    monkeypatch.setattr(schedule.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        schedule.subprocess,
        "run",
        lambda command, check: calls.append(command) or type("Result", (), {"returncode": 0})(),
    )

    assert schedule.main(["continue this task", "--grace", "0"]) == 0
    assert calls == [["/bin/codex", "exec", "continue this task"]]
