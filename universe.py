"""
Stock Universe Module
Loads and filters the NIFTY 500 stock list to return stocks
ranked 210–500 by market capitalization.
"""

import csv
import os
import sys
import time
import pandas as pd
import yfinance as yf

from config import UNIVERSE_FILE, RANK_START, RANK_END, BATCH_SIZE, BATCH_DELAY


# ── Hardcoded NIFTY 500 stock symbols ──────────────────────────────────────
# This is a comprehensive list. In practice, you should periodically update
# this from niftyindices.com → NIFTY 500 → Download CSV.
# The CSV should have columns: Company Name, Industry, Symbol
# Ranked by market-cap (row 1 = largest).

def load_universe() -> pd.DataFrame:
    """
    Load stock universe from the local CSV file.
    Returns a DataFrame with columns: rank, symbol, company, industry, yf_symbol
    Only returns stocks within RANK_START to RANK_END.
    """
    if not os.path.exists(UNIVERSE_FILE):
        print(f"[ERROR] Universe file not found: {UNIVERSE_FILE}")
        print("        Please download the NIFTY 500 CSV from niftyindices.com")
        print("        and place it at the above path.")
        print(f"\n        Or run: python universe.py --download")
        sys.exit(1)

    df = pd.read_csv(UNIVERSE_FILE)

    # Normalize column names (NSE CSVs sometimes have varied headers)
    col_map = {}
    for col in df.columns:
        cl = col.strip().lower()
        if "symbol" in cl:
            col_map[col] = "symbol"
        elif "company" in cl or "name" in cl:
            col_map[col] = "company"
        elif "industry" in cl or "sector" in cl:
            col_map[col] = "industry"
        elif "rank" in cl:
            col_map[col] = "rank"

    df = df.rename(columns=col_map)

    # Ensure required columns exist
    required = ["symbol", "company"]
    for r in required:
        if r not in df.columns:
            print(f"[ERROR] CSV missing required column: '{r}'")
            print(f"        Available columns: {list(df.columns)}")
            sys.exit(1)

    # Add or preserve rank (1-indexed, based on market-cap order)
    if "rank" not in df.columns:
        df["rank"] = range(1, len(df) + 1)
    else:
        fallback_ranks = pd.Series(range(1, len(df) + 1), index=df.index)
        df["rank"] = pd.to_numeric(df["rank"], errors="coerce").fillna(fallback_ranks).astype(int)

    # Filter by rank
    df = df[(df["rank"] >= RANK_START) & (df["rank"] <= RANK_END)].copy()

    # Create yfinance-compatible symbol
    df["yf_symbol"] = df["symbol"].str.strip() + ".NS"

    # Clean up
    df["symbol"] = df["symbol"].str.strip()
    df["company"] = df["company"].str.strip()
    if "industry" not in df.columns:
        df["industry"] = "Unknown"
    else:
        df["industry"] = df["industry"].fillna("Unknown").str.strip()

    df = df[["rank", "symbol", "company", "industry", "yf_symbol"]].reset_index(drop=True)

    print(f"[Universe] Loaded {len(df)} stocks (rank {RANK_START}–{RANK_END})")
    return df


def download_nifty500_list():
    """
    Attempt to download NIFTY 100, Midcap 150, and Smallcap 250 lists from NSE India
    and combine them in market-cap order (Large -> Mid -> Small).
    Falls back to single NIFTY 500 download or starter CSV if downloads fail.
    """
    import io
    import urllib.request
    data_dir = os.path.dirname(UNIVERSE_FILE)
    os.makedirs(data_dir, exist_ok=True)

    print("[Universe] Downloading market-cap segmented lists from NSE India...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/csv,text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/"
    }

    def fetch_index_csv(filename, segment_name):
        url = f"https://archives.nseindia.com/content/indices/{filename}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            df = pd.read_csv(io.BytesIO(response.read()))
            df["Segment"] = segment_name
            return df

    try:
        # Download 3 tiers: Large-cap (1-100), Mid-cap (101-250), Small-cap (251-500)
        n100 = fetch_index_csv("ind_nifty100list.csv", "Large Cap")
        mid150 = fetch_index_csv("ind_niftymidcap150list.csv", "Mid Cap")
        small250 = fetch_index_csv("ind_niftysmallcap250list.csv", "Small Cap")

        combined = pd.concat([n100, mid150, small250], ignore_index=True)
        # Add market-cap order rank
        combined.insert(0, "Rank", range(1, len(combined) + 1))
        combined.to_csv(UNIVERSE_FILE, index=False, encoding="utf-8")
        print(f"[Universe] ✅ Downloaded and structured {len(combined)} stocks (ranks 1–{len(combined)}) to {UNIVERSE_FILE}")
        return True

    except Exception as e:
        print(f"[Universe] ⚠️  Segmented download failed: {e}. Trying full NIFTY 500 list...")
        try:
            url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                content = response.read().decode("utf-8")

            with open(UNIVERSE_FILE, "w", newline="", encoding="utf-8") as f:
                f.write(content)

            print(f"[Universe] ✅ Downloaded NIFTY 500 list to {UNIVERSE_FILE}")
            return True
        except Exception as e2:
            print(f"[Universe] ⚠️  Download failed: {e2}")
            print("[Universe] Creating starter CSV with sample stocks...")
            _create_starter_csv()
            return False


def _create_starter_csv():
    """
    Create a starter CSV with a representative set of mid/small-cap stocks.
    This is a fallback — the user should replace with the actual NIFTY 500 list.
    """
    data_dir = os.path.dirname(UNIVERSE_FILE)
    os.makedirs(data_dir, exist_ok=True)

    # Representative sample of stocks that would appear in ranks 210-500
    # of NIFTY 500 (midcap to smallcap range). This is NOT exhaustive.
    # Rows are ordered roughly by market cap (largest first) to simulate ranking.
    # The first 209 rows are large/mid-cap placeholder entries.
    stocks = []

    # Rows 1-209: Large-cap placeholders (won't be used due to rank filter)
    top_200 = [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR",
        "BHARTIARTL", "SBIN", "BAJFINANCE", "ITC", "LICI", "LT", "KOTAKBANK",
        "HCLTECH", "AXISBANK", "TITAN", "ADANIENT", "ASIANPAINT", "MARUTI",
        "SUNPHARMA", "NTPC", "TATASTEEL", "ULTRACEMCO", "BAJAJFINSV",
        "WIPRO", "ONGC", "NESTLEIND", "JSWSTEEL", "POWERGRID", "M&M",
        "COALINDIA", "LTIM", "TATAMOTORS", "ADANIPORTS", "HDFCLIFE",
        "TECHM", "SBILIFE", "GRASIM", "DIVISLAB", "DRREDDY", "CIPLA",
        "BPCL", "BRITANNIA", "BAJAJ-AUTO", "INDUSINDBK", "EICHERMOT",
        "HEROMOTOCO", "APOLLOHOSP", "DABUR", "TATACONSUM", "HINDALCO",
        "GODREJCP", "PIDILITIND", "SHREECEM", "AMBUJACEM", "HAVELLS",
        "BERGEPAINT", "MARICO", "HDFCAMC", "DLF", "SBICARD", "NAUKRI",
        "ADANIGREEN", "SIEMENS", "TRENT", "VEDL", "INDIGO", "IOC",
        "BANKBARODA", "ICICIPRULI", "ZYDUSLIFE", "MAXHEALTH", "TORNTPHARM",
        "CANBK", "HINDPETRO", "MUTHOOTFIN", "CHOLAFIN", "TATAPOWER",
        "GAIL", "IDBI", "NMDC", "PERSISTENT", "PIIND", "COFORGE", "SAIL",
        "DMART", "IRCTC", "SUPREMEIND", "CONCOR", "OFSS", "NIACL",
        "INDUSTOWER", "LTF", "UPL", "POLYCAB", "LUPIN", "AUBANK",
        "MFSL", "PEL", "RECLTD", "LODHA", "TATAELXSI", "JUBLFOOD",
        "ABFRL", "ABCAPITAL", "AUROPHARMA", "VOLTAS", "GMRINFRA",
        "ALKEM", "OBEROIRLTY", "ASTRAL", "PRESTIGE", "YESBANK",
        "SONATSOFTW", "LLOYDS", "MRF", "MOTHERSON", "ACC",
        "IDFCFIRSTB", "PNB", "CUMMINSIND", "BHEL", "PAGEIND",
        "LTTS", "FEDERALBNK", "SUNDARMFIN", "BEL", "NYKAA", "ICICIGI",
        "GICRE", "BIOCON", "PETRONET", "NHPC", "PHOENIXLTD", "MPHASIS",
        "ESCORTS", "APLAPOLLO", "IPCALAB", "TATACOMM", "NATCOPHARM",
        "BALKRISIND", "METROPOLIS", "CROMPTON", "THERMAX", "CUB",
        "LALPATHLAB", "HONAUT", "BANKINDIA", "TIINDIA", "LINDEINDIA",
        "UNIONBANK", "COROMANDEL", "KEI", "RVNL", "SOLARINDS",
        "SCHAEFFLER", "3MINDIA", "KAJARIACER", "RATNAMANI", "SUNTV",
        "DALBHARAT", "MAHABANK", "JKCEMENT", "SUMICHEM", "BAYERCROP",
        "IIFL", "DEEPAKNTR", "CLEAN", "PGHH", "EMAMILTD", "WHIRLPOOL",
        "ZEEL", "LICHSGFIN", "AARTIIND", "KPITTECH", "CENTRALBK",
        "MANAPPURAM", "FORTIS", "GMMPFAUDLR", "NAM-INDIA", "JSWENERGY",
        "GODREJPROP", "SUNDRMFAST", "ASTERDM", "ANGELONE", "EIDPARRY",
        "TATACHEM", "GLENMARK", "SJVN", "NLCINDIA", "BSOFT",
        "IRFC", "HINDCOPPER", "INDIANB", "FINEORG", "CARBORUNIV",
        "KANSAINER", "RELAXO", "MGL", "IGL", "MSUMI",
    ]
    for i, sym in enumerate(top_200):
        stocks.append({
            "Company Name": sym.replace("&", " and "),
            "Industry": "Large Cap",
            "Symbol": sym
        })

    # Rows 210-500: Midcap / Smallcap stocks (THESE are our target universe)
    mid_small = [
        ("AFFLE", "Affle India", "IT - Software"),
        ("APTUS", "Aptus Value Housing Finance", "Finance - NBFC"),
        ("ATUL", "Atul Ltd", "Chemicals"),
        ("BASF", "BASF India", "Chemicals"),
        ("BATAINDIA", "Bata India", "Consumer - Footwear"),
        ("BDL", "Bharat Dynamics", "Defence"),
        ("BEML", "BEML Ltd", "Capital Goods"),
        ("BSE", "BSE Ltd", "Exchange"),
        ("CANFINHOME", "Can Fin Homes", "Finance - Housing"),
        ("CASTROLIND", "Castrol India", "Oil & Gas"),
        ("CDSL", "Central Depository Services", "Exchange"),
        ("CENTURYTEX", "Century Textiles", "Textiles"),
        ("CESC", "CESC Ltd", "Power"),
        ("CHAMBLFERT", "Chambal Fertilisers", "Fertilizers"),
        ("CHEMPLASTS", "Chemplast Sanmar", "Chemicals"),
        ("COCHINSHIP", "Cochin Shipyard", "Defence"),
        ("CRAFTSMAN", "Craftsman Automation", "Capital Goods"),
        ("CYIENT", "Cyient Ltd", "IT - Services"),
        ("DCMSHRIRAM", "DCM Shriram", "Chemicals"),
        ("DEVYANI", "Devyani International", "QSR"),
        ("ELGIEQUIP", "Elgi Equipments", "Capital Goods"),
        ("EQUITASBNK", "Equitas Small Finance Bank", "Banking"),
        ("EXIDEIND", "Exide Industries", "Auto Components"),
        ("FDC", "FDC Ltd", "Pharma"),
        ("FINCABLES", "Finolex Cables", "Cables"),
        ("FINPIPE", "Finolex Industries", "Pipes"),
        ("FLUOROCHEM", "Gujarat Fluorochemicals", "Chemicals"),
        ("GESHIP", "Great Eastern Shipping", "Shipping"),
        ("GILLETTE", "Gillette India", "FMCG"),
        ("GLAXO", "GSK Pharma", "Pharma"),
        ("GNFC", "GNFC Ltd", "Fertilizers"),
        ("GPPL", "Gujarat Pipavav Port", "Logistics"),
        ("GRINDWELL", "Grindwell Norton", "Abrasives"),
        ("GSFC", "GSFC Ltd", "Fertilizers"),
        ("GSPL", "Gujarat State Petronet", "Oil & Gas"),
        ("GUJGASLTD", "Gujarat Gas", "Oil & Gas"),
        ("HAPPSTMNDS", "Happiest Minds", "IT - Software"),
        ("HBLPOWER", "HBL Power Systems", "Power Equipment"),
        ("HGS", "Hinduja Global Solutions", "IT - BPO"),
        ("IIFLWAM", "IIFL Wealth Management", "Finance"),
        ("INDHOTEL", "Indian Hotels (Taj)", "Hotels"),
        ("IONEXCHANG", "Ion Exchange", "Environment"),
        ("IRB", "IRB Infrastructure", "Infrastructure"),
        ("IRCON", "Ircon International", "Infrastructure"),
        ("ITI", "ITI Ltd", "Telecom Equipment"),
        ("J&KBANK", "J&K Bank", "Banking"),
        ("JBCHEPHARM", "JB Chemicals", "Pharma"),
        ("JINDALSAW", "Jindal SAW", "Steel - Pipes"),
        ("JKLAKSHMI", "JK Lakshmi Cement", "Cement"),
        ("JMFINANCIL", "JM Financial", "Finance"),
        ("JSL", "Jindal Stainless", "Steel"),
        ("JUBLINGREA", "Jubilant Ingrevia", "Chemicals"),
        ("KALPATPOWR", "Kalpataru Projects", "Infrastructure"),
        ("KALYANKJIL", "Kalyan Jewellers", "Jewellery"),
        ("KEC", "KEC International", "Infrastructure"),
        ("KRBL", "KRBL Ltd", "FMCG - Agri"),
        ("KSCL", "Kaveri Seed Company", "Agriculture"),
        ("KSB", "KSB Ltd", "Pumps"),
        ("LATENTVIEW", "Latent View Analytics", "IT - Analytics"),
        ("LAURUSLABS", "Laurus Labs", "Pharma - API"),
        ("LEMONTREE", "Lemon Tree Hotels", "Hotels"),
        ("LXCHEM", "Laxmi Organic Industries", "Chemicals"),
        ("MAHLIFE", "Mahindra Lifespace", "Real Estate"),
        ("MAHSEAMLES", "Maharashtra Seamless", "Steel - Pipes"),
        ("MAPMYINDIA", "CE Info Systems", "IT - Maps"),
        ("MASTEK", "Mastek Ltd", "IT - Software"),
        ("MAXHEALTH", "Max Healthcare", "Healthcare"),
        ("MAZDOCK", "Mazagon Dock Shipbuilders", "Defence"),
        ("MCX", "MCX India", "Exchange"),
        ("MEDANTA", "Global Health (Medanta)", "Healthcare"),
        ("MMTC", "MMTC Ltd", "Trading"),
        ("MOIL", "MOIL Ltd", "Mining"),
        ("MRPL", "MRPL Ltd", "Refineries"),
        ("MSTCLTD", "MSTC Ltd", "Trading"),
        ("NATIONALUM", "National Aluminium", "Mining"),
        ("NBCC", "NBCC India", "Infrastructure"),
        ("NCC", "NCC Ltd", "Infrastructure"),
        ("NESCO", "Nesco Ltd", "Real Estate"),
        ("NETWORK18", "Network18 Media", "Media"),
        ("NH", "Narayana Hrudayalaya", "Healthcare"),
        ("OLECTRA", "Olectra Greentech", "Electric Vehicles"),
        ("PNBHOUSING", "PNB Housing Finance", "Finance - Housing"),
        ("POLYMED", "Poly Medicure", "Healthcare"),
        ("POWERINDIA", "Hitachi Energy India", "Power Equipment"),
        ("PPLPHARMA", "Piramal Pharma", "Pharma"),
        ("PRINCEPIPE", "Prince Pipes", "Pipes"),
        ("PVRINOX", "PVR INOX", "Entertainment"),
        ("RADICO", "Radico Khaitan", "Liquor"),
        ("RAILTEL", "RailTel Corporation", "Telecom"),
        ("RAJESHEXPO", "Rajesh Exports", "Gold - Exports"),
        ("RAYMOND", "Raymond Ltd", "Textiles"),
        ("REDINGTON", "Redington Ltd", "IT - Distribution"),
        ("ROUTE", "Route Mobile", "Cloud Communications"),
        ("RVNL", "Rail Vikas Nigam", "Infrastructure"),
        ("SAPPHIRE", "Sapphire Foods India", "QSR"),
        ("SATIN", "Satin Creditcare", "Finance - MFI"),
        ("SFL", "Sheela Foam", "Consumer"),
        ("SHILPAMED", "Shilpa Medicare", "Pharma"),
        ("SHOPERSTOP", "Shoppers Stop", "Retail"),
        ("SHYAMMETL", "Shyam Metalics", "Steel"),
        ("SOBHA", "Sobha Ltd", "Real Estate"),
        ("SPARC", "Sun Pharma Advanced", "Pharma"),
        ("STARHEALTH", "Star Health Insurance", "Insurance"),
        ("SUVENPHAR", "Suven Pharma", "Pharma"),
        ("SWANENERGY", "Swan Energy", "Diversified"),
        ("SYRMA", "Syrma SGS Technology", "Electronics - EMS"),
        ("TANLA", "Tanla Platforms", "Cloud Communications"),
        ("TATAINVEST", "Tata Investment Corp", "Finance - Investment"),
        ("TCNSBRANDS", "TCNS Clothing", "Fashion"),
        ("TEAMLEASE", "TeamLease Services", "Staffing"),
        ("TECHNOE", "Techno Electric", "Power"),
        ("TITAGARH", "Titagarh Rail Systems", "Railways"),
        ("TRIVENI", "Triveni Engineering", "Sugar"),
        ("TRVENT", "Triveni Turbine", "Capital Goods"),
        ("TTML", "Tata Teleservices", "Telecom"),
        ("TV18BRDCST", "TV18 Broadcast", "Media"),
        ("UTIAMC", "UTI AMC", "Asset Management"),
        ("VAIBHAVGBL", "Vaibhav Global", "Retail - Jewellery"),
        ("VGUARD", "V-Guard Industries", "Consumer Electricals"),
        ("VINATIORGA", "Vinati Organics", "Chemicals"),
        ("VSTIND", "VST Industries", "Tobacco"),
        ("WELCORP", "Welspun Corp", "Steel - Pipes"),
        ("WELSPUNLIV", "Welspun Living", "Textiles - Home"),
        ("ZENSARTECH", "Zensar Technologies", "IT - Software"),
        ("ZFCVINDIA", "ZF Commercial Vehicles", "Auto Components"),
        ("ZOMATO", "Zomato Ltd", "Food - Tech"),
        ("AIAENG", "AIA Engineering", "Capital Goods"),
        ("AMARAJABAT", "Amara Raja Energy", "Batteries"),
        ("ANURAS", "Anupam Rasayan", "Chemicals"),
        ("ASTER", "Aster DM Healthcare", "Healthcare"),
        ("BIRLACORPN", "Birla Corporation", "Cement"),
        ("BLUESTARCO", "Blue Star Ltd", "Consumer Durables"),
        ("CAMS", "CAMS Ltd", "Tech - Fintech"),
        ("CEATLTD", "CEAT Ltd", "Tyres"),
        ("CENTBK", "Central Bank of India", "Banking"),
        ("CHALET", "Chalet Hotels", "Hotels"),
        ("CIEINDIA", "CIE Automotive India", "Auto Components"),
        ("DATAPATTNS", "Data Patterns", "Defence - Electronics"),
        ("ECLERX", "eClerx Services", "IT - BPO"),
        ("ENGINERSIN", "Engineers India", "Consulting"),
        ("FACT", "Fertilisers & Chemicals", "Fertilizers"),
        ("GARFIBRES", "Garware Technical Fibres", "Textiles"),
        ("GHCL", "GHCL Ltd", "Chemicals"),
        ("GODFRYPHLP", "Godfrey Phillips", "FMCG"),
        ("GRANULES", "Granules India", "Pharma - API"),
        ("GRSE", "Garden Reach Shipbuilders", "Defence"),
        ("GUJALKALI", "Gujarat Alkalies", "Chemicals"),
        ("HFCL", "HFCL Ltd", "Telecom Equipment"),
        ("HUDCO", "HUDCO Ltd", "Finance - Housing"),
        ("IFCI", "IFCI Ltd", "Finance - DFI"),
        ("JAMNAAUTO", "Jamna Auto Industries", "Auto Components"),
        ("JBMA", "JBM Auto", "Auto Components"),
        ("JKTYRE", "JK Tyre & Industries", "Tyres"),
        ("JYOTHYLAB", "Jyothy Labs", "FMCG"),
        ("KFINTECH", "KFin Technologies", "Tech - Fintech"),
        ("KIRLOSENG", "Kirloskar Oil Engines", "Capital Goods"),
        ("KNRCON", "KNR Constructions", "Infrastructure"),
        ("METROPOLIS", "Metropolis Healthcare", "Diagnostics"),
        ("MTARTECH", "MTAR Technologies", "Precision Engineering"),
        ("MUTHOOTFIN", "Muthoot Finance", "Finance - Gold"),
        ("NAVINFLUOR", "Navin Fluorine", "Chemicals"),
        ("NELCO", "Nelco Ltd", "Telecom"),
        ("ORIENTELEC", "Orient Electric", "Consumer Electricals"),
        ("PCBL", "PCBL Ltd", "Chemicals"),
        ("PFIZER", "Pfizer India", "Pharma - MNC"),
        ("PRAJIND", "Praj Industries", "Capital Goods"),
        ("QUESS", "Quess Corp", "Staffing"),
        ("RBLBANK", "RBL Bank", "Banking"),
        ("ROSSARI", "Rossari Biotech", "Chemicals"),
        ("SCHNEIDER", "Schneider Electric India", "Power Equipment"),
        ("SHRIRAMFIN", "Shriram Finance", "Finance - NBFC"),
        ("SONACOMS", "Sona BLW Precision", "Auto Components"),
        ("SUNTECK", "Sunteck Realty", "Real Estate"),
        ("SUPRIYA", "Supriya Lifescience", "Pharma - API"),
        ("SYMPHONY", "Symphony Ltd", "Consumer Durables"),
        ("TARSONS", "Tarsons Products", "Lab Equipment"),
        ("TATAMETALI", "Tata Metaliks", "Steel"),
        ("THYROCARE", "Thyrocare Technologies", "Diagnostics"),
        ("TIMKEN", "Timken India", "Bearings"),
        ("UCOBANK", "UCO Bank", "Banking"),
        ("UJJIVANSFB", "Ujjivan Small Finance Bank", "Banking"),
        ("VARROC", "Varroc Engineering", "Auto Components"),
        ("VIPIND", "VIP Industries", "Luggage"),
        ("VRLLOG", "VRL Logistics", "Logistics"),
        ("WESTLIFE", "Westlife Foodworld", "QSR"),
        ("WHEELS", "Wheels India", "Auto Components"),
        ("WOCKPHARMA", "Wockhardt Ltd", "Pharma"),
        ("AETHER", "Aether Industries", "Chemicals"),
        ("ALLCARGO", "Allcargo Logistics", "Logistics"),
        ("AVALON", "Avalon Technologies", "Electronics - EMS"),
        ("AWL", "Adani Wilmar", "FMCG - Edible Oil"),
        ("BECTORFOOD", "Mrs Bectors Food", "FMCG - Bakery"),
        ("BIKAJI", "Bikaji Foods", "FMCG - Snacks"),
        ("CAMPUS", "Campus Activewear", "Footwear"),
        ("CCL", "CCL Products India", "Coffee"),
        ("CELLO", "Cello World", "Consumer Products"),
        ("CONCORDBIO", "Concord Biotech", "Pharma"),
        ("DOMS", "DOMS Industries", "Stationery"),
        ("EASEMYTRIP", "Easy Trip Planners", "Travel"),
        ("ETHOSLTD", "Ethos Ltd", "Luxury - Watches"),
        ("FIVESTAR", "Five Star Business Finance", "Finance - NBFC"),
        ("GALAXYSURF", "Galaxy Surfactants", "Chemicals"),
        ("GATEWAY", "Gateway Distriparks", "Logistics"),
        ("GOCOLORS", "Go Fashion", "Fashion"),
        ("HAPPSTMNDS", "Happiest Minds Tech", "IT - Software"),
        ("HOMEFIRST", "Home First Finance", "Finance - Housing"),
        ("INDIGOPNTS", "Indigo Paints", "Paints"),
        ("ISGEC", "Isgec Heavy Engineering", "Capital Goods"),
        ("JUBLINGREA", "Jubilant Ingrevia", "Chemicals"),
        ("KAYNES", "Kaynes Technology India", "Electronics - EMS"),
        ("KIMS", "Krishna Institute of Medical", "Healthcare"),
        ("KIRLOSBROS", "Kirloskar Brothers", "Pumps"),
        ("LICHSGFIN", "LIC Housing Finance", "Finance - Housing"),
        ("LTFOODS", "LT Foods", "FMCG - Rice"),
        ("LUXIND", "Lux Industries", "Innerwear"),
        ("MAPMYINDIA", "MapMyIndia (CE Info Sys)", "IT - Maps"),
        ("MEDPLUS", "MedPlus Health Services", "Pharmacy Retail"),
        ("NETWEB", "Netweb Technologies", "IT - Hardware"),
        ("PAISALO", "Paisalo Digital", "Finance - NBFC"),
        ("PATELENG", "Patel Engineering", "Infrastructure"),
        ("PGHL", "Procter & Gamble Health", "FMCG - Health"),
        ("RATEGAIN", "RateGain Travel Tech", "Travel - Tech"),
        ("RCF", "Rashtriya Chemicals", "Fertilizers"),
        ("RENUKA", "Shree Renuka Sugars", "Sugar"),
        ("SAFARI", "Safari Industries", "Luggage"),
        ("SAREGAMA", "Saregama India", "Media - Music"),
        ("SWARAJENG", "Swaraj Engines", "Engines"),
        ("TDPOWERSYS", "TD Power Systems", "Power Equipment"),
        ("TIMETECHNO", "Time Technoplast", "Packaging"),
        ("ZYDUSWELL", "Zydus Wellness", "FMCG - Health"),
    ]

    for sym, name, sector in mid_small:
        stocks.append({
            "Company Name": name,
            "Industry": sector,
            "Symbol": sym
        })

    # Write CSV
    data_dir = os.path.dirname(UNIVERSE_FILE)
    os.makedirs(data_dir, exist_ok=True)

    with open(UNIVERSE_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Company Name", "Industry", "Symbol"])
        writer.writeheader()
        writer.writerows(stocks)

    print(f"[Universe] ✅ Starter CSV created at {UNIVERSE_FILE}")
    print(f"           Contains {len(top_200)} large-cap + {len(mid_small)} mid/small-cap entries")
    print(f"           ⚠️  Replace with actual NIFTY 500 list from niftyindices.com")


# ── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stock Universe Manager")
    parser.add_argument("--download", action="store_true",
                        help="Download NIFTY 500 list from NSE (or create starter)")
    parser.add_argument("--show", action="store_true",
                        help="Show loaded universe")
    args = parser.parse_args()

    if args.download:
        success = download_nifty500_list()
        if not success:
            _create_starter_csv()
    elif args.show:
        df = load_universe()
        print(df.to_string(index=False))
    else:
        # Default: try to load, create starter if missing
        if not os.path.exists(UNIVERSE_FILE):
            print("[Universe] No universe file found, creating starter...")
            _create_starter_csv()
        df = load_universe()
        print(f"\nSample (first 5):\n{df.head().to_string(index=False)}")
        print(f"\nSample (last 5):\n{df.tail().to_string(index=False)}")
