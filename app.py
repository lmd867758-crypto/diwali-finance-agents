"""Mobile-friendly dashboard for the Diwali Finance agents. Stdlib only.

Serves the single-page UI and a JSON API:

    GET  /              the dashboard page
    GET  /api/state    latest signal, paper account, trades, message bus
    POST /api/run      run one Analyst -> Trader cycle (live or mock)

Run:  python3 app.py            (reads .env if present)
Env:  PORT (default 8000), HOST (default 0.0.0.0)
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import bus  # noqa: E402
import trader  # noqa: E402
from analyst import LATEST_SIGNAL_FILE  # noqa: E402


def load_dotenv():
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()


def get_state():
    state = trader.load_state()
    signal = None
    if LATEST_SIGNAL_FILE.exists():
        signal = json.loads(LATEST_SIGNAL_FILE.read_text())
    price = signal["price"] if signal else None
    eq = trader.equity(state, price) if price is not None else state["cash"]
    return {
        "simulated": True,
        "symbol": signal["symbol"] if signal else "BTC/USD",
        "price": price,
        "cash": state["cash"],
        "starting_cash": state["starting_cash"],
        "equity": round(eq, 2),
        "total_pnl": round(eq - state["starting_cash"], 2),
        "signal": signal,
        "positions": state["positions"],
        "trades": list(reversed(state["trades"])),
        "messages": list(reversed(bus.read_all(limit=50))),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send_file(BASE_DIR / "static" / "index.html",
                            "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._send_json(200, get_state())
        elif self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/run":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            self._send_json(400, {"error": "invalid JSON body"})
            return
        mock = bool(payload.get("mock"))
        try:
            import analyst
            import run_cycle  # noqa: F401  (import for clarity only)
            analyst.run(mock=mock)
            trader.run(mock=mock)
        except Exception as exc:  # never leak a stack trace to the client
            self._send_json(502, {"error": f"cycle failed: {exc}"})
            return
        self._send_json(200, get_state())


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Finance agents dashboard at http://{host}:{port}")
    print("SIMULATED trading only — no real money, no broker, no real orders.")
    server.serve_forever()
