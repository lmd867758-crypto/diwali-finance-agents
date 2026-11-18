"""Free public market data for the Analyst Agent. Stdlib only, no API key.

Primary source: Kraken public OHLC endpoint (no key, no login).
    GET https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=60
    -> [time, open, high, low, close, vwap, volume, count]

Fallback source: CoinGecko public market chart (no key).
    GET https://api.coingecko.com/api/v3/coins/bitcoin/market_chart
        ?vs_currency=usd&days=2&interval=hourly
    -> {"prices": [[ms, price], ...]}  (closes only, no high/low)

A candle is a dict: {"ts", "open", "high", "low", "close", "volume"}.
"""

import json
import time
import urllib.error
import urllib.request

KRAKEN_URL = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=60"
COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
    "?vs_currency=usd&days=2&interval=hourly"
)
SYMBOL = "BTC/USD"
USER_AGENT = {"User-Agent": "diwali-finance-agents/1.0 (hackathon demo)"}


def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers=USER_AGENT)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_kraken(limit=50, min_needed=31):
    """Fetch the last `limit` 1-hour BTC/USD candles from Kraken."""
    data = _get_json(KRAKEN_URL)
    if data.get("error"):
        raise RuntimeError(f"Kraken error: {data['error']}")
    rows = data["result"]["XXBTZUSD"]
    candles = []
    for row in rows[-limit:]:
        ts, o, h, l, c, _vwap, vol, _count = row
        candles.append({
            "ts": int(ts),
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": float(vol),
        })
    if len(candles) < min_needed:
        raise RuntimeError(f"Kraken returned only {len(candles)} candles")
    return candles


def fetch_coingecko(limit=50, min_needed=31):
    """Fallback: hourly BTC closes from CoinGecko (high/low = close)."""
    data = _get_json(COINGECKO_URL)
    prices = data["prices"][-limit:]
    candles = []
    for ms, price in prices:
        candles.append({
            "ts": int(ms // 1000),
            "open": float(price),
            "high": float(price),
            "low": float(price),
            "close": float(price),
            "volume": 0.0,
        })
    if len(candles) < min_needed:
        raise RuntimeError(f"CoinGecko returned only {len(candles)} points")
    return candles


def fetch_candles(limit=50, min_needed=31):
    """Try Kraken first, fall back to CoinGecko. Returns (candles, source)."""
    try:
        return fetch_kraken(limit, min_needed), "kraken"
    except Exception as exc:  # noqa: BLE001 - fallback is the point
        print(f"Kraken failed ({exc}); falling back to CoinGecko")
        try:
            return fetch_coingecko(limit, min_needed), "coingecko"
        except Exception as exc2:  # noqa: BLE001
            raise RuntimeError(f"both market sources failed: {exc} / {exc2}")


def latest_price(candles):
    """Most recent close (the price the Trader uses)."""
    return candles[-1]["close"]


if __name__ == "__main__":
    t0 = time.time()
    candles, source = fetch_candles()
    print(f"source={source} candles={len(candles)} "
          f"latest_close=${candles[-1]['close']:,.2f} "
          f"took {time.time() - t0:.1f}s")
