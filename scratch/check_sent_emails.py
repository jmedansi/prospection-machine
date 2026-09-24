import sqlite3
import os
import glob

print("Checking database and logs...")

# Check all .db files
db_files = glob.glob("**/*.db", recursive=True)
print("DB Files found:", db_files)

for db_path in db_files:
    print(f"\n==================== DB: {db_path} ====================")
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]
        print("Tables:", tables)

        for table in tables:
            cur.execute(f"PRAGMA table_info({table});")
            columns = [col[1] for col in cur.fetchall()]
            
            # Check count
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            cnt = cur.fetchone()[0]
            print(f"\n-- Table '{table}' (Rows: {cnt}) --")
            print("Columns:", columns)
            
            # Look for sent / date / status columns
            date_cols = [c for c in columns if any(k in c.lower() for k in ['date', 'time', 'sent', 'created', 'updated', 'at', 'status', 'email'])]
            
            # Query recent entries or rows where status relates to sent or dates around Sept 21-22
            # Let's search across string columns for '2026-09-21', '2026-09-22', '2025-09-21', '2025-09-22', '09-21', '09-22', 'septembre'
            query_parts = []
            for c in columns:
                query_parts.append(f"CAST({c} AS TEXT) LIKE '%09-21%'")
                query_parts.append(f"CAST({c} AS TEXT) LIKE '%09-22%'")
                query_parts.append(f"CAST({c} AS TEXT) LIKE '%21/09%'")
                query_parts.append(f"CAST({c} AS TEXT) LIKE '%22/09%'")
            
            if query_parts:
                where_clause = " OR ".join(query_parts)
                try:
                    cur.execute(f"SELECT * FROM {table} WHERE {where_clause}")
                    matching_rows = cur.fetchall()
                    if matching_rows:
                        print(f"  -> Found {len(matching_rows)} rows matching Sept 21/22 in {table}:")
                        for row in matching_rows[:10]:
                            print("     ", dict(row))
                except Exception as e:
                    print(f"  Error querying dates in {table}: {e}")

            # Also check any status = 'SENT' or 'sent' or similar in table
            if 'status' in [c.lower() for c in columns]:
                status_col = [c for c in columns if c.lower() == 'status'][0]
                try:
                    cur.execute(f"SELECT {status_col}, COUNT(*) FROM {table} GROUP BY {status_col}")
                    print("  Status distribution:", cur.fetchall())
                except Exception as e:
                    pass

    except Exception as e:
        print(f"Error opening {db_path}: {e}")

# Check log files in logs/ and root
print("\n==================== LOG FILES ====================")
log_files = glob.glob("logs/**/*.*", recursive=True) + glob.glob("*.log")
for log_file in log_files:
    if os.path.isfile(log_file):
        size = os.path.getsize(log_file)
        print(f"\nLog file: {log_file} (size: {size} bytes)")
        if size > 0 and size < 20000000:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                matches = [l.strip() for l in lines if any(k in l for k in ['09-21', '09-22', '21/09', '22/09', 'Sep 21', 'Sep 22', 'Sept 21', 'Sept 22', '21-09', '22-09'])]
                if matches:
                    print(f"  -> Found {len(matches)} matching log lines in {log_file}:")
                    for m in matches[:15]:
                        print("     ", m)
                # Also check for sent email indicators
                send_matches = [l.strip() for l in lines if any(k in l.lower() for k in ['send_email', 'mail sent', 'email sent', 'resend', 'envoyé', 'email_sent'])]
                if send_matches:
                    print(f"  -> Found {len(send_matches)} email sending lines in {log_file}:")
                    for sm in send_matches[-10:]:
                        print("     ", sm)
