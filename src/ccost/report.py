"""Aggregate usage records and render them with rich."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import re

from . import pricing
from .parse import Record

_DATE_SUFFIX = re.compile(r"-\d{6,}$")


def short_model(model: str) -> str:
    """Trim a trailing date stamp: claude-haiku-4-5-20251001 -> claude-haiku-4-5."""
    return _DATE_SUFFIX.sub("", model)


@dataclass
class Agg:
    cost: float = 0.0
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    records: int = 0
    models: set[str] = field(default_factory=set)

    def add(self, r: Record, overrides) -> None:
        self.cost += pricing.cost_usd(
            r.model, r.input, r.output, r.cache_read, r.cache_write_5m, r.cache_write_1h, overrides
        )
        self.input += r.input
        self.output += r.output
        self.cache_read += r.cache_read
        self.cache_write += r.cache_write_5m + r.cache_write_1h
        self.records += 1
        self.models.add(r.model)

    @property
    def total_tokens(self) -> int:
        return self.input + self.output + self.cache_read + self.cache_write

    @property
    def cache_hit_rate(self) -> float:
        denom = self.cache_read + self.cache_write
        return self.cache_read / denom if denom else 0.0


def _money(x: float) -> str:
    return f"${x:,.2f}" if x >= 0.005 else f"${x:.4f}"


def _tokens(n: int) -> str:
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if n >= size:
            return f"{n / size:.1f}{unit}"
    return str(n)


def _group(records: list[Record], keyfn, overrides) -> dict[str, Agg]:
    buckets: dict[str, Agg] = defaultdict(Agg)
    for r in records:
        buckets[keyfn(r)].add(r, overrides)
    return buckets


def _cache_write_cost(records: list[Record], overrides) -> float:
    """USD spent creating cache entries (5m + 1h writes only)."""
    total = 0.0
    for r in records:
        total += pricing.cost_usd(r.model, 0, 0, 0, r.cache_write_5m, r.cache_write_1h, overrides)
    return total


def _breakdown_table(title: str, buckets: dict[str, Agg], key_header: str, sort_key_desc=True) -> Table:
    t = Table(title=title, title_style="bold", header_style="bold cyan", expand=False)
    t.add_column(key_header, style="white", no_wrap=True)
    t.add_column("Cost", justify="right", style="green")
    t.add_column("Input", justify="right")
    t.add_column("Output", justify="right")
    t.add_column("Cache R", justify="right", style="dim")
    t.add_column("Cache W", justify="right", style="dim")
    t.add_column("Hit%", justify="right")
    items = sorted(buckets.items(), key=lambda kv: kv[1].cost, reverse=sort_key_desc)
    for name, a in items:
        hit = a.cache_hit_rate
        hit_style = "green" if hit >= 0.8 else "yellow" if hit >= 0.5 else "red"
        t.add_row(
            name,
            _money(a.cost),
            _tokens(a.input),
            _tokens(a.output),
            _tokens(a.cache_read),
            _tokens(a.cache_write),
            Text(f"{hit * 100:.0f}%", style=hit_style),
        )
    return t


def print_summary(console: Console, records: list[Record], overrides) -> None:
    if not records:
        console.print("[yellow]No usage found. Point ccost at your Claude logs with --dir, "
                      "or check CLAUDE_CONFIG_DIR.[/]")
        return
    total = Agg()
    for r in records:
        total.add(r, overrides)

    start, end = records[0].ts, records[-1].ts
    days = max((end - start).days, 1)

    header = Table.grid(padding=(0, 3))
    header.add_column(justify="left")
    header.add_column(justify="left")
    header.add_row(Text("Total cost", style="dim"), Text(_money(total.cost), style="bold green"))
    header.add_row(Text("Requests", style="dim"), f"{total.records:,}")
    header.add_row(Text("Tokens", style="dim"), _tokens(total.total_tokens))
    header.add_row(Text("Period", style="dim"),
                   f"{start:%Y-%m-%d} → {end:%Y-%m-%d}  ({days}d, {_money(total.cost / days)}/day)")
    srcs = {r.source for r in records}
    label = "Claude Code spend" if srcs == {"claude"} else "Codex spend" if srcs == {"codex"} else "AI coding spend"
    console.print(Panel(header, title=f"[bold]ccost[/] · {label}", border_style="cyan"))

    # The differentiator: cache economics. Cache writes cost 1.25–2x input; reads
    # cost 0.1x. A low hit rate means you're paying to rebuild context you could reuse.
    write_cost = _cache_write_cost(records, overrides)
    hit = total.cache_hit_rate
    cache_lines = Text()
    cache_lines.append(f"Cache hit rate   {hit * 100:.0f}%\n",
                       style="green" if hit >= 0.8 else "yellow" if hit >= 0.5 else "red")
    cache_lines.append(f"Spent writing cache   {_money(write_cost)}", style="white")
    cache_lines.append(f"  ({write_cost / total.cost * 100:.0f}% of total)\n" if total.cost else "\n",
                       style="dim")
    if hit < 0.7:
        cache_lines.append(
            "Low reuse — long gaps between turns expire the 5m cache and you re-pay to rebuild it. "
            "Keep sessions active or lean on the 1h cache.",
            style="yellow",
        )
    else:
        cache_lines.append("Healthy reuse — you're getting cache back at 0.1x.", style="green")
    console.print(Panel(cache_lines, title="[bold]Cache economics[/]", border_style="magenta"))

    if len({r.source for r in records}) > 1:
        console.print(_breakdown_table("By source", _group(records, lambda r: r.source, overrides), "Source"))
    console.print(_breakdown_table("By model", _group(records, lambda r: short_model(r.model), overrides), "Model"))
    projects = _group(records, lambda r: r.project, overrides)
    console.print(_breakdown_table("By project (top 10)",
                                   dict(sorted(projects.items(), key=lambda kv: kv[1].cost, reverse=True)[:10]),
                                   "Project"))

    if any(pricing.is_estimated(m, overrides) for m in total.models):
        est = sorted(m for m in total.models if pricing.is_estimated(m, overrides))
        console.print(f"[dim]* estimated pricing for: {', '.join(est)} "
                      f"(no public rate; override with --pricing)[/]")
    console.print("[dim]→ run [/][bold]ccost maxx[/][dim] to score your token efficiency and see how to spend less.[/]")


def print_daily(console: Console, records: list[Record], overrides) -> None:
    buckets = _group(records, lambda r: f"{r.ts:%Y-%m-%d}", overrides)
    console.print(_breakdown_table("Daily", buckets, "Date", sort_key_desc=False))


def print_monthly(console: Console, records: list[Record], overrides) -> None:
    buckets = _group(records, lambda r: f"{r.ts:%Y-%m}", overrides)
    console.print(_breakdown_table("Monthly", buckets, "Month", sort_key_desc=False))


def print_projects(console: Console, records: list[Record], overrides) -> None:
    console.print(_breakdown_table("By project", _group(records, lambda r: r.project, overrides), "Project"))


def print_models(console: Console, records: list[Record], overrides) -> None:
    console.print(_breakdown_table("By model", _group(records, lambda r: short_model(r.model), overrides), "Model"))


def print_sources(console: Console, records: list[Record], overrides) -> None:
    console.print(_breakdown_table("By source", _group(records, lambda r: r.source, overrides), "Source"))
