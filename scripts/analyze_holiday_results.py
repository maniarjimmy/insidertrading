import json
import collections

with open("output/holiday_validation_results.json", "r", encoding="utf-8") as f:
    data = json.load(f)

mismatches = data.get("mismatches", [])
print(f"Total mismatches recorded: {len(mismatches)}")

status_counts = collections.Counter(m["status_code"] for m in mismatches)
print("Status code counts among mismatches:", status_counts)

# Real mismatches are those where status_code was 200 (for marked holiday) or 404 (for trading day)
real_mismatches = [m for m in mismatches if m["status_code"] in (200, 404)]
print(f"Mismatches with clean 200 or 404 status: {len(real_mismatches)}")
for rm in real_mismatches:
    print(rm)
