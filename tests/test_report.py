from datetime import datetime, timezone

from rich.console import Console

from ccost import html, report
from ccost.parse import Record


def _record(day, model):
    return Record(
        ts=datetime(2026, 1, day, tzinfo=timezone.utc),
        model=model, project="p", session="s", branch="",
        input=1_000_000, output=0, cache_read=0, cache_write_5m=0, cache_write_1h=0,
    )


def test_daily_reports_keep_chronological_order():
    records = [_record(2, "claude-haiku-4-5"), _record(1, "claude-fable-5")]
    console = Console(record=True, width=160)
    report.print_daily(console, records, None)
    text = console.export_text()
    assert text.index("2026-01-01") < text.index("2026-01-02")

    daily = html.render(records, None).split("<h2>Daily", 1)[1].split("<h2>Monthly", 1)[0]
    assert daily.index("2026-01-01") < daily.index("2026-01-02")
