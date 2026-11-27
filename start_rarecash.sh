#!/usr/bin/env bash
# Rare Cash (Mac/Linux): ./start_rarecash.sh  -> dashboard at http://localhost:8000
cd "$(dirname "$0")"
source .venv/bin/activate
while true; do
  python rarecash.py
  echo "Rare Cash stopped, restarting in 30s..."
  sleep 30
done
