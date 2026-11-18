"""
Report Generator Module (Phase 1)
Produces HTML and CSV reports of scan results, including Outcome Tracking,
Catalyst Hit Rate, Statistical Lift vs Control Group, and Resolved Flags.
"""

from datetime import datetime
import logging
import os
from typing import Any, Dict, List, Optional

from jinja2 import Template
import pandas as pd

from config import (
    MIN_PCT_CHANGE,
    MIN_VOLUME_RATIO,
    OUTPUT_DIR,
    RANK_END,
    RANK_START,
    setup_logging,
)
from db import (
    get_hit_rate_stats,
    get_recent_resolved_flags,
)

logger = setup_logging("report")


# ── HTML Template ───────────────────────────────────────────────────────────
HTML_TEMPLATE = Template("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Insider Activity Scanner — {{ scan_date }}</title>
    <style>
        :root {
            --bg: #0f0f0f;
            --surface: #1a1a2e;
            --surface-2: #16213e;
            --accent-red: #e74c3c;
            --accent-green: #2ecc71;
            --accent-blue: #3498db;
            --accent-amber: #f39c12;
            --accent-purple: #9b59b6;
            --text: #ecf0f1;
            --text-muted: #95a5a6;
            --border: #2c3e50;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 24px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 8px;
            background: linear-gradient(90deg, var(--accent-red), var(--accent-amber));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .subtitle {
            color: var(--text-muted);
            margin-bottom: 24px;
            font-size: 14px;
        }
        .stats-bar {
            display: flex;
            gap: 16px;
            margin-bottom: 32px;
            flex-wrap: wrap;
        }
        .stat-card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 16px 24px;
            min-width: 160px;
            flex: 1;
        }
        .stat-card .label { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }
        .stat-card .value { font-size: 26px; font-weight: 700; margin-top: 4px; }
        .stat-card.suspicious .value { color: var(--accent-red); }
        .stat-card.newsdriven .value { color: var(--accent-green); }
        .stat-card.scanned .value { color: var(--accent-blue); }
        .stat-card.flagged .value { color: var(--accent-amber); }
        .stat-card.lift .value { color: var(--accent-purple); }

        .section { margin-bottom: 40px; }
        .section h2 {
            font-size: 20px;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .badge {
            font-size: 11px;
            padding: 3px 10px;
            border-radius: 20px;
            font-weight: 600;
        }
        .badge-red { background: rgba(231, 76, 60, 0.2); color: var(--accent-red); }
        .badge-green { background: rgba(46, 204, 113, 0.2); color: var(--accent-green); }
        .badge-blue { background: rgba(52, 152, 219, 0.2); color: var(--accent-blue); }
        .badge-purple { background: rgba(155, 89, 182, 0.2); color: var(--accent-purple); }

        table {
            width: 100%;
            border-collapse: collapse;
            background: var(--surface);
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 16px;
        }
        thead th {
            background: var(--surface-2);
            padding: 12px 16px;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-muted);
            text-align: left;
            border-bottom: 1px solid var(--border);
        }
        tbody td {
            padding: 10px 16px;
            border-bottom: 1px solid var(--border);
            font-size: 14px;
        }
        tbody tr:hover { background: rgba(52, 152, 219, 0.08); }
        tbody tr:last-child td { border-bottom: none; }

        .positive { color: var(--accent-green); font-weight: 600; }
        .negative { color: var(--accent-red); font-weight: 600; }
        .high-vol { color: var(--accent-amber); font-weight: 600; }
        .news-cell { font-size: 12px; color: var(--text-muted); max-width: 350px; }
        .catalyst-link { color: var(--accent-blue); text-decoration: none; }
        .catalyst-link:hover { text-decoration: underline; }

        .disclaimer {
            margin-top: 40px;
            padding: 16px;
            background: rgba(243, 156, 18, 0.1);
            border: 1px solid rgba(243, 156, 18, 0.3);
            border-radius: 8px;
            font-size: 12px;
            color: var(--accent-amber);
        }
        .empty { text-align: center; padding: 40px; color: var(--text-muted); }

        .grid-2 {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 24px;
        }

        @media (max-width: 768px) {
            body { padding: 12px; }
            .stats-bar { flex-direction: column; }
            .grid-2 { grid-template-columns: 1fr; }
            table { font-size: 12px; }
            thead th, tbody td { padding: 8px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Insider Activity Scanner</h1>
        <p class="subtitle">
            Scan Date: {{ scan_date }} &nbsp;|&nbsp;
            Universe: Rank {{ rank_start }}–{{ rank_end }} &nbsp;|&nbsp;
            Filters: ≥{{ min_pct }}% price, ≥{{ min_vol_ratio }}x volume
        </p>

        <!-- Primary Scan Stats -->
        <div class="stats-bar">
            <div class="stat-card scanned">
                <div class="label">Scanned</div>
                <div class="value">{{ total_scanned }}</div>
            </div>
            <div class="stat-card flagged">
                <div class="label">Price+Vol Alert</div>
                <div class="value">{{ total_flagged }}</div>
            </div>
            <div class="stat-card suspicious">
                <div class="label">Suspicious</div>
                <div class="value">{{ num_suspicious }}</div>
            </div>
            <div class="stat-card newsdriven">
                <div class="label">News Driven</div>
                <div class="value">{{ num_news_driven }}</div>
            </div>
        </div>

        <!-- Suspicious Stocks Today -->
        <div class="section">
            <h2>🔴 Suspicious Stocks — No Catalyst News <span class="badge badge-red">{{ num_suspicious }}</span></h2>
            {% if suspicious_stocks %}
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Symbol</th>
                        <th>Company</th>
                        <th>Industry</th>
                        <th>Price (₹)</th>
                        <th>Change %</th>
                        <th>Volume</th>
                        <th>Vol Ratio</th>
                    </tr>
                </thead>
                <tbody>
                    {% for stock in suspicious_stocks %}
                    <tr>
                        <td>{{ loop.index }}</td>
                        <td><strong>{{ stock.symbol }}</strong></td>
                        <td>{{ stock.company }}</td>
                        <td>{{ stock.industry }}</td>
                        <td>₹{{ stock.current_price }}</td>
                        <td class="positive">+{{ stock.pct_change }}%</td>
                        <td>{{ stock.current_volume_fmt }}</td>
                        <td class="high-vol">{{ stock.volume_ratio }}x</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty">No suspicious stocks found today. All movers have catalyst news explaining the move.</div>
            {% endif %}
        </div>

        <!-- News-Driven Movers Today -->
        <div class="section">
            <h2>🟢 News-Driven Movers — Move Explained <span class="badge badge-green">{{ num_news_driven }}</span></h2>
            {% if news_driven_stocks %}
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Symbol</th>
                        <th>Company</th>
                        <th>Change %</th>
                        <th>Vol Ratio</th>
                        <th>Headlines</th>
                    </tr>
                </thead>
                <tbody>
                    {% for stock in news_driven_stocks %}
                    <tr>
                        <td>{{ loop.index }}</td>
                        <td><strong>{{ stock.symbol }}</strong></td>
                        <td>{{ stock.company }}</td>
                        <td class="positive">+{{ stock.pct_change }}%</td>
                        <td class="high-vol">{{ stock.volume_ratio }}x</td>
                        <td class="news-cell">{{ stock.headlines_preview }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty">No news-driven movers found.</div>
            {% endif %}
        </div>

        <!-- Phase 1: Outcome Tracking & Hit Rate Section -->
        <div class="section">
            <h2>📈 Outcome Tracking & Hit Rate <span class="badge badge-purple">T+1 to T+10 Evaluation</span></h2>

            <div class="stats-bar">
                <div class="stat-card suspicious">
                    <div class="label">10-Day Catalyst Hit Rate</div>
                    <div class="value">{{ hit_stats.flagged_precision }}%</div>
                    <small style="color: var(--text-muted)">{{ hit_stats.flagged_catalysts }}/{{ hit_stats.flagged_evaluated }} flagged flags</small>
                </div>
                <div class="stat-card newsdriven">
                    <div class="label">Control Baseline Hit Rate</div>
                    <div class="value">{{ hit_stats.control_precision }}%</div>
                    <small style="color: var(--text-muted)">{{ hit_stats.control_catalysts }}/{{ hit_stats.control_evaluated }} random control</small>
                </div>
                <div class="stat-card lift">
                    <div class="label">Statistical Lift</div>
                    <div class="value">{{ hit_stats.lift }}x</div>
                    <small style="color: var(--text-muted)">Precision vs. Control</small>
                </div>
                <div class="stat-card scanned">
                    <div class="label">Avg 10D Fwd Return</div>
                    <div class="value {% if hit_stats.avg_fwd_ret_10d >= 0 %}positive{% else %}negative{% endif %}">
                        {% if hit_stats.avg_fwd_ret_10d >= 0 %}+{% endif %}{{ hit_stats.avg_fwd_ret_10d }}%
                    </div>
                    <small style="color: var(--text-muted)">From T+1 Open</small>
                </div>
                <div class="stat-card flagged">
                    <div class="label">Avg 10D Excess Return</div>
                    <div class="value {% if hit_stats.avg_excess_ret_10d >= 0 %}positive{% else %}negative{% endif %}">
                        {% if hit_stats.avg_excess_ret_10d >= 0 %}+{% endif %}{{ hit_stats.avg_excess_ret_10d }}%
                    </div>
                    <small style="color: var(--text-muted)">vs. Midcap 150 Benchmark</small>
                </div>
            </div>

            {% if hit_stats.score_buckets %}
            <div style="margin-bottom: 24px;">
                <h3 style="font-size: 15px; margin-bottom: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Average Forward Return by Score Bucket</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Score Bucket</th>
                            <th>Sample Size (n)</th>
                            <th>Statistical Reliability</th>
                            <th>Average T+10 Return</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for bucket, bdata in hit_stats.score_buckets.items() %}
                        <tr>
                            <td><strong>{{ bucket }}</strong></td>
                            <td>{{ bdata.count }}</td>
                            <td>
                                {% if bdata.is_low_sample %}
                                <span class="badge" style="background: rgba(243, 156, 18, 0.2); color: var(--accent-amber);">⚠️ Low Sample (n &lt; 30)</span>
                                {% else %}
                                <span class="badge badge-green">✓ Valid Sample (n ≥ 30)</span>
                                {% endif %}
                            </td>
                            <td class="{% if bdata.avg_return >= 0 %}positive{% else %}negative{% endif %}">
                                {% if bdata.avg_return >= 0 %}+{% endif %}{{ bdata.avg_return }}%
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                <p style="font-size: 11px; color: var(--text-muted); margin-top: -8px;">
                    * Ground rule: Returns and hit rates with n &lt; 30 are exploratory indicators only, not statistically significant findings.
                </p>
            </div>
            {% endif %}

            <h3 style="font-size: 15px; margin-bottom: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Recent Resolved & Tracked Flags (Measured from Next-Day Open)</h3>
            {% if resolved_flags %}
            <table>
                <thead>
                    <tr>
                        <th>Scan Date</th>
                        <th>Symbol</th>
                        <th>Move %</th>
                        <th>Vol Ratio</th>
                        <th>T+1 Open (₹)</th>
                        <th>T+1 Ret</th>
                        <th>T+3 Ret</th>
                        <th>T+5 Ret</th>
                        <th>T+10 Ret</th>
                        <th>Excess 10D</th>
                        <th>Catalyst Identified</th>
                    </tr>
                </thead>
                <tbody>
                    {% for f in resolved_flags %}
                    <tr>
                        <td>{{ f.scan_date }}</td>
                        <td><strong>{{ f.symbol }}</strong></td>
                        <td class="positive">+{{ f.price_change }}%</td>
                        <td class="high-vol">{{ f.volume_ratio }}x</td>
                        <td>{% if f.entry_price %}₹{{ f.entry_price }}{% else %}—{% endif %}</td>
                        <td class="{% if f.ret_1d and f.ret_1d >= 0 %}positive{% elif f.ret_1d %}negative{% endif %}">
                            {% if f.ret_1d %}{% if f.ret_1d >= 0 %}+{% endif %}{{ f.ret_1d }}%{% else %}—{% endif %}
                        </td>
                        <td class="{% if f.ret_3d and f.ret_3d >= 0 %}positive{% elif f.ret_3d %}negative{% endif %}">
                            {% if f.ret_3d %}{% if f.ret_3d >= 0 %}+{% endif %}{{ f.ret_3d }}%{% else %}—{% endif %}
                        </td>
                        <td class="{% if f.ret_5d and f.ret_5d >= 0 %}positive{% elif f.ret_5d %}negative{% endif %}">
                            {% if f.ret_5d %}{% if f.ret_5d >= 0 %}+{% endif %}{{ f.ret_5d }}%{% else %}—{% endif %}
                        </td>
                        <td class="{% if f.ret_10d and f.ret_10d >= 0 %}positive{% elif f.ret_10d %}negative{% endif %}">
                            {% if f.ret_10d %}{% if f.ret_10d >= 0 %}+{% endif %}{{ f.ret_10d }}%{% else %}—{% endif %}
                        </td>
                        <td class="{% if f.excess_10d and f.excess_10d >= 0 %}positive{% elif f.excess_10d %}negative{% endif %}">
                            {% if f.excess_10d %}{% if f.excess_10d >= 0 %}+{% endif %}{{ f.excess_10d }}%{% else %}—{% endif %}
                        </td>
                        <td>
                            {% if f.material_found == 1 and f.catalyst_url %}
                                <a href="{{ f.catalyst_url }}" target="_blank" class="catalyst-link">📄 {{ f.catalyst_title or 'Material Filing' }}</a>
                            {% elif f.material_found == 1 %}
                                📄 {{ f.catalyst_title or 'Material Filing' }}
                            {% else %}
                                <span style="color: var(--text-muted)">None (Unexplained)</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <div class="empty">No resolved tracking outcomes yet. Evaluation populates as T+1..T+10 trading days elapse.</div>
            {% endif %}
        </div>

        <div class="disclaimer">
            ⚠️ <strong>Disclaimer:</strong> Statistical screen only. Not evidence of wrongdoing. Not investment advice.
            Forward returns are measured from next-day open to test realistic execution feasibility.
        </div>
    </div>
</body>
</html>""")


def _format_volume(vol: int) -> str:
    """Format volume with Indian number system (lakhs, crores)."""
    if vol >= 1_00_00_000:
        return f"{vol / 1_00_00_000:.1f}Cr"
    elif vol >= 1_00_000:
        return f"{vol / 1_00_00_000:.1f}L" if vol >= 1_00_00_000 else f"{vol / 1_00_000:.1f}L"
    elif vol >= 1000:
        return f"{vol / 1000:.1f}K"
    return str(vol)


def generate_report(suspicious_df: pd.DataFrame,
                    news_driven_df: pd.DataFrame,
                    total_scanned: int,
                    total_flagged: int,
                    timestamp: Optional[datetime] = None) -> str:
    """
    Generate an HTML report from scan results and database outcome tracking.
    Returns the file path of the generated HTML report.
    """
    if timestamp is None:
        timestamp = datetime.now()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Prepare suspicious stocks list
    suspicious_stocks = []
    if not suspicious_df.empty:
        for _, row in suspicious_df.iterrows():
            suspicious_stocks.append({
                "symbol": row.get("symbol", ""),
                "company": row.get("company", ""),
                "industry": row.get("industry", "Unknown"),
                "current_price": row.get("current_price", 0),
                "pct_change": row.get("pct_change", 0),
                "current_volume_fmt": _format_volume(int(row.get("current_volume", 0))),
                "volume_ratio": row.get("volume_ratio", 0),
            })

    # Prepare news-driven stocks list
    news_driven_stocks = []
    if not news_driven_df.empty:
        for _, row in news_driven_df.iterrows():
            headlines = row.get("headlines", "")
            if isinstance(headlines, str) and "|" in headlines:
                preview = headlines.split("|")[0].strip()[:100]
            else:
                preview = str(headlines)[:100] if headlines else "News found"

            news_driven_stocks.append({
                "symbol": row.get("symbol", ""),
                "company": row.get("company", ""),
                "pct_change": row.get("pct_change", 0),
                "volume_ratio": row.get("volume_ratio", 0),
                "headlines_preview": preview,
            })

    # Fetch Phase 1 outcome tracking statistics and recent resolved flags
    hit_stats = get_hit_rate_stats()
    resolved_flags = get_recent_resolved_flags(limit=15)

    html = HTML_TEMPLATE.render(
        scan_date=timestamp.strftime("%d %b %Y, %I:%M %p IST"),
        rank_start=RANK_START,
        rank_end=RANK_END,
        min_pct=MIN_PCT_CHANGE,
        min_vol_ratio=MIN_VOLUME_RATIO,
        total_scanned=total_scanned,
        total_flagged=total_flagged,
        num_suspicious=len(suspicious_stocks),
        num_news_driven=len(news_driven_stocks),
        suspicious_stocks=suspicious_stocks,
        news_driven_stocks=news_driven_stocks,
        hit_stats=hit_stats,
        resolved_flags=resolved_flags,
    )

    date_str = timestamp.strftime("%Y-%m-%d_%H%M")
    html_path = os.path.join(OUTPUT_DIR, f"scan_{date_str}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info("HTML report saved: %s", html_path)
    return html_path


def save_csv(df: pd.DataFrame, label: str, timestamp: Optional[datetime] = None) -> str:
    """Save a DataFrame to CSV in the output directory."""
    if timestamp is None:
        timestamp = datetime.now()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    date_str = timestamp.strftime("%Y-%m-%d_%H%M")
    csv_path = os.path.join(OUTPUT_DIR, f"{label}_{date_str}.csv")

    export_cols = [c for c in [
        "rank", "symbol", "company", "industry",
        "current_price", "prev_close", "pct_change",
        "current_volume", "avg_volume_20d", "volume_ratio",
        "has_catalyst_news", "classification", "headlines", "news_source"
    ] if c in df.columns]

    df[export_cols].to_csv(csv_path, index=False, encoding="utf-8")
    logger.info("CSV saved: %s", csv_path)
    return csv_path


def append_to_master_csv(df: pd.DataFrame, filename: str,
                         timestamp: Optional[datetime] = None) -> str:
    """
    Append scan results to persistent master CSV file (backward-compatible).
    """
    if timestamp is None:
        timestamp = datetime.now()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, f"{filename}.csv")

    master_cols = [
        "scan_timestamp", "rank", "symbol", "company", "industry",
        "current_price", "prev_close", "pct_change",
        "current_volume", "avg_volume_20d", "volume_ratio",
        "has_catalyst_news", "classification", "headlines", "news_source"
    ]

    ts_str = timestamp.strftime("%Y-%m-%d %H:%M")

    if df.empty:
        row = {col: "" for col in master_cols}
        row["scan_timestamp"] = ts_str
        row["company"] = "NONE"
        append_df = pd.DataFrame([row])
    else:
        append_df = pd.DataFrame()
        append_df["scan_timestamp"] = [ts_str] * len(df)
        for col in master_cols[1:]:
            if col in df.columns:
                append_df[col] = df[col].values
            else:
                append_df[col] = ""

    file_exists = os.path.isfile(csv_path)
    append_df.to_csv(csv_path, mode="a", header=not file_exists,
                     index=False, encoding="utf-8")

    action = "appended to" if file_exists else "created"
    logger.info("Master CSV %s: %s (%d rows)", action, csv_path, len(append_df))
    return csv_path
