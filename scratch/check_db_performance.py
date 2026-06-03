# -*- coding: utf-8 -*-
import sqlite3
import os

def main():
    db_path = 'data/prospection.db'
    
    print(f"=== DATABASE DIAGNOSTICS: {db_path} ===")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. List existing tables
    print("\n--- TABLES ---")
    tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    for t in tables:
        name = t['name']
        count = cursor.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        print(f"Table: {name:<20} | Rows: {count}")
        
    # 2. List existing indexes
    print("\n--- INDEXES ---")
    indexes = cursor.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index'").fetchall()
    for idx in indexes:
        print(f"Index: {idx['name']:<25} | On Table: {idx['tbl_name']:<20} | SQL: {idx['sql']}")
        
    # 3. Explain Query Plan
    print("\n--- EXPLAIN QUERY PLAN (Slow Query) ---")
    query = """
        SELECT COUNT(*) 
        FROM leads_bruts lb 
        LEFT JOIN leads_audites la ON la.lead_id = lb.id
    """
    try:
        plan = cursor.execute(f"EXPLAIN QUERY PLAN {query}").fetchall()
        for step in plan:
            print(dict(step))
    except Exception as e:
        print(f"Explain failed: {e}")
        
    conn.close()

if __name__ == '__main__':
    main()
