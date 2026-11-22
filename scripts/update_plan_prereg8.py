import os

plan_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "PLAN.md")

with open(plan_path, "r", encoding="utf-8") as fp:
    content = fp.read()

# Normalize CRLF to LF for reliable manipulation
content = content.replace("\r\n", "\n")

target_start = "     - **Classifier Freeze & Evolution Policy**: `classifier-v2` is frozen."
target_end = "\n---\n\n### Phase 4: India-Specific Market Microstructure Data"

start_idx = content.find(target_start)
end_idx = content.find(target_end)

if start_idx == -1 or end_idx == -1:
    print(f"Error: target strings not found (start_idx={start_idx}, end_idx={end_idx})")
    exit(1)

new_block = """     - **Classifier Freeze & Evolution Policy**: `classifier-v3` is FROZEN under annotated tag `classifier-v3`. It operates strictly as deterministic TEXT-ONLY (desc + attchmntText), with zero PDF extraction and zero network calls.
       - *Positive Unscheduled-Material Categories (is_material = 1)*: Order Win, Acquisition (Third-Party), Production Commencement, Credit Rating (Upgrade), Regulatory Approval.
       - *Secondary / Routine Categories (is_material = 0 for primary)*: Credit Rating (Downgrade/Reaffirmation/Other), Acquisition (Intra-Group/JV), Disinvestment (slump sale), Fund Raising, Board Meeting / Financial Results, Routine Disclosure (SAST Reg 29/31, Dividend TDS circular, share certificates, newspaper notices).
       - *Regraded 4-Row Fidelity*: ACMESOLAR (Routine), HFCL (Routine), IKS (Acquisition Third-Party), TRITURBINE (Routine TDS fix) all verified 100% PASS in `output/audit/classifier_v3_regraded_4rows_8825201.txt`.
     - **Co-Primary Outcome (Classifier-Free)**:
       - **Forward Excess Return**: Forward return measured from next-day open to $T+10$ close minus matched control's return over the identical horizon ($R_{\\text{flag}} - R_{\\text{ctrl}}$). Completely free of classification artifacts.

   * **Pre-Registered Success Rule & Questions Answered (Items 2 & 7)**:
     - **Questions Answered**:
       1. **Primary A (Announcement Lift)**: *"Do price/volume moves precede material news?"* Tests information leakage and insider trading mechanisms.
       2. **Primary B (Forward Excess Return)**: *"Is there a tradable post-move return edge?"* Tests economic exploitability and profitability of the anomaly post-move.
     - **Multiple-Testing Correction (Holm-Bonferroni Method)**:
       - Evaluating two co-primaries at independent $\\alpha = 0.05$ inflates family-wise error rate to ~0.0975.
       - Decision Rule: Both hypotheses are tested with Holm-Bonferroni step-down adjustment starting at $\\alpha = 0.025$ (one-sided):
         * Sort $p$-values: $p_{(1)} \\le p_{(2)}$.
         * Step 1: Reject $H_{0(1)}$ if $p_{(1)} < 0.025$ ($\\alpha / 2$). If not rejected, stop (neither declared significant).
         * Step 2: If $H_{0(1)}$ is rejected, reject $H_{0(2)}$ if $p_{(2)} < 0.05$ ($\\alpha / 1$).
       - Sizing target: 1.25x lift and +1.50% excess return serve as sizing targets; confirmation gate is statistical significance under Holm adjustment.
     - **Inference, Clustering & Robustness**:
       - Return regressions use two-way date- and symbol-clustered standard errors (Cameron-Gelbach-Miller).
       - Forward excess returns are winsorized at 1st and 99th percentiles.
       - Both Mean Excess Return and Median Excess Return (with Wilcoxon signed-rank paired test) will be reported.
     - **Inconclusive Threshold**: Any null result ($p \\ge 0.025$) obtained when statistical power is $<80\\%$ is reported strictly as **INCONCLUSIVE**, not as evidence of absence of edge.

   * **Statistical Power, Clustering & Effective Sample Size (Items 2 & 7a)**:
     - **Removal of Fixed Assumptions**: Fixed DEFF assumptions and ungrounded "100% power" claims are permanently removed.
     - **Simulation-Based MDE Gate**: Minimum Detectable Effect is calibrated via matched-pair binomial sign simulation under empirical base rate $P_0 = 6.54\\%$ (`scripts/audit_stage1_gates_and_mde.py`).
     - Target sample sizing of $N = 1,250$ clean matched pairs yields:
       * Power at 1.25x lift: 34.5%
       * Power at 1.30x lift: 45.9%
       * Power at 1.35x lift: 57.5%
       * MDE at 80% power: **1.46x lift** ($\\alpha = 0.025$ one-sided).
     - **Confirmatory Sizing Gate**: If Stage 1 yields $< 1,000$ clean pairs, the backtest run is classified as **EXPLORATORY** and cannot claim confirmatory statistical power.

   * **Automated Stage 1 Stopping Gates & Rationale (Items 1, 7 & 8)**:
     - Before unblinding Stage 2 outcomes, the Stage 1 artifact (`output/backtest_stage1_flags_controls.csv`) must satisfy all automated gates:
       1. **Data Completeness Gate**: Any year with $> 2\\%$ missing trading sessions fails the gate (threshold: $\\le 5$ missing days/year).
       2. **Covariate Balance**: Standardized Mean Difference ($\\text{SMD} < 0.10$) across 20-day Turnover, 60-day Volatility, and $\\log(\\text{Close})$.
       3. **Clean Matched-Pair Yield**: $\\ge 200$ clean matched pairs per calendar year ($\\ge 1,000$ clean pairs across 2021–2025). Evaluates **CLEAN PAIRS** (both flag AND control clean), not isolated flags.
       4. **Matching Tolerance & Success**: 1:1 nearest-neighbor matching within turnover quintile ($\\pm 20\\%$) and volatility quintile ($\\pm 20\\%$), achieving $\\ge 95.0\\%$ matching success among clean flags.
       5. **Measurement Error / UNCLEAR Share**: Annual UNCLEAR share on evaluated stock-days $\\le 40.0\\%$ across all years (calibrated against empirical range 23.9%–36.4%).
       6. **User Review & Sign-Off**: Explicit user review and written approval of Stage 1a/1b artifacts before running Stage 2.

   * **Data Completeness & Dry Count Redo Summary (Items 1 & 7)**:
     - **Trading Sessions & Data Availability (2021–2025)**:
       - 2021: 247 sessions (100% complete across `sec_bhavdata` and `MTO`).
       - 2022: 247 sessions (100% complete across `sec_bhavdata` and `MTO`).
       - 2023: 245 sessions (100% complete across `sec_bhavdata` and `MTO`).
       - 2024: 245 sessions (100% complete across `UDDiP` and `MTO`).
       - 2025: 246 sessions (100% complete across `UDDiP` and `MTO`).
       - 0 missing sessions across all 5 calendar years; passes data completeness gate.
     - **2022 Truncation Root Cause**: The earlier reported 105 sessions (85 effective) was caused by a silent rate-throttle termination at 2022-05-31. The 146 missing dates were downloaded and audited.
     - **Full-Year 2022 Dry Count (All 247 Sessions)**:
       - Raw Flags: 2,082 flags (mean 9.17/day, median 9.0, P90 17.0, max 35).
       - Top 5 Dates Share: 122/2,082 = 5.9%.
       - Unique Flagged Symbols: 631 stocks (mean 3.30 flags/symbol).
       - Nifty 500 Constituent Share: 1,043/2,082 = 50.1%.
       - Matching Success Under Cap $C=3$: 2,030/2,082 = **97.5%** (846 eligible control stocks, 2,538 slots vs 1,638 expected clean flags = 1.55x capacity cushion).
     - **Full-Year 2024 Dry Count**: 2,014 raw flags (mean 8.91, median 8.0, P90 15.0, max 28). Top 5 dates share: 6.3%. Unique symbols: 649. Matching success under Cap $C=3$: 99.7%.
     - **EOD Flag Yield Explanation**: EOD flags (~9/day) exceed 14:30 intraday snapshots (~3/day) due to late-session volume accumulation (25–35% of volume traded post-14:30) and late-day momentum expansion crossing +4.0%, combined with scanning all liquid EQ equities rather than a narrow ~150-symbol watchlist.
     - **Pre-Move Retention**: 97.1% clean under `classifier-v3` on random mid/small-cap non-flag stock days ($N = 3,500$, seed = 42).

   * **Era Validity, Category Migration & Taxonomy Reconciliation (Items 4 & 7b)**:
     - **2022 Category Reconciliation**:
       - `Loss of share certificate` (940) + `Loss of Share Certificates` (252) = 1,192 filings.
       - `Newspaper Advertisements` (193) + `Newspaper Publication` (27) = 220 filings.
       - `Annual General Meeting` (77) + `Postal Ballot` (62) + `Shareholders meeting` (8) = 147 filings.
       - `Closure of trading window` (62) + `Trading Window` (26) = 88 filings.
       - `ESOP/ESPS/SBEB Scheme` (274) + `ESOP/ESOS/ESPS` (12) = 286 filings.
       - `Schedule of Analysts Meet` (676) + `Updates` (122) = 954 filings.
       - `General updates` (625) + `Updates` (99) = 724 filings.
     - Conclusion: There was zero collapse in filing activity in 2022; differences are entirely attributable to alternate taxonomy strings used by NSE, all mapped to routine disclosures in `classifier-v3`.
     - **Annual UNCLEAR Share**: 2021 (23.9%), 2022 (32.0%), 2023 (28.7%), 2024 (33.6%), 2025 (36.4%), establishing empirical calibration for the $\\le 40.0\\%$ measurement error gate.

   * **Historical Data Span & Evaluation Horizon (Item 6)**:
     - **Pre-Registered Horizon**: The primary backtest evaluation window remains strictly pre-registered as **2021-01-01 through 2025-12-31 (60 calendar months, ~1,230 trading days)**. Pre-2021 data is dropped due to incomplete Bhavcopy/MTO archives. Development data (Feb–May 2026, Nov 2026) remains strictly quarantined.

   * **Authoritative Publication Timing & Operational Rules (Item 6d)**:
     - **Publication Milestones (Verified from Server HTTP Headers)**:
       - UDDiP Bhavcopy: 11:03:02 GMT (16:33:02 IST) to the exact second.
       - MTO Delivery Position: Published between 16:49 IST and 17:03 IST.
       - Bulk Deals (`bulk.csv`) & Block Deals (`block.csv`): Empirical range **18:02 – 18:31 IST**.
       - Security List (`sec_list.csv`): Empirical range **18:31 – 19:29 IST**.
     - **As-Of Rules**:
       - The 17:15 IST pass may use UDDiP Bhavcopy and MTO delivery files. It may NOT use same-day bulk deals, block deals, or security list files.
       - The scheduled 20:00 IST logger operates as the authoritative EOD archive pass.
     - **Retry & Abort Policy for 17:15 IST Pass**:
       - Given the 12-minute margin between MTO publication (~17:03 IST) and the 17:15 IST scan, verify HTTP 200 availability of UDDiP and MTO files at 17:15 IST.
       - If either file returns 404, retry at 17:30, 17:45, and 18:00 IST.
       - If files remain unavailable at 18:00 IST, abort with alert log `DATA_NOT_READY_AT_1800` and fall back to scheduled evening pass at 19:30 IST. Zero partial or unverified scans.

   * **Standardized Operational Rules for Backtest Execution**:
     1. **Primary Signal**: Price return $r_{\\text{day}} \\in [+4.0\\%, +15.0\\%]$, Volume multiple $V / \\text{SMA}_{20}(V) \\ge 2.0\\text{x}$, Series `EQ`.
     2. **Matching Protocol**: 1:1 nearest-neighbor matching on 20-day Average Daily Turnover quintile ($\\pm 20\\%$) and 60-day historical volatility quintile ($\\pm 20\\%$) on the SAME scan date $T$.
     3. **Control Uniqueness**: Zero reuse of the same symbol on the same scan date; symbol reuse capped at $\\le 3\\text{x}$ per symbol per calendar year.
     4. **Repeat-Flag Cooldown**: 5-trading-day cooldown on the same symbol (initial flag retained).
     5. **Corporate Action Exclusions**: Flags and controls within ex-date $\\pm 2$ trading days of stock splits, bonus issues, or rights issues are strictly excluded.
     6. **Clean-Pair Definition**: Both flag and matched control must have NO positive unscheduled-material corporate filing in $[T-3, T\\text{ 17:15 IST}]$ evaluated under `classifier-v3`. Both must possess verified $T+1$ Open price and full $T+1..T+10$ OHLCV candle history.
     7. **Standardized Window Labels**: Every table must report Pre-Move Window ($[T-3, T\\text{ 17:15 IST}]$ baseline or $[T-10, T\\text{ 17:15 IST}]$ sensitivity) and Forward Horizon ($[T+1, T+10]$ primary or $[T+1, T+3]$ secondary).
     8. **Stage 1 Decoupling & Protocol Separation (Item 8)**:
        - **Stage 1a**: Pure Price, Volume, and Corporate Action Matching. Generates raw flags, matches controls under Cap $C=3$, computes covariate balance (SMDs on Turnover, Volatility, $\\log(\\text{Close})$). Zero announcements accessed.
        - **Stage 1b**: Pre-Move Cleanliness Filtering. Filters pairs for pre-move cleanliness under frozen `classifier-v3`. Runs ONLY after `classifier-v3` is frozen and user hand-labels are scored.
        - **Stage 2**: Evaluates forward outcomes in $[T+1, T+10]$ strictly after Stage 1 artifact approval and user hand-label scoring. Zero rule changes after unblinding.
     9. **Frozen Stage 1a Code and Config Hashes**:
        - `config.py`: `e5757e345829f46ee71ab8d440504ecba49f0b27078dcd6137c490edd8d0f889`
        - `holidays.py`: `302bcdfd1290d7c935f5bfca32ad57740691109f86e1b766530e0e4130094df7`
        - `corporate_actions.py`: `df10d62f33c76c7fdb2148d1ae38616856a0673aee54b7612c13b13bb6be2bcb`
        - `scanner.py`: `0fdd4443b574afdda95bcd618371265509434c2e60202dfe4b14255ac064cd32`
        - `scripts/audit_data_completeness_and_full_2022.py`: `1217aafbf215418014934d1129f73322728f746e5d363a63798e7c0189b8b4c1`
"""

content = content[:start_idx] + new_block + content[end_idx:]

with open(plan_path, "w", encoding="utf-8") as fp:
    fp.write(content)

print("PLAN.md updated successfully for prereg-v8!")
