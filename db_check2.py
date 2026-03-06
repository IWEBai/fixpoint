import psycopg2
import sys

conn = psycopg2.connect(
    host='railo-postgres.postgres.database.azure.com',
    port=5432,
    user='railo_admin',
    password=sys.argv[1],
    dbname='railo',
    sslmode='require'
)
cur = conn.cursor()
cur.execute("SELECT id::text, status, head_sha, head_ref, base_ref FROM runs WHERE id='b8e90356-10b3-43ff-bbc5-6486457c3bd5'")
for row in cur.fetchall():
    print(row)
cur.close()
conn.close()
