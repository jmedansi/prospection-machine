"""Dernier recours — emails pattern-based pour les 26 restants + deliverability check"""
import sys, os, logging, concurrent.futures
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database.connection import get_conn
from core.deliverability import verify_email

logging.basicConfig(level=logging.WARNING)

PATTERNS = ['contact', 'info', 'bonjour', 'hello']

def try_patterns(domain):
    found = []
    for p in PATTERNS:
        email = f'{p}@{domain}'
        try:
            result = verify_email(email)
            if result and result.get('status') == 'valide':
                found.append(email)
                break
        except:
            continue
    return found[0] if found else None

with get_conn() as conn:
    cur = conn.execute(
        "SELECT id, nom, site_web FROM leads_bruts "
        "WHERE source='ads' AND secteur IS NOT NULL AND secteur != '' "
        "AND (email_valide IS NULL OR email_valide = '') "
        "AND site_web IS NOT NULL AND site_web != '' "
        "ORDER BY id"
    )
    leads = cur.fetchall()

print(f'{len(leads)} leads — email patterns + deliverability...\n')
ok = 0
for lid, nom, site_web in leads:
    from urllib.parse import urlparse
    domain = urlparse(site_web).netloc.lower()
    if domain.startswith('www.'):
        domain = domain[4:]
    print(f'  #{lid} {nom[:35]:35s} {domain:30s}', end=' ')
    sys.stdout.flush()
    email = try_patterns(domain)
    if email:
        with get_conn() as conn2:
            conn2.execute("UPDATE leads_bruts SET email_valide=?, email=? WHERE id=?", (email, email, lid))
            conn2.commit()
        ok += 1
        print(f'OK {email}')
    else:
        print('-')

print(f'\n{ok}/{len(leads)} emails trouvés')
