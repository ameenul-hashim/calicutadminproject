import threading
import time
import urllib.request
import os
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

def is_active_hours():
    now = datetime.now(IST)
    # Active: 6:00 AM to 11:59 PM IST — sleep between 12 AM and 5:59 AM
    return now.hour >= 6

def ping_health_endpoint():
    time.sleep(60)
    url = "https://neolearner.onrender.com/health/"

    while True:
        now = datetime.now(IST)
        if is_active_hours():
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'KeepAlivePingBot'})
                with urllib.request.urlopen(req) as response:
                    if response.status == 200:
                        print(f"[{now.strftime('%H:%M IST')}] Keep-alive ping successful")
            except Exception as e:
                print(f"[{now.strftime('%H:%M IST')}] Keep-alive ping failed: {e}")
            time.sleep(720)
        else:
            print(f"[{now.strftime('%H:%M IST')}] Night hours — sleeping. Server will spin down.")
            time.sleep(300)

def start_keep_alive():
    if os.getenv('DEBUG', 'True') == 'False':
        for thread in threading.enumerate():
            if thread.name == "KeepAliveThread":
                return
        t = threading.Thread(target=ping_health_endpoint, name="KeepAliveThread")
        t.daemon = True
        t.start()
        print("Keep-alive thread started (IST 6AM-12AM only).")
