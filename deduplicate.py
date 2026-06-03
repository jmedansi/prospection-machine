import sqlite3

def deduplicate():
    conn = sqlite3.connect('d:/prospection-machine/data/prospection.db')
    conn.row_factory = sqlite3.Row
    
    # 1. Get all lead_ids with duplicates
    dups = conn.execute("""
        SELECT lead_id
        FROM leads_audites
        GROUP BY lead_id
        HAVING COUNT(*) > 1
    """).fetchall()
    
    lead_ids = [r['lead_id'] for r in dups]
    print(f"Found {len(lead_ids)} leads with duplicated audits.")
    
    deleted_count = 0
    for lid in lead_ids:
        # Get all audit rows for this lead
        rows = conn.execute("SELECT id, score_performance, audit_error FROM leads_audites WHERE lead_id=?", (lid,)).fetchall()
        
        # Determine the "best" row to keep.
        # We prefer a row with score_performance > 0.
        # If multiple, we prefer the one with MIN(id) because that's the one insert_audit was updating.
        best_row = None
        for r in rows:
            if best_row is None:
                best_row = r
            else:
                # Compare
                if (r['score_performance'] or 0) > (best_row['score_performance'] or 0):
                    best_row = r
                elif (r['score_performance'] or 0) == (best_row['score_performance'] or 0):
                    # Prefer smaller ID
                    if r['id'] < best_row['id']:
                        best_row = r
                        
        # Keep best_row['id'], delete others
        ids_to_delete = [r['id'] for r in rows if r['id'] != best_row['id']]
        
        for del_id in ids_to_delete:
            conn.execute("DELETE FROM leads_audites WHERE id=?", (del_id,))
            deleted_count += 1
            
    conn.commit()
    print(f"Deleted {deleted_count} duplicate rows.")

if __name__ == '__main__':
    deduplicate()
