import sqlite3, pandas as pd
conn = sqlite3.connect("pcc_data.db")
df = pd.read_sql("select * from patients limit 10", conn)
print(df)