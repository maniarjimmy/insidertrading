import os
import re
import hashlib
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def sha256_file(filepath):
    if not os.path.exists(filepath):
        return "MISSING"
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def run():
    head_commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    out_file = os.path.join(BASE_DIR, "output", "audit", f"provenance_manifest_{head_commit}.txt")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)

    # Get tracked files in git
    tracked_files = set(subprocess.check_output(["git", "ls-files"]).decode("utf-8").splitlines())

    entries = [
        {
            "metric": "Flags Status (Active vs Resolved)",
            "value": "1 ACTIVE / 155 RESOLVED (156 real flags)",
            "script": "scripts/regenerate_confusion_matrix.py",
            "file": "output/audit/confusion_matrix_8bc1d15.txt",
            "notes": "Verified from scanner.db (156 flags: 1 active, 155 with resolved 10d horizon)."
        },
        {
            "metric": "Confusion Matrix (News-Driven vs Unexplained)",
            "value": "111 News-Driven / 44 Unexplained; 35 Catalyst at [T-3, T]",
            "script": "scripts/regenerate_confusion_matrix.py",
            "file": "output/audit/confusion_matrix_8bc1d15.txt",
            "notes": "DB truth: 111 CATALYST / 44 UNEXPLAINED; 35 (22.6%) pre-move catalysts at [T-3, T]."
        },
        {
            "metric": "Matched-Control Lift Baseline (classifier-v2)",
            "value": "N=99 clean pairs, Lift 0.79x, p=0.2912 (Flag 30.3% vs Ctrl 38.4%)",
            "script": "scripts/recalc_bounds_and_unique.py",
            "file": "output/audit/bounds_analysis_8367e6e.txt",
            "notes": "Paired McNemar test on 99 matched pairs under deterministic classifier-v2."
        },
        {
            "metric": "Matched-Control Lift Strictly Unique (classifier-v2)",
            "value": "N=66 unique clean pairs, Lift 1.00x, p=1.0000 (Flag 31.8% vs Ctrl 31.8%)",
            "script": "scripts/recalc_bounds_and_unique.py",
            "file": "output/audit/unique_controls_8367e6e.txt",
            "notes": "Strictly unique controls (1:1 matching without control symbol reuse)."
        },
        {
            "metric": "Legacy Flags Migration Count",
            "value": "156 real flags, 530 controls (686 total)",
            "script": "scripts/migrate_csv_to_db.py",
            "file": "output/audit/confusion_matrix_8bc1d15.txt",
            "notes": "Migrated from legacy CSVs into scanner.db; verified via SELECT is_control, count(*)."
        },
        {
            "metric": "Split Adjustment on Raw UDDiP Prices",
            "value": "5 real splits/bonuses ex-date |r| < 25% (COCHINSHIP, CANBK, BPCL, etc.)",
            "script": "scripts/audit_real_splits.py",
            "file": "output/audit/split_adjustment_07a3381.txt",
            "notes": "Direct UDDiP raw prices + internal adjuster, zero yfinance."
        },

        {
            "metric": "Stage 1 Dry Count Redo (2024 & 2022 Full Year)",
            "value": "2024: 2014 flags (8.91/d, 63.6% Nifty500); 2022: 678 flags (7.98/d, 48.4% Nifty500); Clean Ret: 78.67% (N=300); Cap C=3 Success: 99.7%",
            "script": "scripts/redo_stage1_dry_count.py",
            "file": "output/audit/stage1_dry_count_redo_bf85152.txt",
            "notes": "Full-year UDDiP 2024 (226 sessions post-warmup) and 2022 (85 sessions). Series EQ, ADTV>=5Cr, rank 101-500, ex-date +/-2d, 5d cooldown strictly applied."
        },
        {
            "metric": "Era Validity, Category Migration & Crosstab",
            "value": "2022 monthly vs annual diff=0; 2022 analyst drop explained by 'Schedule of Analysts' (579); 'General updates' (428); 'Updates'->'General Updates' in 2024",
            "script": "scripts/audit_era_validity_v2.py",
            "file": "output/audit/era_validity_crosstab_bf85152.txt",
            "notes": "Top 15 categories crosstab across 2021-2026. Claims of category 'stability' and 'zero thinning' formally retracted."
        },
        {
            "metric": "Historical Data Availability (2016-2020 5-Symbol Audit)",
            "value": "2016-2020 Bhavcopy, MTO, and announcements verified across RELIANCE, INFY, TCS, HDFCBANK, SBIN; Primary window strictly 2021-2026",
            "script": "scripts/audit_span_2016_2020_v2.py",
            "file": "output/audit/historical_span_2016_2020_5syms_bf85152.txt",
            "notes": "Sampled >=20 dates/yr for 5 symbols. Pre-registered evaluation window strictly 2021-01 to 2026-01 (61 months)."
        },
        {
            "metric": "Regrading of 4 Mismatch Rows & Formal Drop of $330M",
            "value": "ACMESOLAR/HFCL routine; IKS material; TRITURBINE desc 'Updates'; $330M dropped (absent from attchmntText)",
            "script": "scripts/regrade_mismatch_rows.py",
            "file": "output/audit/regrade_mismatches_audit_8bc1d15.txt",
            "notes": "Regraded strictly from printed text. External $330M claim dropped. Outcome 105 cached PDF text USD 39M PSV."
        },
        {
            "metric": "Historical Era Validity & User Labeling Batch",
            "value": "Uniform category distribution across 2021-2026; 40-row user batch exported",
            "script": "scripts/generate_historical_labeling_batch.py",
            "file": "output/audit/era_validity_and_categories_8bc1d15.txt",
            "notes": "Exported to output/labeling_batch_2021_2024.csv without classifier labels."
        },
        {
            "metric": "Large-Sample Control Base Rate P0 (N=3,000)",
            "value": "P0 = 11.83% [10.65%, 13.13%] across 2021-2025 non-flag stock-days",
            "script": "scripts/estimate_base_rate_3000_and_dry_count.py",
            "file": "output/audit/base_rate_3000_and_dry_count_8367e6e.txt",
            "notes": "3,000 stock-days sampled under classifier-v2 (600/year)."
        },
    ]

    lines = []
    lines.append("=" * 165)
    lines.append(f"PROGRAMMATIC AUDIT PROVENANCE MANIFEST & RETRACTION LEDGER | COMMIT: {head_commit}")
    lines.append("=" * 165)
    lines.append(f"{'Metric / Finding':<48} | {'Script (git ls-files)':<42} | {'Output File & SHA-256':<70}")
    lines.append("-" * 165)

    for e in entries:
        script_tracked = "TRACKED" if e["script"] in tracked_files else "UNTRACKED"
        fpath = os.path.join(BASE_DIR, e["file"])
        f_exists = os.path.exists(fpath)
        sha = sha256_file(fpath)[:16] if f_exists else "MISSING"
        file_desc = f"{e['file']} (sha256: {sha}...)" if f_exists else f"{e['file']} (MISSING)"
        script_desc = f"{e['script']} [{script_tracked}]"
        lines.append(f"{e['metric'][:47]:<48} | {script_desc:<42} | {file_desc:<70}")

    lines.append("-" * 165)
    lines.append("\nDETAILED VERIFICATION, DB TRUTH & CORRECTION NOTES:")
    for e in entries:
        fpath = os.path.join(BASE_DIR, e["file"])
        full_sha = sha256_file(fpath)
        lines.append(f"- {e['metric']}:")
        lines.append(f"    Claimed Value: {e['value']}")
        lines.append(f"    Script:        {e['script']} (Tracked: {e['script'] in tracked_files})")
        lines.append(f"    Output File:   {e['file']}")
        lines.append(f"    SHA-256:       {full_sha}")
        lines.append(f"    Audit Notes:   {e['notes']}")
        lines.append("")

    lines.append("=" * 165)
    out_text = "\n".join(lines)
    print(out_text)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(out_text)
    print(f"\nSaved updated provenance manifest to: {out_file}")

if __name__ == "__main__":
    run()
