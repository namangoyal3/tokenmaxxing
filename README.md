<h1 align="center">ccost</h1>

<p align="center">
  <b>See what your AI coding agents actually cost you.</b><br>
  A fast, zero-config CLI that turns your local <b>Claude Code</b> &amp; <b>Codex</b> logs into a beautiful cost report —<br>
  by agent, model, project, day — and shows you the <b>cache waste</b> nobody else surfaces.
</p>

<p align="center">
  <code>uvx --from git+https://github.com/namangoyal3/ccost ccost</code>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#what-you-get">What you get</a> ·
  <a href="#the-cache-angle">The cache angle</a> ·
  <a href="#commands">Commands</a> ·
  <a href="#pricing">Pricing</a>
</p>

<p align="center"><img src="docs/report.png" alt="ccost HTML report" width="820"></p>

<p align="center"><sub><code>ccost html</code> writes a shareable, self-contained report like this.</sub></p>

---

Claude Code and Codex each write a JSONL log for every session (`~/.claude/projects/` and
`~/.codex/sessions/`). Those files already know exactly how many tokens you burned, on which
model, in which project. `ccost` reads them locally, prices them, and tells you where your
money went — across both agents at once. Nothing is uploaded.

```text
╭──────────────────── ccost · AI coding spend ────────────────────╮
│ Total cost   $18,211.68                                          │
│ Requests     40,944                                              │
│ Tokens       8.9B                                                │
│ Period       2026-05-13 → 2026-07-19  (66d, $275.9/day)          │
╰──────────────────────────────────────────────────────────────────╯
╭─────────────────────── Cache economics ─────────────────────────╮
│ Cache hit rate   96%                                             │
│ Spent writing cache   $6,942.95  (38% of total)                  │
│ Healthy reuse — you're getting cache back at 0.1x.               │
╰──────────────────────────────────────────────────────────────────╯
                          By source
┃ Source ┃       Cost ┃ Input ┃ Cache R ┃ Cache W ┃ Hit% ┃
┡━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━┩
│ claude │ $17,637.75 │ 36.1M │    6.7B │  345.7M │  95% │
│ codex  │    $573.93 │ 153M  │    1.7B │       0 │ 100% │
                          By model
┃ Model            ┃       Cost ┃ Cache R ┃ Cache W ┃ Hit% ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━┩
│ claude-opus-4-8  │ $12,191.30 │    4.0B │  170.4M │  96% │
│ claude-fable-5   │  $4,695.48 │    1.4B │   73.9M │  95% │
│ gpt-5.6-sol      │    $524.99 │    1.5B │       0 │ 100% │
│ claude-sonnet-5  │    $606.51 │  838.9M │   59.7M │  93% │
```

<sub>Real output from ~6,100 sessions across both agents. On a Max/Pro plan the Claude figures
are equivalent-API-value estimates, not billed dollars — that number is the leverage your
subscription is giving you. Locally-run models (Ollama, `:free`) are correctly counted as $0.</sub>

## Install

`ccost` runs with [`uv`](https://docs.astral.sh/uv/) — no clone, no virtualenv:

```bash
# one-off run
uvx --from git+https://github.com/namangoyal3/ccost ccost

# install as a persistent tool
uv tool install git+https://github.com/namangoyal3/ccost
ccost
```

Or with pip:

```bash
pip install git+https://github.com/namangoyal3/ccost
```

## What you get

- **Total spend** across every session, priced per model with real published rates.
- **By agent** — Claude Code vs Codex, side by side.
- **By model** — where Opus/Sonnet/Haiku/GPT-5 each land on your bill.
- **By project** — which repo is quietly burning the most.
- **Daily / monthly** trends with a `$/day` burn rate.
- **An HTML report** you can share: `ccost html`.
- **JSON** for piping into anything else: `ccost json`.

## The cache angle

Claude Code's cost is dominated by **prompt caching**, and most tools ignore it. Cache
*writes* cost 1.25–2× the input rate; cache *reads* cost only 0.1×. So your bill hinges on
one number: **how often you reuse cached context instead of rebuilding it.**

`ccost` computes your **cache hit rate** and the exact dollars spent creating cache entries.
A low hit rate means long gaps between turns are expiring the 5-minute cache and you're
*re-paying* to rebuild context you already had. That's a knob you can turn — and `ccost` is
the only reader that shows you the knob.

## Commands

| Command | Shows |
|---|---|
| `ccost` | Headline summary + cache economics + source/model/project breakdown |
| `ccost daily` | Cost per day |
| `ccost monthly` | Cost per month |
| `ccost projects` | Cost per project |
| `ccost models` | Cost per model |
| `ccost sources` | Cost per agent (Claude Code vs Codex) |
| `ccost html` | Write a shareable `ccost-report.html` |
| `ccost json` | Dump every priced record as JSON |

Flags: `--source claude\|codex\|all` (default all), `--days N` (last N days),
`--dir PATH` (custom Claude log dir), `--pricing file.json` (override rates),
`-o FILE` (html output path).

## Pricing

Prices are USD per million tokens, standard tier, baked in from Anthropic's public pricing.
Cache rates use Anthropic's documented multipliers of the base input rate (read 0.10×,
5-minute write 1.25×, 1-hour write 2.00×). **These are local estimates, not your billed
amount** — Max/Pro plans are flat-rate, and prices drift. Override anything:

```bash
ccost --pricing my-prices.json
```

```json
{ "opus": { "input": 15, "output": 75 }, "sonnet": { "input": 3, "output": 15 } }
```

Models with no public rate (e.g. experimental ones) are priced by best estimate and marked
with `*` in the report.

## Sources

| Agent | Log location | Status |
|---|---|---|
| **Claude Code** | `~/.claude/projects/` (`CLAUDE_CONFIG_DIR`) | ✅ per-turn usage |
| **Codex CLI** | `~/.codex/sessions/` (`CODEX_HOME`) | ✅ per-session totals |
| Gemini CLI / Cursor / OpenCode | — | ❌ don't log per-request token usage locally |

`ccost` reads whatever is present and merges it. Use `--source` to scope to one agent.
Codex reports a *cumulative* token count per session, so ccost takes each session's final
total (never double-counting turns). OpenAI has no cache-write premium, so Codex cache
columns are read-only. New source? [Open an issue](https://github.com/namangoyal3/ccost/issues) —
a source is one function that yields `Record`s.

## How it works

1. Walk `~/.claude/projects/**/*.jsonl` and `~/.codex/sessions/**/rollout-*.jsonl`.
2. Pull token usage from each assistant turn (Claude) or session total (Codex).
3. Dedupe by message + request id — resumed sessions replay old turns.
4. Price each record cache-aware, aggregate, render.

Pure local reads. No network. ~700 lines of Python.

## License

MIT
