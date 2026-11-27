"""Telegram: alerts on your phone, plus simple remote control (/status, /on, /off, /run, ...).

Setup: talk to @BotFather on Telegram -> /newbot -> copy the token into Rare Cash Settings.
Then send /start to your new bot; Rare Cash shows your chat id in Settings to confirm.
Only that one chat can control the bot.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time

import requests

log = logging.getLogger("bot")
API = "https://api.telegram.org/bot{token}/{method}"


def _redact(text: str) -> str:
    return re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot***", str(text))


def token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def call(method: str, http_timeout: float = 20, **params) -> dict:
    t = token()
    if not t:
        raise RuntimeError("Telegram token set nahi hai")
    try:
        r = requests.post(API.format(token=t, method=method), json=params, timeout=http_timeout)
        data = r.json()
    except Exception as e:  # the URL holds the token: never let it reach the logs
        raise RuntimeError(_redact(f"Telegram error: {type(e).__name__}: {e}")) from None
    if not data.get("ok"):
        raise RuntimeError(_redact(f"Telegram: {data.get('description', 'unknown error')}"))
    return data.get("result", {})


def send(chat_id: str, text: str) -> bool:
    if not (token() and chat_id):
        return False
    try:
        call("sendMessage", chat_id=chat_id, text=text[:4000], disable_web_page_preview=True)
        return True
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")
        return False


class Notifier:
    """Used by the bot engine. Reads settings from the config each time, so changes apply live."""

    def __init__(self):
        self.cfg = None
        self._last: dict[str, float] = {}

    def enabled(self, kind: str) -> bool:
        t = getattr(self.cfg, "telegram", None)
        return bool(t and t.enabled and t.chat_id and token() and getattr(t, f"notify_{kind}", True))

    def __call__(self, kind: str, text: str, dedupe_minutes: float = 0) -> None:
        """kind: posts | errors | campaigns | summary"""
        if not self.enabled(kind):
            return
        key = f"{kind}:{text[:60]}"
        if dedupe_minutes and time.time() - self._last.get(key, 0) < dedupe_minutes * 60:
            return
        self._last[key] = time.time()
        threading.Thread(target=send, args=(self.cfg.telegram.chat_id, f"💎 Rare Cash\n{text}"), daemon=True).start()


notify = Notifier()

HELP = """Rare Cash commands:
/status - bot abhi kya kar raha hai
/on - bot ON
/off - bot OFF
/run - abhi ek round chalao
/scan - Vyro scan abhi
/vpn_on, /vpn_off - built-in VPN
/today - aaj ka hisaab
/help - ye list"""


def command_loop(stop: threading.Event, get_cfg, st_factory, handlers: dict) -> None:
    """Long-polls Telegram for commands. Runs in its own thread; quiet when Telegram isn't set up."""
    offset = None
    while not stop.is_set():
        cfg = get_cfg()
        t = getattr(cfg, "telegram", None)
        # poll as soon as a token exists, so /start can reveal the chat id before setup is finished
        if not (t and token()):
            stop.wait(15)
            continue
        try:
            # long poll: Telegram holds the request up to 25 s until a message arrives
            updates = call("getUpdates", http_timeout=40, offset=offset, timeout=25, allowed_updates=["message"])
        except Exception as e:
            log.warning(str(e))
            stop.wait(30)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            chat = str((msg.get("chat") or {}).get("id", ""))
            text = (msg.get("text") or "").strip().split("@")[0].lower()
            if not chat or not text.startswith("/"):
                continue
            st = st_factory()
            if not t.chat_id:  # first contact: show the id in Settings, accept nothing else
                st.set("telegram_pending_chat", chat)
                send(chat, f"Tumhara chat id: {chat}\nRare Cash Settings mein 'Use karo' dabao, phir yahan /help bhejo.")
                continue
            if chat != str(t.chat_id) or not t.enabled:
                continue  # someone else found the bot, or Telegram is switched off: ignore
            cmd = text.split()[0].lstrip("/")
            fn = handlers.get(cmd)
            try:
                reply = fn(st) if fn else HELP
            except Exception as e:
                reply = f"Error: {e}"
            send(chat, reply or "OK")
        stop.wait(1)
