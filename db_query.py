import subprocess, re, json

conn_str = subprocess.check_output(
    'az keyvault secret show --vault-name railo-kv --name pg-conn --query value -o tsv',
    text=True, stderr=subprocess.DEVNULL, shell=True
).strip()

# Parse: postgresql+asyncpg://user:pass@host/db?sslmode=require
# or postgresql+asyncpg://user:pass@host:port/db?sslmode=require
m = re.match(r'postgresql\+\w+://([^:]+):([^@]+)@([^/?]+)/([^?]+)', conn_str)
if not m:
    print(f"Could not parse: {conn_str[:50]}...")
    exit(1)
user, pwd, host, db = m.groups()
# strip ? params from db
db = db.split('?')[0]

import psycopg2
# host might include port like host:port
if ':' in host:
    h, port = host.split(':', 1)
else:
    h, port = host, 5432
conn = psycopg2.connect(host=h, port=int(port), user=user, password=pwd, dbname=db, sslmode='require')
cur = conn.cursor()
cur.execute("SELECT id::text, status, error_code, error, error_summary, created_at FROM runs ORDER BY created_at DESC LIMIT 3")
for row in cur.fetchall():
    print(row)
cur.close()
conn.close()
