"""Self-contained HTML report — no external assets, opens anywhere."""
from __future__ import annotations

import html as _html
from datetime import datetime

from .parse import Record
from .report import Agg, _cache_write_cost, _group, _money, _tokens, short_model


def _rows(buckets: dict[str, Agg], reverse=True) -> str:
    items = sorted(buckets.items(), key=lambda kv: kv[1].cost, reverse=reverse)
    out = []
    for name, a in items:
        hit = a.cache_hit_rate * 100
        cls = "good" if hit >= 80 else "ok" if hit >= 50 else "bad"
        out.append(
            f"<tr><td>{_html.escape(name)}</td><td class=num>{_money(a.cost)}</td>"
            f"<td class=num>{_tokens(a.input)}</td><td class=num>{_tokens(a.output)}</td>"
            f"<td class=num dim>{_tokens(a.cache_read)}</td><td class=num dim>{_tokens(a.cache_write)}</td>"
            f"<td class='num {cls}'>{hit:.0f}%</td></tr>"
        )
    return "\n".join(out)


def _table(title: str, buckets: dict[str, Agg], key: str, reverse=True) -> str:
    return f"""<section><h2>{_html.escape(title)}</h2><table>
<thead><tr><th>{_html.escape(key)}</th><th>Cost</th><th>Input</th><th>Output</th>
<th>Cache R</th><th>Cache W</th><th>Hit%</th></tr></thead>
<tbody>{_rows(buckets, reverse)}</tbody></table></section>"""


def render(records: list[Record], overrides) -> str:
    total = Agg()
    for r in records:
        total.add(r, overrides)
    write_cost = _cache_write_cost(records, overrides)
    hit = total.cache_hit_rate * 100
    span = (f"{records[0].ts:%Y-%m-%d} → {records[-1].ts:%Y-%m-%d}" if records else "—")
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>ccost report</title>
<style>
:root{{--bg:#0f1115;--card:#171a21;--fg:#e6e8ec;--dim:#8b93a1;--acc:#7dd3fc;--good:#4ade80;--ok:#fbbf24;--bad:#f87171;--line:#252a34}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
.wrap{{max-width:960px;margin:0 auto;padding:2.5rem 1.25rem}}
h1{{font-size:1.6rem;margin:0 0 .25rem}}h1 span{{color:var(--acc)}}.sub{{color:var(--dim);margin:0 0 2rem}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1rem;margin-bottom:2rem}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:1rem 1.15rem}}
.card .k{{color:var(--dim);font-size:.8rem;text-transform:uppercase;letter-spacing:.04em}}
.card .v{{font-size:1.5rem;font-weight:700;margin-top:.25rem}}.card .v.money{{color:var(--good)}}
h2{{font-size:1rem;color:var(--acc);margin:2rem 0 .6rem;font-weight:600}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
th,td{{text-align:left;padding:.55rem .8rem;border-bottom:1px solid var(--line)}}
th{{color:var(--dim);font-size:.78rem;text-transform:uppercase;letter-spacing:.03em;font-weight:600}}
tr:last-child td{{border-bottom:none}}.num{{text-align:right;font-variant-numeric:tabular-nums}}.dim{{color:var(--dim)}}
.good{{color:var(--good)}}.ok{{color:var(--ok)}}.bad{{color:var(--bad)}}
footer{{color:var(--dim);font-size:.8rem;margin-top:2.5rem;text-align:center}}
footer a{{color:var(--acc);text-decoration:none}}
</style></head><body><div class=wrap>
<h1><span>ccost</span> — Claude Code spend</h1>
<p class=sub>{span} · generated {gen}</p>
<div class=cards>
<div class=card><div class=k>Total cost</div><div class="v money">{_money(total.cost)}</div></div>
<div class=card><div class=k>Requests</div><div class=v>{total.records:,}</div></div>
<div class=card><div class=k>Tokens</div><div class=v>{_tokens(total.total_tokens)}</div></div>
<div class=card><div class=k>Cache hit rate</div><div class="v {'good' if hit>=80 else 'ok' if hit>=50 else 'bad'}">{hit:.0f}%</div></div>
<div class=card><div class=k>Spent on cache writes</div><div class=v>{_money(write_cost)}</div></div>
</div>
{_table("By model", _group(records, lambda r: short_model(r.model), overrides), "Model")}
{_table("By project", _group(records, lambda r: r.project, overrides), "Project")}
{_table("Daily", _group(records, lambda r: f"{r.ts:%Y-%m-%d}", overrides), "Date", reverse=False)}
{_table("Monthly", _group(records, lambda r: f"{r.ts:%Y-%m}", overrides), "Month", reverse=False)}
<footer>Made with <a href="https://github.com/namangoyal3/ccost">ccost</a> · prices are local estimates, not billed amounts</footer>
</div></body></html>"""
