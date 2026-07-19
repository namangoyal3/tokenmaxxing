from datetime import datetime, timedelta, timezone

from ccost import blocks
from ccost.parse import Record


def _rec(minutes, tokens=1000):
    return Record(
        ts=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes),
        model="claude-sonnet-5", project="p", session="s", branch="",
        input=tokens, output=0, cache_read=0, cache_write_5m=0, cache_write_1h=0,
    )


def test_gap_over_5h_opens_new_window():
    recs = [_rec(0), _rec(60), _rec(60 + 6 * 60)]  # third is 6h after the second
    bl = blocks.detect_blocks(recs)
    assert len(bl) == 2
    assert bl[0].records == 2 and bl[1].records == 1


def test_window_spans_five_hours_then_rolls():
    # activity every 30 min for 6h -> two windows (0-5h, 5h+)
    recs = [_rec(i * 30) for i in range(13)]
    bl = blocks.detect_blocks(recs)
    assert len(bl) == 2


def test_active_window_detection():
    start = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    recs = [_rec(0), _rec(30)]
    now = start + timedelta(hours=1)  # inside the 5h window
    bl = blocks.detect_blocks(recs)
    assert bl[0].active(now) is True
    assert bl[0].active(start + timedelta(hours=6)) is False  # window elapsed


def test_window_renders_without_crashing(capsys):
    from rich.console import Console
    recs = [_rec(0, 500), _rec(30, 500)]
    now = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    blocks.print_window(Console(), recs, None, now=now)
    assert "5-hour" in capsys.readouterr().out
