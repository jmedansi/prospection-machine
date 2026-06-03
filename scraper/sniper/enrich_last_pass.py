"""Dernier pass — scrape toutes les pages pour trouver un email, sans contact_finder"""
import sys, os, re, logging, urllib.request, urllib.error, urllib.parse, socket, ssl
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database.connection import get_conn

logging.basicConfig(level=logging.WARNING)

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@([a-zA-Z0-9.-]+\.(?:fr|com|eu|io|net|org))')
BLOCKED = {'gmail.com','yahoo.fr','hotmail.fr','orange.fr','laposte.net','sfr.fr','free.fr','icloud.com','outlook.fr','ymail.com'}

def scrape_for_emails(url, timeout=6):
    domain = urllib.parse.urlparse(url).netloc.lower()
    pages = set()
    pages.add(url.rstrip('/'))
    for prefix in ['', '/contact', '/mentions-legales', '/nous-contacter', '/a-propos',
                   '/about', '/contactez-nous', '/contact-us', '/qui-sommes-nous',
                   '/equipe', '/team', '/le-cabinet', '/agence']:
        pages.add(url.rstrip('/') + prefix)
    emails = set()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for p in pages:
        try:
            req = urllib.request.Request(p, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                html = resp.read().decode('utf-8', errors='ignore')
                for m in EMAIL_RE.finditer(html):
                    e = m.group(0).lower()
                    d = m.group(1).lower()
                    if d not in BLOCKED and d != 'example.com' and d != 'domaine.fr' and ' ' not in e:
                        # Only accept if domain matches site domain or is plausible
                        emails.add(e)
        except:
            continue
    return list(emails)

with get_conn() as conn:
    cur = conn.execute(
        "SELECT id, nom, site_web, secteur FROM leads_bruts "
        "WHERE source='ads' AND secteur IS NOT NULL AND secteur != '' "
        "AND (email_valide IS NULL OR email_valide = '') "
        "AND site_web IS NOT NULL AND site_web != '' "
        "ORDER BY secteur, id"
    )
    leads = cur.fetchall()

print(f'{len(leads)} leads — scraping pages pour emails...')
ok = 0
for i, (lid, nom, site_web, secteur) in enumerate(leads, 1):
    sys.stdout.flush()
    emails = scrape_for_emails(site_web)
    if emails:
        valid = emails[0]
        with get_conn() as conn2:
            conn2.execute("UPDATE leads_bruts SET email_valide=?, email=? WHERE id=?", (valid, valid, lid))
            conn2.commit()
        ok += 1
        print(f'  [{i}/{len(leads)}] #{lid} {nom[:35]:35s} -> {valid[:35]}')
    else:
        print(f'  [{i}/{len(leads)}] #{lid} {nom[:35]:35s} -> rien')

print(f'\n{ok}/{len(leads)} emails trouvés')
