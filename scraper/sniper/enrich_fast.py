"""Enrichissement rapide — scrape contact pages + regex email"""
import sys, os, re, logging, urllib.request, urllib.error, socket
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database.connection import get_conn
from core.contact_finder import find_contacts

logging.basicConfig(level=logging.WARNING)

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
PHONE_RE = re.compile(r'(?:\+33|0)[1-9](?:[\s.-]?\d{2}){4}')
BLOCKED_DOMS = {'gmail.com','yahoo.fr','hotmail.fr','orange.fr','laposte.net','sfr.fr','free.fr','icloud.com','outlook.fr'}

def quick_scrape(url, timeout=8):
    pages = [url.rstrip('/'), url.rstrip('/') + '/contact', url.rstrip('/') + '/mentions-legales',
             url.rstrip('/') + '/nous-contacter', url.rstrip('/') + '/a-propos',
             url.rstrip('/') + '/about', url.rstrip('/') + '/contactez-nous']
    emails, phones = set(), set()
    for p in pages:
        try:
            req = urllib.request.Request(p, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
                for m in EMAIL_RE.finditer(html):
                    e = m.group().lower()
                    d = e.split('@')[1] if '@' in e else ''
                    if d not in BLOCKED_DOMS and '.' in d:
                        emails.add(e)
                for m in PHONE_RE.finditer(html):
                    phones.add(m.group())
        except:
            continue
    return list(emails), list(phones)

with get_conn() as conn:
    cur = conn.execute(
        "SELECT id, nom, site_web, secteur FROM leads_bruts "
        "WHERE source='ads' AND secteur IS NOT NULL AND secteur != '' "
        "AND (email_valide IS NULL OR email_valide = '') "
        "AND site_web IS NOT NULL AND site_web != '' "
        "ORDER BY secteur, id"
    )
    leads = cur.fetchall()

print(f'{len(leads)} leads — scrape contact pages + find_contacts fallback\n')
ok = 0
for i, (lid, nom, site_web, secteur) in enumerate(leads, 1):
    print(f'[{i}/{len(leads)}] #{lid} [{secteur:25s}] {nom[:40]:40s}', end=' ')
    sys.stdout.flush()

    emails, phones = quick_scrape(site_web)
    valid_email = None
    if emails:
        # Pick best email (prefer professional domain, not generic contact@)
        good = [e for e in emails if not e.startswith('contact@') and not e.startswith('info@') and not e.startswith('bonjour@')]
        valid_email = (good or emails)[0]

    # If quick scrape failed, try full contact_finder with aggressive mode
    if not valid_email:
        print('(full scan) ')
        sys.stdout.flush()
        try:
            contacts = find_contacts(site_web, nom, enrich_ceo=True, fast_mode=False)
            valid_email = contacts.get('email_valide') or contacts.get('email_contact')
            ceo_name = f"{contacts.get('ceo_prenom_norm', '') or ''} {contacts.get('ceo_nom_norm', '') or ''}".strip()
        except:
            valid_email = None
            ceo_name = ''
    else:
        ceo_name = ''

    if valid_email:
        with get_conn() as conn2:
            conn2.execute("UPDATE leads_bruts SET email_valide=?, email=? WHERE id=?", (valid_email, valid_email, lid))
            conn2.commit()
            # Also try CEO enrichment only if quick_scrape worked
            try:
                contacts = find_contacts(site_web, nom, enrich_ceo=True, fast_mode=True)
                ceo_updates = {}
                if contacts.get('ceo_prenom_norm'):
                    ceo_updates['prenom_gerant'] = contacts['ceo_prenom_norm']
                if contacts.get('ceo_nom_norm'):
                    ceo_updates['nom_gerant'] = contacts['ceo_nom_norm']
                if contacts.get('telephone'):
                    ceo_updates['telephone'] = contacts['telephone']
                if ceo_updates:
                    set_clause = ', '.join(f'{k}=?' for k in ceo_updates)
                    conn2.execute(f"UPDATE leads_bruts SET {set_clause} WHERE id=?", list(ceo_updates.values()) + [lid])
                    conn2.commit()
            except:
                pass
        ok += 1
        print('OK ' + valid_email[:35])
    else:
        print('NO email')

print(f'\n{ok}/{len(leads)} emails trouvés')
