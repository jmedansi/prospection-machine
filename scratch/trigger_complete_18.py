import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.campaign_tracker import complete_campaign

print("Triggering complete_campaign(18)...")
complete_campaign(18)
print("Done!")
