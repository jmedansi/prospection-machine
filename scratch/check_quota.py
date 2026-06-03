# -*- coding: utf-8 -*-
import sys
import os

# Add project root to sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.sniper_sender_service import (
    get_sniper_daily_quota,
    get_sniper_sent_today,
    get_sniper_quota_remaining
)

def main():
    print("=== SNIPER QUOTA DIAGNOSTICS ===")
    daily_quota = get_sniper_daily_quota()
    sent_today = get_sniper_sent_today()
    remaining = get_sniper_quota_remaining()
    
    print(f"Daily Quota (planning_settings): {daily_quota}")
    print(f"Sent Today:                     {sent_today}")
    print(f"Remaining for Today:            {remaining}")
    
if __name__ == '__main__':
    main()
