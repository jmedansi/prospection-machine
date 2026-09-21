import sqlite3, json, math, time

DB = r'D:\prospection-machine\data\prospection.db'
LEADS_JSON = r'D:\prospection-machine\output\agence_leads.json'

with open(LEADS_JSON, 'r', encoding='utf-8') as f:
    leads = json.load(f)

# connect with timeout to avoid 'database is locked' errors
# Attempt to open DB and perform inserts with retries on lock
campaign_id = None
for attempt in range(6):
    try:
        conn = sqlite3.connect(DB, timeout=30)
        cur = conn.cursor()
        cur.execute("PRAGMA busy_timeout = 5000")

        # Create campaign
        campaign_name = 'Agences webs'
        cur.execute("INSERT INTO campagnes (nom, description, statut, backend_pref, max_touches, qualification) VALUES (?, ?, 'actif', 'auto', 3, '')",
                    (campaign_name, 'Campagne auto générée — agences web/digital'))
        campaign_id = cur.lastrowid
        print('Created campaign id', campaign_id)
        break
    except sqlite3.OperationalError as e:
        print('DB locked, retry', attempt, 'error', e)
        time.sleep(2)
else:
    raise RuntimeError('Could not acquire DB lock after retries')

# Split leads into chunks of 20
chunk_size = 20
num_lists = math.ceil(len(leads) / chunk_size)
list_ids = []
for i in range(num_lists):
    start = i * chunk_size
    end = start + chunk_size
    chunk = leads[start:end]
    list_name = f"Agences webs - Liste {i+1}"
    cur.execute("INSERT INTO lead_lists (nom, description, couleur, icone, campaign_id) VALUES (?, ?, '#06b6d4', '📋', ?)",
                (list_name, f'Contient {len(chunk)} leads', campaign_id))
    lid = cur.lastrowid
    list_ids.append((lid, chunk))
    print('Created list', lid, 'for', list_name)

# Insert lead_list_items
count = 0
for lid, chunk in list_ids:
    for lead in chunk:
        lead_id = lead.get('id')
        if lead_id is None:
            continue
        try:
            cur.execute('INSERT INTO lead_list_items (list_id, lead_id) VALUES (?, ?)', (lid, lead_id))
            count += 1
        except Exception:
            pass

conn.commit()
conn.close()
print('Inserted', count, 'items into', len(list_ids), 'lists under campaign', campaign_id)
