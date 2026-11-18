"""Run one full Analyst -> Trader cycle (used by the dashboard, the demo,
and the Agent37 sandbox runner).

    python3 run_cycle.py          (live market data)
    python3 run_cycle.py --mock   (built-in sample candles, no network)
"""

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import analyst  # noqa: E402
import trader  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    print("=== Analyst ===")
    analyst.run(mock=args.mock)
    print("=== Trader ===")
    trader.run(mock=args.mock)
    print("=== Cycle done ===")


if __name__ == "__main__":
    main()
