"""
Phase 2 suite: enrichir les leads Ads incomplets (email + CEO)
Version ultra-legere: homepage email regex only, pas de multipage.
"""
import sys, os, concurrent.futures, logging, sqlite3, random, time, re
from datetime import datetime
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

import requests

import sniper.enrichment.ceo_finder as ceo_mod
# Desactiver Ollama (pas de serveur local)
ceo_mod._find_via_ollama = lambda *a, **kw: None
from sniper.enrichment.ceo_finder import find_ceo

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("phase2_suite")
fh = logging.FileHandler(os.path.join(ROOT, "logs", f"phase2_suite_{datetime.now().strftime('%Y-%m-%d')}.log"), encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
}

def extract_email_homepage(url):
    """Extrait un email depuis la homepage uniquement (rapide, pas de SMTP)."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
        if resp.status_code >= 500:
            return None
        emails = EMAIL_REGEX.findall(resp.text)
        # Filtrer les emails valides (pas des images, faux, etc.)
        valid = []
        for e in emails:
            e = e.lower().strip()
            domain_part = e.split('@')[1] if '@' in e else ''
            # Ignorer les emails generiques non porteurs
            if any(skip in e for skip in ['example.com', 'domain.com', 'your@', '@email.com', '@mail.com', 'noreply@', 'no-reply@']):
                continue
            # Ignorer les domaines trop longs (probablement du faux)
            if len(domain_part) > 40:
                continue
            # Eviter les doublons
            if e not in valid:
                valid.append(e)
        if valid:
            return valid[0]
    except requests.Timeout:
        pass
    except Exception:
        pass
    return None

def get_incomplete():
    conn = sqlite3.connect('data/prospection.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, nom, site_web, email, prenom_gerant, pays FROM leads_bruts
        WHERE source = 'ads'
          AND (email IS NULL OR email = '' OR email = '-'
            OR prenom_gerant IS NULL OR prenom_gerant = '' OR prenom_gerant = '-')
        ORDER BY secteur, id
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def enrich_one(lid, url, nom, pays="fr"):
    domain = urlparse(url).netloc.lstrip("www.") or url
    updates = {}
    try:
        email = extract_email_homepage(url)
        if email:
            updates["email"] = email
    except Exception as e:
        logger.error(f"  email #{lid}: {type(e).__name__}: {e}")
    try:
        ceo = find_ceo(nom or domain, domain, url, pays=pays)
        if ceo.get("ceo_prenom_norm"):
            updates["prenom_gerant"] = ceo["ceo_prenom_norm"]
        if ceo.get("ceo_nom_norm"):
            updates["nom_gerant"] = ceo["ceo_nom_norm"]
    except Exception as e:
        logger.error(f"  ceo #{lid}: {type(e).__name__}: {e}")
    return lid, updates

def main():
    leads = get_incomplete()
    logger.info(f"Phase 2 suite: {len(leads)} leads a enrichir")
    
    ok = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {}
        for r in leads:
            f = pool.submit(enrich_one, r['id'], r['site_web'], r['nom'], r.get('pays', 'fr'))
            futures[f] = r['id']
        
        for f in concurrent.futures.as_completed(futures, timeout=180):
            lid = futures[f]
            try:
                _, updates = f.result(timeout=20)
            except concurrent.futures.TimeoutError:
                logger.error(f"  #{lid} TIMEOUT")
                continue
            except Exception as e:
                logger.error(f"  #{lid} ERREUR: {type(e).__name__}: {e}")
                continue
            
            if updates:
                conn = sqlite3.connect('data/prospection.db')
                set_clause = ", ".join(f"{k}=?" for k in updates)
                conn.execute(f"UPDATE leads_bruts SET {set_clause} WHERE id=?", list(updates.values()) + [lid])
                conn.commit()
                conn.close()
            
            email = updates.get("email", "-")
            ceo_str = f"{updates.get('prenom_gerant', '') or ''} {updates.get('nom_gerant', '') or ''}".strip() or "-"
            logger.info(f"  #{lid} email={email} ceo={ceo_str}")
            ok += 1
            time.sleep(random.uniform(0.3, 1))
    
    logger.info(f"Termine: {ok}/{len(leads)} OK")

if __name__ == "__main__":
    main()
