import psycopg2
import sys
conn = psycopg2.connect(host='railo-postgres.postgres.database.azure.com', port=5432, user='railo_admin', password=sys.argv[1], dbname='railo', sslmode='require')
cur = conn.cursor()
cur.execute("SELECT head_sha, head_ref, summary FROM runs WHERE id='5683b939-2386-44d2-9a14-d59c207c5c23'")
for row in cur.fetchall():
    print(row)
cur.close()
conn.close()
