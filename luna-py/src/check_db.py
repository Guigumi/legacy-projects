import sqlite3
import os

db_path = "src/data/luna.db"
if not os.path.exists(db_path):
    print(f"Banco não encontrado em {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tabelas:", [t[0] for t in tables])
conn.close()
