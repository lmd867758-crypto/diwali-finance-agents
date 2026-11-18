"""Analyst Agent — watches BTC/USD, writes a signal to the shared bus.

Method (simple, explainable, no black box):
  * SMA-10 vs SMA-30 on 1-hour closes  -> trend
  * 10-hour momentum                   -> confirmation
  * ATR-14 (mean hourly high-low range) -> volatility, for the Trader's stops

Signal: LONG / SHORT / FLAT with confidence 0..1 and a plain-English reason.
The signal is appended to the message bus (bus.py) and saved to
latest_signal.json for the Trader and the dashboard.

Run:  python3 analyst.py            (fetches live candles)
      python3 analyst.py --mock     (uses a built-in rising sample series)
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

LATEST_SIGNAL_FILE = Path(
    os.environ.get("FINANCE_SIGNAL_FILE", BASE_DIR / "latest_signal.json")
)
CONFIDENCE_THRESHOLD = 0.60  # below this the Trader ignores the signal


def sma(values, n):
    return sum(values[-n:]) / n


def atr(candles, n=14):
    ranges = [c["high"] - c["low"] for c in candles[-n:]]
    return sum(ranges) / len(ranges)


def analyse(candles, source="unknown"):
    """Turn candles into a signal dict."""
    closes = [c["close"] for c in candles]
    if len(closes) < 31:
        raise ValueError(f"need >=31 candles, got {len(closes)}")
    fast = sma(closes, 10)
    slow = sma(closes, 30)
    trend = (fast - slow) / slow
    momentum = (closes[-1] - closes[-11]) / closes[-11]
    volatility = atr(candles, 14)
    price = closes[-1]

    # Trend counts double; momentum confirms. Score is a rough % move.
    score = 2.0 * trend + 1.0 * momentum
    confidence = min(1.0, abs(score) * 40.0)
    if abs(score) < 0.0015:
        direction = "FLAT"
        confidence = min(confidence, 0.45)
    else:
        direction = "LONG" if score > 0 else "SHORT"

    if direction == "LONG":
        reason = (f"SMA-10 (${fast:,.0f}) above SMA-30 (${slow:,.0f}), "
                  f"10h momentum {momentum * 100:+.2f}%. Trend up.")
    elif direction == "SHORT":
        reason = (f"SMA-10 (${fast:,.0f}) below SMA-30 (${slow:,.0f}), "
                  f"10h momentum {momentum * 100:+.2f}%. Trend down.")
    else:
        reason = (f"SMA-10 (${fast:,.0f}) and SMA-30 (${slow:,.0f}) almost "
                  f"equal; no clear trend. Stay flat.")

    return {
        "id": str(uuid.uuid4())[:8],
        "symbol": market.SYMBOL,
        "direction": direction,
        "confidence": round(confidence, 2),
        "reason": reason,
        "price": round(price, 2),
        "sma_fast": round(fast, 2),
        "sma_slow": round(slow, 2),
        "momentum_pct": round(momentum * 100, 2),
        "atr": round(volatility, 2),
        "candles": len(candles),
        "source": source,
        "ts": bus.now_iso(),
    }


def mock_candles():
    """A rising sample series (50 hourly candles) for offline testing."""
    candles = []
    price = 60000.0
    for i in range(50):
        price *= 1.0015  # steady ~0.15%/h climb
        candles.append({
            "ts": 1700000000 + i * 3600,
            "open": price / 1.0015,
            "high": price * 1.001,
            "low": price * 0.999,
            "close": price,
            "volume": 10.0,
        })
    return candles


def run(mock=False):
    if mock:
        candles, source = mock_candles(), "mock"
    else:
        candles, source = market.fetch_candles()
    signal = analyse(candles, source)
    LATEST_SIGNAL_FILE.write_text(json.dumps(signal, indent=2))
    bus.append("analyst", "signal", signal)
    print(f"[analyst] {signal['direction']} conf={signal['confidence']:.2f} "
          f"price=${signal['price']:,.2f} atr=${signal['atr']:,.2f} "
          f"({signal['source']})")
    print(f"[analyst] {signal['reason']}")
    return signal


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true",
                        help="use built-in sample candles, no network")
    args = parser.parse_args()
    run(mock=args.mock)
