"""5-hour usage windows: are you maxing the quota before it resets?

Claude subscription limits reset on a rolling ~5-hour window. The exact token
cap is dynamic and undisclosed, so ccost measures how full each window is
against *your own peak window* (or a `--limit` you set) — enough to tell you
whether you're leaving quota on the table or about to hit the wall.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .parse import Record

WINDOW = timedelta(hours=5)


@dataclass
class Block:
    start: datetime
    last: datetime
    tokens: int = 0
    records: int = 0

    @property
    def end(self) -> datetime:
        return self.start + WINDOW

    def active(self, now: datetime) -> bool:
        return self.start <= now < self.end and (now - self.last) < WINDOW


def _floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def detect_blocks(records: list[Record]) -> list[Block]:
    """Group time-sorted records into 5-hour windows (gap > 5h opens a new one)."""
    blocks: list[Block] = []
    cur: Block | None = None
    for r in sorted(records, key=lambda x: x.ts):
        if cur is None or r.ts - cur.start >= WINDOW or r.ts - cur.last >= WINDOW:
            cur = Block(start=_floor_hour(r.ts), last=r.ts)
            blocks.append(cur)
        cur.tokens += r.total_tokens
        cur.records += 1
        cur.last = r.ts
    return blocks


def _fmt_delta(td: timedelta) -> str:
    m = max(int(td.total_seconds() // 60), 0)
    return f"{m // 60}h {m % 60:02d}m"


def _tokens(n: float) -> str:
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if n >= size:
            return f"{n / size:.1f}{unit}"
    return str(int(n))


def _bar(frac: float, width: int = 24) -> str:
    frac = max(0.0, min(frac, 1.0))
    filled = round(frac * width)
    return "█" * filled + "░" * (width - filled)


def print_window(console: Console, records: list[Record], overrides, limit: int | None = None,
                 now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    if not records:
        console.print("[yellow]No usage found.[/]")
        return
    blocks = detect_blocks(records)
    peak = max((b.tokens for b in blocks), default=0)
    denom = limit or peak or 1
    denom_label = "your --limit" if limit else "your peak window"

    active = next((b for b in blocks if b.active(now)), None)
    if active is None:
        last = blocks[-1]
        console.print(Panel(
            Text.assemble(
                ("No active window.\n", "yellow"),
                (f"Your last window ended ~{_fmt_delta(now - last.end)} ago.\n", "white"),
                ("Send a message to open a fresh 5-hour window — the clock only runs once you start.",
                 "dim"),
            ),
            title="[bold]ccost window[/] · 5-hour quota", border_style="yellow"))
        _recent_blocks(console, blocks, denom, denom_label, now)
        return

    elapsed = now - active.start
    remaining = active.end - now
    elapsed_min = max(elapsed.total_seconds() / 60, 1)
    burn = active.tokens / elapsed_min  # tokens/min
    projected = active.tokens + burn * (remaining.total_seconds() / 60)
    util = active.tokens / denom
    util_proj = projected / denom

    body = Text()
    body.append(f"Window   {active.start:%H:%M} → {active.end:%H:%M}   ", style="white")
    body.append(f"resets in {_fmt_delta(remaining)}\n", style="bold cyan")
    body.append(f"Used     {_bar(util)}  {_tokens(active.tokens)}  ({util * 100:.0f}% of {denom_label})\n",
                style="white")
    body.append(f"Pace     {_tokens(burn)}/min → ~{_tokens(projected)} by reset "
                f"({util_proj * 100:.0f}%)\n", style="dim")

    if util_proj < 0.5:
        body.append("You're on pace to use less than half your window — lots of headroom, push harder.",
                    style="yellow")
        border = "yellow"
    elif util_proj < 0.9:
        body.append("Good pace — you'll use most of this window.", style="green")
        border = "green"
    elif util_proj <= 1.1:
        body.append("You're maxing this window. Nicely done.", style="green")
        border = "green"
    else:
        body.append("On pace to blow past your usual peak — you may hit the wall before reset.",
                    style="red")
        border = "red"
    console.print(Panel(body, title="[bold]ccost window[/] · 5-hour quota", border_style=border))
    _recent_blocks(console, blocks, denom, denom_label, now)


def _recent_blocks(console: Console, blocks: list[Block], denom: float, denom_label: str,
                   now: datetime, n: int = 8) -> None:
    t = Table(title=f"Recent windows (vs {denom_label})", title_style="bold",
              header_style="bold cyan")
    t.add_column("Window start", no_wrap=True)
    t.add_column("Used", justify="right")
    t.add_column("Fill", justify="left")
    for b in blocks[-n:][::-1]:
        frac = b.tokens / denom if denom else 0
        style = "green" if frac >= 0.9 else "yellow" if frac >= 0.5 else "red"
        t.add_row(f"{b.start:%b %d %H:%M}", _tokens(b.tokens),
                  Text(f"{_bar(frac, 18)} {frac * 100:.0f}%", style=style))
    console.print(t)
    console.print("[dim]Fill = tokens vs your fullest window. Undisclosed real cap — "
                  "set your own with --limit TOKENS.[/]")


def print_calendar(console: Console, records: list[Record], weeks: int = 15,
                   now: datetime | None = None) -> None:
    """GitHub-style heatmap of daily token usage — see which days you leaned in."""
    now = now or datetime.now(timezone.utc)
    if not records:
        console.print("[yellow]No usage found.[/]")
        return
    daily: dict[date, int] = defaultdict(int)
    for r in records:
        daily[r.ts.date()] += r.total_tokens
    peak_day = max(daily.values(), default=1)

    # Columns are weeks; rows are Mon..Sun. End on the current week.
    end = now.date()
    start = end - timedelta(days=end.weekday() + 7 * (weeks - 1))
    levels = " ▁▃▅▇█"  # 6 intensity steps

    def cell(day) -> Text:
        v = daily.get(day, 0)
        if v == 0:
            return Text("·", style="grey30")
        step = min(int(v / peak_day * (len(levels) - 1)) + 1, len(levels) - 1)
        pct = v / peak_day
        color = "green" if pct >= 0.66 else "yellow" if pct >= 0.33 else "cyan"
        return Text(levels[step] * 2, style=color)

    rows = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    grid = Text()
    for wd in range(7):
        grid.append(f"{rows[wd]} ", style="dim")
        day = start + timedelta(days=wd)
        while day <= end:
            grid.append_text(cell(day) if day <= end else Text("  "))
            day += timedelta(days=7)
        grid.append("\n")
    total = sum(daily.values())
    grid.append(f"\n{len([d for d in daily if daily[d] > 0])} active days · "
                f"{_tokens(total)} tokens · busiest day {_tokens(peak_day)}", style="dim")
    console.print(Panel(grid, title="[bold]ccost calendar[/] · token usage heatmap",
                        border_style="cyan"))
