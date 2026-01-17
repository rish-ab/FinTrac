import yfinance as yf
import pandas as pd
import sqlite3
import os

DB_PATH = 'data/FinTrac.db'

def fetch_market_indicators():
    """
    Fetches market indicators from Yahoo Finance, aligns dates, 
    and prepares a clean DataFrame for SQLite storage.
    """
    
    SERIES_MAP_YFINANCE = {
        '^GSPC': 'SP500',                   
        '^W5000': 'Total_Market_Cap',       
        '^RUT': 'Small_Cap_Index',          

        # --- Volatility & Sentiment ---
        '^VIX': 'VIX_Volatility',           
        'DX-Y.NYB': 'US_Dollar_Index',      

        # --- Commodities ---
        'CL=F': 'Crude_Oil',                
        'GC=F': 'Gold',                     
        'HG=F': 'Copper',                   

        # --- Sectors ---
        'XLE': 'Sector_Energy',             
        'XLF': 'Sector_Finance',            
        'XLK': 'Sector_Tech',               
        'XLP': 'Sector_Consumer_Staples',    
        'XLY': 'Sector_Consumer_Discretionary', 

        # --- Fixed Income ---
        '^TNX': 'Treasury_Yield_10Y_Market', 
        'HYG': 'High_Yield_Bond_ETF'         
    }

    print("--- Fetching Market Data from Yahoo Finance ---")
    
    # We will collect all series in a list and merge them later
    data_frames = []

    for ticker, name in SERIES_MAP_YFINANCE.items():
        try:
            # Fetch history (last 10 years is usually sufficient for analysis)
            ticker_obj = yf.Ticker(ticker)
            hist = ticker_obj.history(period="10y")['Close']
            
            # 1. Clean Timezone (Crucial for SQLite)
            # Remove timezone info so it's just "2023-01-01" not "2023-01-01 00:00:00-05:00"
            hist.index = hist.index.tz_localize(None)
            
            # 2. Rename the Series to our meaningful name
            hist.name = name
            
            data_frames.append(hist)
            print(f"Fetched: {name} ({ticker})")
            
        except Exception as e:
            print(f"Failed to fetch {name} ({ticker}): {e}")

    # 3. Combine all into one DataFrame
    # pd.concat aligns them by Date automatically (handling missing days/holidays)
    if not data_frames:
        print("Error: No data fetched.")
        return pd.DataFrame()
        
    sector_df = pd.concat(data_frames, axis=1)

    # 4. CRITICAL FIX: Move Date from Index to Column
    sector_df = sector_df.reset_index()
    sector_df.rename(columns={'Date': 'date'}, inplace=True) # Force lowercase 'date'

    return sector_df

def save_to_db(df, db_path):
    if df.empty:
        print("DataFrame is empty. Skipping save.")
        return
        
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        
        # Save to 'sector_data' table
        # if_exists='replace' will overwrite the old broken table with this new clean one
        df.to_sql('sector_data', conn, if_exists='replace', index=False)
        
        conn.close()
        print(f"\nSUCCESS: Saved {len(df)} rows to DB at '{db_path}'")
        print(f"   Columns: {list(df.columns[:3])} ...") # Print first few cols as proof
        
    except Exception as e:
        print(f"Database Error: {e}")

if __name__ == "__main__":
    # 1. Fetch
    market_df = fetch_market_indicators()
    
    # 2. Inspect (Sanity Check)
    print("\n--- Preview of Fetched Data ---")
    print(market_df.head())
    
    # 3. Save
    save_to_db(market_df, DB_PATH)