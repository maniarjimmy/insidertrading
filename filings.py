"""
Corporate Filings & Catalyst Detection Module (filings.py)
Phase 2 Implementation:
1. Ingest corporate disclosures from NSE API (primary) with BSE fallback.
2. Symbol Mapping: NSE Symbol -> ISIN -> BSE Scrip Code.
3. Event Calendar: 7-day forward window for upcoming board meeting intimations.
4. Unified Classifier: Standardized categorization using NSE 'desc' first, text rules for ambiguous cases.
   Outputs: (catalyst_state, is_material, category)
   catalyst_state: "CATALYST" | "UNCLEAR" | "NONE"
   is_material: 1 | 0
5. Caching and rate-throttling to respect exchange limits and GitHub Actions runtime budget.
"""

from datetime import date, datetime, timedelta
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from config import (
    REQUEST_BACKOFF_FACTOR,
    REQUEST_MAX_RETRIES,
    REQUEST_TIMEOUT,
    setup_logging,
)

logger = setup_logging("filings")

# In-memory filing caches to eliminate redundant HTTP calls
_FILINGS_CACHE: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
_EVENT_CALENDAR_CACHE: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
_NSE_SESSION: Optional[requests.Session] = None
_BSE_SESSION: Optional[requests.Session] = None
_NSE_TO_BSE_MAP: Optional[Dict[str, Dict[str, str]]] = None

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

BSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.bseindia.com/",
    "Origin": "https://www.bseindia.com",
}


def load_symbol_mapping() -> Dict[str, Dict[str, str]]:
    """Load pre-generated NSE-to-BSE symbol and ISIN mapping."""
    global _NSE_TO_BSE_MAP
    if _NSE_TO_BSE_MAP is not None:
        return _NSE_TO_BSE_MAP

    mapping_file = os.path.join(os.path.dirname(__file__), "data", "nse_to_bse_mapping.json")
    if os.path.exists(mapping_file):
        try:
            with open(mapping_file, "r", encoding="utf-8") as f:
                _NSE_TO_BSE_MAP = json.load(f)
                return _NSE_TO_BSE_MAP
        except Exception as exc:
            logger.warning("Failed to load nse_to_bse_mapping.json: %s", exc)

    _NSE_TO_BSE_MAP = {}
    return _NSE_TO_BSE_MAP


def get_bse_scrip_code(symbol: str) -> Optional[str]:
    """Resolve an NSE symbol to its 6-digit BSE scrip code."""
    mapping = load_symbol_mapping()
    item = mapping.get(symbol)
    if item and "bse_scrip" in item:
        return item["bse_scrip"]
    return None


def get_nse_session() -> requests.Session:
    """Return a shared requests.Session with active NSE session cookies."""
    global _NSE_SESSION
    if _NSE_SESSION is None:
        _NSE_SESSION = requests.Session()
        _NSE_SESSION.headers.update(NSE_HEADERS)
        try:
            _NSE_SESSION.get("https://www.nseindia.com", timeout=REQUEST_TIMEOUT)
        except Exception as exc:
            logger.debug("Failed initial NSE cookie handshake: %s", exc)
    return _NSE_SESSION


def get_bse_session() -> requests.Session:
    """Return a shared requests.Session for BSE queries."""
    global _BSE_SESSION
    if _BSE_SESSION is None:
        _BSE_SESSION = requests.Session()
        _BSE_SESSION.headers.update(BSE_HEADERS)
    return _BSE_SESSION


# ─────────────────────────────────────────────────────────────────────────────
# 1. Unified Catalyst & Materiality Classifier (Requirements A & B)
# ─────────────────────────────────────────────────────────────────────────────

# Explicit Desc Categories (Priority 1)
MATERIAL_DESC_CATEGORIES = {
    "Financial Results": "Financial Results",
    "Financial Result": "Financial Results",
    "Audited Financial Results": "Financial Results",
    "Unaudited Financial Results": "Financial Results",
    "Board Meeting": "Board Meeting",
    "Board Meeting Intimation": "Board Meeting",
    "Outcome of Board Meeting": "Board Meeting",
    "Acquisition": "Acquisition",
    "Amalgamation/Merger": "Acquisition",
    "Takeover": "Acquisition",
    "Diversification/Disinvestment": "Acquisition",
    "Disinvestment": "Acquisition",
    "Commencement of commercial production/operations": "Production Commencement",
    "Commencement of Commercial Production": "Production Commencement",
    "Award of Order / Receipt of Order": "Order Win",
    "Order / Contract": "Order Win",
    "Fund Raising": "Fund Raising",
    "Preferential Issue": "Fund Raising",
    "Rights Issue": "Fund Raising",
    "Qualified Institutions Placement": "Fund Raising",
    "Credit Rating": "Credit Rating",
    "Regulatory Action": "Regulatory Approval",
    "Action(s) initiated or orders passed": "Regulatory Action",
}

ROUTINE_DESC_CATEGORIES = {
    "Loss of Share Certificates / Issue of Duplicate Share Certificate": "Routine Disclosure",
    "Loss of Share Certificates": "Routine Disclosure",
    "Duplicate Share Certificate": "Routine Disclosure",
    "Newspaper Publication": "Routine Disclosure",
    "Copy of Newspaper Publication": "Routine Disclosure",
    "Compliance Certificate": "Routine Disclosure",
    "Certificate under Regulation 74(5)": "Routine Disclosure",
    "Certificate under Regulation 40(9)": "Routine Disclosure",
    "Closure of Trading Window": "Routine Disclosure",
    "Clarification on Price Movement": "Routine Disclosure",
    "Clarification on Spurt in Volume": "Routine Disclosure",
    "Allotment of ESOP / Shares": "Routine Disclosure",
    "Analysts/Institutional Investor Meet": "Routine Disclosure",
    "Transcript": "Routine Disclosure",
    "Audio / Video Recording": "Routine Disclosure",
}

# Text Pattern Rules (Priority 2: used when desc is ambiguous, e.g. "Updates", "General", or empty)
ROUTINE_TEXT_PATTERNS = [
    (r"\b(closure\s+of\s+trading\s+window|trading\s+window\s+clos(?:ed|ure))\b", "Routine Disclosure"),
    (r"\b(newspaper\s+publication|notice\s+published|press\s+release\s+newspaper)\b", "Routine Disclosure"),
    (r"\b(loss\s+of\s+share\s+cert|duplicate\s+share\s+cert|regulation\s+39\s*\(\s*3\s*\))\b", "Routine Disclosure"),
    (r"\b(regulation\s+74\s*\(\s*5\s*\)|regulation\s+40\s*\(\s*9\s*\)|compliance\s+certificate|depositories\s+and\s+participants|certificate\s+under\s+sebi)\b", "Routine Disclosure"),
    (r"\b(clarification\s+on\s+price\s+movement|spurt\s+in\s+volume|no\s+undisclosed\s+(?:price|info))\b", "Routine Disclosure"),
    (r"\b(investor\s+presentation|analyst\s+meet|conference\s+call|transcript|concall|earnings\s+call)\b", "Routine Disclosure"),
    (r"\b(esop|employee\s+stock\s+option|allotment\s+of\s+\d+\s+shares)\b", "Routine Disclosure"),
    (r"\b(investor\s+complaints|redressal\s+of\s+investor|score\s+report)\b", "Routine Disclosure"),
    (r"\b(customs\s+duty|gst\s+(?:demand|order|penalty)|income\s+tax\s+(?:demand|order)|differential\s+customs\s+duty|penalty\s+under\s+(?:customs|gst|income\s+tax))\b", "Routine Disclosure"),
]

MATERIAL_TEXT_PATTERNS = [
    (r"\b(financial\s+results?|quarterly\s+results?|q[1-4]\s+results?|limited\s+review|annual\s+results?)\b", "Financial Results"),
    (r"\b(board\s+meeting|outcome\s+of\s+board|dividend|bonus\s+issue|stock\s+split|buyback)\b", "Board Meeting"),
    (r"\b(acqui(?:re[ds]?|sition)|amalgamation|merger|takeover|joint\s+venture|stake\s+purchase|investment\s+in\s+subsidiary)\b", "Acquisition"),
    (r"\b(order\s+win|award\s+of\s+contract|signs?\s+contract|bags?\s+(?:new\s+)?orders?|secures?\s+(?:export\s+|new\s+)?orders?|receives?\s+(?:new\s+)?orders?|letter\s+of\s+award)\b", "Order Win"),
    (r"\b(contract\s+with|entered\s+into\s+(?:a\s+)?contract|construction\s+and\s+sale\s+of|award\s+of\s+(?:contract|order)|commercial\s+contract)\b", "Order Win"),
    (r"\b(divest(?:ed|ment|ing)?|disinvest(?:ed|ment|ing)?|slump\s+sale)\b", "Acquisition"),
    (r"\b(commencement\s+of\s+commercial\s+production|commercial\s+production|operationalization\s+of\s+facility)\b", "Production Commencement"),
    (r"\b(fund\s+rais(?:ing|e)|qip|preferential\s+(?:issue|allotment)|rights\s+issue|commercial\s+paper|ncd\s+issu)\b", "Fund Raising"),
    (r"\b(credit\s+rating\s+(?:upgrade|reaffirm|revised)|crisil|icra|care\s+ratings|india\s+ratings)\b", "Credit Rating"),
    (r"\b(usfda|establishment\s+inspection|eir\s+with\s+vai|regulatory\s+approval|patent\s+grant|product\s+approval)\b", "Regulatory Approval"),
]

_PDF_TEXT_CACHE_PATH = os.path.join(os.path.dirname(__file__), "output", "cache", "pdf_text_cache.json")
_PDF_TEXT_CACHE: Optional[Dict[str, str]] = None
PDF_CACHE_MISSES: List[Dict[str, str]] = []


def _load_pdf_text_cache() -> Dict[str, str]:
    global _PDF_TEXT_CACHE
    if _PDF_TEXT_CACHE is not None:
        return _PDF_TEXT_CACHE
    if os.path.exists(_PDF_TEXT_CACHE_PATH):
        try:
            with open(_PDF_TEXT_CACHE_PATH, "r", encoding="utf-8") as f:
                _PDF_TEXT_CACHE = json.load(f)
                return _PDF_TEXT_CACHE
        except Exception:
            pass
    _PDF_TEXT_CACHE = {}
    return _PDF_TEXT_CACHE


def extract_pdf_first_page_text(url: str, fetch_remote: bool = True) -> str:
    """Download and extract text from the first page of an exchange attachment PDF with local disk caching."""
    if not url or not str(url).startswith("http"):
        return ""
    cache = _load_pdf_text_cache()
    if url in cache:
        return cache[url]
    if not fetch_remote:
        return ""

    try:
        import io
        import pypdf
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=6)
        if r.status_code == 200:
            reader = pypdf.PdfReader(io.BytesIO(r.content))
            if len(reader.pages) > 0:
                p1_text = reader.pages[0].extract_text() or ""
                cache[url] = p1_text[:2000]
                try:
                    os.makedirs(os.path.dirname(_PDF_TEXT_CACHE_PATH), exist_ok=True)
                    with open(_PDF_TEXT_CACHE_PATH, "w", encoding="utf-8") as f:
                        json.dump(cache, f)
                except Exception:
                    pass
                return cache[url]
    except Exception as exc:
        logger.debug("PDF first-page extraction skipped for %s: %s", url, exc)

    cache[url] = ""
    return ""


def classify_catalyst_v2(desc: Optional[str] = None,
                         text: Optional[str] = None,
                         source: str = "filing") -> Tuple[str, int, str]:
    """
    classifier-v2: Deterministic TEXT-ONLY classifier (desc + attchmntText).
    Zero PDF extraction, zero network requests, fully reproducible across all
    historical eras (2021-2026).
    """
    return classify_catalyst(
        desc=desc,
        text=text,
        source=source,
        url=None,
        parse_pdf=False,
        fetch_remote_pdf=False,
        cache_only_pdf=False,
    )


def classify_catalyst_v3(desc: Optional[str] = None,
                         text: Optional[str] = None,
                         source: str = "filing") -> Tuple[str, int, str]:
    """
    classifier-v3: Signed positive unscheduled-material classifier for primary outcome.
    Deterministic TEXT-ONLY (desc + attchmntText). Zero PDF extraction, zero network requests.
    
    Constituent Positive Unscheduled-Material Categories (is_material = 1):
      - "Order Win": Commercial contracts, LOA, supply/construction agreements, PPA.
      - "Acquisition (Third-Party)": Genuine third-party acquisitions, mergers, open offers.
      - "Production Commencement": Plant commissioning, commercial operations launch.
      - "Credit Rating (Upgrade)": Rating upgrades or new rating assignments.
      - "Regulatory Approval": USFDA approvals/EIR VAI, product approvals, patent grants.

    Separate Secondary / Routine Categories (is_material = 0 for primary positive):
      - "Credit Rating (Downgrade)" / "Credit Rating (Reaffirmation)" / "Credit Rating (Other)"
      - "Acquisition (Intra-Group/JV)" / "Disinvestment"
      - "Fund Raising": Preferential issue, QIP, rights issue, warrants
      - "Board Meeting" / "Financial Results": Scheduled disclosures
      - "Routine Disclosure": Statutorily routine (SAST Reg 29/31, Dividend TDS, share certs, newspaper)
    """
    clean_desc = (desc or "").strip()
    clean_text = (text or "").strip()
    combined_text = f"{clean_desc} {clean_text}".lower()

    # Priority 0a: Genuine Open Offer / Acquirer Disclosure Exemption check
    is_open_offer = bool(re.search(
        r"\b(open\s+offer|public\s+announcement|detailed\s+public\s+statement|"
        r"draft\s+letter\s+of\s+offer|letter\s+of\s+offer|"
        r"regulation\s+[345]\s*\(\s*[1-4]?\s*\)|regulation\s+18\s*\(\s*[1-4]?\s*\))\b",
        combined_text,
        re.IGNORECASE,
    ))

    # Priority 0b: Routine SAST Reg 29/31 exclusion (when NOT a genuine open offer)
    if not is_open_offer and re.search(
        r"\b(regulation\s+31\s*\(\s*[1-4]\s*\)|regulation\s+29\s*\(\s*[1-3]\s*\)|"
        r"disclosure\s+under\s+regulation\s+31|disclosure\s+under\s+regulation\s+29|"
        r"reg\.\s*31\s*\(\s*[1-4]\s*\)|reg\.\s*29\s*\(\s*[1-3]\s*\)|"
        r"declaration\s+under\s+regulation\s+31|promoter\s+encumbrance|pledge\s+of\s+shares)\b",
        combined_text,
        re.IGNORECASE,
    ):
        return ("NONE", 0, "Routine Disclosure")

    # Priority 0c: Dividend TDS / Tax Deduction Routine Circular Exemption (TRITURBINE fix)
    if re.search(
        r"\b(tax\s+deduction\s+on\s+dividend|tds\s+on\s+dividend|"
        r"deduction\s+of\s+tax\s+at\s+source\s+on\s+dividend|"
        r"intimation\s+on\s+tax\s+deduction|tax\s+deducted\s+at\s+source\s+on\s+dividend|"
        r"communication\s+to\s+shareholders\s*-\s*intimation\s+on\s+tax)\b",
        combined_text,
        re.IGNORECASE,
    ):
        return ("NONE", 0, "Routine Disclosure")

    # Priority 1: Exact / Normalized Routine Desc match
    for rtn_desc, cat_name in ROUTINE_DESC_CATEGORIES.items():
        if rtn_desc.lower() in clean_desc.lower():
            return ("NONE", 0, cat_name)

    # Priority 2a: Routine text patterns
    for pattern, cat_name in ROUTINE_TEXT_PATTERNS:
        if re.search(pattern, combined_text, re.IGNORECASE):
            return ("NONE", 0, cat_name)

    if re.search(r"\b(submission\s+of\s+newspaper|newspaper\s+publication|notice\s+published)\b", combined_text, re.IGNORECASE):
        return ("NONE", 0, "Routine Disclosure")
    if re.search(r"\b(transcript\s+of\s+(?:conference|concall|analyst)|audio\s+recording|video\s+recording)\b", combined_text, re.IGNORECASE):
        return ("NONE", 0, "Routine Disclosure")

    # Priority 2b: Credit Rating Sub-categorization
    if "credit rating" in clean_desc.lower() or re.search(r"\b(crisil|icra|care\s+ratings?|india\s+ratings?|infomerics|acuite)\b", combined_text, re.IGNORECASE):
        if re.search(r"\b(upgrade|upgraded|up-grade|revision\s+upwards?|revised\s+upwards?|assigned\s+(?:a\s+)?(?:new\s+)?rating|assignment\s+of\s+rating)\b", combined_text, re.IGNORECASE):
            return ("CATALYST", 1, "Credit Rating (Upgrade)")
        elif re.search(r"\b(downgrade|downgraded|down-grade|revision\s+downwards?|revised\s+downwards?)\b", combined_text, re.IGNORECASE):
            return ("CATALYST", 0, "Credit Rating (Downgrade)")
        elif re.search(r"\b(reaffirm|re-affirm|reaffirmed|re-affirmed|revalidated|withdrawal|withdrawn|stable\s+outlook)\b", combined_text, re.IGNORECASE):
            return ("NONE", 0, "Credit Rating (Reaffirmation)")
        else:
            return ("NONE", 0, "Credit Rating (Other)")

    # Priority 2c: Order Win (Positive Unscheduled-Material)
    if any(k in clean_desc.lower() for k in ["award of order", "order / contract"]) or re.search(
        r"\b(order\s+win|award\s+of\s+contract|signs?\s+contract|bags?\s+(?:new\s+)?orders?|"
        r"secures?\s+(?:export\s+|new\s+)?orders?|receives?\s+(?:new\s+)?orders?|letter\s+of\s+award|"
        r"contract\s+with|entered\s+into\s+(?:a\s+)?contract|construction\s+and\s+sale\s+of|"
        r"award\s+of\s+(?:contract|order)|commercial\s+contract|signs?\s+ppa)\b",
        combined_text,
        re.IGNORECASE,
    ):
        return ("CATALYST", 1, "Order Win")

    # Priority 2d: Production Commencement (Positive Unscheduled-Material)
    if any(k in clean_desc.lower() for k in ["commercial production", "commencement of commercial"]) or re.search(
        r"\b(commencement\s+of\s+commercial\s+production|commercial\s+production|"
        r"operationalization\s+of\s+facility|plant\s+commissioning|capacity\s+commissioning)\b",
        combined_text,
        re.IGNORECASE,
    ):
        return ("CATALYST", 1, "Production Commencement")

    # Priority 2e: Acquisition / M&A Sub-categorization
    if is_open_offer or any(k in clean_desc.lower() for k in ["acquisition", "amalgamation", "merger", "takeover", "disinvestment", "diversification/disinvestment"]) or re.search(
        r"\b(acqui(?:re[ds]?|sition)|amalgamation|merger|takeover|open\s+offer)\b",
        combined_text,
        re.IGNORECASE,
    ):
        # Disinvestment / Sale check (check clean_text for disinvestment even if filed under Acquisition desc)
        if re.search(
            r"\b(divest(?:ed|ment|ing)?|disinvest(?:ed|ment|ing)?|slump\s+sale|sale\s+of\s+(?:a\s+)?(?:subsidiary|division|business|manufacturing|shares?|stake)|stake\s+sale|share\s+sale)\b",
            clean_text if clean_text else combined_text,
            re.IGNORECASE,
        ) and not re.search(r"\b(agreement\s+to\s+acquire|acquires?\b|completed\s+acquisition)\b", clean_text, re.IGNORECASE):
            return ("CATALYST", 0, "Disinvestment")

        # Intra-group / Subsidiary investment / JV check
        if re.search(
            r"\b(wholly\s+owned\s+subsidiary|intra-group|step-down\s+subsidiary|incorporation\s+of\s+(?:a\s+)?subsidiary|investment\s+in\s+subsidiary|joint\s+venture|formation\s+of\s+(?:a\s+)?jv)\b",
            combined_text,
            re.IGNORECASE,
        ) and not re.search(r"\b(third[- ]party|independent\s+entity|agreement\s+to\s+acquire)\b", clean_text, re.IGNORECASE):
            return ("CATALYST", 0, "Acquisition (Intra-Group/JV)")

        return ("CATALYST", 1, "Acquisition (Third-Party)")

    # Priority 2f: Regulatory Approval (Positive Unscheduled-Material)
    if re.search(
        r"\b(usfda|establishment\s+inspection|eir\s+with\s+vai|regulatory\s+approval|patent\s+grant|product\s+approval)\b",
        combined_text,
        re.IGNORECASE,
    ):
        return ("CATALYST", 1, "Regulatory Approval")

    # Priority 2g: Fund Raising (Separate Bucket: is_material = 0 for primary positive)
    if any(k in clean_desc.lower() for k in ["fund raising", "preferential issue", "rights issue", "qualified institutions placement"]) or re.search(
        r"\b(fund\s+rais(?:ing|e)|qip|preferential\s+(?:issue|allotment)|rights\s+issue|commercial\s+paper|ncd\s+issu|warrants?\s+allotment)\b",
        combined_text,
        re.IGNORECASE,
    ):
        return ("CATALYST", 0, "Fund Raising")

    # Priority 2h: Scheduled Outcomes (Board Meeting / Financial Results: is_material = 0 for primary)
    if any(k in clean_desc.lower() for k in ["financial results", "financial result", "board meeting", "outcome of board meeting"]) or re.search(
        r"\b(financial\s+results?|quarterly\s+results?|q[1-4]\s+results?|limited\s+review|annual\s+results?|"
        r"board\s+meeting|outcome\s+of\s+board|dividend|bonus\s+issue|stock\s+split|buyback)\b",
        combined_text,
        re.IGNORECASE,
    ):
        return ("CATALYST", 0, "Board Meeting" if "board" in combined_text or "dividend" in combined_text else "Financial Results")

    # Priority 2i: Regulatory Action / Demand (Negative: is_material = 0 for primary positive)
    if any(k in clean_desc.lower() for k in ["action(s) initiated or orders passed", "regulatory action"]) or re.search(
        r"\b(penalty\s+imposed|show\s+cause\s+notice|customs\s+demand|gst\s+demand|income\s+tax\s+demand|search\s+and\s+seizure)\b",
        combined_text,
        re.IGNORECASE,
    ):
        return ("CATALYST", 0, "Regulatory Action")

    # Priority 3: Fallback classification
    if any(k in combined_text for k in ["update", "action", "order passed", "launch", "subsidiary", "intimation"]):
        return ("UNCLEAR", 0, "General Update")

    if not clean_desc and not clean_text:
        return ("NONE", 0, "No Disclosure")

    return ("UNCLEAR", 0, "Unclassified")



def classify_catalyst(desc: Optional[str] = None,
                      text: Optional[str] = None,
                      source: str = "filing",
                      url: Optional[str] = None,
                      parse_pdf: bool = True,
                      fetch_remote_pdf: bool = True,
                      cache_only_pdf: bool = False) -> Tuple[str, int, str]:
    """
    Unified classifier for corporate filings and news headlines.
    Rule Sequence:
      1. Priority 0: Explicit statutory routine exemptions (SAST 31/29).
      2. Priority 1: Exact / normalized exchange 'desc' category matching.
      3. Priority 2: Text pattern rules on desc + attchmntText.
      4. Priority 2b: If status is UNCLEAR on a generic category, check first-page PDF text (cached, when parse_pdf=True).
      5. Output 3-valued catalyst state ("CATALYST" | "UNCLEAR" | "NONE"),
         materiality flag (1 | 0), and normalized category name.
    """
    clean_desc = (desc or "").strip()
    clean_text = (text or "").strip()
    combined_text = f"{clean_desc} {clean_text}".lower()

    # Priority 0: Explicit Statutory Routine Exemptions (e.g. SAST Reg 31(4) / Reg 29 filed under 'Acquisition')
    if re.search(
        r"\b(regulation\s+31\s*\(\s*[1-4]\s*\)|regulation\s+29\s*\(\s*[1-3]\s*\)|"
        r"disclosure\s+under\s+regulation\s+31|disclosure\s+under\s+regulation\s+29|"
        r"disclosure\s+under\s+sebi\s+takeover|sebi\s+takeover\s+regulations?|"
        r"sebi\s+sast\s+regulations?|takeover\s+regulations?|"
        r"reg\.\s*31\s*\(\s*[1-4]\s*\)|reg\.\s*29\s*\(\s*[1-3]\s*\)|declaration\s+under\s+regulation\s+31)",
        combined_text,
        re.IGNORECASE,
    ):
        return ("NONE", 0, "Routine Disclosure")

    # Priority 1: Exact / Normalized Desc match
    for mat_desc, cat_name in MATERIAL_DESC_CATEGORIES.items():
        if mat_desc.lower() in clean_desc.lower():
            return ("CATALYST", 1, cat_name)

    for rtn_desc, cat_name in ROUTINE_DESC_CATEGORIES.items():
        if rtn_desc.lower() in clean_desc.lower():
            return ("NONE", 0, cat_name)

    # Priority 2: Text pattern matching for ambiguous descriptions or news
    # Check routine disclosures first (e.g. trading window closure mentioning "results")
    for pattern, cat_name in ROUTINE_TEXT_PATTERNS:
        if re.search(pattern, combined_text, re.IGNORECASE):
            return ("NONE", 0, cat_name)

    for pattern, cat_name in MATERIAL_TEXT_PATTERNS:
        if re.search(pattern, combined_text, re.IGNORECASE):
            return ("CATALYST", 1, cat_name)

    # Priority 2b: First-page PDF inspection for generic categories with attached PDF (opt-in parse_pdf)
    generic_descs = [
        "disclosure of material issue",
        "action(s) taken or orders passed",
        "action(s) initiated or orders passed",
        "updates",
        "general updates",
        "general",
        "intimation",
        "announcement",
    ]
    if parse_pdf and url and any(g in clean_desc.lower() for g in generic_descs):
        if cache_only_pdf:
            cache = _load_pdf_text_cache()
            if url in cache:
                pdf_text = cache[url]
            else:
                PDF_CACHE_MISSES.append({"desc": clean_desc, "url": url})
                logger.warning("PDF cache miss in cache-only mode for URL %s (desc: %s)", url, clean_desc)
                pdf_text = ""
        else:
            pdf_text = extract_pdf_first_page_text(url, fetch_remote=fetch_remote_pdf)

        if pdf_text:
            pdf_combined = f"{clean_desc} {pdf_text}".lower()
            for pattern, cat_name in ROUTINE_TEXT_PATTERNS:
                if re.search(pattern, pdf_combined, re.IGNORECASE):
                    return ("NONE", 0, cat_name)
            for pattern, cat_name in MATERIAL_TEXT_PATTERNS:
                if re.search(pattern, pdf_combined, re.IGNORECASE):
                    return ("CATALYST", 1, cat_name)

    # Priority 3: Fallback classification
    if any(k in combined_text for k in ["update", "action", "order passed", "launch", "subsidiary", "intimation"]):
        return ("UNCLEAR", 0, "General Update")

    if not clean_desc and not clean_text:
        return ("NONE", 0, "No Disclosure")

    return ("UNCLEAR", 0, "Unclassified")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Exchange Filings Ingestion (NSE Primary + BSE Fallback)
# ─────────────────────────────────────────────────────────────────────────────

def parse_filing_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse various exchange datetime formats into a datetime object."""
    if not dt_str:
        return None
    s = dt_str.strip()
    formats = [
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y %H:%M",
        "%d-%b-%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def fetch_nse_announcements(symbol: str, from_date: date, to_date: date) -> List[Dict[str, Any]]:
    """Fetch corporate announcements from NSE public API with rate throttling and caching."""
    from_str = from_date.strftime("%d-%m-%Y")
    to_str = to_date.strftime("%d-%m-%Y")
    cache_key = (symbol, from_str, to_str)
    if cache_key in _FILINGS_CACHE:
        return _FILINGS_CACHE[cache_key]

    url = (
        f"https://www.nseindia.com/api/corporate-announcements?"
        f"index=equities&symbol={symbol}&from_date={from_str}&to_date={to_str}"
    )
    session = get_nse_session()

    for attempt in range(1, REQUEST_MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code in (401, 403):
                # Cookie session refresh
                try:
                    session.get("https://www.nseindia.com", timeout=REQUEST_TIMEOUT)
                    resp = session.get(url, timeout=REQUEST_TIMEOUT)
                except Exception:
                    pass

            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("data", [])
                announcements = []
                for item in items:
                    raw_dt = item.get("sort_date") or item.get("an_dt") or item.get("exchdisstime")
                    desc = item.get("desc", "")
                    text = item.get("attchmntText", "")
                    att_url = item.get("attchmntFile", "")
                    state, is_mat, cat = classify_catalyst(desc=desc, text=text, source="filing", url=att_url)
                    announcements.append({
                        "symbol": symbol,
                        "date_str": raw_dt,
                        "dt": parse_filing_datetime(raw_dt),
                        "desc": desc,
                        "text": text,
                        "url": att_url,
                        "catalyst_state": state,
                        "is_material": is_mat,
                        "category": cat,
                        "source": "NSE",
                    })
                _FILINGS_CACHE[cache_key] = announcements
                time.sleep(0.15)  # Rate throttling
                return announcements
            elif resp.status_code == 404:
                _FILINGS_CACHE[cache_key] = []
                return []
        except Exception as exc:
            logger.debug("NSE announcement attempt %d for %s failed: %s", attempt, symbol, exc)
            time.sleep(REQUEST_BACKOFF_FACTOR ** attempt)

    _FILINGS_CACHE[cache_key] = []
    return []


def fetch_bse_announcements(symbol: str, from_date: date, to_date: date) -> List[Dict[str, Any]]:
    """Fetch corporate announcements from BSE API fallback using BSE scrip code."""
    scrip_code = get_bse_scrip_code(symbol)
    if not scrip_code:
        logger.debug("No BSE scrip code mapped for %s. Skipping BSE fallback.", symbol)
        return []

    from_str = from_date.strftime("%Y%m%d")
    to_str = to_date.strftime("%Y%m%d")
    url = (
        f"https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?"
        f"pageno=1&strCat=-1&strPrevDate={from_str}&strScrip={scrip_code}&strSearch=P&strToDate={to_str}&strType=C"
    )
    session = get_bse_session()

    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            table = data.get("Table", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            announcements = []
            for item in table:
                raw_dt = item.get("NEWS_DT") or item.get("DT_TM")
                desc = item.get("CATEGORYNAME", "")
                text = item.get("HEADLINE", "")
                bse_att = item.get("ATTACHMENTNAME", "")
                state, is_mat, cat = classify_catalyst(desc=desc, text=text, source="filing", url=bse_att)
                announcements.append({
                    "symbol": symbol,
                    "date_str": raw_dt,
                    "dt": parse_filing_datetime(raw_dt),
                    "desc": desc,
                    "text": text,
                    "url": bse_att,
                    "catalyst_state": state,
                    "is_material": is_mat,
                    "category": cat,
                    "source": "BSE",
                })
            time.sleep(0.15)
            return announcements
    except Exception as exc:
        logger.debug("BSE fallback announcement query failed for %s (%s): %s", symbol, scrip_code, exc)

    return []


def fetch_corporate_filings(symbol: str,
                            from_date: date,
                            to_date: date,
                            use_fallback: bool = True) -> List[Dict[str, Any]]:
    """
    Fetch corporate filings for a symbol over a date range.
    Primary: NSE API.
    Fallback: BSE API if NSE returns empty and use_fallback is True.
    """
    results = fetch_nse_announcements(symbol, from_date, to_date)
    if not results and use_fallback:
        results = fetch_bse_announcements(symbol, from_date, to_date)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 3. Pre-Announcement Radar Check (7-Day Event Calendar)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_event_calendar(from_date: Optional[date] = None,
                         to_date: Optional[date] = None) -> List[Dict[str, Any]]:
    """
    Fetch upcoming corporate events (e.g. board meetings for results/dividends)
    over a forward window (default: today through today + 7 days).
    """
    start_d = from_date or date.today()
    end_d = to_date or (start_d + timedelta(days=7))

    from_str = start_d.strftime("%d-%m-%Y")
    to_str = end_d.strftime("%d-%m-%Y")
    cache_key = (from_str, to_str)
    if cache_key in _EVENT_CALENDAR_CACHE:
        return _EVENT_CALENDAR_CACHE[cache_key]

    url = (
        f"https://www.nseindia.com/api/event-calendar?"
        f"index=equities&from_date={from_str}&to_date={to_str}"
    )
    session = get_nse_session()

    for attempt in range(1, REQUEST_MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("data", [])
                events = []
                for item in items:
                    events.append({
                        "symbol": item.get("symbol", ""),
                        "company": item.get("company", ""),
                        "purpose": item.get("purpose", ""),
                        "event_date": item.get("date", ""),
                        "bm_desc": item.get("bm_desc", ""),
                    })
                _EVENT_CALENDAR_CACHE[cache_key] = events
                return events
            elif resp.status_code in (401, 403):
                session.get("https://www.nseindia.com", timeout=REQUEST_TIMEOUT)
        except Exception as exc:
            logger.debug("Event calendar attempt %d failed: %s", attempt, exc)
            time.sleep(REQUEST_BACKOFF_FACTOR ** attempt)

    _EVENT_CALENDAR_CACHE[cache_key] = []
    return []


def check_pre_announcement_radar(symbol: str, days_ahead: int = 7) -> Optional[Dict[str, Any]]:
    """
    Check if a stock has an upcoming board meeting or event scheduled in next N days.
    """
    events = fetch_event_calendar(date.today(), date.today() + timedelta(days=days_ahead))
    for ev in events:
        if ev.get("symbol", "").upper() == symbol.upper():
            return {
                "symbol": symbol,
                "event_date": ev.get("event_date") or ev.get("date", ""),
                "purpose": ev.get("purpose", ""),
                "bm_desc": ev.get("bm_desc", ""),
            }
    return None
