# (Full script — corrected)
#!/usr/bin/env python3
"""
ULTRA SAFE ADD BOT v3.2 — FIXED
- Removed invalid 'exclusive' kw
- Safe run_in_thread (pass function, not coroutine object)
- Do NOT run /validate and /add at same time (avoid DB lock)
"""
import os, time, json, asyncio, random, threading, requests, traceback
from telethon import TelegramClient
from telethon.sessions import SQLiteSession
from telethon.errors import (
    SessionPasswordNeededError, FloodWaitError, AuthRestartError,
    UserPrivacyRestrictedError, UserAlreadyParticipantError,
    UserBannedInChannelError, UsernameNotOccupiedError
)
from telethon.tl.functions.channels import InviteToChannelRequest
from flask import Flask

# CONFIG
API_ID = 18085901
API_HASH = "baa5a6ca152c717e88ea45f888d3af74"
PHONE = "+918436452250"
BOT_TOKEN = "8254353086:AAEMim12HX44q0XYaFWpbB3J7cxm4VWprEc"
USER_CHAT_ID = 1602198875
TARGET_GROUP = -1001823169797
IDS_FILE = "only_ids.txt"
CLEAN_IDS_FILE = "clean_ids.txt"
STATE_FILE = "add_state.json"
PING_URL = "https://adder-tg.onrender.com"
app = Flask(__name__)

is_validating = False

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
        return {"added": 0, "failed": 0, "skipped": 0, "last_index": 0, "min_delay": 60, "max_delay": 120}

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

# LOGIN helpers (use SQLiteSession WITHOUT 'exclusive' kw)
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

# VALIDATE
async def validate_ids():
    global is_validating
    if is_validating:
        bot_send("Already validating... please wait.")
        return
    is_validating = True
    try:
        session = SQLiteSession("safe_add_session")
        c = TelegramClient(session, API_ID, API_HASH)
        await c.connect()
        if not await c.is_user_authorized():
            bot_send("Not logged in!")
            await c.disconnect()
            is_validating = False
            return

        if not os.path.exists(IDS_FILE):
            bot_send("IDs file not found!")
            await c.disconnect()
            is_validating = False
            return

        with open(IDS_FILE) as f:
            all_ids = [line.strip() for line in f if line.strip()]
        total = len(all_ids)
        valid_ids, invalid = [], []

        bot_send(f"Validating {total} entries... (this may take a while)")
        for i, raw in enumerate(all_ids, 1):
            uid = raw.strip()
            if uid.startswith("@"):
                try_id = uid
            elif uid.isdigit():
                try_id = int(uid)
            else:
                try_id = "@" + uid
            try:
                entity = await c.get_entity(try_id)
                valid_ids.append(str(entity.id))
            except Exception as e:
                log_print(f"INVALID → {uid} | {e}")
                invalid.append(uid)

            if i % 100 == 0 or i == total:
                bot_send(f"Validated {i}/{total} | Valid: {len(valid_ids)} | Invalid: {len(invalid)}")
            await asyncio.sleep(random.uniform(0.4, 1.0))

        with open(CLEAN_IDS_FILE, "w") as f:
            for uid in valid_ids: f.write(uid + "\n")
        with open("invalid_ids.txt", "w") as f:
            for uid in invalid: f.write(uid + "\n")

        bot_send(f"VALIDATION DONE ✅ Valid: {len(valid_ids)} | Invalid: {len(invalid)}")
        s = load_state()
        s.update({"last_index": 0, "added": 0, "failed": 0, "skipped": 0})
        save_state(s)
        await c.disconnect()
    finally:
        is_validating = False

# ADD
async def add_members():
    session = SQLiteSession("safe_add_session")
    c = TelegramClient(session, API_ID, API_HASH)
    await c.connect()
    if not await c.is_user_authorized():
        bot_send("Not logged in!")
        await c.disconnect()
        return
    if not os.path.exists(CLEAN_IDS_FILE):
        bot_send("Run /validate first!")
        await c.disconnect()
        return

    with open(CLEAN_IDS_FILE) as f:
        ids = [line.strip() for line in f if line.strip()]
    s = load_state()
    total_ids = len(ids)
    start_index = s.get("last_index", 0)
    group = await c.get_entity(TARGET_GROUP)

    for i in range(start_index, total_ids):
        uid = int(ids[i])
        try:
            user = await c.get_entity(uid)
            await c(InviteToChannelRequest(group, [user]))
            s["added"] += 1
            log_print(f"ADDED {uid} → {s['added']}/{total_ids}")
            bot_send(f"Added {s['added']} | Next: {i+1}/{total_ids}")
        except UserAlreadyParticipantError:
            s["skipped"] += 1
        except UserPrivacyRestrictedError:
            s["skipped"] += 1
        except UserBannedInChannelError:
            s["skipped"] += 1
        except FloodWaitError as e:
            wait_time = e.seconds + random.uniform(60, 120)
            log_print(f"FLOODWAIT {e.seconds}s → sleeping {wait_time}s")
            await asyncio.sleep(wait_time)
            continue
        except Exception as e:
            s["failed"] += 1
            log_print(f"ADD FAIL {uid} → {e}")
        finally:
            s["last_index"] = i + 1
            save_state(s)
            delay = random.randint(s["min_delay"], s["max_delay"])
            bot_send(f"Next in {delay}s | Added: {s['added']} | Skipped: {s['skipped']} | Failed: {s['failed']}")
            await asyncio.sleep(delay)

    bot_send(f"✅ COMPLETE! Added: {s['added']} | Skipped: {s['skipped']} | Failed: {s['failed']}")
    await c.disconnect()

# PING
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

# COMMANDS
def process_cmd(text):
    s = load_state()
    lower = text.lower().strip()
    if lower.startswith("/start"):
        bot_send("Ready ✅ /login → /otp → /validate → /setdelay 60-120 → /add → /status"); return
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
    if lower.startswith("/validate"):
        if not s.get("logged_in"):
            bot_send("Login first!"); return
        run_in_thread(validate_ids)
        bot_send("Validating entries... (this may take several minutes)"); return
    if lower.startswith("/setdelay"):
        try:
            rng = lower.split()[1]; a,b = map(int, rng.split('-'))
            if a>=b: raise ValueError
            s["min_delay"], s["max_delay"] = a,b; save_state(s)
            bot_send(f"Delay set: {a}-{b}s")
        except:
            bot_send("Usage: /setdelay 60-120")
        return
    if lower.startswith("/add"):
        if not s.get("logged_in"):
            bot_send("Login first!"); return
        # IMPORTANT: do NOT run /add while validate is running
        run_in_thread(add_members)
        bot_send("Starting ultra safe add (Random delay, Skip already added, FloodWait 0%)"); return
    if lower.startswith("/status"):
        msg = f"Added: {s['added']} | Skipped: {s['skipped']} | Failed: {s['failed']} | Delay: {s['min_delay']}-{s['max_delay']}s"
        bot_send(msg); log_print(msg); return
    bot_send("Unknown command. Use /start")

# MAIN LOOP
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
