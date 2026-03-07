import pandas as pd
import numpy as np
import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = 'data/FinTrac.db'

def generate_mock_transactions(num_users=5, months=60):
    """
    Generates synthetic transaction data for multiple users.
    """
    np.random.seed(42)
    categories = {
        'Income': {'type': 'credit', 'avg': 5000, 'std': 500},
        'Housing': {'type': 'debit', 'avg': 1800, 'std': 0},
        'Groceries': {'type': 'debit', 'avg': 400, 'std': 100},
        'Utilities': {'type': 'debit', 'avg': 200, 'std': 50},
        'Discretionary': {'type': 'debit', 'avg': 1000, 'std': 400},
        'Debt_Repayment': {'type': 'debit', 'avg': 500, 'std': 50},
        'Subscription': {'type': 'debit', 'avg': 100, 'std': 10}
    }

    all_transactions = []
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months*30)

    for user_id in range(1, num_users + 1):
        current_date = start_date
        
        # Assign an archetype multiplier (some users earn/spend more)
        user_multiplier = np.random.uniform(0.7, 1.5)
        
        # ... inside the loop ...
        while current_date <= end_date:
            
            # --- NEW: Add Inflation Drift ---
            # Calculate how many years have passed since start
            years_passed = (current_date - start_date).days / 365
            # Assume ~3% inflation per year
            inflation_factor = 1 + (0.03 * years_passed)
            
            # Monthly Recurring Items
            for cat, details in categories.items():
                if cat in ['Income', 'Housing', 'Subscription']:
                    # Apply inflation only to expenses, maybe income stays flatter (realistic pain)
                    drift = inflation_factor if details['type'] == 'debit' else 1.05 ** years_passed # Income grows slower?
                    
                    amount = details['avg'] * user_multiplier * drift
                    
                    all_transactions.append({
                        'user_id': f'USER_{user_id:03}',
                        'date': current_date.strftime('%Y-%m-%d'),
                        'category': cat,
                        'amount': round(amount, 2),
                        'type': details['type']
                    })
                else:
                    # Frequent items (Groceries get more expensive)
                    num_trips = np.random.randint(1, 5)
                    for _ in range(num_trips):
                        drift = inflation_factor
                        base_amount = details['avg'] / num_trips
                        amount = np.random.normal(base_amount, details['std']/2) * user_multiplier * drift
                        
                        tx_date = current_date + timedelta(days=np.random.randint(0, 28))
                        all_transactions.append({
                            'user_id': f'USER_{user_id:03}',
                            'date': tx_date.strftime('%Y-%m-%d'),
                            'category': cat,
                            'amount': round(max(5, amount), 2),
                            'type': details['type']
                        })
            
            current_date += timedelta(days=30)

    return pd.DataFrame(all_transactions)

def save_user_data(df):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    df.to_sql('user_transactions_raw', conn, if_exists='replace', index=False)
    
    # Create a quick summary table (Profile table)
    user_profiles = pd.DataFrame({
        'user_id': df['user_id'].unique(),
        'account_type': ['Checking', 'Savings', 'Investment', 'Credit', 'Checking'][:len(df['user_id'].unique())],
        'risk_tolerance': ['Low', 'Medium', 'High', 'Medium', 'Low'][:len(df['user_id'].unique())]
    })
    user_profiles.to_sql('user_profiles', conn, if_exists='replace', index=False)
    
    conn.close()
    print(f"SUCCESS: Generated {len(df)} transactions for {df['user_id'].nunique()} users.")

if __name__ == "__main__":
    transactions_df = generate_mock_transactions()
    save_user_data(transactions_df)