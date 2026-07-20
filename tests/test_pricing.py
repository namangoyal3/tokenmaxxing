from ccost import pricing


def test_sonnet_cost_is_cache_aware():
    # 1000 in, 500 out, 2000 cache-read, 4000 5m-write, 1000 1h-write @ Sonnet 5 (2/10).
    cost = pricing.cost_usd("claude-sonnet-5", 1000, 500, 2000, 4000, 1000)
    assert round(cost, 6) == 0.0214


def test_longest_substring_wins():
    # "claude-3-5-haiku" must resolve to haiku, not a broad fallback.
    r = pricing.rates_for("claude-3-5-haiku-20241022")
    assert (r.input, r.output) == (1.0, 5.0)
    assert r.estimated is False


def test_unknown_model_is_flagged_estimated():
    r = pricing.rates_for("some-random-model")
    assert r.estimated is True


def test_current_fable_and_codex_rates():
    r = pricing.rates_for("claude-fable-5")
    assert (r.input, r.output, r.estimated) == (10.0, 50.0, False)
    assert pricing.rates_for("gpt-5.6-sol").input == 5.0
    assert pricing.rates_for("gpt-5.6-terra").output == 15.0


def test_pricing_override_wins_and_clears_estimate():
    over = {"fable": {"input": 20, "output": 100}}
    r = pricing.rates_for("claude-fable-5", over)
    assert r.input == 20.0 and r.estimated is False
