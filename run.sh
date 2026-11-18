#!/bin/bash
# Run one Analyst -> Trader cycle, then start the dashboard.
# Usage: ./run.sh            (live market data)
#        ./run.sh --mock     (built-in sample candles, no network)
set -e
cd "$(dirname "$0")"
python3 run_cycle.py "$@"
PORT="${PORT:-8000}" python3 app.py
