import os
import time
from datetime import datetime

def verify_backup_health():
    print("🛡️ EDUSTREAM BACKUP REDUNDANCY VERIFICATION")
    print("=" * 60)
    
    # 1. Local Success Check
    if os.path.exists('last_success.txt'):
        with open('last_success.txt', 'r') as f:
            last_ts = f.read().strip()
            print(f"✅ Local last_success.txt: {last_ts}")
            
            # Check if stale (>26 hours)
            try:
                last_dt = datetime.fromisoformat(last_ts)
                delta = datetime.now() - last_dt
                if delta.total_seconds() > 26 * 3600:
                    print(f"⚠️ STALE BACKUP: Last success was {delta.total_seconds()/3600:.1f} hours ago!")
                else:
                    print("✅ Backup is fresh (within 26h window).")
            except:
                print("❌ Invalid timestamp in last_success.txt")
    else:
        print("❌ last_success.txt NOT FOUND locally.")

    # 2. Local Backup Presence
    if os.path.exists('backups'):
        backups = os.listdir('backups')
        print(f"📂 Local Backup Files: {len(backups)}")
        if backups:
            latest = max([os.path.join('backups', f) for f in backups], key=os.path.getmtime)
            print(f"📄 Latest Local: {os.path.basename(latest)} ({os.path.getsize(latest)/1024/1024:.2f}MB)")
    else:
        print("❌ 'backups' directory not found locally.")

    print("=" * 60)
    print("💡 ACTION: If stale, run 'python auto_backup.py' immediately.")

if __name__ == "__main__":
    verify_backup_health()
