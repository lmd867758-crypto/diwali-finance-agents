"""End-to-end test for the Diwali Finance agents (no network, no money).

Runs the full Analyst -> Trader -> dashboard flow with mocked market data
and checks the collaboration actually happens:
  * Analyst writes a signal to the bus
  * Trader reads it, opens a simulated position with the 1% risk rule
  * The dashboard /api/state reports the signal, position and messages

Run:  python3 test_flow.py
"""

import json
import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Isolate test state in a temp dir so the real state.json is untouched.
TMP = Path(tempfile.mkdtemp(prefix="diwali-finance-test-"))
os.environ["FINANCE_BUS_FILE"] = str(TMP / "messages.jsonl")
os.environ["FINANCE_SIGNAL_FILE"] = str(TMP / "latest_signal.json")
os.environ["FINANCE_STATE_FILE"] = str(TMP / "state.json")

import analyst  # noqa: E402
import bus  # noqa: E402
import trader  # noqa: E402

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}")


def main():
    print("== test: analyst (mock candles) ==")
    signal = analyst.run(mock=True)
    check("analyst direction is LONG on rising mock data",
          signal["direction"] == "LONG", signal["direction"])
    check("analyst confidence in range", 0.0 <= signal["confidence"] <= 1.0,
          str(signal["confidence"]))
    check("signal saved to latest_signal.json",
          analyst.LATEST_SIGNAL_FILE.exists())

    print("== test: bus carries the signal ==")
    latest = bus.latest_signal()
    check("bus.latest_signal() returns the analyst signal",
          latest is not None and latest["data"]["id"] == signal["id"])
    check("bus has >=1 message", len(bus.read_all()) >= 1)

    print("== test: trader (mock price) opens a position ==")
    state = trader.run(mock=True)
    check("trader opened exactly 1 position", len(state["positions"]) == 1,
          str(len(state["positions"])))
    if state["positions"]:
        pos = state["positions"][0]
        check("position side matches signal", pos["side"] == "LONG")
        check("risk is 1% of equity ($100.00)",
              abs(pos["risk_dollars"] - 100.0) < 0.01,
              str(pos["risk_dollars"]))
        check("stop below entry (LONG)", pos["stop"] < pos["entry"])
        check("take-profit above entry (LONG)", pos["tp"] > pos["entry"])
        check("position qty > 0", pos["qty"] > 0, str(pos["qty"]))

    print("== test: trader closes on opposite signal ==")
    # Flip the signal to a strong SHORT and re-run: position must close.
    sig = json.loads(analyst.LATEST_SIGNAL_FILE.read_text())
    sig["direction"] = "SHORT"
    sig["confidence"] = 0.9
    sig["id"] = "testflip"
    analyst.LATEST_SIGNAL_FILE.write_text(json.dumps(sig))
    bus.append("analyst", "signal", sig)
    state = trader.run(mock=True)
    check("opposite signal closed the LONG and opened a SHORT",
          len(state["positions"]) == 1
          and state["positions"][0]["side"] == "SHORT",
          str([(p["side"]) for p in state["positions"]]))
    check("trade booked in history", len(state["trades"]) == 1)
    if state["trades"]:
        check("closed trade has a P/L number",
              isinstance(state["trades"][0]["pnl"], (int, float)),
              str(state["trades"][0]["pnl"]))

    print("== test: dashboard state endpoint ==")
    import app
    st = app.get_state()
    check("dashboard reports simulated=true", st.get("simulated") is True)
    check("dashboard carries the signal", st.get("signal") is not None)
    check("dashboard carries the message log", len(st.get("messages", [])) >= 3,
          str(len(st.get("messages", []))))
    check("dashboard equity is a number",
          isinstance(st.get("equity"), (int, float)), str(st.get("equity")))

    print("== test: live HTTP server serves page + health ==")
    import threading
    from http.server import ThreadingHTTPServer
    os.environ["PORT"] = "8125"
    server = ThreadingHTTPServer(("127.0.0.1", 8125), app.Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen("http://127.0.0.1:8125/", timeout=10) as r:
            page = r.read().decode("utf-8")
        check("dashboard page serves", "Finance Agents" in page)
        with urllib.request.urlopen("http://127.0.0.1:8125/api/state",
                                    timeout=10) as r:
            api_state = json.loads(r.read())
        check("/api/state serves JSON", api_state.get("simulated") is True)
    finally:
        server.shutdown()
        server.server_close()

    print("== test: agent37 runner mock ==")
    import agent37_runner
    agent37_runner.mock_run()
    check("agent37 runner mock runs without API calls", True)

    failed = [c for c in CHECKS if not c[1]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} checks passed")
    shutil.rmtree(TMP, ignore_errors=True)
    if failed:
        print("FAILURES:", [c[0] for c in failed])
        sys.exit(1)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
