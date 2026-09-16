import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from app.config import settings

conn = psycopg2.connect(
    host=settings.pg_host, port=settings.pg_port,
    dbname=settings.pg_dbname, user=settings.pg_user,
    password=settings.pg_password,
)
cur = conn.cursor()

# 所有表
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = [r[0] for r in cur.fetchall()]
print("=== 所有表 ===")
for t in tables:
    print(" ", t)

# 每张表的字段
print("\n=== 各表字段 ===")
for t in tables:
    cur.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name='{t}' ORDER BY ordinal_position")
    cols = cur.fetchall()
    print(f"\n[{t}]")
    for col, dtype in cols:
        print(f"  {col}  ({dtype})")

conn.close()
