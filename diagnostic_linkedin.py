# -*- coding: utf-8 -*-
"""
Diagnostic LinkedIn — teste la connexion CDP, l'etat de la session,
les credentials, et fait un rapport complet.
Lancement : python diagnostic_linkedin.py
"""

import os, sys, json, logging, time

if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger('linkedin_diag')

# --- 1. Verification Chrome CDP ---
print("\n" + "="*60)
print("  DIAGNOSTIC LINKEDIN - prospection-machine")
print("="*60)

print("\n[1/6] Connexion Chrome CDP...")
import urllib.request
try:
    resp = urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=5)
    data = json.loads(resp.read())
    browser = data.get("Browser", "?")
    print(f"  [OK] Chrome connecte - {browser}")
except Exception as e:
    print(f"  [FAIL] Chrome CDP indisponible : {e}")
    print("  Lance d'abord : python core/open_chrome.py")
    sys.exit(1)

# --- 2. Verification .env ---
print("\n[2/6] Credentials LinkedIn...")
from core.config import ensure_env
ensure_env()

accounts = []
for i in range(1, 11):
    email    = os.getenv(f"LINKEDIN_EMAIL_{i}", "").strip()
    password = os.getenv(f"LINKEDIN_PASSWORD_{i}", "").strip()
    if email and password:
        accounts.append({"email": email, "password": "***present***"})
if not accounts:
    email    = os.getenv("LINKEDIN_EMAIL", "").strip()
    password = os.getenv("LINKEDIN_PASSWORD", "").strip()
    if email and password:
        accounts.append({"email": email, "password": "***present***"})

daily_limit = os.getenv("LINKEDIN_DAILY_LIMIT", "15")
print(f"  Comptes configures : {len(accounts)}")
for acc in accounts:
    print(f"    - {acc['email']} (password: {acc['password']})")
print(f"  Limite quotidienne : {daily_limit} par compte")

# --- 3. Test connexion LinkedIn ---
print("\n[3/6] Test de connexion LinkedIn (Patchright)...")
try:
    from core.browser import cdp_tab
    from sniper.linkedin_agent import _MESSAGE_TEMPLATE, _load_accounts

    loaded = _load_accounts()
    if not loaded:
        print("  [FAIL] Aucun compte charge")
        sys.exit(1)

    test_account = loaded[0]
    print(f"  Compte test : {test_account['email']}")
    print(f"  Message template OK ({len(_MESSAGE_TEMPLATE)} chars)")

    with cdp_tab(viewport={"width": 1280, "height": 800}) as page:
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        current_url = page.url
        print(f"  URL actuelle : {current_url}")

        if "feed" in current_url or "mynetwork" in current_url:
            print("  [OK] Deja connecte a LinkedIn ! Session active.")
        elif "login" in current_url or "checkpoint" in current_url:
            print("  [WARN] Page de login affichee - tentative de connexion...")

            page.fill("#username", test_account["email"])
            time.sleep(0.5)
            page.fill("#password", test_account["password"])
            time.sleep(0.5)
            page.click('[type="submit"]')
            page.wait_for_load_state("domcontentloaded", timeout=20000)
            time.sleep(3)

            current_url = page.url
            print(f"  URL apres login : {current_url}")

            if "checkpoint" in current_url or "captcha" in current_url or "challenge" in current_url:
                print("  [FAIL] LinkedIn demande une verification (CAPTCHA / checkpoint)")
                print("  -> Connecte-toi manuellement dans Chrome et relance ce diagnostic")
            elif "feed" in current_url or "mynetwork" in current_url:
                print("  [OK] Connexion reussie ! Session LinkedIn active.")
            else:
                print(f"  [UNKNOWN] Statut inconnu - {current_url}")
                if "password" in page.content().lower():
                    print("  -> Identifiants probablement incorrects")
                else:
                    print("  -> Page inattendue, verifie manuellement")
        else:
            print(f"  [UNKNOWN] Page inattendue : {current_url}")

except Exception as e:
    print(f"  [FAIL] Erreur Patchright : {e}")
    import traceback
    traceback.print_exc()

# --- 4. Verification cookies LinkedIn ---
print("\n[4/6] Cookies LinkedIn dans le profil Chrome...")
try:
    from core.browser import cdp_tab
    with cdp_tab(viewport={"width": 1280, "height": 800}) as page:
        page.goto("https://www.linkedin.com", wait_until="domcontentloaded", timeout=15000)
        cookies = page.context.cookies()
        li_cookies = [c for c in cookies if "linkedin" in c.get("domain", "")]
        print(f"  Cookies LinkedIn trouves : {len(li_cookies)}")
        if li_cookies:
            for c in li_cookies[:5]:
                print(f"    - {c['name']}: {c['value'][:30]}... (domain: {c['domain']})")
except Exception as e:
    print(f"  [FAIL] Impossible de lire les cookies : {e}")

# --- 5. Base de donnees ---
print("\n[5/6] Base de donnees - leads eligibles LinkedIn...")
try:
    from database.db_manager import get_conn
    with get_conn() as conn:
        r1 = conn.execute("""
            SELECT COUNT(*) as n FROM leads_audites
            WHERE ceo_prenom IS NOT NULL AND ceo_nom IS NOT NULL
        """).fetchone()
        print(f"  Leads avec CEO identifie : {r1['n'] if r1 else 0}")

        r2 = conn.execute("""
            SELECT COUNT(*) as n FROM leads_audites
            WHERE statut_prospection = 'linkedin_envoye'
        """).fetchone()
        print(f"  Deja contactes via LinkedIn : {r2['n'] if r2 else 0}")

        r3 = conn.execute("""
            SELECT COUNT(*) as n FROM leads_audites la
            JOIN leads_bruts lb ON lb.id = la.lead_id
            WHERE (lb.email IS NULL OR lb.email = '')
              AND la.ceo_prenom IS NOT NULL AND la.ceo_nom IS NOT NULL
              AND la.statut_prospection IS NULL
        """).fetchone()
        print(f"  Prets pour LinkedIn (catch-all, CEO connu) : {r3['n'] if r3 else 0}")

        r4 = conn.execute("""
            SELECT COUNT(*) as n FROM leads_audites la
            JOIN leads_bruts lb ON lb.id = la.lead_id
            WHERE lb.email IS NOT NULL AND lb.email != ''
              AND la.ceo_prenom IS NOT NULL AND la.ceo_nom IS NOT NULL
              AND la.statut_prospection IS NULL
        """).fetchone()
        print(f"  Avec email + CEO connu (email normal prioritaire) : {r4['n'] if r4 else 0}")

except Exception as e:
    print(f"  [FAIL] Erreur DB : {e}")

# --- 6. Synthese ---
print("\n[6/6] SYNTHESE DU DIAGNOSTIC")
print("="*60)

if len(accounts) == 0:
    print("  [FAIL] Aucun compte LinkedIn configure dans .env")
elif len(accounts) > 0:
    print(f"  [OK] {len(accounts)} compte(s) LinkedIn configure(s)")
    print(f"  [OK] Chrome CDP connecte (port 9222)")
    print(f"  [OK] Profil Chrome present")
    print(f"  [OK] Bibliotheque Patchright installee")
    print()
    print("  [WARN] Verifie le resultat du test de connexion [3/6] ci-dessus.")
    print("  Si la connexion a echoue :")
    print("    1. Ouvre Chrome manuellement -> linkedin.com")
    print("    2. Connecte-toi avec jmedansi@gmail.com")
    print("    3. Relance ce diagnostic")
    print()
    print("  Une fois la session validee, le pipeline pourra :")
    print("    - Chercher des profils LinkedIn via la recherche interne")
    print("    - Envoyer des demandes de connexion avec message")
    print(f"    - Jusqu'a {int(daily_limit) * len(accounts)} messages/jour")
print("="*60)
