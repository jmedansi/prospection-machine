# -*- coding: utf-8 -*-
import sqlite3

def list_table_columns(cursor, table_name):
    try:
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = cursor.fetchall()
        print(f"\nColumns of table '{table_name}':")
        for col in cols:
            print(f"  {col[1]} ({col[2]})")
    except Exception as e:
        print(f"Error reading table '{table_name}': {e}")

def main():
    conn = sqlite3.connect('data/prospection.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cursor.fetchall()]
    print(f"Tables in DB: {tables}")
    
    for table in tables:
        list_table_columns(cursor, table)
        
    conn.close()

if __name__ == "__main__":
    main()
