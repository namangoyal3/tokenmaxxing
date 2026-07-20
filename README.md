<h1 align="center">tokenmaxxing</h1>

<p align="center">
  <b>Max out your Claude Code &amp; Codex tokens — don't waste the quota you paid for.</b><br>
  A fast, zero-config CLI (the <code>ccost</code> command) over your local agent logs: see your live
  <b>5-hour window</b>, a token-efficiency <b>score</b>, cost by agent/model/project, and the
  <b>cache waste</b> nobody else surfaces.
</p>

<p align="center">
  <code>uvx --from git+https://github.com/namangoyal3/tokenmaxxing ccost</code>
</p>

<p align="center">
  <a href="#max-your-5-hour-window">5-hour window</a> ·
  <a href="#install">Install</a> ·
  <a href="#what-you-get">What you get</a> ·
  <a href="#the-cache-angle">The cache angle</a> ·
  <a href="#tokenmaxxing">Tokenmaxxing</a> ·
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

<sub>This example uses a mixed Claude and Codex history. The Claude values estimate an equivalent API cost, not a billed amount.
The command assigns a zero cost to local models, such as Ollama and `:free` models.</sub>

## Max your 5-hour window

Claude subscription limits reset on a rolling **5-hour window**. The trap isn't only hitting
the wall — it's the opposite: finishing your window having used a fraction of the quota you
already paid for. `ccost window` shows the live picture so you use it fully.

```text
╭──────────────── ccost window · 5-hour quota ────────────────╮
│ Window   17:00 → 22:00   resets in 1h 01m                   │
│ Used     ███░░░░░░░░░░░░░░░░░░  70.5M  (13% of your peak)    │
│ Pace     295K/min → ~88.6M by reset (16%)                   │
│ On pace to use less than half your window — push harder.    │
╰─────────────────────────────────────────────────────────────╯
  Recent windows (vs your peak window)
  Jul 19 17:00   70.5M   ██░░░░░░░░░░░░░░░░ 13%
  Jul 19 05:00  326.5M   ███████████░░░░░░░ 60%   ← your fullest
  Jul 18 18:00    6.2M   ░░░░░░░░░░░░░░░░░░  1%    ← wasted window
```

- **Reset countdown** — exactly how long until the window rolls, so you front-load heavy work.
- **Burn rate → projection** — where you'll land by reset, and whether that's leaving quota
  unused or about to hit the wall.
- **Per-window fill** — every past window scored, so you can see the ones you wasted.
- The real per-plan cap is undisclosed and dynamic, so `ccost` measures against **your own
  fullest window** by default. Know your budget? Pass `--limit TOKENS` for a true percentage.

`ccost calendar` gives the contributions-style heatmap — which days you leaned in, which you
left on the table.

```text
╭──────── ccost calendar · token usage heatmap ────────╮
│ Mon ··········▁▁▁▁▁▁▅▅▅▅                              │
│ Fri ········▁▁·▁▁▁▁████▇▇                             │
│ Sun ······▁▁·▁▁▁▁▁▁▁▁▇▇▃▃▅▅                           │
│ 44 active days · 8.9B tokens · busiest day 948.5M     │
╰───────────────────────────────────────────────────────╯
```

## Schedule a prompt for the reset

Run `schedule` after Claude or Codex reports a limit error:

```bash
schedule "Review this repository and fix the failing tests"
```

The command detects the active agent and reads its reset time from the local log.
It waits five extra seconds for clock drift. It then starts the agent in the current directory.
Keep the terminal process active until the command starts. Press Ctrl-C to cancel the prompt.

Use `-` as the prompt to read a multi-line prompt from standard input.

## Install

`ccost` runs with [`uv`](https://docs.astral.sh/uv/) — no clone, no virtualenv:

```bash
# one-off run
uvx --from git+https://github.com/namangoyal3/tokenmaxxing ccost

# install as a persistent tool
uv tool install git+https://github.com/namangoyal3/tokenmaxxing
ccost
```

Or with pip:

```bash
pip install git+https://github.com/namangoyal3/tokenmaxxing
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

## Tokenmaxxing

`ccost maxx` scores how efficiently you spend and ranks concrete ways to spend less —
in dollars, so you fix the biggest thing first. It separates **reclaim** (waste you can
confidently recover) from **lever** (bigger potential savings that need your judgment).

```text
╭──────────── ccost maxx · tokenmaxxing ────────────╮
│ Token efficiency  A  (96/100)                     │
│ Cache reuse 96%  ·  total spend $18,241            │
╰───────────────────────────────────────────────────╯
~$608 (3%) is reclaimable waste. Bigger structural levers below.

  Move                       Impact    Type      How
  Downshift claude-opus-4-8  $7,331    lever     $12,219 on claude-opus-4-8 ≈ $4,888 on claude-sonnet-4-5.
  Trim output                ~$626     lever     Output is 11% of spend, priced 4–5× input.
  Batch one-shot sessions    $586      reclaim   142 sessions built cache they never read.
  Kill idle-gap rebuilds     $21       reclaim   12 turns rebuilt the 5m cache after a >5min gap.
```

What it computes from your logs (not vibes):

- **Idle-gap rebuilds** — turns that came after a >5-minute gap and re-paid to rebuild the
  5-minute cache. Staying active or using the 1-hour cache turns that write back into a
  0.1× read. *(Claude only — needs per-turn timestamps.)*
- **Cold one-shot sessions** — sessions that built cache and never read it. Each short,
  separate session re-pays the first-turn cache build; batching related work avoids it.
- **Model downshift** — how much a model's spend would drop one tier down (Opus→Sonnet).
  A what-if, not a promise: not every turn can downshift, but routing routine edits does.
- **Output trim** — output tokens cost 4–5× input; your output share is the ceiling on
  what terser prompts can save.

## Commands

| Command | Shows |
|---|---|
| `ccost` | Headline summary + cache economics + source/model/project breakdown |
| `ccost window` | Live 5-hour quota: used, burn rate, reset countdown, per-window fill |
| `ccost calendar` | Contributions-style heatmap of daily token usage |
| `ccost maxx` | Token-efficiency score + ranked, quantified ways to spend less |
| `ccost daily` | Cost per day |
| `ccost monthly` | Cost per month |
| `ccost projects` | Cost per project |
| `ccost models` | Cost per model |
| `ccost sources` | Cost per agent (Claude Code vs Codex) |
| `ccost html` | Write a shareable `ccost-report.html` |
| `ccost json` | Dump every priced record as JSON |
| `schedule PROMPT` | Run one prompt after the active agent limit resets |

Flags: `--source claude\|codex\|all` (default all), `--days N` (last N days),
`--limit TOKENS` (your per-window budget, for `window`), `--dir PATH` (custom Claude log
dir), `--pricing file.json` (override rates), `-o FILE` (html output path).

## Pricing

Prices use the standard public tiers from Anthropic and OpenAI. The table stores USD per million tokens.
Anthropic cache rates use the documented input multipliers: 0.10× for reads, 1.25× for 5-minute writes, and 2.00× for 1-hour writes.
Sonnet 5 uses its introductory rate through August 31, 2026. **These values estimate API cost, not your billed amount.**
Max and Pro plans use flat rates. Provider prices can change. Override a rate with this command:

```bash
ccost --pricing my-prices.json
```

```json
{ "fable": { "input": 10, "output": 50 }, "gpt-5.6-sol": { "input": 5, "output": 30 } }
```

Models with no public rate (e.g. experimental ones) are priced by best estimate and marked
with `*` in the report.

## Sources

| Agent | Log location | Status |
|---|---|---|
| **Claude Code** | `~/.claude/projects/` (`CLAUDE_CONFIG_DIR`) | ✅ per-turn usage |
| **Codex CLI** | `~/.codex/sessions/` (`CODEX_HOME`) | ✅ per-event deltas |
| Gemini CLI / Cursor / OpenCode | — | ❌ don't log per-request token usage locally |

`ccost` reads the available logs and merges the records. Use `--source` to select one agent.
Codex reports cumulative token counts. `ccost` calculates each event delta to prevent double counts and preserve model changes.
Codex logs expose cache reads but not cache writes. Thus, the Codex cache-write columns remain zero.
Want another source? [Open an issue](https://github.com/namangoyal3/tokenmaxxing/issues).

## How it works

1. Walk `~/.claude/projects/**/*.jsonl` and `~/.codex/sessions/**/rollout-*.jsonl`.
2. Pull token usage from each Claude turn or Codex snapshot.
3. Dedupe by message + request id — resumed sessions replay old turns.
4. Calculate each Codex cumulative counter delta.
5. Apply the cache-aware price to each record.
6. Aggregate the records and render the report.

The command reads local files only. It does not use the network. The source contains approximately 1,000 lines of Python.

## License

MIT
