import os
import json
import sqlite3

CACHE_DIR = "output/cache/announcements"
# Let's inspect a couple of cached announcement files
for f in os.listdir(CACHE_DIR)[:5]:
    path = os.path.join(CACHE_DIR, f)
    with open(path, "r", encoding="utf-8") as fp:
        data = json.load(fp)
        if data:
            print(f, "keys:", list(data[0].keys()))
            for item in data[:3]:
                if item.get("attchmntText"):
                    print(f"  attchmntText found in {f}: {item.get('attchmntText')[:80]}")
            break
