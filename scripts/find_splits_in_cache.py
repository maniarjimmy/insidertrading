import json, os
from datetime import date
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bhavcopy import download_uddip_bhavcopy

# Let's inspect cached corporate actions or find 5 verified splits/bonuses in 2024-2026
with open("output/cache/corporate_actions_cache.json", "r", encoding="utf-8") as f:
    actions = json.load(f)

splits_bonuses = [a for a in actions if a.get("action_type") in ("SPLIT", "BONUS") and a.get("ratio", 1.0) > 1.0]
print(f"Total splits/bonuses in cache: {len(splits_bonuses)}")
for a in splits_bonuses[:15]:
    print(a)
