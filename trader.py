"""Trader Agent — reads the Analyst's signal and trades SIMULATED money.

SIMULATED TRADING ONLY. This agent never touches real money, never connects
to a broker or exchange account, and never places a real order. It manages a
virtual $10,000 paper account and logs every simulated trade.

Risk rules (fixed, no exceptions):
  * 1% of equity risked per trade.
  * Stop distance = 1.5 x ATR(14) from the Analyst's signal.
  * Take-profit = 2 x stop distance (2:1 reward:risk).
  * One open position at a time; minimum signal confidence 0.60.
  * A position closes on: stop hit, take-profit hit, or an opposite signal
    with confidence >= 0.60.

Flow per cycle:
  1. Read the latest price + latest Analyst signal.
  2. Check the open position for stop / take-profit.
  3. If flat and the signal is strong enough, open a simulated position.
  4. Every decision is written to the message bus (bus.py) and to state.json.

Run:  python3 trader.py            (uses latest_signal.json + live price)
      python3 trader.py --mock     (uses the mock price from the signal)
"""

import argparse
import json
import math
import os
import sys
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import bus  # noqa: E402
import market  # noqa: E402
from analyst import CONFIDENCE_THRESHOLD, LATEST_SIGNAL_FILE  # noqa: E402

STATE_FILE = Path(os.environ.get("FINANCE_STATE_FILE", BASE_DIR / "state.json"))
STARTING_CASH = 10_000.0
RISK_PCT = 0.01        # 1% of equity per trade
STOP_ATR_MULT = 1.5    # stop = 1.5 x ATR
TP_MULT = 2.0          # take-profit = 2 x stop distance


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "cash": STARTING_CASH,
        "starting_cash": STARTING_CASH,
        "positions": [],
        "trades": [],
    }


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def equity(state, price):
    """Cash + unrealised P/L of the open position at `price`."""
    total = state["cash"]
    for pos in state["positions"]:
        if pos["side"] == "LONG":
            total += (price - pos["entry"]) * pos["qty"]
        else:
            total += (pos["entry"] - price) * pos["qty"]
    return total


def open_position(state, signal):
    """Open one simulated position sized by the 1% risk rule."""
    eq = equity(state, signal["price"])
    risk_dollars = eq * RISK_PCT
    stop_distance = STOP_ATR_MULT * signal["atr"]
    if stop_distance <= 0:
        return None
    qty = risk_dollars / stop_distance
    side = signal["direction"]
    entry = signal["price"]
    if side == "LONG":
        stop = entry - stop_distance
        tp = entry + TP_MULT * stop_distance
    else:
        stop = entry + stop_distance
        tp = entry - TP_MULT * stop_distance
    pos = {
        "id": str(uuid.uuid4())[:8],
        "symbol": signal["symbol"],
        "side": side,
        "entry": round(entry, 2),
        "qty": round(qty, 6),
        "stop": round(stop, 2),
        "tp": round(tp, 2),
        "risk_dollars": round(risk_dollars, 2),
        "signal_id": signal["id"],
        "opened_at": bus.now_iso(),
    }
    state["positions"].append(pos)
    bus.append("trader", "trade_opened", {
        "position_id": pos["id"],
        "side": side,
        "entry": pos["entry"],
        "qty": pos["qty"],
        "stop": pos["stop"],
        "tp": pos["tp"],
        "risk_dollars": pos["risk_dollars"],
        "reason": f"Analyst signal {side} conf={signal['confidence']:.2f}: "
                  f"{signal['reason']}",
    })
    print(f"[trader] OPENED {side} {pos['qty']} {signal['symbol']} @ "
          f"${entry:,.2f} stop=${stop:,.2f} tp=${tp:,.2f} "
          f"(risk ${risk_dollars:.2f})")
    return pos


def close_position(state, pos, price, reason):
    """Close a simulated position, book the P/L, log the trade."""
    if pos["side"] == "LONG":
        pnl = (price - pos["entry"]) * pos["qty"]
    else:
        pnl = (pos["entry"] - price) * pos["qty"]
    pnl = round(pnl, 2)
    state["cash"] = round(state["cash"] + pnl, 2)
    state["positions"] = [p for p in state["positions"] if p["id"] != pos["id"]]
    trade = {
        "id": pos["id"],
        "symbol": pos["symbol"],
        "side": pos["side"],
        "entry": pos["entry"],
        "exit": round(price, 2),
        "qty": pos["qty"],
        "pnl": pnl,
        "reason": reason,
        "opened_at": pos["opened_at"],
        "closed_at": bus.now_iso(),
    }
    state["trades"].append(trade)
    bus.append("trader", "trade_closed", trade)
    print(f"[trader] CLOSED {pos['side']} @ ${price:,.2f} "
          f"P/L=${pnl:+,.2f} ({reason})")
    return trade


def run(mock=False):
    state = load_state()
    if not LATEST_SIGNAL_FILE.exists():
        print("[trader] no signal yet — run analyst.py first")
        return state
    signal = json.loads(LATEST_SIGNAL_FILE.read_text())
    if mock:
        price = signal["price"]
    else:
        candles, _source = market.fetch_candles(limit=5, min_needed=1)
        price = market.latest_price(candles)

    # 1. Check the open position for stop / take-profit.
    for pos in list(state["positions"]):
        if pos["side"] == "LONG":
            if price <= pos["stop"]:
                close_position(state, pos, price, "stop-loss hit")
            elif price >= pos["tp"]:
                close_position(state, pos, price, "take-profit hit")
        else:
            if price >= pos["stop"]:
                close_position(state, pos, price, "stop-loss hit")
            elif price <= pos["tp"]:
                close_position(state, pos, price, "take-profit hit")

    # 2. Act on the Analyst's signal.
    direction = signal["direction"]
    confidence = signal["confidence"]
    open_pos = state["positions"][0] if state["positions"] else None
    if open_pos and direction in ("LONG", "SHORT") and direction != open_pos["side"] \
            and confidence >= CONFIDENCE_THRESHOLD:
        close_position(state, open_pos, price,
                       f"opposite Analyst signal ({direction} "
                       f"conf={confidence:.2f})")
        open_pos = None
    if not state["positions"]:
        if direction in ("LONG", "SHORT") and confidence >= CONFIDENCE_THRESHOLD:
            open_position(state, signal)
        else:
            bus.append("trader", "note", {
                "text": f"No trade: signal {direction} "
                        f"conf={confidence:.2f} below threshold "
                        f"{CONFIDENCE_THRESHOLD:.2f} or flat.",
                "price": price,
            })
            print(f"[trader] no trade (signal {direction} "
                  f"conf={confidence:.2f})")
    save_state(state)
    eq = equity(state, price)
    print(f"[trader] cash=${state['cash']:,.2f} equity=${eq:,.2f} "
          f"open={len(state['positions'])} closed={len(state['trades'])}")
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true",
                        help="use the signal price, no network")
    args = parser.parse_args()
    run(mock=args.mock)
