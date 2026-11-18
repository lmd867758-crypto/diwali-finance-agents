"""Shared message bus for the two Diwali Finance agents.

The Analyst and the Trader never talk directly: every message they send
each other goes through one append-only JSON-lines file (messages.jsonl),
so their whole collaboration is visible in the dashboard and in the demo.

Message shape:
    {"ts": "<ISO time>", "from": "analyst"|"trader", "type": "...", "data": {...}}
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BUS_FILE = Path(os.environ.get("FINANCE_BUS_FILE", BASE_DIR / "messages.jsonl"))


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append(sender, msg_type, data):
    """Append one message to the bus. Returns the message dict."""
    msg = {"ts": now_iso(), "from": sender, "type": msg_type, "data": data}
    with open(BUS_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(msg) + "\n")
    return msg


def read_all(limit=None):
    """Read all bus messages, oldest first. Returns a list of dicts."""
    if not BUS_FILE.exists():
        return []
    out = []
    with open(BUS_FILE, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if limit is not None:
        out = out[-limit:]
    return out


def latest_signal():
    """Return the most recent analyst signal message, or None."""
    for msg in reversed(read_all()):
        if msg.get("from") == "analyst" and msg.get("type") == "signal":
            return msg
    return None
