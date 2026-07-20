from datetime import datetime, timezone
from pathlib import Path

from ccost import pricing
from ccost.parse import load_records

FIXTURES = Path(__file__).parent / "fixtures" / "codex"


def test_codex_diffs_cumulative_totals_at_each_model():
    recs = load_records(sources=("codex",), codex_root=FIXTURES)
    assert len(recs) == 2
    assert [r.model for r in recs] == ["gpt-5", "gpt-5.3-codex"]
    assert [r.ts.minute for r in recs] == [1, 2]
    assert {r.source for r in recs} == {"codex"}
    assert {r.project for r in recs} == {"proj-codex"}
    # Deltas sum to the final total without double-counting the first snapshot.
    assert sum(r.input for r in recs) == 60000
    assert sum(r.cache_read for r in recs) == 40000
    assert sum(r.output for r in recs) == 5000


def test_codex_cost():
    recs = load_records(sources=("codex",), codex_root=FIXTURES)
    cost = sum(pricing.cost_usd(r.model, r.input, r.output, r.cache_read, 0, 0) for r in recs)
    assert round(cost, 5) == 0.1635


def test_codex_since_filters_usage_events_not_session_start():
    since = datetime(2026, 2, 1, 10, 1, 30, tzinfo=timezone.utc)
    recs = load_records(sources=("codex",), codex_root=FIXTURES, since=since)
    assert len(recs) == 1
    assert recs[0].model == "gpt-5.3-codex"


def test_local_models_are_free():
    assert pricing.cost_usd("codex-qwen3-coder-30b", 1_000_000, 1_000_000, 0, 0, 0) == 0.0
    assert pricing.rates_for("nvidia/nemotron-3-nano:free").estimated is False
