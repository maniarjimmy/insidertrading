"""
Report Generator Module
Produces HTML and CSV reports of scan results.
"""

import os
from datetime import datetime

import pandas as pd
from jinja2 import Template

from config import OUTPUT_DIR


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
        }
        .stat-card .label { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }
        .stat-card .value { font-size: 28px; font-weight: 700; margin-top: 4px; }
        .stat-card.suspicious .value { color: var(--accent-red); }
        .stat-card.newsdriven .value { color: var(--accent-green); }
        .stat-card.scanned .value { color: var(--accent-blue); }
        .stat-card.flagged .value { color: var(--accent-amber); }

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

        table {
            width: 100%;
            border-collapse: collapse;
            background: var(--surface);
            border-radius: 12px;
            overflow: hidden;
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
        .high-vol { color: var(--accent-amber); font-weight: 600; }
        .news-cell { font-size: 12px; color: var(--text-muted); max-width: 350px; }

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

        @media (max-width: 768px) {
            body { padding: 12px; }
            .stats-bar { flex-direction: column; }
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

        <!-- Suspicious Stocks -->
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

        <!-- News-Driven Movers -->
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

        <div class="disclaimer">
            ⚠️ <strong>Disclaimer:</strong> This scanner identifies stocks with unusual price and volume
            moves without associated public news. It does NOT confirm insider trading. Always perform
            your own due diligence. Not investment advice. Use at your own risk.
        </div>
    </div>
</body>
</html>""")


def _format_volume(vol: int) -> str:
    """Format volume with Indian number system (lakhs, crores)."""
    if vol >= 1_00_00_000:  # 1 crore
        return f"{vol / 1_00_00_000:.1f}Cr"
    elif vol >= 1_00_000:  # 1 lakh
        return f"{vol / 1_00_000:.1f}L"
    elif vol >= 1000:
        return f"{vol / 1000:.1f}K"
    return str(vol)


def generate_report(suspicious_df: pd.DataFrame,
                    news_driven_df: pd.DataFrame,
                    total_scanned: int,
                    total_flagged: int,
                    timestamp: datetime = None) -> str:
    """
    Generate an HTML report from scan results.

    Returns the file path of the generated HTML report.
    """
    if timestamp is None:
        timestamp = datetime.now()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Prepare template data
    suspicious_stocks = []
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

    news_driven_stocks = []
    for _, row in news_driven_df.iterrows():
        headlines = row.get("headlines", "")
        # Show first headline only as preview
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

    from config import RANK_START, RANK_END, MIN_PCT_CHANGE, MIN_VOLUME_RATIO

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
    )

    # Save HTML
    date_str = timestamp.strftime("%Y-%m-%d_%H%M")
    html_path = os.path.join(OUTPUT_DIR, f"scan_{date_str}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[Report] ✅ HTML report saved: {html_path}")
    return html_path


def save_csv(df: pd.DataFrame, label: str, timestamp: datetime = None) -> str:
    """Save a DataFrame to CSV in the output directory."""
    if timestamp is None:
        timestamp = datetime.now()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    date_str = timestamp.strftime("%Y-%m-%d_%H%M")
    csv_path = os.path.join(OUTPUT_DIR, f"{label}_{date_str}.csv")

    # Select relevant columns for export
    export_cols = [c for c in [
        "rank", "symbol", "company", "industry",
        "current_price", "prev_close", "pct_change",
        "current_volume", "avg_volume_20d", "volume_ratio",
        "has_catalyst_news", "classification", "headlines", "news_source"
    ] if c in df.columns]

    df[export_cols].to_csv(csv_path, index=False, encoding="utf-8")
    print(f"[Report] ✅ CSV saved: {csv_path}")
    return csv_path
