#!/usr/bin/env bash
# Mac/Linux: ./start_bot.sh  (restarts the bot if it ever exits)
cd "$(dirname "$0")"
source .venv/bin/activate
while true; do
  python bot.py
  echo "Bot stopped, restarting in 60s..."
  sleep 60
done
