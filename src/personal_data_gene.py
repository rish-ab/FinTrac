import sqlite3
import pandas as pd
conn = sqlite3.connect('data/FinTrac.db')
df = pd.read_sql("SELECT * FROM feature_store LIMIT 5", conn)
print(df)
conn.close()