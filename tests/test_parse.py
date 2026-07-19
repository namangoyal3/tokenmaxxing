from pathlib import Path

from ccost import pricing
from ccost.parse import load_records

FIXTURES = Path(__file__).parent / "fixtures"


def test_dedupe_and_extraction():
    recs = load_records(FIXTURES)
    # Two assistant turns share (msg_1, req_1) -> deduped to one; user line ignored.
    assert len(recs) == 2
    assert {r.project for r in recs} == {"proj-a", "proj-b"}
    assert recs[0].branch == "main"


def test_cache_breakdown_parsed():
    a = next(r for r in load_records(FIXTURES) if r.project == "proj-a")
    assert a.cache_write_5m == 4000
    assert a.cache_write_1h == 1000
    assert a.cache_read == 2000


def test_total_cost_matches_hand_math():
    recs = load_records(FIXTURES)
    total = sum(
        pricing.cost_usd(r.model, r.input, r.output, r.cache_read, r.cache_write_5m, r.cache_write_1h)
        for r in recs
    )
    # proj-a = 0.0321, proj-b haiku 1M input = 1.0
    assert round(total, 4) == 1.0321
