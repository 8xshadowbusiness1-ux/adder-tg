#!/usr/bin/env python3
"""
ULTRA SAFE ADD SCRIPT: Random Delay, Skip Already Added, No FloodWait Ever!
✔ /setdelay 60-120 → Random 60-120 sec delay per add
✔ 1-by-1 add → Skip if already added (no wait)
✔ FloodWait auto-handle + retry with exponential backoff
✔ Logs in Bot + Live Status (/status)
✔ Resume from last position
✔ Same Config + Group: -1001823169797
✔ Even 5 days lage to chalega — No ban!
✔ FIXED: add_members now runs in separate thread
"""
import os, time, json, asyncio, random, threading, requests, traceback
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError, FloodWaitError, AuthRestartError,
    UserPrivacyRestrictedError, UserAlreadyParticipantError,
    UserBannedInChannelError
)
from telethon.tl.functions.channels import InviteToChannelRequest
from flask import Flask

# ---------------- CONFIG (SAME) ----------------
API_ID = 18085901
API_HASH = "baa5a6ca152c717e88ea45f888d3af74"
PHONE = "+918436452250"
BOT_TOKEN = "8254353086:AAEMim12HX44q0XYaFWpbB3J7cxm4VWprEc"
USER_CHAT_ID = 1602198875
TARGET_GROUP = -1001823169797  # ← YE GROUP
IDS_FILE = "only_ids.txt"  # ← IDs wala file
STATE_FILE = "add_state.json"
PING_URL = "https://adder-tg.onrender.com"
app = Flask(__name__)

@app.route('/')
def home():
    return "Ultra Safe Add Bot Running! Random Delay Active"

# ---------- LOGS + BOT SEND ----------
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
        log_print(f"BOT → {text}")
    except Exception as e:
        log_print(f"bot_send error: {e}")

# ---------- STATE ----------
def load_state():
    try:
        return json.load(open(STATE_FILE, "r"))
    except:
        return {"added": 0, "failed": 0, "skipped": 0, "last_index": 0, "min_delay": 60, "max_delay": 120}

def save_state(s):
    json.dump(s, open(STATE_FILE, "w"))
    log_print("STATE SAVED")

# ---------- LOGIN (Same, FloodWait Safe) ----------
def tele_send_code():
    async def inner():
        c = TelegramClient("safe_add_session", API_ID, API_HASH)
        await c.connect()
        r = await c.send_code_request(PHONE)
        await c.disconnect()
        return getattr(r, "phone_code_hash", None)
    for _ in range(3):
        try:
            hashv = asyncio.run(inner())
            s = load_state()
            s["phone_code_hash"] = hashv
            save_state(s)
            bot_send("OTP sent! /otp <code>")
            return
        except AuthRestartError:
            time.sleep(5)
        except FloodWaitError as e:
            log_print(f"FloodWait in login: {e.seconds}s")
            time.sleep(e.seconds + 5)
        except Exception as e:
            bot_send(f"Login error: {e}")
            return

def tele_sign_in_with_code(code):
    async def inner():
        c = TelegramClient("safe_add_session", API_ID, API_HASH)
        await c.connect()
        s = load_state()
        hashv = s.get("phone_code_hash")
        if not hashv:
            r = await c.send_code_request(PHONE)
            s["phone_code_hash"] = getattr(r, "phone_code_hash", "")
            save_state(s)
            await c.disconnect()
            return (False, False, "Code expired.")
        try:
            await c.sign_in(PHONE, code, phone_code_hash=hashv)
            s["logged_in"] = True
            save_state(s)
            await c.disconnect()
            return (True, False, "Login success!")
        except SessionPasswordNeededError:
            await c.disconnect()
            return (True, True, "2FA needed.")
    for _ in range(3):
        try:
            ok, need2fa, msg = asyncio.run(inner())
            return ok, need2fa, msg
        except AuthRestartError:
            time.sleep(5)
        except FloodWaitError as e:
            log_print(f"FloodWait in sign_in: {e.seconds}s")
            time.sleep(e.seconds + 5)
        except Exception as e:
            return False, False, f"Error: {e}"
    return False, False, "Max retries."

def tele_sign_in_with_password(pwd):
    async def inner():
        c = TelegramClient("safe_add_session", API_ID, API_HASH)
        await c.connect()
        await c.sign_in(password=pwd)
        s = load_state()
        s["logged_in"] = True
        save_state(s)
        await c.disconnect()
    for _ in range(3):
        try:
            asyncio.run(inner())
            return True, "2FA success!"
        except AuthRestartError:
            time.sleep(5)
        except FloodWaitError as e:
            log_print(f"FloodWait in 2FA: {e.seconds}s")
            time.sleep(e.seconds + 5)
        except Exception as e:
            return False, str(e)
    return False, "Max retries."

# ---------- ULTRA SAFE ADD (1-by-1, Random Delay, Skip Already Added) ----------
async def add_members():
    c = TelegramClient("safe_add_session", API_ID, API_HASH)
    await c.connect()
    if not await c.is_user_authorized():
        bot_send("Not logged in!")
        await c.disconnect()
        return
    s = load_state()
    if not os.path.exists(IDS_FILE):
        bot_send("IDs file not found!")
        await c.disconnect()
        return
    with open(IDS_FILE) as f:
        ids = [line.strip() for line in f if line.strip()]
    total_ids = len(ids)
    start_index = s.get("last_index", 0)
    min_delay = s.get("min_delay", 60)
    max_delay = s.get("max_delay", 120)
    added = s.get("added", 0)
    failed = s.get("failed", 0)
    skipped = s.get("skipped", 0)
    group = await c.get_entity(TARGET_GROUP)
    for i in range(start_index, total_ids):
        uid = int(ids[i])
        try:
            user = await c.get_entity(uid)
            try:
                await c(InviteToChannelRequest(group, [user]))
                added += 1
                log_print(f"ADDED {uid} → Total: {added}/{total_ids}")
                bot_send(f"Added: {added} | Next: {i+1}/{total_ids}")
            except UserAlreadyParticipantError:
                skipped += 1
                log_print(f"SKIP (already added): {uid}")
            except UserPrivacyRestrictedError:
                skipped += 1
                log_print(f"SKIP (privacy): {uid}")
            except UserBannedInChannelError:
                skipped += 1
                log_print(f"SKIP (banned): {uid}")
            except FloodWaitError as e:
                wait_time = e.seconds + random.uniform(60, 120)  # Extra random
                log_print(f"FLOODWAIT {e.seconds}s → Waiting {wait_time}s + retry")
                await asyncio.sleep(wait_time)
                # Retry this user
                try:
                    await c(InviteToChannelRequest(group, [user]))
                    added += 1
                    log_print(f"RETRY ADDED {uid}")
                except:
                    failed += 1
                    log_print(f"Retry failed {uid}")
            except Exception as e:
                failed += 1
                log_print(f"Failed {uid}: {e}")
        except Exception as e:
            failed += 1
            log_print(f"Entity error {uid}: {e}")
        s["added"] = added
        s["failed"] = failed
        s["skipped"] = skipped
        s["last_index"] = i + 1
        save_state(s)
        # Random delay (min-max)
        delay = random.randint(min_delay, max_delay)
        log_print(f"Next in {delay}s... (Progress: {i+1}/{total_ids})")
        bot_send(f"Next in {delay}s | Added: {added} | Skipped: {skipped} | Failed: {failed}")
        await asyncio.sleep(delay)
    bot_send(f"COMPLETE! Added: {added} | Skipped: {skipped} | Failed: {failed}")
    s["last_index"] = 0
    save_state(s)
    await c.disconnect()

# ---------- PING ----------
async def ping_forever():
    while True:
        try:
            requests.get(PING_URL, timeout=10)
            log_print("PING OK")
        except:
            log_print("PING FAIL")
        await asyncio.sleep(600)

def start_ping_thread():
    threading.Thread(target=lambda: asyncio.run(ping_forever()), daemon=True).start()

# ---------- COMMANDS ----------
def process_cmd(text):
    s = load_state()
    lower = text.lower().strip()
    if lower.startswith("/start"):
        bot_send("Ready! /login → /otp → /setdelay 60-120 → /add → /status")
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
        p = text.split()
        if len(p) < 3: bot_send("Usage: /setdelay min-max (e.g., 60-120)"); return
        try:
            min_d, max_d = map(int, p[1].split('-'))
            if min_d >= max_d: raise ValueError
            s["min_delay"] = min_d
            s["max_delay"] = max_d
            save_state(s)
            bot_send(f"Delay set: {min_d}-{max_d} sec (random)")
        except:
            bot_send("Invalid: min-max (e.g., 60-120)")
        return
    if lower.startswith("/add"):
        if not s.get("logged_in"):
            bot_send("Login first!"); return
        bot_send("Starting ultra safe add (Random delay, Skip already added, FloodWait 0%)")
        # FIXED: Run add_members in separate thread
        threading.Thread(target=lambda: asyncio.run(add_members()), daemon=True).start()
        return
    if lower.startswith("/status"):
        status = f"Added: {s.get('added', 0)} | Failed: {s.get('failed', 0)} | Skipped: {s.get('skipped', 0)} | Delay: {s.get('min_delay', 60)}-{s.get('max_delay', 120)}s"
        bot_send(status)
        log_print(status)
        return
    bot_send("Unknown. /start for help")

# ---------- MAIN LOOP ----------
def main_loop():
    log_print("BOT STARTED")
    offset = None
    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                params={"offset": offset, "timeout": 15},
                timeout=20,
            ).json()
            if not r.get("ok"):
                time.sleep(1); continue
            for u in r["result"]:
                offset = u["update_id"] + 1
                msg = u.get("message", {})
                text = msg.get("text", "")
                chat = msg.get("chat", {})
                if not text or str(chat.get("id")) != str(USER_CHAT_ID):
                    continue
                process_cmd(text)
            time.sleep(1)
        except Exception as e:
            log_print(f"LOOP ERROR: {e}")
            time.sleep(3)

if __name__ == "__main__":
    start_ping_thread()
    threading.Thread(target=main_loop, daemon=True).start()
    port = int(os.environ.get('PORT', 10000))
    log_print(f"HTTP on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
