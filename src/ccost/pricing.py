"""Model pricing and cost computation for Claude Code usage records.

Prices are USD per million tokens (MTok), standard tier, from Anthropic's
public pricing. Cache rates follow Anthropic's documented multipliers of the
base input rate:

  - cache read              = 0.10 x input
  - cache write (5m TTL)    = 1.25 x input
  - cache write (1h TTL)    = 2.00 x input

Prices change. Override any of this with `--pricing pricing.json` (a JSON map of
`{"model-substring": {"input": <per_mtok>, "output": <per_mtok>}}`), or edit the
PRICING table below. `ccost` never phones home for prices.
"""
from __future__ import annotations

from dataclasses import dataclass

# Cache multipliers relative to the model's base input rate.
CACHE_READ_MULT = 0.10
CACHE_WRITE_5M_MULT = 1.25
CACHE_WRITE_1H_MULT = 2.00

# (input_per_mtok, output_per_mtok). Matched by substring against the model id,
# longest pattern first, so "claude-3-5-haiku" hits "haiku" not a broad default.
PRICING: dict[str, tuple[float, float]] = {
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (1.0, 5.0),
    # Fable 5 / Mythos 5 sit above Opus; no public price exists, so we estimate
    # at Opus tier. Flagged as an estimate in reports. Override if you know better.
    "fable": (15.0, 75.0),
    "mythos": (15.0, 75.0),
}

# Used when a model matches nothing above. Sonnet-tier is the safe middle bet.
FALLBACK = (3.0, 15.0)

ESTIMATED_MODELS = ("fable", "mythos")


@dataclass(frozen=True)
class Rates:
    input: float  # per MTok
    output: float  # per MTok
    estimated: bool  # True when the price is a guess (unknown or Fable/Mythos)


def rates_for(model: str, overrides: dict[str, dict] | None = None) -> Rates:
    """Resolve per-MTok rates for a model id. Longest substring match wins."""
    m = (model or "").lower()
    table = dict(PRICING)
    if overrides:
        for k, v in overrides.items():
            table[k.lower()] = (float(v["input"]), float(v["output"]))
    matches = [pat for pat in table if pat in m]
    if matches:
        pat = max(matches, key=len)
        inp, out = table[pat]
        estimated = pat in ESTIMATED_MODELS and not (overrides and pat in {k.lower() for k in overrides})
        return Rates(inp, out, estimated)
    inp, out = FALLBACK
    return Rates(inp, out, True)  # unknown model -> estimated


def cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int,
    cache_write_5m: int,
    cache_write_1h: int,
    overrides: dict[str, dict] | None = None,
) -> float:
    """Compute the USD cost of a single usage record, cache-aware."""
    r = rates_for(model, overrides)
    per_tok_in = r.input / 1_000_000
    per_tok_out = r.output / 1_000_000
    return (
        input_tokens * per_tok_in
        + output_tokens * per_tok_out
        + cache_read * per_tok_in * CACHE_READ_MULT
        + cache_write_5m * per_tok_in * CACHE_WRITE_5M_MULT
        + cache_write_1h * per_tok_in * CACHE_WRITE_1H_MULT
    )


def is_estimated(model: str, overrides: dict[str, dict] | None = None) -> bool:
    return rates_for(model, overrides).estimated
