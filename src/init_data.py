import pandas as pd
import numpy as np
from fredapi import Fred
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sqlite3
from dotenv import load_dotenv
from datetime import datetime


din = datetime.today().strftime('%Y-%M-%D')
print(din)

# --- CONFIGURATION ---
# 1. Load Environment Variables from .env file  
# NOTE: This assumes you have a .env file with FRED_API_KEY=YOUR_KEY
load_dotenv() 

# 2. Get the Key
FRED_API_KEY = os.getenv('FRED_API_KEY') 

# 3. Validation Check
if not FRED_API_KEY:
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    print("!!! ERROR: FRED_API_KEY not found.                                     !!!")
    print("!!! Please ensure you have a '.env' file with: FRED_API_KEY=your_key  !!!")
    print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

# 4. Define the Mega Trend Series List
# This is the comprehensive list from your strategy document, cleaned up for FRED codes.
FRED_INDICATORS = {
    # --- Growth & Output ---
    'GDP': 'GDP',                       # Total economic output (Denominator for Buffett Indicator)
    'INDPRO': 'Industrial_Production',   # Measures real output of manufacturing, mining, and electric/gas utilities
    
    # --- Inflation & Prices ---
    'CPIAUCSL': 'CPI_Index',            # Consumer Price Index (Headline Inflation)
    'PSAVERT': 'Savings_Rate',          # Personal Savings Rate (Consumer financial buffer)
    
    # --- Labor Market ---
    'UNRATE': 'Unemployment_Rate',      # Percentage of labor force that is jobless (Laggard indicator)
    'HOUST': 'Housing_Starts',          # Leading indicator for economic expansion and consumer confidence
    
    # --- Monetary Policy & Yields ---
    'FEDFUNDS': 'Fed_Funds_Rate',       # Central bank interest rate (Cost of borrowing)
    'DGS10': 'Treasury_10Y_Rate',       # Benchmark for long-term loans and mortgage rates
    'T10Y2Y': 'Yield_Curve_10Y2Y',      # Spread between 10Y and 2Y (Key recession prophet)
    
    # --- Financial Stress & Money ---
    'M2SL': 'Money_Supply_M2',          # Total money in circulation (Liquidity indicator)
    'BAMLH0A0HYM2': 'High_Yield_Spread', # Junk bond spread (Measures corporate default risk/fear)
    'TOTCI': 'Commercial_Loans',        # Lending activity to businesses (Credit growth)
    
    # --- Consumer Sentiment & Spending ---
    'UMCSENT': 'Consumer_Sentiment',    # Survey-based mood of the consumer
    'RSAFS': 'Retail_Sales',            # Actual consumer spending behavior
    'CSUSHPINSA': 'Home_Price_Index'    # S&P Case-Shiller National Home Price Index (Wealth effect)
}

DB_PATH = 'data/FinTrac.db'

def fetch_single_series(fred_client, series_id, name, start_date='1990-01-01'):
    """
    Helper function to fetch one series and align it to a Monthly Timeline.
    This fixes the 'Bad Request' errors by letting FRED send the native frequency
    and handling the resampling on the client side.
    """
    try:
        # Fetch raw data at its native frequency (Daily, Weekly, Quarterly, Monthly)
        s = fred_client.get_series(series_id, observation_start=start_date)
        
        # RESAMPLING LOGIC: Convert everything to monthly averages.
        # - 'ME' = Month End (Fixed FutureWarning)
        # - .mean() = Takes the average of the month (suitable for Daily/Weekly data like VIX/ICSA)
        # - .ffill() = Fills gaps if any month is missing (crucial for Quarterly data like GDP)
        s = s.resample('ME').mean().ffill()
        
        df = pd.DataFrame(s, columns=[name])
        df.index.name = 'date'
        return df
    except Exception as e:
        print(f"FAILED to fetch {name} ({series_id}): {e}")
        return None

def fetch_all_macro_data_parallel(api_key, FRED_INDICATORS):
    """
    Fetches all series in parallel using threads.
    Returns a single merged DataFrame.
    """
    if not api_key:
        print("Error: No API Key provided.")
        return pd.DataFrame()

    fred = Fred(api_key=api_key)
    results = []
    
    # Note: len(series_map) is 24 (all intended indicators)
    print(f"Starting parallel fetch for {len(FRED_INDICATORS)} economic indicators...")
    
    # --- PARALLEL EXECUTION START ---
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Submit all tasks to the pool
        future_to_series = {
            executor.submit(fetch_single_series, fred, sid, name): name 
            for sid, name in FRED_INDICATORS.items()
        }
        
        for future in as_completed(future_to_series):
            data = future.result()
            if data is not None:
                results.append(data)
    # --- PARALLEL EXECUTION END ---
                
    if not results:
        print("No data fetched.")
        return pd.DataFrame()

    print("Merging data...")
    # Merge all series into one big DataFrame on the Date index
    macro_df = pd.concat(results, axis=1)
    
    # Sort by date
    macro_df = macro_df.sort_index()
    
    # Reset index to make 'date' a column (easier for SQLite)
    return macro_df.reset_index()

def save_to_db(df, db_path):
    if df.empty:
        print("DataFrame is empty. Nothing to save.")
        return
        
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    
    # Store in 'macro_raw' table
    df.to_sql('macro_raw', conn, if_exists='replace', index=False)
    conn.close()
    print(f"Saved {len(df)} rows and {len(df.columns)} columns to {db_path}")

if __name__ == "__main__":
    if FRED_API_KEY:
        # 1. Fetch
        df = fetch_all_macro_data_parallel(FRED_API_KEY, FRED_INDICATORS)
        
        # 2. Preview
        print("\n--- Data Preview (head) & (Tail) ---")
        print(df.head())
        print(df.tail())
        
        # 3. Save
        save_to_db(df, DB_PATH)
    else:
        print("Please set your FRED_API_KEY in the .env file to run this script.")