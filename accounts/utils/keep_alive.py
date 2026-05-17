import threading
import time
import urllib.request
import os

def ping_health_endpoint():
    # Wait a minute before first ping to ensure server is fully up
    time.sleep(60)
    # The URL to ping. Ideally we want the production URL.
    # We can use the Render domain.
    url = "https://edustreamcalicut.onrender.com/health/"
    
    while True:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'KeepAlivePingBot'})
            with urllib.request.urlopen(req) as response:
                if response.status == 200:
                    print(f"✅ Keep-alive ping successful to {url}")
        except Exception as e:
            print(f"⚠️ Keep-alive ping failed: {e}")
            
        # Ping every 12 minutes (720 seconds) to prevent the 15-minute Render sleep
        time.sleep(720)

def start_keep_alive():
    # Only run the ping in production/when not in debug to avoid cluttering local dev
    if os.getenv('DEBUG', 'True') == 'False':
        # Check if the thread is already running to avoid duplicates in certain WSGI/ASGI setups
        for thread in threading.enumerate():
            if thread.name == "KeepAliveThread":
                return
                
        t = threading.Thread(target=ping_health_endpoint, name="KeepAliveThread")
        t.daemon = True
        t.start()
        print("🚀 Keep-alive background thread started.")
