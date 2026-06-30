import sqlite3

conn = sqlite3.connect('data/prospection.db')
cur = conn.cursor()

# Check if logo_url column exists
cur.execute('PRAGMA table_info(leads_bruts)')
cols = [c[1] for c in cur.fetchall()]
print('logo_url present in leads_bruts:', 'logo_url' in cols)

# Count leads with logo
cur.execute("SELECT COUNT(*) FROM leads_bruts WHERE logo_url IS NOT NULL AND logo_url != ''")
print('Leads with logo:', cur.fetchone()[0])

# Sample leads with logo
cur.execute("SELECT id, nom, secteur, logo_url FROM leads_bruts WHERE logo_url IS NOT NULL AND logo_url != '' LIMIT 5")
rows = cur.fetchall()
print('\n--- Sample leads WITH logo ---')
for r in rows:
    print(r)

# Count leads without site
cur.execute("SELECT COUNT(*) FROM leads_bruts WHERE site_web IS NULL OR site_web = ''")
print('\nLeads sans site:', cur.fetchone()[0])

# Sample leads sans site + leurs logos
cur.execute("""
    SELECT id, nom, secteur, site_web, logo_url 
    FROM leads_bruts 
    WHERE site_web IS NULL OR site_web = ''
    LIMIT 10
""")
rows = cur.fetchall()
print('\n--- Sample leads SANS SITE ---')
for r in rows:
    print(r)

conn.close()
