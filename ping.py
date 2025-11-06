import requests
import time
import threading

PING_URL = "https://your-bot-name.onrender.com"  # ← TUMHARA RENDER URL

def ping_forever():
    while True:
        try:
            requests.get(PING_URL, timeout=10)
            print(f"[{time.strftime('%H:%M')}] PING SENT → {PING_URL}")
        except:
            print(f"[{time.strftime('%H:%M')}] PING FAILED")
        time.sleep(300)  # 5 min = 300 sec

# Background thread
threading.Thread(target=ping_forever, daemon=True).start()
