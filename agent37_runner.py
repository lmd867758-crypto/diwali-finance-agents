"""Run the Finance agents inside an Agent37 sandbox (Diwali sponsor tool).

This is the Agent37 integration for the hackathon: it provisions a fresh
Agent37 sandbox via the Sandbox API (POST /v1/instances), uploads the agent
code, runs one Analyst -> Trader cycle inside it, pulls the message log and
paper-account state back, then DELETES the sandbox so nothing keeps billing.

Cost: a 2 vCPU / 4 GB sandbox bills $4.76/month while running, metered per
minute (~$0.00011/min). A ~10 minute test costs about $0.001. The sandbox is
created with auto_sleep on, and deleted at the end in all cases.

Auth: reuses the workspace's registered Agent37 credential through the same
dynamic_credentials mechanism as custom.agent37's agent37.py helper. No key
is ever read, printed, or stored here.

Usage:
    python3 agent37_runner.py --mock     # dry run, no API calls
    python3 agent37_runner.py --live     # real sandbox test (then delete)
    python3 agent37_runner.py --live --keep   # do NOT delete afterwards
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
HELPER_DIR = Path.home() / "workspace" / "custom-connectors" / "custom.agent37" / "bin"
sys.path.insert(0, str(HELPER_DIR))
sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")

from agent37 import api  # noqa: E402  (registered-credential helper)
from dynamic_credentials import read_json_response  # noqa: E402

# Files uploaded into the sandbox (stdlib only — no pip install needed).
UPLOAD_FILES = ["bus.py", "market.py", "analyst.py", "trader.py", "run_cycle.py"]
SANDBOX_DIR = "/home/node/diwali-finance"

# 2 vCPU / 4 GB / 4 GB disk = $4.76/month while running, ~$0.000109/minute.
RUNNING_RATE_PER_MIN = 4.76 / 43800.0


def _exec(instance_id, command):
    """Run a shell command inside the instance via the Sandbox API."""
    try:
        _status, result = api(
            "POST", f"/v1/instances/{instance_id}/exec", {"command": command})
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"exec failed: HTTP {exc.code}: "
                           f"{exc.read().decode('utf-8', 'replace')[:300]}")
    if isinstance(result, dict) and result.get("exit_code") not in (None, 0):
        raise RuntimeError(
            f"exec exit {result.get('exit_code')}: "
            f"{result.get('stderr', '')[:500]}")
    return result


def _get(instance_id):
    _status, result = api("GET", f"/v1/instances/{instance_id}")
    return result


def create_instance():
    body = {
        "template": "agent37-base",
        "resources": {"cpu": 2, "memory": 4, "disk": 4},
        "type": "default",
        "region": "us",
        "name": "diwali-finance-agents",
        "metadata": {"project": "diwali-festiverse-finance", "track": "finance"},
        "auto_sleep": True,
        "idle_timeout_seconds": 300,
    }
    try:
        status, result = api("POST", "/v1/instances", body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"create failed: HTTP {exc.code}: {detail}")
    print(f"[agent37] created instance {result.get('id')} "
          f"(HTTP {status}, status={result.get('status')})")
    return result


def wait_running(instance_id, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        inst = _get(instance_id)
        status = inst.get("status")
        print(f"[agent37] instance status: {status}")
        if status == "running":
            return inst
        if status in ("failed", "deleted"):
            raise RuntimeError(f"instance went {status}")
        time.sleep(5)
    raise RuntimeError("timed out waiting for instance to run")


def upload_code(instance_id):
    _exec(instance_id, f"mkdir -p {SANDBOX_DIR}")
    for name in UPLOAD_FILES:
        data = (BASE_DIR / name).read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        _exec(instance_id,
              f"printf '%s' '{b64}' | base64 -d > {SANDBOX_DIR}/{name}")
        print(f"[agent37] uploaded {name} ({len(data)} bytes)")
    _exec(instance_id, f"cd {SANDBOX_DIR} && python3 -c "
                       f"'import bus, market, analyst, trader; "
                       f"print(\"imports ok\")'")


def run_cycle_in_sandbox(instance_id):
    result = _exec(instance_id, f"cd {SANDBOX_DIR} && python3 run_cycle.py")
    print("[agent37] --- cycle output inside sandbox ---")
    print(result.get("stdout", ""))
    if result.get("stderr"):
        print("[agent37] --- stderr ---")
        print(result["stderr"][:2000])


def fetch_results(instance_id):
    result = _exec(
        instance_id,
        f"echo '=== messages.jsonl ==='; cat {SANDBOX_DIR}/messages.jsonl; "
        f"echo '=== state.json ==='; cat {SANDBOX_DIR}/state.json")
    print("[agent37] --- results pulled from sandbox ---")
    print(result.get("stdout", ""))
    return result.get("stdout", "")


def delete_instance(instance_id):
    try:
        _status, result = api("DELETE", f"/v1/instances/{instance_id}")
        print(f"[agent37] deleted instance {instance_id}: {result}")
    except urllib.error.HTTPError as exc:
        print(f"[agent37] WARNING: delete failed HTTP {exc.code}: "
              f"{exc.read().decode('utf-8', 'replace')[:200]}")


def live_run(keep=False):
    t0 = time.time()
    instance_id = None
    try:
        inst = create_instance()
        instance_id = inst["id"]
        wait_running(instance_id)
        upload_code(instance_id)
        run_cycle_in_sandbox(instance_id)
        fetch_results(instance_id)
    finally:
        if instance_id and not keep:
            delete_instance(instance_id)
        elif instance_id and keep:
            print(f"[agent37] KEPT instance {instance_id} — "
                  f"remember to delete it, it bills while running!")
    minutes = (time.time() - t0) / 60.0
    cost = minutes * RUNNING_RATE_PER_MIN
    print(f"[agent37] sandbox alive ~{minutes:.1f} min, "
          f"estimated cost ~${cost:.4f} (rate $4.76/mo)")
    return cost


def mock_run():
    print("[mock] would create instance: template=agent37-base, "
          "resources={cpu:2, memory:4, disk:4}, auto_sleep=true, "
          "idle_timeout_seconds=300, name=diwali-finance-agents")
    print(f"[mock] would upload: {', '.join(UPLOAD_FILES)} -> {SANDBOX_DIR}")
    print("[mock] would run: cd /home/node/diwali-finance && python3 run_cycle.py")
    print("[mock] would fetch messages.jsonl + state.json, then DELETE instance")
    print("[mock] estimated cost for a ~10 min test: "
          f"~${10 * RUNNING_RATE_PER_MIN:.4f}")
    print("[mock] no API calls made. Use --live for a real sandbox test.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true",
                        help="really create a sandbox, run, then delete it")
    parser.add_argument("--mock", action="store_true",
                        help="dry run (default): print what would happen")
    parser.add_argument("--keep", action="store_true",
                        help="with --live: do not delete the sandbox after")
    args = parser.parse_args()
    if args.live:
        live_run(keep=args.keep)
    else:
        mock_run()
