import os
import requests
from datetime import datetime

def get_health():
    try:
        res = requests.get("http://localhost:8000/health/", timeout=5)
        return res.json()
    except:
        return {"status": "unreachable"}

def run_diagnostic():
    print("🚑 EDUSTREAM INCIDENT COMMAND: SYSTEM DIAGNOSTIC")
    print("=" * 60)
    
    # 1. Health Endpoint
    print(f"🏥 Health Status: {get_health()}")

    # 2. Backup Status
    if os.path.exists("last_success.txt"):
        with open("last_success.txt", "r") as f:
            print(f"💾 Last Backup Success: {f.read().strip()}")
    else:
        print("💾 Last Backup Success: NEVER")

    # 3. Log Inspection (Last 50 Errors)
    if os.path.exists("security.log"):
        print("\n🚫 RECENT LOG ERRORS (Last 50 lines):")
        with open("security.log", "r") as f:
            lines = f.readlines()
            errors = [l for l in lines if "ERROR" in l or "CRITICAL" in l][-50:]
            if errors:
                for err in errors:
                    print(f"  {err.strip()}")
            else:
                print("  (No critical errors found in log)")
    else:
        print("\n🚫 Log file 'security.log' not found.")

    # 4. Storage Check
    backups_dir = "backups"
    if os.path.exists(backups_dir):
        files = os.listdir(backups_dir)
        print(f"\n📂 Local Backup Files: {len(files)}")
    
    print("=" * 60)
    print("💡 NEXT STEP: Refer to edustream_runbooks.md for resolution steps.")

if __name__ == "__main__":
    run_diagnostic()
