import sqlite3
import os
from sec_api import ExtractorApi, QueryApi
from dotenv import load_dotenv

load_dotenv()

#get the key



# --- CONFIGURATION ---
# Get a free API key at https://sec-api.io
SEC_API_KEY = os.getenv('SEC_API_KEY')
DB_PATH = 'data/FinTrac.db'

# 3. Validation Check
if not SEC_API_KEY:
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print("!!! ERROR: SEC_API_KEY not found.                                     !!!")
    print("!!! Please ensure you have a '.env' file with: FRED_API_KEY=your_key  !!!")
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

extractor_api = ExtractorApi(SEC_API_KEY)
query_api = QueryApi(SEC_API_KEY)

# The "Bellwether 10": Representing 10 diverse sectors
BELLWETHERS = {
    "AAPL": "Technology",
    "WMT": "Consumer Retail",
    "JPM": "Financials",
    "CAT": "Industrial/Construction",
    "XOM": "Energy",
    "FDX": "Logistics/Transport",
    "PG":  "Consumer Staples",
    "HD":  "Housing/Home Improvement",
    "F":   "Automotive",
    "GS":  "Investment Banking"
}

def get_latest_filing_url(ticker, form_type="10-K"):
    """Finds the URL for the most recent 10-K or 10-Q."""
    query = {
        "query": f"ticker:{ticker} AND formType:\"{form_type}\"",
        "from": "0", "size": "1", 
        "sort": [{"filedAt": {"order": "desc"}}]
    }
    try:
        response = query_api.get_filings(query)
        if response['filings']:
            return response['filings'][0]['linkToFilingDetails'], response['filings'][0]['filedAt']
    except Exception as e:
        print(f"Query Error for {ticker}: {e}")
    return None, None

def fetch_mda_text(url):
    """
    Extracts Section 7 (MD&A) from a 10-K.
    Note: For 10-Q, the MD&A is usually 'part2item2' or 'item2'.
    """
    try:
        # '7' is the standard item number for MD&A in 10-Ks
        return extractor_api.get_section(url, "7", "text")
    except Exception as e:
        print(f"Extraction Error: {e}")
        return None

def run_sec_pipeline():
    if SEC_API_KEY == 'your_sec_api_key_here':
        print("ERROR: Please set your SEC_API_KEY as an environment variable.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create table for textual analysis
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS corporate_reports (
            ticker TEXT,
            sector TEXT,
            filed_date TEXT,
            report_type TEXT,
            mda_text TEXT
        )
    """)

    for ticker, sector in BELLWETHERS.items():
        print(f"Processing {ticker} ({sector})...")
        url, filed_at = get_latest_filing_url(ticker)
        
        if url:
            mda_content = fetch_mda_text(url)
            if mda_content:
                # Clean up text a bit (basic whitespace)
                clean_text = " ".join(mda_content.split())
                
                cursor.execute("""
                    INSERT INTO corporate_reports (ticker, sector, filed_date, report_type, mda_text)
                    VALUES (?, ?, ?, ?, ?)
                """, (ticker, sector, filed_at, "10-K", clean_text))
                conn.commit()
                print(f"Successfully saved MD&A for {ticker}.")
            else:
                print(f"Failed to extract MD&A for {ticker}.")
        else:
            print(f"No filing found for {ticker}.")

    conn.close()
    print("\nSEC Data Integration Complete.")

if __name__ == "__main__":
    run_sec_pipeline()