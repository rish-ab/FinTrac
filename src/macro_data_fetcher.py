import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sqlite3
import os
from fred_key import fred_key

# --- CONFIGURATION ---
# NOTE: Replace 'YOUR_FRED_API_KEY_HERE' with your actual key
FRED_API_KEY = fred_key 
FRED_BASE_URL = 'https://api.stlouisfed.org/fred/series/observations'
DB_PATH = 'data/FinTrac.db'

# --- 1. MACRO DATA SERIES DEFINITION ---
# These are the specific time-series IDs required for the FinTrac model
MACRO_SERIES = {
    # Consumer Price Index (Inflation) - Essential for ASR and PFRS
    'CPIAUCSL': 'CPI_Index', 
    # Civilian Unemployment Rate - Essential for Economic Risk/Strategy
    'UNRATE': 'Unemployment_Rate', 
    # Federal Funds Effective Rate - Essential for Financial Forecasting
    'DFF': 'Fed_Rate'
}

# --- 2. DATA ACQUISITION FUNCTION ---

def fetch_macro_data(api_key, base_url, series_ids, start_date='2020-01-01', end_date=None):
    """
    Fetches multiple FRED time series IDs and combines them into a single clean DataFrame.
    """
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
        
    all_data = pd.DataFrame()
    print(f"Fetching data from FRED, start date: {start_date}...")

    for series_id, col_name in series_ids.items():
        obs_params = {
            'series_id': series_id,
            'api_key': api_key,
            'file_type': 'json',
            'observation_start': start_date,
            'observation_end': end_date,
            # We request monthly frequency and values
            'frequency': 'm', 
            'units': 'lin' 
        }

        try:
            response = requests.get(base_url, params=obs_params)
            response.raise_for_status() # Raise exception for bad status codes (4xx or 5xx)
            
            res_data = response.json()
            obs_data = pd.DataFrame(res_data.get('observations', []))
            
            if obs_data.empty:
                print(f"Warning: No data found for {series_id}")
                continue

            # Cleaning and indexing
            obs_data['date'] = pd.to_datetime(obs_data['date'])
            # Convert '.' (missing values) to NaN, then to float
            obs_data['value'] = obs_data['value'].replace('.', np.nan).astype(float)
            obs_data = obs_data.dropna(subset=['value'])
            
            # Select relevant columns and rename
            series_df = obs_data[['date', 'value']].rename(columns={'value': col_name})
            series_df.set_index('date', inplace=True)
            
            if all_data.empty:
                all_data = series_df
            else:
                # Merge the new series with the existing data on the 'date' index
                all_data = all_data.merge(series_df, left_index=True, right_index=True, how='outer')

        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error for {series_id}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred for {series_id}: {e}")

    print("Macro data fetch complete.")
    return all_data.reset_index()

# --- 3. USER DATA SIMULATION FUNCTION (Micro-Data Requirement) ---

def simulate_user_data(n_users=500, n_months=12):
    """
    Simulates 12 months of highly variable income/spending data for 500 users.
    This generates the time-series required for the IVI calculation.
    """
    np.random.seed(42)
    start_date = datetime.now() - timedelta(days=30 * n_months)
    
    user_records = []
    
    for user_id in range(1, n_users + 1):
        # Base Income for the user (Average)
        base_income = np.random.normal(5500, 1500)
        
        # Simulating Volatility: Income fluctuates significantly around the mean
        income_series = base_income + np.random.randn(n_months) * (base_income * 0.40)
        
        # Simulating Essential Spend (Less volatile than income)
        essential_spend_base = base_income * 0.65
        essential_spend_series = essential_spend_base + np.random.randn(n_months) * (essential_spend_base * 0.1)
        
        # Ensure values are positive
        income_series = income_series.clip(1000)
        essential_spend_series = essential_spend_series.clip(500)

        # Total Debt (Single snapshot metric, needed for DTI compliance)
        total_debt = np.random.normal(30000, 18000, size=1).clip(0)[0] 
        total_savings = np.random.normal(12000, 7000, size=1).clip(0)[0]

        for i in range(n_months):
            record_date = start_date + timedelta(days=30 * i)
            
            # Store data in raw format
            user_records.append({
                'user_id': user_id,
                'date': record_date.strftime('%Y-%m-%d'),
                'monthly_income': income_series[i],
                'essential_spend': essential_spend_series[i],
                'total_debt_snapshot': total_debt if i == n_months - 1 else np.nan, # Only save once
                'total_savings_snapshot': total_savings if i == n_months - 1 else np.nan # Only save once
            })
            
    user_df = pd.DataFrame(user_records)
    # Forward-fill and drop duplicates to ensure the snapshot metrics are available
    user_df = user_df.sort_values(by=['user_id', 'date'])
    user_df['total_debt_snapshot'] = user_df.groupby('user_id')['total_debt_snapshot'].ffill()
    user_df['total_savings_snapshot'] = user_df.groupby('user_id')['total_savings_snapshot'].ffill()
    user_df = user_df.dropna(subset=['total_debt_snapshot', 'total_savings_snapshot'])
    
    print(f"User data simulation complete: {len(user_df)} records.")
    return user_df

# --- 4. DATABASE INITIALIZATION & LOAD ---

def initialize_database(db_path, macro_df, user_df):
    """
    Initializes the SQLite database and loads the raw data into staging tables.
    """
    if not os.path.exists(os.path.dirname(db_path)):
        os.makedirs(os.path.dirname(db_path))

    conn = sqlite3.connect(db_path)
    print(f"Database initialized at {db_path}")

    # --- A. Load Macro Data (macro_raw) ---
    print("Loading macro_raw table...")
    macro_df.to_sql('macro_raw', conn, if_exists='replace', index=False)

    # --- B. Load User Data (user_transactions_raw) ---
    print("Loading user_transactions_raw table...")
    user_df.to_sql('user_transactions_raw', conn, if_exists='replace', index=False)
    
    # --- C. Create Empty Feature Store (feature_store) ---
    # We define the basic structure of the feature store table now, even though it's empty
    # This table will be populated later in Notebook 01
    
    try:
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS feature_store (
                user_id INTEGER PRIMARY KEY,
                mean_income REAL,
                total_debt REAL,
                total_savings REAL,
                IVI REAL,
                ABF_Target REAL,
                PFRS REAL,
                PFRS_Forecast REAL,
                compliance_flag TEXT
            );
        """)
        conn.commit()
        print("Feature store table structure created.")
    except Exception as e:
        print(f"Error creating feature store table: {e}")
        
    conn.close()

# --- 5. EXECUTION ---

if __name__ == "__main__":
    if FRED_API_KEY == 'YOUR_FRED_API_KEY_HERE':
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!! WARNING: Please set your FRED_API_KEY before running data acquisition. !!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    
    # 1. Fetch Macro Data
    macro_df = fetch_macro_data(FRED_API_KEY, FRED_BASE_URL, MACRO_SERIES)
    
    # 2. Simulate User Data
    user_df = simulate_user_data()
    
    # 3. Initialize and Load Database
    initialize_database(DB_PATH, macro_df, user_df)

    print("\nData Acquisition Complete. Ready for Notebook 01 (Transformation).")