"""
Phase 0: Endpoint Feasibility Spike & Data Quality Verification
Tests all candidate NSE, BSE, Bhavcopy, and alternative endpoints from the runner environment.
Validates HTTP status, JSON/CSV parsing, record counts, and field completeness.
"""

import gzip
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("FeasibilitySpike")

DEFAULT_TIMEOUT = 15
REPORT_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

NSE_HEADERS = {
    **BROWSER_HEADERS,
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nseindia.com/",
    "Origin": "https://www.nseindia.com",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

BSE_HEADERS = {
    **BROWSER_HEADERS,
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.bseindia.com/",
    "Origin": "https://www.bseindia.com",
}


def create_resilient_session(is_nse: bool = False) -> requests.Session:
    """Create a configured session with default headers and optional cookie bootstrap."""
    session = requests.Session()
    headers = NSE_HEADERS if is_nse else BROWSER_HEADERS
    session.headers.update(headers)

    if is_nse:
        try:
            logger.info("Bootstrapping NSE session cookies from homepage...")
            r = session.get("https://www.nseindia.com", timeout=DEFAULT_TIMEOUT)
            logger.info("NSE homepage response: %s (cookies: %d)", r.status_code, len(session.cookies))
            time.sleep(1.0)
        except Exception as e:
            logger.warning("NSE homepage bootstrap failed: %s", e)

    return session


def _decode_response_content(resp: requests.Response) -> str:
    """Safely decode content handling gzip/deflate if needed."""
    content = resp.content
    if resp.headers.get("Content-Encoding") == "gzip" or content[:2] == b"\x1f\x8b":
        try:
            content = gzip.decompress(content)
        except Exception:
            pass
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="replace")


def test_endpoint(
    name: str,
    url: str,
    category: str,
    expected_format: str = "CSV",
    required_fields: Optional[List[str]] = None,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    session: Optional[requests.Session] = None,
    params: Optional[Dict[str, Any]] = None,
    retries: int = 2
) -> Dict[str, Any]:
    """Test an endpoint for HTTP 200, valid body parsing, record counts, and required fields."""
    req_session = session or requests.Session()
    active_headers = headers or BROWSER_HEADERS
    status_code: Optional[int] = None
    latency_ms = 0.0
    payload_size = 0
    preview = ""
    error_msg = ""
    success = False
    valid_format = False
    items_count = 0
    fields_checked = "N/A"

    logger.info("Testing [%s] %s ...", category, name)
    start_time = time.time()

    for attempt in range(1, retries + 1):
        try:
            t0 = time.time()
            if method.upper() == "GET":
                resp = req_session.get(url, headers=active_headers, params=params, timeout=DEFAULT_TIMEOUT)
            else:
                resp = req_session.post(url, headers=active_headers, json=params, timeout=DEFAULT_TIMEOUT)
            latency_ms = round((time.time() - t0) * 1000, 1)

            status_code = resp.status_code
            payload_size = len(resp.content)
            text_body = _decode_response_content(resp)

            if status_code in (200, 206):
                # Validate Format
                if expected_format.upper() == "JSON":
                    try:
                        parsed_json = json.loads(text_body)
                        valid_format = True
                        if isinstance(parsed_json, list):
                            items_count = len(parsed_json)
                            preview = f"Valid JSON Array ({items_count} items)"
                            if required_fields and items_count > 0:
                                first = parsed_json[0]
                                missing = [f for f in required_fields if f not in first]
                                fields_checked = "All Present" if not missing else f"Missing: {missing}"
                        elif isinstance(parsed_json, dict):
                            keys = list(parsed_json.keys())
                            items_count = len(keys)
                            preview = f"Valid JSON Dict (keys: {keys[:4]})"
                            if required_fields:
                                # Check if required fields exist either at root or inside Table/data array
                                sub_table = parsed_json.get("Table") or parsed_json.get("data")
                                if isinstance(sub_table, list) and sub_table:
                                    first = sub_table[0]
                                    missing = [f for f in required_fields if f not in first]
                                    fields_checked = "All Present" if not missing else f"Missing: {missing}"
                                else:
                                    missing = [f for f in required_fields if f not in parsed_json]
                                    fields_checked = "All Present" if not missing else f"Missing: {missing}"
                        else:
                            preview = "Valid JSON scalar"
                    except Exception as json_err:
                        valid_format = False
                        error_msg = f"Invalid JSON: {json_err}"

                elif expected_format.upper() == "CSV":
                    lines = [ln.strip() for ln in text_body.strip().splitlines() if ln.strip()]
                    if lines:
                        valid_format = True
                        items_count = len(lines) - 1  # data rows
                        header_line = lines[0]
                        preview = f"Valid CSV ({items_count} rows)"
                        if required_fields:
                            missing = [f for f in required_fields if f.lower() not in header_line.lower()]
                            fields_checked = "All Present" if not missing else f"Missing: {missing}"
                    else:
                        valid_format = False
                        error_msg = "Empty CSV"
                elif expected_format.upper() == "XML":
                    if text_body.strip().startswith("<?xml") or "<rss" in text_body:
                        valid_format = True
                        preview = f"Valid XML/RSS ({len(text_body)} bytes)"
                    else:
                        valid_format = False
                        error_msg = "Not XML"

                if valid_format:
                    success = True
                    break
                else:
                    logger.warning("Attempt %d format validation failed for %s: %s", attempt, name, error_msg)
            else:
                error_msg = f"HTTP {status_code}"
                logger.warning("Attempt %d for %s failed with HTTP %d", attempt, name, status_code)

            time.sleep(1.0 * attempt)

        except Exception as ex:
            latency_ms = round((time.time() - start_time) * 1000, 1)
            error_msg = str(ex)
            logger.warning("Attempt %d for %s error: %s", attempt, name, ex)
            time.sleep(1.0 * attempt)

    return {
        "name": name,
        "category": category,
        "url": url,
        "status_code": status_code or "ERR",
        "expected_format": expected_format,
        "valid_format": valid_format,
        "items_count": items_count,
        "fields_checked": fields_checked,
        "success": success,
        "latency_ms": latency_ms,
        "payload_size": payload_size,
        "preview": preview if success else error_msg[:100],
        "notes": "Verified" if success else error_msg
    }


def find_recent_trading_days(count: int = 5) -> List[datetime]:
    """Return dates for recent weekdays."""
    dates = []
    curr = datetime.now()
    while len(dates) < count:
        curr -= timedelta(days=1)
        if curr.weekday() < 5:  # Mon-Fri
            dates.append(curr)
    return dates


def run_all_checks() -> Dict[str, Any]:
    """Execute complete Phase 0 test suite and extract quality inspection samples."""
    results: List[Dict[str, Any]] = []
    samples: Dict[str, Any] = {}
    recent_dates = find_recent_trading_days(5)
    latest_weekday_str = recent_dates[0].strftime("%Y%m%d")

    # ─────────────────────────────────────────────────────────────────────────
    # 1. NSE Index Lists
    # ─────────────────────────────────────────────────────────────────────────
    index_files = [
        ("NSE Index - NIFTY 100", "https://archives.nseindia.com/content/indices/ind_nifty100list.csv", ["Symbol", "Company Name"]),
        ("NSE Index - Midcap 150", "https://archives.nseindia.com/content/indices/ind_niftymidcap150list.csv", ["Symbol", "Company Name"]),
        ("NSE Index - Smallcap 250", "https://archives.nseindia.com/content/indices/ind_niftysmallcap250list.csv", ["Symbol", "Company Name"]),
        ("NSE Index - NIFTY 500", "https://archives.nseindia.com/content/indices/ind_nifty500list.csv", ["Symbol", "Company Name"]),
    ]
    for name, url, req_cols in index_files:
        results.append(test_endpoint(name, url, "1. NSE Index Lists", expected_format="CSV", required_fields=req_cols))

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Bhavcopy & Delivery
    # ─────────────────────────────────────────────────────────────────────────
    for d in recent_dates:
        d_str = d.strftime("%d%m%Y")
        url = f"https://archives.nseindia.com/products/content/sec_bhavdata_full_{d_str}.csv"
        res = test_endpoint(
            f"NSE Full Bhavcopy ({d.strftime('%Y-%m-%d')})",
            url,
            "2. Bhavcopy & Delivery",
            expected_format="CSV",
            required_fields=["SYMBOL", "SERIES", "CLOSE_PRICE", "DELIV_QTY", "DELIV_PER"]
        )
        results.append(res)
        if res["success"]:
            break

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Deals & Surveillance
    # ─────────────────────────────────────────────────────────────────────────
    results.append(test_endpoint(
        "NSE Bulk Deals CSV",
        "https://archives.nseindia.com/content/equities/bulk.csv",
        "3. Deals & Surveillance",
        expected_format="CSV",
        required_fields=["Date", "Symbol", "Client Name", "Quantity Traded"]
    ))
    results.append(test_endpoint(
        "NSE Block Deals CSV",
        "https://archives.nseindia.com/content/equities/block.csv",
        "3. Deals & Surveillance",
        expected_format="CSV",
        required_fields=["Date", "Symbol", "Client Name", "Quantity Traded"]
    ))

    # ─────────────────────────────────────────────────────────────────────────
    # 4. NSE Dynamic APIs
    # ─────────────────────────────────────────────────────────────────────────
    nse_session = create_resilient_session(is_nse=True)

    # 4.1 Announcements
    ann_res = test_endpoint(
        "NSE Corporate Announcements API",
        "https://www.nseindia.com/api/corporate-announcements?index=equities",
        "4. NSE Dynamic APIs",
        expected_format="JSON",
        required_fields=["symbol", "desc", "an_dt", "attchmntFile"],
        headers=NSE_HEADERS,
        session=nse_session
    )
    results.append(ann_res)

    # Capture 2 announcement samples
    if ann_res["success"]:
        try:
            r = nse_session.get("https://www.nseindia.com/api/corporate-announcements?index=equities", timeout=10)
            ann_data = r.json()
            samples["nse_announcements"] = ann_data[:2]
        except Exception as e:
            samples["nse_announcements_error"] = str(e)
    time.sleep(1.0)

    # 4.2 Event Calendar (Board Meetings & Results)
    ev_res = test_endpoint(
        "NSE Event Calendar (Board Meetings / Results)",
        "https://www.nseindia.com/api/event-calendar?index=equities",
        "4. NSE Dynamic APIs",
        expected_format="JSON",
        required_fields=["symbol", "purpose", "date"],
        headers=NSE_HEADERS,
        session=nse_session
    )
    results.append(ev_res)

    if ev_res["success"]:
        try:
            r = nse_session.get("https://www.nseindia.com/api/event-calendar?index=equities", timeout=10)
            ev_data = r.json()
            samples["nse_event_calendar"] = ev_data[:2]
        except Exception as e:
            samples["nse_event_calendar_error"] = str(e)
    time.sleep(1.0)

    # 4.3 Corporate Actions & Holidays
    results.append(test_endpoint(
        "NSE Corporate Actions API",
        "https://www.nseindia.com/api/corporates-corporateActions?index=equities",
        "4. NSE Dynamic APIs",
        expected_format="JSON",
        required_fields=["symbol", "subject", "exDate"],
        headers=NSE_HEADERS,
        session=nse_session
    ))
    time.sleep(1.0)

    results.append(test_endpoint(
        "NSE Trading Holidays Master",
        "https://www.nseindia.com/api/holiday-master?type=trading",
        "4. NSE Dynamic APIs",
        expected_format="JSON",
        required_fields=["CM"],
        headers=NSE_HEADERS,
        session=nse_session
    ))

    # ─────────────────────────────────────────────────────────────────────────
    # 5. BSE Dynamic APIs
    # ─────────────────────────────────────────────────────────────────────────
    bse_session = requests.Session()
    bse_session.headers.update(BSE_HEADERS)

    bse_ann_url = (
        f"https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?"
        f"pageno=1&strCat=-1&strPrevDate={latest_weekday_str}&strScrip=&strSearch=P&strToDate={latest_weekday_str}&strType=C"
    )
    bse_res = test_endpoint(
        f"BSE Announcements API ({latest_weekday_str})",
        bse_ann_url,
        "5. BSE Dynamic APIs",
        expected_format="JSON",
        required_fields=["SCRIP_CD", "HEADLINE", "CATEGORYNAME", "NEWS_DT"],
        headers=BSE_HEADERS,
        session=bse_session
    )
    results.append(bse_res)

    if bse_res["success"]:
        try:
            r = bse_session.get(bse_ann_url, timeout=10)
            bse_json = r.json()
            table = bse_json.get("Table", [])
            samples["bse_announcements"] = table[:2]
        except Exception as e:
            samples["bse_announcements_error"] = str(e)

    # ─────────────────────────────────────────────────────────────────────────
    # 6. News Feeds
    # ─────────────────────────────────────────────────────────────────────────
    results.append(test_endpoint(
        "Google News RSS (Reliance 1d)",
        "https://news.google.com/rss/search?q=Reliance+when:1d&hl=en-IN&gl=IN&ceid=IN:en",
        "6. News & Fallback Feeds",
        expected_format="XML"
    ))

    # ─────────────────────────────────────────────────────────────────────────
    # 7. Market Data Fallback (yfinance)
    # ─────────────────────────────────────────────────────────────────────────
    yf_success = False
    yf_status = "ERR"
    yf_preview = ""
    t0 = time.time()
    try:
        import yfinance as yf
        ticker = yf.Ticker("RELIANCE.NS")
        info = ticker.fast_info
        last_price = getattr(info, "last_price", None)
        hist = ticker.history(period="3d")
        yf_success = last_price is not None and not hist.empty
        yf_status = 200 if yf_success else 500
        yf_preview = f"Valid yfinance data (lastPrice: {round(last_price, 2) if last_price else 'N/A'}, 3d candles: {len(hist)})"
    except Exception as yf_err:
        yf_preview = str(yf_err)[:100]

    results.append({
        "name": "yfinance (RELIANCE.NS fast_info & history)",
        "category": "7. Market Data Fallback",
        "url": "yfinance:RELIANCE.NS",
        "status_code": yf_status,
        "expected_format": "Python API",
        "valid_format": yf_success,
        "items_count": len(hist) if yf_success else 0,
        "fields_checked": "last_price, history candles",
        "success": yf_success,
        "latency_ms": round((time.time() - t0) * 1000, 1),
        "payload_size": 0,
        "preview": yf_preview,
        "notes": "Verified" if yf_success else "yfinance error"
    })

    return {"results": results, "samples": samples}


def generate_markdown_report(data: Dict[str, Any], runner_environment: str = "Local") -> str:
    """Generate comprehensive Markdown report."""
    results = data["results"]
    samples = data["samples"]
    total = len(results)
    passed = sum(1 for r in results if r["success"])
    failed = total - passed

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        f"# Phase 0: Feasibility & Data Quality Report ({runner_environment})",
        f"**Environment**: {runner_environment}",
        f"**Run Timestamp**: {timestamp}",
        f"**Total Tested**: {total} | **Passed**: {passed} | **Failed**: {failed}",
        "",
        "| Category | Endpoint / Source | Status | Format Valid? | Items/Rows | Required Fields | Latency |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
    ]

    for r in results:
        status_badge = f"✅ `{r['status_code']}`" if r["success"] else f"❌ `{r['status_code']}`"
        fmt_badge = "✅ Yes" if r["valid_format"] else "❌ No"
        name = r["name"]
        cat = r["category"]
        cnt = str(r["items_count"])
        flds = r["fields_checked"]
        lat = f"{r['latency_ms']} ms"
        lines.append(f"| {cat} | {name} | {status_badge} | {fmt_badge} | {cnt} | {flds} | {lat} |")

    lines.extend([
        "",
        "---",
        "## Content Quality & Sample Records",
        "",
        "### 1. NSE Corporate Announcements (Sample 2 Records)",
        "```json",
        json.dumps(samples.get("nse_announcements", []), indent=2),
        "```",
        "",
        "### 2. BSE Corporate Announcements (Sample 2 Records)",
        "```json",
        json.dumps(samples.get("bse_announcements", []), indent=2),
        "```",
        "",
        "### 3. NSE Event Calendar: Board Meetings & Financial Results (Sample 2 Records)",
        "```json",
        json.dumps(samples.get("nse_event_calendar", []), indent=2),
        "```",
        ""
    ])

    return "\n".join(lines)


def main():
    os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
    is_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    env_name = "GitHub-Hosted Runner (ubuntu-latest)" if is_ci else "Local Environment"

    logger.info("Starting Phase 0 Endpoint Feasibility Spike (%s)...", env_name)

    data = run_all_checks()
    report_content = generate_markdown_report(data, runner_environment=env_name)

    report_filename = "runner_feasibility_report.md" if is_ci else "endpoint_feasibility_report.md"
    out_path = os.path.join(REPORT_OUTPUT_DIR, report_filename)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    print("\n" + report_content + "\n")
    logger.info("Report written to %s", out_path)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path and os.path.exists(os.path.dirname(summary_path)):
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(report_content + "\n")
            logger.info("Written to GITHUB_STEP_SUMMARY")
        except Exception as e:
            logger.warning("Could not write to GITHUB_STEP_SUMMARY: %s", e)

    sys.exit(0)


if __name__ == "__main__":
    main()
