"""`ccost maxx` — token-maxxing: score your efficiency and rank the levers.

Two tiers of advice, kept honest:
  - Reclaimable waste: dollars you can almost certainly get back (cache you paid
    to rebuild after it expired, cache you built and never read). Computed, not
    guessed.
  - Structural levers: bigger potential savings that need your judgment (running
    routine turns on a cheaper model, asking for terser output). Shown as
    what-ifs with the math, never as promises.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import pricing
from .parse import Record
from .report import Agg, _money, short_model

CACHE_5M_TTL = timedelta(minutes=5)
GAP_MIN_TOKENS = 1000  # ignore trivial cache rebuilds
# One cheaper tier down, with a representative model id for repricing.
DOWNSHIFT = {"opus": "claude-sonnet-4-5", "fable": "claude-sonnet-4-5",
             "mythos": "claude-sonnet-4-5", "sonnet": "claude-haiku-4-5"}


def _cost(r: Record, overrides, model: str | None = None) -> float:
    return pricing.cost_usd(model or r.model, r.input, r.output, r.cache_read,
                            r.cache_write_5m, r.cache_write_1h, overrides)


def idle_gap_waste(records: list[Record], overrides) -> tuple[float, int]:
    """$ overpaid rebuilding the 5-minute cache after >5min idle gaps.

    Only Claude has per-turn timestamps + the 5m/1h split needed for this.
    The overpay is the write premium minus the read it should have been.
    """
    waste, turns = 0.0, 0
    by_session: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        if r.source == "claude":
            by_session[r.session].append(r)
    premium = pricing.CACHE_WRITE_5M_MULT - pricing.CACHE_READ_MULT
    for recs in by_session.values():
        recs.sort(key=lambda r: r.ts)
        prev = None
        for r in recs:
            if prev is not None and (r.ts - prev.ts) > CACHE_5M_TTL and r.cache_write_5m > GAP_MIN_TOKENS:
                rate = pricing.rates_for(r.model, overrides).input / 1_000_000
                waste += r.cache_write_5m * rate * premium
                turns += 1
            prev = r
    return waste, turns


def cold_session_waste(records: list[Record], overrides) -> tuple[float, int]:
    """Sessions that built cache but never read any — a one-shot that paid the
    cache-write premium for nothing."""
    writes: dict[str, float] = defaultdict(float)
    reads: dict[str, int] = defaultdict(int)
    for r in records:
        if r.source != "claude":
            continue
        writes[r.session] += pricing.cost_usd(r.model, 0, 0, 0, r.cache_write_5m, r.cache_write_1h, overrides)
        reads[r.session] += r.cache_read
    waste = sum(w for s, w in writes.items() if w > 0 and reads[s] == 0)
    n = sum(1 for s, w in writes.items() if w > 0 and reads[s] == 0)
    return waste, n


def best_downshift(records: list[Record], overrides) -> tuple[str, str, float, float] | None:
    """The model whose spend would drop most one tier down. Returns
    (model, cheaper_id, current_cost, cost_if_downshifted)."""
    groups: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        groups[r.model].append(r)
    best = None
    for model, recs in groups.items():
        m = model.lower()
        cheaper = next((DOWNSHIFT[k] for k in DOWNSHIFT if k in m), None)
        if not cheaper:
            continue
        cur = sum(_cost(r, overrides) for r in recs)
        low = sum(_cost(r, overrides, cheaper) for r in recs)
        if best is None or (cur - low) > (best[2] - best[3]):
            best = (model, cheaper, cur, low)
    return best


def print_maxx(console: Console, records: list[Record], overrides) -> None:
    if not records:
        console.print("[yellow]No usage found.[/]")
        return
    total = Agg()
    for r in records:
        total.add(r, overrides)
    hit = total.cache_hit_rate
    score = round(100 * hit)
    grade = ("A" if score >= 90 else "B" if score >= 80 else "C" if score >= 65
             else "D" if score >= 50 else "F")
    color = "green" if score >= 80 else "yellow" if score >= 65 else "red"

    head = Text()
    head.append(f"Token efficiency  {grade}  ", style=f"bold {color}")
    head.append(f"({score}/100)\n", style=color)
    head.append(f"Cache reuse {hit * 100:.0f}%  ·  total spend {_money(total.cost)}", style="dim")
    console.print(Panel(head, title="[bold]ccost maxx[/] · tokenmaxxing", border_style=color))

    gap_waste, gap_turns = idle_gap_waste(records, overrides)
    cold_waste, cold_n = cold_session_waste(records, overrides)
    output_cost = sum(_cost_out(r, overrides) for r in records)
    shift = best_downshift(records, overrides)

    reclaimable = gap_waste + cold_waste
    r_pct = reclaimable / total.cost * 100 if total.cost else 0
    verdict = Text()
    if score >= 90 and r_pct < 2:
        verdict.append("You're already tokenmaxxed. ", style="green")
        verdict.append("The reclaimable waste below is small — the real lever is model choice.",
                       style="dim")
    else:
        verdict.append(f"~{_money(reclaimable)} ({r_pct:.0f}%) is reclaimable waste. "
                       f"Bigger structural levers below.", style="white")
    console.print(verdict)

    t = Table(title="Maxx moves — ranked by impact", title_style="bold",
              header_style="bold cyan", show_lines=False)
    t.add_column("Move", style="white")
    t.add_column("Impact", justify="right", style="green")
    t.add_column("Type", justify="center")
    t.add_column("How", style="dim")

    moves: list[tuple[float, str, str, str, str]] = []
    if shift and (shift[2] - shift[3]) > 0.01:
        model, cheaper, cur, low = shift
        moves.append((cur - low, f"Downshift {short_model(model)}",
                      _money(cur - low), "lever",
                      f"{_money(cur)} on {short_model(model)} ≈ "
                      f"{_money(low)} on {short_model(cheaper)}. "
                      f"Route routine turns down a tier."))
    if output_cost > 0.01:
        share = output_cost / total.cost * 100 if total.cost else 0
        moves.append((output_cost * 0.3, "Trim output",
                      f"~{_money(output_cost * 0.3)}", "lever",
                      f"Output is {_money(output_cost)} ({share:.0f}%), priced 4–5× input. "
                      f"Terser prompts / lower max_tokens."))
    if gap_waste > 0.01:
        moves.append((gap_waste, "Kill idle-gap rebuilds", _money(gap_waste), "reclaim",
                      f"{gap_turns} turns rebuilt the 5m cache after a >5min gap. "
                      f"Keep sessions warm or use the 1h cache."))
    if cold_waste > 0.01:
        moves.append((cold_waste, "Batch one-shot sessions", _money(cold_waste), "reclaim",
                      f"{cold_n} sessions built cache they never read. "
                      f"Group related work into fewer, longer sessions."))

    for _, move, impact, kind, how in sorted(moves, key=lambda m: m[0], reverse=True):
        tag = "[green]reclaim[/]" if kind == "reclaim" else "[yellow]lever[/]"
        t.add_row(move, impact, tag, how)
    if not moves:
        t.add_row("Nothing material to fix", "—", "—", "You're spending efficiently.")
    console.print(t)
    console.print("[dim]reclaim = confidently recoverable · lever = potential, needs your "
                  "judgment (not all work can downshift). Estimates, not billed amounts.[/]")


def _cost_out(r: Record, overrides) -> float:
    return pricing.cost_usd(r.model, 0, r.output, 0, 0, 0, overrides)
