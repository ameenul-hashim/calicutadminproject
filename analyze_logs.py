import os
import re
from collections import Counter

def analyze_logs(log_file='security.log'):
    if not os.path.exists(log_file):
        print(f"❌ Log file {log_file} not found.")
        return

    print(f"🔍 ANALYZING LOG INTELLIGENCE: {log_file}")
    print("=" * 60)
    
    with open(log_file, 'r') as f:
        lines = f.readlines()

    # 1. Error Frequency
    errors = [line for line in lines if 'ERROR' in line or 'CRITICAL' in line]
    print(f"❌ Total Critical Errors: {len(errors)}")
    
    # 2. Top Recurring Issues (Module/Message)
    if errors:
        error_types = []
        for err in errors:
            # Extract module name or common error message pattern
            match = re.search(r'([A-Za-z_.]+) \d+ \d+', err)
            if match:
                error_types.append(match.group(1))
        
        print("\n📈 TOP RECURRING MODULE FAILURES:")
        for module, count in Counter(error_types).most_common(5):
            print(f"  - {module}: {count} occurrences")

    # 3. Pipeline Specifics
    pipeline_fails = [line for line in lines if 'PARTIAL_PIPELINE_FAILURE' in line]
    print(f"\n⚠️ Pipeline Failures: {len(pipeline_fails)}")

    # 4. Access Logs Check
    access_logs = [line for line in lines if 'PDFAccessLog' in line]
    print(f"📄 Audited Access Events: {len(access_logs)}")

    print("=" * 60)
    print("💡 RECOMMENDATION: If module failure count > 10, investigate code logic.")

if __name__ == "__main__":
    analyze_logs()
