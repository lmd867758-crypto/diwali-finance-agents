# Finance Agents — Diwali Festiverse Agent-to-Agent Hackathon (SF Edition)

**Track:** Finance — Analyze & Trade
**Team:** solo (1 person)
**Status:** built, tested locally and inside a real Agent37 sandbox

Two AI agents that collaborate on BTC/USD. The **Analyst Agent** watches the
market and writes signals to a shared message log. The **Trader Agent**
reads those signals and trades **simulated money only** — a virtual $10,000
paper account. No real money, no broker, no real orders, ever.

## How the two agents collaborate

```
Kraken public API (free, no key)
        │
        ▼
┌────────────────┐   signal (LONG/SHORT/FLAT + confidence + reason)   ┌────────────────┐
│ Analyst Agent  │ ───────────────►  messages.jsonl (shared bus) ────► │ Trader Agent   │
│ analyst.py     │                                                      │ trader.py      │
└────────────────┘   trade_opened / trade_closed / note ◄───────────── └────────────────┘
                              (same bus — the whole conversation is visible)
```

## Analyst Agent (`analyst.py`)

- Fetches 50 × 1-hour BTC/USD candles (Kraken public OHLC; CoinGecko fallback).
- Signal from SMA-10 vs SMA-30 trend + 10-hour momentum, with ATR-14 volatility.
- Output: `LONG` / `SHORT` / `FLAT`, confidence 0–1, plain-English reason, ATR.

## Trader Agent (`trader.py`)

Fixed risk rules, no exceptions:

- **1% of equity risked per trade**, stop = 1.5 × ATR, take-profit = 2 × stop (2:1).
- One open position at a time; minimum signal confidence **0.60**.
- Closes on stop-loss, take-profit, or an opposite signal (confidence ≥ 0.60).
- Every decision is written to the message bus and to `state.json`.

## Agent37 integration (`agent37_runner.py`)

This is the sponsor-tool integration: the runner provisions a real Agent37
sandbox (`POST /v1/instances`, template `agent37-base`, 2 vCPU / 4 GB,
`auto_sleep: true`), uploads the agent code, runs one Analyst → Trader
cycle **inside the sandbox**, pulls the message log and paper-account state
back, then **deletes the sandbox**. A ~10-minute test costs about **$0.001**
($4.76/month while running, metered per minute).

Verified live on 2026-11-16: sandbox `jelo480grh` created, cycle ran inside
it on real Kraken data (SHORT, confidence 0.33 — Trader correctly held off),
results pulled back, sandbox deleted. Estimated cost ≈ $0.0000. The live
GrideX instance and the stopped OpenCode instance were not touched.

```bash
python3 agent37_runner.py --mock   # dry run, no API calls
python3 agent37_runner.py --live   # real sandbox test, then delete it
```

## Run it

No API keys needed. Python 3.10+, standard library only — no pip install.

```bash
./run.sh              # one live cycle + dashboard on http://localhost:8000
./run.sh --mock       # sample candles, no network
python3 test_flow.py  # 21 end-to-end checks (mock data)
```

Dashboard (`app.py`): latest Analyst signal, paper-account equity / P/L,
open and closed simulated trades, the full agent message log, and a
"Run one cycle" button. `GET /api/state`, `POST /api/run`.

## Files

| File | What it is |
|---|---|
| `analyst.py` | Analyst Agent — market data → signal |
| `trader.py` | Trader Agent — signal → simulated trades |
| `bus.py` | Shared message log (`messages.jsonl`) |
| `market.py` | Free public market data (Kraken + CoinGecko fallback) |
| `run_cycle.py` | One full Analyst → Trader cycle |
| `app.py` + `static/index.html` | Mobile-friendly dashboard |
| `agent37_runner.py` | Agent37 sandbox runner (create → run → fetch → delete) |
| `test_flow.py` | 21 end-to-end checks |
| `state.json` / `latest_signal.json` / `messages.jsonl` | Runtime state (created on first run) |

## What was verified (honest)

- ✅ `python3 test_flow.py` — **21/21 checks pass** (mock data): signal → bus → trade with exact 1% risk ($100.00), stop/TP placement, opposite-signal close, dashboard API + live HTTP server.
- ✅ Live Kraken data locally: Analyst produced a real signal (SHORT, conf 0.33) and the Trader correctly refused to trade below the 0.60 threshold.
- ✅ Live Agent37 sandbox: full cycle ran inside a real sandbox on real market data; sandbox deleted afterwards, cost ≈ $0.0000.
- ❌ **Not yet verified with a strong live signal** — the live market has been flat (confidence ~0.33), so a live trade opening has only been proven on mock data so far. Run more cycles when the trend strengthens.

## 2-minute demo outline (for submission)

1. **0:00–0:20** — Dashboard: "Two agents, one paper account." Show the Analyst signal card.
2. **0:20–0:50** — Run one cycle live: Analyst fetches Kraken candles, writes the signal to the bus; Trader reads it and opens/closes a simulated position with the 1% risk rule.
3. **0:50–1:20** — Message log: show the Analyst → Trader conversation and the trade with stop / take-profit.
4. **1:20–1:50** — Agent37: `python3 agent37_runner.py --live` — the same agents running inside a real Agent37 sandbox, results pulled back, sandbox deleted.
5. **1:50–2:00** — "Simulated trading only. Built with Agent37."

## Submission checklist (still to do — needs the user)

- [ ] Register on Luma: https://luma.com/bc8etq9q
- [ ] Join the event WhatsApp group (link on the Luma page)
- [ ] Push this folder to a **public** GitHub repo
- [ ] Record the ≤2-minute demo video (outline above)
- [ ] Submit repo link + demo before **19 Nov 2026, 08:00 Dhaka time**
- [ ] Mention Agent37 in the submission (the Agent37 prize is $1,500 in credits)
