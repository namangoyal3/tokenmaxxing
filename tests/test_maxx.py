from datetime import datetime, timedelta, timezone

from ccost import maxx
from ccost.parse import Record
from rich.console import Console


def _rec(session, minutes, cw5m=0, cache_read=0, model="claude-sonnet-5", input_tokens=100):
    return Record(
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minutes),
        model=model, project="p", session=session, branch="",
        input=input_tokens, output=10, cache_read=cache_read, cache_write_5m=cw5m, cache_write_1h=0,
    )


def test_idle_gap_waste_flags_rebuild_after_long_gap():
    # turn 2 is 10 min after turn 1 and rebuilds 100k of 5m cache -> flagged.
    recs = [_rec("s", 0, cw5m=50000), _rec("s", 10, cw5m=100000)]
    waste, turns = maxx.idle_gap_waste(recs, None)
    assert turns == 1
    # 100000 * (2/1e6) * (1.25-0.10) = 0.23
    assert round(waste, 3) == 0.23


def test_no_waste_when_turns_are_close():
    recs = [_rec("s", 0, cw5m=50000), _rec("s", 2, cw5m=100000)]
    waste, turns = maxx.idle_gap_waste(recs, None)
    assert (waste, turns) == (0.0, 0)


def test_cold_session_is_write_without_read():
    cold = [_rec("cold", 0, cw5m=100000, cache_read=0)]
    warm = [_rec("warm", 0, cw5m=100000, cache_read=100000)]
    waste, n = maxx.cold_session_waste(cold + warm, None)
    assert n == 1 and waste > 0


def test_downshift_prefers_opus():
    recs = [_rec("s", 0, model="claude-opus-4-8")]
    model, cheaper, cur, low = maxx.best_downshift(recs, None)
    assert "opus" in model
    assert cur > low  # sonnet is cheaper


def test_downshift_copy_names_the_actual_models():
    console = Console(record=True, width=200)
    maxx.print_maxx(console, [_rec("s", 0, input_tokens=1_000_000)], None)
    output = console.export_text()
    assert "$2.00 on claude-sonnet-5" in output
    assert "$1.00 on claude-haiku-4-5" in output
    assert "Opus rates" not in output
