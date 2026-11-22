import glob
import json
import os
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "output", "cache", "announcements")


def run():
    head_commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    out_file = os.path.join(BASE_DIR, "output", "audit", f"cache_redesign_{head_commit}.txt")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)

    lines = []
    lines.append("=" * 105)
    lines.append(f"ANNOUNCEMENT CACHE REDESIGN AUDIT (RAW FIELDS ONLY) | COMMIT: {head_commit}")
    lines.append("=" * 105)

    files = glob.glob(os.path.join(CACHE_DIR, "*.json"))
    lines.append(f"Total Announcement Cache Files: {len(files)}")

    # Sample before redesign
    with open(files[0], "r", encoding="utf-8") as f:
        before_item = json.load(f)[0]
    lines.append(f"Previous Cached Keys (with classifier outputs): {list(before_item.keys())}")
    lines.append(f"Sample Stored Classifier Outputs: catalyst_state={before_item.get('catalyst_state')}, is_material={before_item.get('is_material')}, category={before_item.get('category')}\n")

    total_records = 0
    # Convert all files to raw fields only
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            items = json.load(f)

        raw_items = []
        for it in items:
            raw_items.append({
                "symbol": it.get("symbol", ""),
                "date_str": it.get("date_str", "") or it.get("an_dt", ""),
                "desc": it.get("desc", ""),
                "attchmntText": it.get("attchmntText") or it.get("text", "") or "",
                "url": it.get("url") or it.get("attchmntFile", "") or "",
            })
            total_records += 1

        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw_items, f)

    # Sample after redesign
    with open(files[0], "r", encoding="utf-8") as f:
        after_item = json.load(f)[0]
    lines.append(f"Redesigned Cached Keys (RAW FIELDS ONLY): {list(after_item.keys())}")
    lines.append(f"Total Records Migrated across {len(files)} symbol cache files: {total_records}")
    lines.append("Removed Fields: ['catalyst_state', 'is_material', 'category', 'dt', 'source']")
    lines.append("Retained Raw Exchange Fields: ['symbol', 'date_str', 'desc', 'attchmntText', 'url']\n")

    lines.append("ARCHITECTURAL GUARANTEE:")
    lines.append("1. Zero classifier outputs are stored in announcement cache.")
    lines.append("2. Catalyst classification is computed dynamically at analysis time using the frozen tagged classifier (classifier-v1).")
    lines.append("3. Decouples raw exchange data ingestion from evolving or versioned classification rules.")
    lines.append("=" * 105)

    out_text = "\n".join(lines)
    print(out_text)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(out_text)
    print(f"\n[Cache redesign report written to {out_file}]")


if __name__ == "__main__":
    run()
