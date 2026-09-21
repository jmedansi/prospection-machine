import sys
sys.path.append('.')
from database.connection import get_conn
with get_conn() as conn:
    rows = conn.execute('SELECT COUNT(*) FROM leads_audites WHERE lien_rapport IS NULL OR lien_rapport = ""').fetchone()
    print(f'Leads sans rapport: {rows[0]}')
    rows2 = conn.execute('SELECT COUNT(*) FROM leads_audites WHERE lien_rapport LIKE "local://%"').fetchone()
    print(f'Leads avec rapport local: {rows2[0]}')
    rows3 = conn.execute('SELECT COUNT(*) FROM leads_audites WHERE lien_rapport LIKE "https://%"').fetchone()
    print(f'Leads avec rapport public: {rows3[0]}')