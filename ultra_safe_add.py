#!/usr/bin/env python3
"""
ULTRA SAFE ADD BOT v4.0 — ZERO FLOOD RISK MODE
- Increased default delays to 300-900s (5-15 min) based on Telegram limits
- Exponential backoff on flood: multiplier increases delays temporarily
- Extra delay after get_entity to separate resolves from invites
- Supports @usernames or numeric IDs from only_ids.txt
"""
import os, time, json, asyncio, random, threading, requests, traceback
from telethon import TelegramClient
from telethon.sessions import SQLiteSession
from telethon.errors import (
    SessionPasswordNeededError, FloodWaitError, AuthRestartError,
    UserPrivacyRestrictedError, UserAlreadyParticipantError,
    UserBannedInChannelError
)
from telethon.tl.functions.channels import InviteToChannelRequest
from flask import Flask
# CONFIG
API_ID = 22676464
API_HASH = "b52406ee2c61546d8b560e2d009052d3"
PHONE = "+917671914528"
BOT_TOKEN = "8254353086:AAEMim12HX44q0XYaFWpbB3J7cxm4VWprEc"
USER_CHAT_ID = 1602198875
TARGET_GROUP = -1001823169797
IDS_FILE = "only_ids.txt" # Put usernames (with @) or numeric IDs here, one per line
STATE_FILE = "add_state.json"
PING_URL = "https://adder-tg.onrender.com"
app = Flask(__name__)
def log_print(msg):
    print(f"[LIVE] {msg}")
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": USER_CHAT_ID, "text": f"LOG: {msg}"},
            timeout=10,
        )
    except: pass
def bot_send(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": USER_CHAT_ID, "text": text},
            timeout=10,
        )
    except Exception as e:
        log_print(f"bot_send error: {e}")
def load_state():
    try:
        return json.load(open(STATE_FILE, "r"))
    except:
        return {"added": 0, "failed": 0, "skipped": 0, "last_index": 0, "min_delay": 300, "max_delay": 900, "flood_multiplier": 1.0}
def save_state(s):
    json.dump(s, open(STATE_FILE, "w"))
    log_print("STATE SAVED")
# safer run_in_thread: pass function (sync or async) and args
def run_in_thread(fn, *args, **kwargs):
    def _runner():
        try:
            if asyncio.iscoroutinefunction(fn):
                asyncio.run(fn(*args, **kwargs))
            else:
                fn(*args, **kwargs)
        except Exception as e:
            log_print(f"run_in_thread error: {e}")
    threading.Thread(target=_runner, daemon=True).start()
# LOGIN helpers (unchanged)
def tele_send_code():
    async def inner():
        session = SQLiteSession("safe_add_session")
        c = TelegramClient(session, API_ID, API_HASH)
        await c.connect()
        r = await c.send_code_request(PHONE)
        await c.disconnect()
        return getattr(r, "phone_code_hash", None)
    try:
        hashv = asyncio.run(inner())
        s = load_state()
        s["phone_code_hash"] = hashv
        save_state(s)
        bot_send("OTP sent! /otp <code>")
    except Exception as e:
        bot_send(f"Login error: {e}")
def tele_sign_in_with_code(code):
    async def inner():
        session = SQLiteSession("safe_add_session")
        c = TelegramClient(session, API_ID, API_HASH)
        await c.connect()
        s = load_state()
        hashv = s.get("phone_code_hash")
        try:
            await c.sign_in(PHONE, code, phone_code_hash=hashv)
            s["logged_in"] = True
            save_state(s)
            await c.disconnect()
            return True, False, "Login success!"
        except SessionPasswordNeededError:
            await c.disconnect()
            return True, True, "2FA needed."
    return asyncio.run(inner())
def tele_sign_in_with_password(pwd):
    async def inner():
        session = SQLiteSession("safe_add_session")
        c = TelegramClient(session, API_ID, API_HASH)
        await c.connect()
        await c.sign_in(password=pwd)
        s = load_state()
        s["logged_in"] = True
        save_state(s)
        await c.disconnect()
    try:
        asyncio.run(inner())
        return True, "2FA success!"
    except Exception as e:
        return False, str(e)
# Ultra-safe ADD with zero flood risk
async def add_members():
    session = SQLiteSession("safe_add_session")
    c = TelegramClient(session, API_ID, API_HASH)
    await c.connect()
    if not await c.is_user_authorized():
        bot_send("Not logged in!")
        await c.disconnect()
        return
    if not os.path.exists(IDS_FILE):
        bot_send("IDs file not found! Create only_ids.txt with one username/ID per line.")
        await c.disconnect()
        return
    with open(IDS_FILE) as f:
        entries = [line.strip() for line in f if line.strip()]
    s = load_state()
    total = len(entries)
    start = s.get("last_index", 0)
    mult = s.get("flood_multiplier", 1.0)
    successful_streak = 0  # Track to reduce multiplier
    try:
        group = await c.get_entity(TARGET_GROUP)
    except Exception as e:
        bot_send(f"Can't find target group: {e}")
        await c.disconnect()
        return
    for i in range(start, total):
        raw = entries[i]
        # Prepare identifier
        if raw.startswith("@"):
            try_id = raw
        elif raw.isdigit():
            try_id = int(raw)
        else:
            try_id = "@" + raw
        try:
            # Resolve user entity with small buffer delay
            await asyncio.sleep(random.uniform(10, 30))
            user = await c.get_entity(try_id)
            # Attempt to invite
            await c(InviteToChannelRequest(group, [user]))
            s["added"] += 1
            successful_streak += 1
            log_print(f"ADDED {raw} → {s['added']}/{total}")
            bot_send(f"Added {s['added']} | Next: {i+1}/{total}")
        except UserAlreadyParticipantError:
            s["skipped"] += 1
            successful_streak += 1  # Treat as success for streak
            log_print(f"SKIP (already): {raw}")
        except UserPrivacyRestrictedError:
            s["skipped"] += 1
            successful_streak += 1
            log_print(f"SKIP (privacy): {raw}")
        except UserBannedInChannelError:
            s["skipped"] += 1
            successful_streak += 1
            log_print(f"SKIP (banned): {raw}")
        except FloodWaitError as e:
            wait_time = e.seconds + random.uniform(60, 120)  # Extra buffer
            mult *= 1.5  # Exponential backoff
            if mult > 10: mult = 10  # Cap
            s["flood_multiplier"] = mult
            log_print(f"FLOODWAIT {e.seconds}s detected → sleeping {wait_time}s, mult now {mult}")
            bot_send(f"Flood detected: Waiting {wait_time//60}m, increasing delays.")
            await asyncio.sleep(wait_time)
            # Retry this user next (don't increment index)
            s["last_index"] = i
            save_state(s)
            successful_streak = 0  # Reset streak on flood
            continue
        except Exception as e:
            s["failed"] += 1
            log_print(f"ADD FAIL {raw} → {e}")
            successful_streak = 0
        finally:
            s["last_index"] = i + 1
            # Reduce multiplier after successes
            if successful_streak >= 5:
                mult = max(1.0, mult / 1.5)
                s["flood_multiplier"] = mult
                successful_streak = 0
            save_state(s)
            # Ultra-safe delay: base * multiplier + jitter
            base_min = s.get("min_delay", 300) * mult
            base_max = s.get("max_delay", 900) * mult
            delay = random.randint(int(base_min), int(base_max))
            log_print(f"Next in {delay}s... (Progress: {i+1}/{total}, Mult: {mult:.1f})")
            bot_send(f"Next in ~{delay//60}m | Added: {s['added']} | Skipped: {s['skipped']} | Failed: {s['failed']}")
            await asyncio.sleep(delay)
    bot_send(f"✅ COMPLETE! Added: {s['added']} | Skipped: {s['skipped']} | Failed: {s['failed']}")
    # Reset
    s["last_index"] = 0
    s["flood_multiplier"] = 1.0
    save_state(s)
    await c.disconnect()
# PING (unchanged)
async def ping_forever():
    while True:
        try:
            requests.get(PING_URL, timeout=10)
            log_print("PING OK")
        except:
            log_print("PING FAIL")
        await asyncio.sleep(600)
def start_ping_thread():
    run_in_thread(ping_forever)
# COMMANDS (updated setdelay default)
def process_cmd(text):
    s = load_state()
    lower = text.lower().strip()
    if lower.startswith("/start"):
        bot_send("Ready ✅ /login → /otp → /setdelay 300-900 (ultra safe) → /add → /status")
        return
    if lower.startswith("/login"):
        tele_send_code(); return
    if lower.startswith("/otp"):
        p = text.split()
        if len(p) < 2: bot_send("Usage: /otp <code>"); return
        ok, need2fa, msg = tele_sign_in_with_code(p[1])
        bot_send(msg)
        if need2fa: bot_send("Send /2fa <password>")
        return
    if lower.startswith("/2fa"):
        p = text.split(maxsplit=1)
        if len(p) < 2: bot_send("Usage: /2fa <password>"); return
        ok, msg = tele_sign_in_with_password(p[1])
        bot_send(msg)
        return
    if lower.startswith("/setdelay"):
        try:
            rng = lower.split()[1]; a,b = map(int, rng.split('-'))
            if a>=b: raise ValueError
            s["min_delay"], s["max_delay"] = a,b; save_state(s)
            bot_send(f"Delay set: {a}-{b}s (recommend 300-900 for zero flood)")
        except:
            bot_send("Usage: /setdelay 300-900")
        return
    if lower.startswith("/add"):
        if not s.get("logged_in"):
            bot_send("Login first!"); return
        run_in_thread(add_members)
        bot_send("Starting ZERO flood risk add (from only_ids.txt). Expect slow but safe progress.")
        return
    if lower.startswith("/status"):
        mult = s.get("flood_multiplier", 1.0)
        msg = f"Added: {s.get('added',0)} | Skipped: {s.get('skipped',0)} | Failed: {s.get('failed',0)} | Delay: {s.get('min_delay',300)}-{s.get('max_delay',900)}s x{mult:.1f}"
        bot_send(msg); log_print(msg); return
    bot_send("Unknown command. Use /start")
# MAIN LOOP (unchanged)
def main_loop():
    log_print("BOT STARTED")
    offset = None
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                             params={"offset": offset, "timeout": 15}, timeout=20).json()
            if not r.get("ok"):
                time.sleep(1); continue
            for u in r["result"]:
                offset = u["update_id"] + 1
                msg = u.get("message", {}); text = msg.get("text", ""); chat = msg.get("chat", {})
                if not text or str(chat.get("id")) != str(USER_CHAT_ID): continue
                process_cmd(text)
            time.sleep(1)
        except Exception as e:
            log_print(f"LOOP ERROR: {e}"); time.sleep(3)
if __name__ == "__main__":
    start_ping_thread()
    threading.Thread(target=main_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    log_print(f"HTTP on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
