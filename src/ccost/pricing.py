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
    # Anthropic (Claude Code)
    "opus": (15.0, 75.0),
    "sonnet": (3.0, 15.0),
    "haiku": (1.0, 5.0),
    # Fable 5 / Mythos 5 sit above Opus; no public price exists, so we estimate
    # at Opus tier. Flagged as an estimate in reports. Override if you know better.
    "fable": (15.0, 75.0),
    "mythos": (15.0, 75.0),
    # OpenAI (Codex CLI)
    "gpt-5": (1.25, 10.0),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4o": (2.5, 10.0),
    "o4-mini": (1.1, 4.4),
    "o3": (2.0, 8.0),
}

# Locally-run / free-tier models cost $0 marginal — don't price them at a guess.
# Checked before the table so "codex-qwen3-coder-30b" is free, not "gpt-5-codex".
FREE_PATTERNS = (
    ":free", "qwen", "nemotron", "laguna", "poolside", "llama", "mistral",
    "gemma", "deepseek", "glm-", "kimi", "minimax", "ollama",
)

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
    override_keys = {k.lower() for k in overrides} if overrides else set()
    table = dict(PRICING)
    if overrides:
        for k, v in overrides.items():
            table[k.lower()] = (float(v["input"]), float(v["output"]))
    # An explicit override always wins, even for a model we'd otherwise treat as free.
    matches = [pat for pat in table if pat in m]
    override_matches = [pat for pat in matches if pat in override_keys]
    if override_matches:
        pat = max(override_matches, key=len)
        inp, out = table[pat]
        return Rates(inp, out, False)
    # Locally-run / free models: $0, and we're confident (not an estimate).
    if any(p in m for p in FREE_PATTERNS):
        return Rates(0.0, 0.0, False)
    if matches:
        pat = max(matches, key=len)
        inp, out = table[pat]
        return Rates(inp, out, pat in ESTIMATED_MODELS)
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
