"""
News Verification Module
Checks Google News for recent articles about flagged stocks.
Analyzes article content to distinguish real catalysts (earnings, orders,
M&A, regulatory) from generic mentions (watchlists, analyst opinions,
technical analysis, market roundups).

A stock is SUSPICIOUS only if there is no genuine catalyst-level news.
"""

import re
import time
from datetime import datetime, timedelta

import pandas as pd

from config import NEWS_LOOKBACK_HOURS, NEWS_SEARCH_DELAY, NEWS_MAX_RESULTS


# ── Keywords that indicate REAL catalysts (news explains the move) ──────────
CATALYST_KEYWORDS = [
    # Earnings & Financials
    r"\bresults?\b", r"\bearnings?\b", r"\bprofit\b", r"\brevenue\b",
    r"\bquarterly\b", r"\bq[1-4]\b", r"\bannual\b", r"\bdividend\b",
    r"\bbonus\b", r"\bsplit\b", r"\bbuyback\b", r"\beps\b",
    r"\bnet\s+income\b", r"\bturnover\b", r"\bPAT\b", r"\bEBITDA\b",

    # Orders & Business wins
    r"\border\b", r"\borders\b", r"\bcontract\b", r"\baward\b",
    r"\bwins?\b", r"\bbag(?:s|ged)?\b", r"\bsecure[sd]?\b",
    r"\bcrore\b.*\border\b", r"\border\b.*\bcrore\b",

    # M&A & Corporate Actions
    r"\bacquire[sd]?\b", r"\bacquisition\b", r"\bmerger\b",
    r"\btakeover\b", r"\bdemerger\b", r"\bstake\b",
    r"\bjoint\s+venture\b", r"\bpartnership\b", r"\bMOU\b",
    r"\bopen\s+offer\b", r"\bbuyout\b",

    # Regulatory & Approvals
    r"\bSEBI\b", r"\bapproval\b", r"\bapproved\b", r"\bclearance\b",
    r"\blicen[cs]e\b", r"\bregulator\b", r"\bcompliance\b",
    r"\bFDA\b", r"\bDCGI\b",

    # Major events
    r"\blaunch\b", r"\blaunched\b", r"\bexpansion\b",
    r"\bplant\b", r"\bcapacity\b", r"\bcommission\b",
    r"\bIPO\b", r"\bQIP\b", r"\brights\s+issue\b",
    r"\bFPO\b", r"\bOFS\b",

    # Management changes
    r"\bCEO\b", r"\bMD\b", r"\bchairman\b", r"\bappoint\b",
    r"\bresign\b", r"\bmanagement\b.*\bchange\b",

    # Sector/Industry specific catalysts
    r"\bdefence\b.*\border\b", r"\bnavy\b", r"\bgovernment\b.*\border\b",
    r"\bexport\b.*\border\b", r"\brallie[sd]\b.*\bafter\b",
    r"\bsurg(?:e[sd]?|ing)\b.*\bafter\b", r"\bjump(?:s|ed)?\b.*\bafter\b",
    r"\bsurge[sd]?\b", r"\bsoar[sed]*\b",
    r"\brecord\b.*\bhigh\b",

    # Rating & Upgrade (by actual brokerages)
    r"\bupgrade[sd]?\b", r"\bdowngrade[sd]?\b", r"\btarget\s+price\b",
    r"\bbuy\s+rating\b", r"\boverweight\b", r"\bunderweight\b",
]

# ── Keywords that indicate GENERIC / NON-CATALYST mentions ──────────────────
# These headlines do NOT explain a price move — they're noise.
GENERIC_KEYWORDS = [
    # Watchlist / picks articles
    r"\bwatchlist\b", r"\bstocks?\s+to\s+(?:watch|focus|buy|track)\b",
    r"\btop\s+\d+\s+stocks?\b", r"\bpicks?\b",
    r"\bstocks?\s+in\s+(?:focus|news)\b",
    r"\bstocks?\s+(?:to|that)\s+(?:keep|look)\b",
    r"\bmarket\s+(?:today|this\s+week|tomorrow)\b",

    # Technical analysis
    r"\bsupport\b.*\bresistance\b", r"\btechnical\s+analysis\b",
    r"\bcharting\b", r"\bmoving\s+average\b", r"\bbreakout\b",
    r"\bcandlestick\b", r"\bRSI\b", r"\bMACD\b",
    r"\btechnical\s+view\b", r"\bchart\s+pattern\b",

    # Generic market commentary
    r"\bmarket\s+roundup\b", r"\bmarket\s+wrap\b",
    r"\bmarket\s+snapshot\b", r"\bmarket\s+update\b",
    r"\btrade\s+setup\b", r"\bmarket\s+(?:open|close)\b",

    # Trivial mentions  
    r"\brated\b.*\b(?:hold|neutral|sell|strong sell|strong buy)\b",
    r"\bMarketsMOJO\b", r"\bMarkets\s*Mojo\b",
    r"\bmoneycontrol\b.*\bpoll\b",
    r"\bshare\s+price\s+today\b",
    r"\bbuzzing\b", r"\btrending\b",
]


def _is_catalyst_headline(headline: str) -> bool:
    """
    Analyze a headline to determine if it describes a real catalyst.
    Returns True if the headline contains catalyst-level information.
    """
    hl = headline.lower()

    # First check if it's clearly a generic/noise headline
    for pattern in GENERIC_KEYWORDS:
        if re.search(pattern, hl, re.IGNORECASE):
            return False

    # Then check if it contains real catalyst keywords
    for pattern in CATALYST_KEYWORDS:
        if re.search(pattern, hl, re.IGNORECASE):
            return True

    return False


def _classify_headline(headline: str) -> str:
    """
    Classify a headline into categories:
    - 'catalyst': Real news that explains price movement
    - 'generic': Watchlist, technical analysis, or noise
    - 'unclear': Cannot determine — treat as non-catalyst
    """
    hl = headline.lower()

    # Check generic first (these override catalyst keywords)
    for pattern in GENERIC_KEYWORDS:
        if re.search(pattern, hl, re.IGNORECASE):
            return "generic"

    # Check catalyst
    for pattern in CATALYST_KEYWORDS:
        if re.search(pattern, hl, re.IGNORECASE):
            return "catalyst"

    return "unclear"


def check_news(company_name: str, symbol: str) -> dict:
    """
    Search Google News for recent articles about a stock and
    analyze whether the news is a real catalyst or just generic mention.

    Parameters
    ----------
    company_name : str - Full company name
    symbol : str - NSE ticker symbol (without .NS)

    Returns
    -------
    dict with keys:
        has_catalyst_news : bool - True if real catalyst news found
        has_any_news : bool - True if any news at all was found
        catalyst_headlines : list[str] - Headlines that are real catalysts
        generic_headlines : list[str] - Generic/noise headlines
        all_headlines : list[str] - All headlines found
        source : list[str] - News source names
        classification : str - 'catalyst', 'generic_only', or 'no_news'
    """
    try:
        from gnews import GNews
    except ImportError:
        print("[News] WARNING: gnews not installed. Run: pip install gnews")
        return {
            "has_catalyst_news": False, "has_any_news": False,
            "catalyst_headlines": [], "generic_headlines": [],
            "all_headlines": [], "source": [], "classification": "no_news"
        }

    result = {
        "has_catalyst_news": False,
        "has_any_news": False,
        "catalyst_headlines": [],
        "generic_headlines": [],
        "all_headlines": [],
        "source": [],
        "classification": "no_news",
    }

    # Initialize GNews with Indian English, last 24 hours
    google_news = GNews(
        language="en",
        country="IN",
        max_results=NEWS_MAX_RESULTS,
        period="1d",
    )

    # Search strategies: company name, then symbol
    search_queries = [
        company_name,
        f"{symbol} NSE",
        f"{symbol} share price",
    ]

    all_articles = []
    seen_titles = set()

    for query in search_queries:
        try:
            articles = google_news.get_news(query)
            if articles:
                for article in articles:
                    title = article.get("title", "")
                    if title and title not in seen_titles:
                        seen_titles.add(title)
                        all_articles.append(article)
        except Exception:
            pass

        if len(all_articles) >= NEWS_MAX_RESULTS:
            break

    if not all_articles:
        result["classification"] = "no_news"
        return result

    # Analyze each headline
    result["has_any_news"] = True

    for article in all_articles[:NEWS_MAX_RESULTS]:
        title = article.get("title", "N/A")
        publisher = article.get("publisher", {})
        source_name = publisher.get("title", "Unknown") if isinstance(publisher, dict) else str(publisher or "Unknown")

        result["all_headlines"].append(title)
        result["source"].append(source_name)

        classification = _classify_headline(title)

        if classification == "catalyst":
            result["catalyst_headlines"].append(title)
        else:
            result["generic_headlines"].append(title)

    # Final classification
    if result["catalyst_headlines"]:
        result["has_catalyst_news"] = True
        result["classification"] = "catalyst"
    elif result["generic_headlines"]:
        result["classification"] = "generic_only"
    else:
        result["classification"] = "no_news"

    return result


def classify_stocks(flagged_df: pd.DataFrame) -> tuple:
    """
    Classify flagged stocks into:
    - suspicious: No news at all, OR only generic mentions (watchlists etc.)
    - news_driven: Has real catalyst news explaining the move

    Parameters
    ----------
    flagged_df : pd.DataFrame with columns: symbol, company

    Returns
    -------
    tuple(suspicious_df, news_driven_df)
    """
    if flagged_df.empty:
        return flagged_df.copy(), flagged_df.copy()

    total = len(flagged_df)
    print(f"[News] Checking news for {total} flagged stocks...")

    news_results = []

    for idx, row in flagged_df.iterrows():
        symbol = row["symbol"]
        company = row["company"]
        count = len(news_results) + 1

        print(f"  [{count}/{total}] {symbol} ({company})...", end=" ")

        news = check_news(company, symbol)

        if news["classification"] == "catalyst":
            preview = news["catalyst_headlines"][0][:70]
            print(f"CATALYST: {preview}...")
        elif news["classification"] == "generic_only":
            preview = news["generic_headlines"][0][:70]
            print(f"GENERIC ONLY (suspicious): {preview}...")
        else:
            print("NO NEWS (suspicious)")

        news_results.append({
            "yf_symbol": row.get("yf_symbol", f"{symbol}.NS"),
            "has_catalyst_news": news["has_catalyst_news"],
            "classification": news["classification"],
            "headlines": " | ".join(news["catalyst_headlines"]) if news["catalyst_headlines"] else " | ".join(news["generic_headlines"]),
            "news_source": " | ".join(news["source"]) if news["source"] else "",
            "catalyst_count": len(news["catalyst_headlines"]),
            "generic_count": len(news["generic_headlines"]),
        })

        if count < total:
            time.sleep(NEWS_SEARCH_DELAY)

    news_df = pd.DataFrame(news_results)
    merged = flagged_df.merge(news_df, on="yf_symbol", how="left")
    merged["has_catalyst_news"] = merged["has_catalyst_news"].fillna(False)
    merged["classification"] = merged["classification"].fillna("no_news")

    # Suspicious = no news OR only generic mentions
    suspicious = merged[~merged["has_catalyst_news"]].copy().reset_index(drop=True)

    # News-driven = has real catalyst news
    news_driven = merged[merged["has_catalyst_news"]].copy().reset_index(drop=True)

    print(f"\n[News] Classification complete:")
    print(f"       SUSPICIOUS (no catalyst):  {len(suspicious)}")
    print(f"       NEWS-DRIVEN (catalyst):    {len(news_driven)}")

    # Detail breakdown
    no_news_count = len(merged[merged["classification"] == "no_news"])
    generic_only_count = len(merged[merged["classification"] == "generic_only"])
    print(f"         - No news at all:        {no_news_count}")
    print(f"         - Generic mentions only:  {generic_only_count}")

    return suspicious, news_driven


# ── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 65)
    print("  News Module - Headline Analysis Test")
    print("=" * 65)

    # Test headline classification
    test_headlines = [
        "Cochin Shipyard bags Rs 6000 crore Navy order for survey vessels",
        "Reliance Industries Q3 profit rises 12% to Rs 18,500 crore",
        "Top 5 stocks to watch today: HDFC, Reliance, TCS in focus",
        "BSE Ltd Stock Hits All-Time High at Rs.3227, Marking a Milestone",
        "Stocks to buy: 3 short-term trading ideas by experts",
        "MCX Gold, Silver Rate Today highlights: Gold prices rise",
        "Cochin Shipyard Ltd is Rated Strong Sell - Markets Mojo",
        "Olectra wins Rs 300 crore order for 150 electric buses",
        "Technical Analysis: MAZDOCK support at 2400, resistance at 2500",
        "SEBI approves Adani Wilmar OFS for promoter stake reduction",
    ]

    for hl in test_headlines:
        cat = _classify_headline(hl)
        marker = "CATALYST" if cat == "catalyst" else "GENERIC " if cat == "generic" else "UNCLEAR "
        print(f"  [{marker}] {hl[:75]}")

    # Test live news check
    print(f"\n{'='*65}")
    print("  Live News Check")
    print(f"{'='*65}")

    test_cases = [
        ("Reliance Industries", "RELIANCE"),
        ("Cochin Shipyard", "COCHINSHIP"),
    ]

    for company, symbol in test_cases:
        print(f"\n  Checking: {company} ({symbol})")
        result = check_news(company, symbol)
        print(f"    Classification: {result['classification']}")
        print(f"    Catalyst headlines: {len(result['catalyst_headlines'])}")
        print(f"    Generic headlines:  {len(result['generic_headlines'])}")
        if result["catalyst_headlines"]:
            for h in result["catalyst_headlines"][:2]:
                print(f"      [C] {h[:80]}")
        if result["generic_headlines"]:
            for h in result["generic_headlines"][:2]:
                print(f"      [G] {h[:80]}")
        time.sleep(NEWS_SEARCH_DELAY)
