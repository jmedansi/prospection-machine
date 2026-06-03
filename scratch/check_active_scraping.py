import sqlite3

conn = sqlite3.connect('data/prospection.db')
conn.row_factory = sqlite3.Row

print('=== Campagnes actives (scraping/running) ===')
rows = conn.execute("""
    SELECT id, nom, source, phase, started_at
    FROM campagnes
    WHERE phase IN ('scraping', 'running', 'enrichment')
    ORDER BY id DESC LIMIT 10
""").fetchall()
for r in rows:
    print(dict(r))

print()
print('=== Dernieres campagnes (toutes phases) ===')
rows2 = conn.execute("""
    SELECT id, nom, source, phase, started_at, stopped_at
    FROM campagnes
    ORDER BY id DESC LIMIT 5
""").fetchall()
for r in rows2:
    print(dict(r))

print()
print('=== Planned campaigns today ===')
rows3 = conn.execute("""
    SELECT id, keyword, city, source, statut, date_planifiee
    FROM planned_campaigns
    WHERE date_planifiee >= date('now', '-1 day')
    ORDER BY id DESC LIMIT 10
""").fetchall()
for r in rows3:
    print(dict(r))

conn.close()
