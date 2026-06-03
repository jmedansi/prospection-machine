"""
Scraping Ads de rattrapage pour courtage et cliniques_esthetiques.
"""
import asyncio, logging, sys, os, random, subprocess, time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

import uuid as _uuid

from scraper.sniper.headless_extract import search_one, cleanup_captcha, extract_from_captcha_page
from database.leads import insert_lead
from core.telegram_adapter import notify, send_validation_request, check_pending_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("catchup")
fh = logging.FileHandler(os.path.join(ROOT, "logs", f"ads_catchup_{datetime.now().strftime('%Y-%m-%d')}.log"), encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)

SECTEURS = {
    "courtage": [
        "courtier immobilier", "courtier pret immobilier",
        "simulation credit immobilier", "rachat de credit",
        "pret immobilier", "assurance pret", "meilleur taux immobilier",
    ],
    "cliniques_esthetiques": [
        "medecine esthetique", "chirurgie esthetique", "clinique esthetique",
        "dermatologue esthetique", "injection acide hyaluronique",
        "medecine anti-age", "laser esthetique",
    ],
}

VILLES = ["Paris", "Lyon", "Marseille", "Bordeaux", "Lille"]

def _kill_chrome(on_port: int = None):
    try:
        if on_port:
            r = subprocess.run(['netstat', '-ano'], capture_output=True, text=True, timeout=5)
            for l in r.stdout.split('\n'):
                if f':{on_port}' in l and 'LISTENING' in l:
                    parts = l.strip().split()
                    if parts:
                        subprocess.run(['taskkill', '/PID', parts[-1], '/F'], capture_output=True, timeout=3)
        else:
            r = subprocess.run(['tasklist', '/NH', '/FI', 'IMAGENAME eq chrome.exe'], capture_output=True, text=True, timeout=5)
            for l in r.stdout.split('\n'):
                if 'chrome.exe' in l:
                    parts = l.strip().split()
                    if parts:
                        subprocess.run(['taskkill', '/PID', parts[1], '/F'], capture_output=True, timeout=3)
    except:
        pass

def clean_url(url: str) -> str | None:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    url = url.replace("http://", "https://")
    return url.rstrip("/")

async def retry_query(query, port, max_retries=3):
    """Execute search_one avec retry captcha et détection IP bloquée.
    Retourne (domaines, "ok"|"captcha_abandon"|"block_abandon")."""
    consecutive_block = 0

    for attempt in range(max_retries + 1):
        suffix = f" (tentative {attempt+1}/{max_retries+1})" if attempt > 0 else ""
        logger.info(f"  {query} port {port}{suffix}")

        try:
            domains = await asyncio.wait_for(search_one(query, port), timeout=60)
        except asyncio.TimeoutError:
            logger.error(f"    TIMEOUT > 60s")
            _kill_chrome()
            consecutive_block += 1
            if consecutive_block >= 3:
                notify("Ads Catchup", f"🚫 {query}\nIP bloquée Google — pause 30 min")
                logger.error(f"    IP BLOQUÉE — pause 30 min")
                await asyncio.sleep(1800)
                consecutive_block = 0
            continue
        except Exception as e:
            logger.error(f"    ERREUR: {e}")
            _kill_chrome(on_port=port)
            continue

        # Reset bloque consecutive sur toute réponse
        consecutive_block = 0

        # ── Captcha ───────────────────────────────────────────────
        if domains and domains[0] == "__captcha__":
            callback_id = f"captcha_{port}_{_uuid.uuid4().hex[:6]}"
            sent = send_validation_request("Ads Catchup",
                f"🚨 Captcha Google Ads\n{query}\n"
                f"Port {port} — fenêtre Chrome ouverte\n"
                f"✅ J'ai résolu TOUS les captchas → extraction\n"
                f"❌ Abandon → passe au suivant",
                callback_id, 30)

            if sent != "pending":
                notify("Ads Catchup", f"🚨 Captcha + Telegram indispo\n{query}\nPort {port}\nRésous dans Chrome → reprise 10 min")
                logger.info(f"    CAPTCHA (fallback) — pause 10 min...")
                await asyncio.sleep(600)
                await cleanup_captcha(port)
                continue

            logger.info(f"    CAPTCHA port {port} — attente validation Telegram ✅/❌...")
            loop = asyncio.get_event_loop()

            while True:
                user_result = await loop.run_in_executor(None, check_pending_db, callback_id, 30)

                if user_result != "ok":
                    logger.info(f"    ❌ Captcha abandonné")
                    await cleanup_captcha(port)
                    return None  # abandon keyword

                logger.info(f"    ✅ Extraction depuis la page...")
                domains = await extract_from_captcha_page(query, port)

                if domains == ["__captcha__"]:
                    callback_id = f"captcha_{port}_{_uuid.uuid4().hex[:6]}"
                    send_validation_request("Ads Catchup",
                        f"🚨 Captcha encore présent\n{query}\nPort {port}\n"
                        f"✅ Résolu → extraction\n❌ Abandon",
                        callback_id, 30)
                    continue

                await cleanup_captcha(port)
                return domains  # [] ou liste de domaines

        # ── IP bloquée / timeout ──────────────────────────────────
        if domains and domains[0] == "__timeout__":
            notify("Ads Catchup", f"🚫 {query}\nTimeoute Google — IP bloquée ? Pause 30 min")
            logger.info(f"    TIMEOUT GOOGLE — pause 30 min...")
            await asyncio.sleep(1800)
            continue

        # ── Succès ou 0 annonces ──────────────────────────────────
        _kill_chrome(on_port=port)
        return domains

    return None  # abandon après max_retries

async def scrape_secteur(secteur, keywords):
    total = len(keywords) * len(VILLES)
    seen = set()
    frais = 0
    tries = 0
    secteur_ids = []

    logger.info(f"\n{'='*40}")
    logger.info(f"Secteur: {secteur} ({total} keywords)")
    logger.info(f"{'='*40}")

    for kw in keywords:
        for ville in VILLES:
            if tries >= total:
                break
            tries += 1
            query = f"{kw} {ville}"
            port = 9600 + (tries % 50)

            domains = await retry_query(query, port)
            if not domains:
                logger.info(f"    - 0 annonces (abandon après retry)")
                continue

            for raw_url in domains:
                url = clean_url(raw_url)
                if not url or url in seen:
                    continue
                seen.add(url)

                lid = insert_lead({
                    "nom": url.replace("https://", "").replace("http://", "").rstrip("/"),
                    "site_web": url,
                    "telephone": "",
                    "ville": ville,
                    "mot_cle": query,
                    "source": "ads",
                    "secteur": secteur,
                    "rating": 0,
                })
                if lid:
                    frais += 1
                    secteur_ids.append(lid)
                    logger.info(f"    [OK] #{lid} {url}")

            await asyncio.sleep(random.randint(10, 20))

    return secteur_ids

async def main():
    logger.info("="*50)
    logger.info("ADS CATCHUP - courtage + cliniques_esthetiques")
    logger.info(f"Date: {datetime.now().isoformat()}")
    logger.info("="*50)

    total_new = 0
    for secteur, keywords in SECTEURS.items():
        ids = await scrape_secteur(secteur, keywords)
        logger.info(f"  => {secteur}: {len(ids)} nouveaux leads")
        total_new += len(ids)

    logger.info(f"\nTotal nouveaux leads: {total_new}")

    if total_new > 0:
        logger.info(f"Lancement enrichissement avec phase2_suite.py...")

    logger.info(f"\nFIN: {datetime.now().isoformat()}")

if __name__ == "__main__":
    asyncio.run(main())
