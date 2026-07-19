from pathlib import Path

from ccost import pricing
from ccost.parse import load_records

FIXTURES = Path(__file__).parent / "fixtures" / "codex"


def test_codex_takes_final_cumulative_total():
    recs = load_records(sources=("codex",), codex_root=FIXTURES)
    assert len(recs) == 1
    r = recs[0]
    assert r.source == "codex"
    assert r.model == "gpt-5"
    assert r.project == "proj-codex"
    # final total: input 100k incl 40k cached -> input=60k, cache_read=40k, output=5k
    assert r.input == 60000
    assert r.cache_read == 40000
    assert r.output == 5000


def test_codex_cost():
    r = load_records(sources=("codex",), codex_root=FIXTURES)[0]
    cost = pricing.cost_usd(r.model, r.input, r.output, r.cache_read, 0, 0)
    # 60k*1.25 + 5k*10 + 40k*1.25*0.1 = 130000/1e6
    assert round(cost, 4) == 0.13


def test_local_models_are_free():
    assert pricing.cost_usd("codex-qwen3-coder-30b", 1_000_000, 1_000_000, 0, 0, 0) == 0.0
    assert pricing.rates_for("nvidia/nemotron-3-nano:free").estimated is False
