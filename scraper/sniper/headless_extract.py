"""Extraction Google ADS — fresh Chrome + remote-debugging"""
import asyncio, logging, sys, os, subprocess, tempfile, time, shutil, socket, random, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from playwright.async_api import async_playwright as _ap

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe"

# Profils Chrome persistants (rotation identités)
PROFILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chrome_profiles")

# Instances captcha : Chrome gardé ouvert pour résolution manuelle
# {port: {"proc": Popen, "profile_dir": str, "keyword": str}}
_CAPTCHA_INSTANCES = {}


async def cleanup_captcha(port: int):
    """Tue le Chrome d'une instance captcha (garde le profil)."""
    inst = _CAPTCHA_INSTANCES.pop(port, None)
    if inst:
        logger.info(f"  Nettoyage instance captcha port {port} ({inst['keyword']})")
        try:
            if inst["proc"]:
                inst["proc"].kill()
                inst["proc"].wait(timeout=5)
        except: pass

_JS_ADS = """
    () => {
        const urls = new Set();
        // 1. data-pcu (ancien format Google Ads)
        document.querySelectorAll('[data-pcu]').forEach(el => {
            const u = el.getAttribute('data-pcu') || '';
            if (u.startsWith('http') && !u.includes('google.')) urls.add(u);
        });
        // 2. data-dtld
        document.querySelectorAll('[data-dtld]').forEach(el => {
            const u = el.getAttribute('data-dtld') || '';
            if (u && !u.includes('google.') && u.includes('.'))
                urls.add((u.startsWith('http') ? '' : 'https://') + u);
        });
        // 3. /aclk links (trackers)
        document.querySelectorAll('a[href*="/aclk"]').forEach(a => {
            if (a.href) urls.add(a.href);
        });
        // 4. data-text-ad containers
        document.querySelectorAll('[data-text-ad] a[href]').forEach(a => {
            if (a.href && !a.href.includes('google.') && !a.href.startsWith('#')) urls.add(a.href);
        });
        // 5. data-vc attribute (nouveau format Google)
        document.querySelectorAll('[data-vc] a[href]').forEach(a => {
            if (a.href && !a.href.includes('google.') && !a.href.startsWith('#')) urls.add(a.href);
        });
        // 6. Annonce / Sponsored labels
        document.querySelectorAll('[aria-label*="Annonce"], [aria-label*="Sponsored"]').forEach(el => {
            el.querySelectorAll('a[href]').forEach(a => {
                if (a.href && !a.href.includes('google.') && !a.href.startsWith('#')) urls.add(a.href);
            });
        });
        // 7. Tous les liens dans les divs contenant "Annonce" en texte visible
        document.querySelectorAll('div, section').forEach(div => {
            const txt = (div.textContent || '').trim();
            if (!txt.includes('Annonce') && !txt.includes('Sponsorisé') && !txt.includes('Sponsored')) return;
            div.querySelectorAll('a[href]').forEach(a => {
                if (a.href && !a.href.includes('google.') && !a.href.startsWith('#') && !a.href.startsWith('javascript')) urls.add(a.href);
            });
        });
        // 8. #tads / #bottomads (ancien format)
        ['#tads', '#bottomads', '#tadsb', '#adwords'].forEach(sel => {
            const el = document.querySelector(sel);
            if (el) el.querySelectorAll('a[href]').forEach(a => {
                if (a.href && !a.href.includes('google.') && !a.href.startsWith('#')) urls.add(a.href);
            });
        });
        // 9. Tout lien contenant "/ad" ou "adurl" dans l'URL
        document.querySelectorAll('a[href*="/ad"], a[href*="adurl"], a[href*="adclick"]').forEach(a => {
            if (a.href && !a.href.includes('google.') && !a.href.startsWith('#')) urls.add(a.href);
        });
        return [...urls];
    }
"""

_JS_CAPTCHA = """
    () => document.body.innerText.toLowerCase().includes('captcha')
        || document.body.innerText.toLowerCase().includes('not a robot')
        || document.body.innerText.toLowerCase().includes('automated queries')
        || document.body.innerText.toLowerCase().includes('notre système')
        || document.body.innerText.toLowerCase().includes('vérification')
        || document.body.innerText.toLowerCase().includes('unusual traffic')
"""


def clean(href):
    if not href or href.startswith("#") or href.startswith("javascript:"): return None
    from urllib.parse import urlparse, parse_qs
    if "/aclk" in href:
        parsed = urlparse(href)
        params = parse_qs(parsed.query)
        dest = params.get("adurl", [None])[0] or params.get("q", [None])[0]
        if dest: href = dest
        else: return None
    try:
        parsed = urlparse(href)
        if not parsed.netloc: return None
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."): netloc = netloc[4:]
        blacklist = {"facebook.com","instagram.com","linkedin.com","twitter.com","youtube.com","google.com","google.fr","amazon.fr","wixsite.com","wix.com","squarespace.com","wikipedia.org"}
        if any(netloc == b or netloc.endswith("." + b) for b in blacklist): return None
        if "." not in netloc or len(netloc) < 4: return None
        return f"https://{netloc}"
    except:
        return None


async def _detect_captcha(page) -> bool:
    """Détecte un captcha Google par URL + body text."""
    try:
        url = page.url.lower()
        if "sorry" in url or "captcha" in url or "unusual" in url:
            return True
        text = await page.evaluate("document.body.innerText.toLowerCase()")
        keywords = ["captcha", "not a robot", "automated queries", "notre système",
                     "vérification", "unusual traffic", "trafic inhabituel",
                     "prouvez", "prouver", "are you a robot"]
        return any(kw in text for kw in keywords)
    except:
        return False


async def search_one(keyword: str, port: int) -> list:
    os.makedirs(PROFILES_DIR, exist_ok=True)
    profile_idx = (port % 8) + 1  # 8 profils en rotation
    profile_dir = os.path.join(PROFILES_DIR, f"profile_{profile_idx}")
    proc = None
    captcha_detected = False
    try:
        proc = subprocess.Popen([
            CHROME, f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}", "--no-first-run",
            "--no-default-browser-check", "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for i in range(25):
            await asyncio.sleep(0.5)
            try: s = socket.socket(); s.connect(("127.0.0.1", port)); s.close(); break
            except: continue
        else:
            return []

        async with _ap() as pw:
            browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            if not browser.contexts: return []
            page = await browser.contexts[0].new_page()

            # Vider TOUT le stockage pour éviter détection
            try:
                await browser.contexts[0].clear_cookies()
                await page.evaluate("localStorage.clear(); sessionStorage.clear()")
            except: pass

            # ── RECHERCHE DIRECTE ──────────────────────────────────
            search_url = f"https://www.google.fr/search?q={keyword}&gl=fr&hl=fr&num=10"
            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                logger.info(f"  TIMEOUT search '{keyword}'")
                await browser.close()
                return ["__timeout__"]
            if await _detect_captcha(page):
                captcha_detected = True
                _CAPTCHA_INSTANCES[port] = {"proc": proc, "profile_dir": profile_dir, "keyword": keyword}
                return ["__captcha__"]

            # ── 3. ATTENTE RENDU + SCROLL ────────────────────────
            await page.wait_for_timeout(random.randint(2000, 4000))
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(600)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(400)
            await page.wait_for_timeout(500)

            if await _detect_captcha(page):
                captcha_detected = True
                _CAPTCHA_INSTANCES[port] = {"proc": proc, "profile_dir": profile_dir, "keyword": keyword}
                return ["__captcha__"]

            raw = await page.evaluate(_JS_ADS) or []
            domains = []
            seen = set()
            for h in raw:
                d = clean(h)
                if d and d not in seen:
                    seen.add(d)
                    domains.append(d)

            if not domains:
                try:
                    ad_links = await page.locator('a').filter(has_text=re.compile(r'Annonce|Sponsorisé|Sponsored')).all()
                    for a in ad_links:
                        href = await a.get_attribute('href')
                        if href:
                            d = clean(href)
                            if d and d not in seen:
                                seen.add(d)
                                domains.append(d)
                except: pass
            if not domains:
                try:
                    all_links = await page.locator('a[href*="://"]:not([href*="google."])').all()
                    for a in all_links:
                        href = await a.get_attribute('href')
                        if href:
                            d = clean(href)
                            if d and d not in seen:
                                seen.add(d)
                                domains.append(d)
                except: pass

            await browser.close()
            return domains
    finally:
        if not captcha_detected:
            if proc:
                try: proc.kill()
                except: pass
                try: proc.wait(timeout=5)
                except: pass
            # On garde le profil Chrome — pas de rmtree


async def extract_from_captcha_page(keyword: str, port: int) -> list:
    """Reconnect au Chrome captcha (résolu par l'utilisateur), scrappe la page affichée."""
    inst = _CAPTCHA_INSTANCES.get(port)
    if not inst:
        logger.warning(f"  Aucune instance captcha port {port}")
        return []
    logger.info(f"  Reconnection au Chrome port {port}...")
    try:
        async with _ap() as pw:
            browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            if not browser.contexts:
                logger.info(f"  Browser deja ferme port {port}")
                return []
            page = await browser.contexts[0].new_page()
            await page.wait_for_timeout(3000)

            current_url = page.url.lower()
            logger.info(f"  URL actuelle: {current_url}")

            # Si encore captcha → retourner signal
            if "sorry" in current_url or await _detect_captcha(page):
                logger.info(f"  Captcha encore present")
                await browser.close()
                return ["__captcha__"]

            # Si sur page d'accueil → naviguer vers recherche
            if "google.fr" in current_url and "/search" not in current_url:
                search_url = f"https://www.google.fr/search?q={keyword}&gl=fr&hl=fr&num=10"
                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=20_000)
                except Exception as e:
                    logger.info(f"  Navigation impossible: {e}")
                    await browser.close()
                    return ["__captcha__"]
                await page.wait_for_timeout(random.randint(2000, 4000))

                if await _detect_captcha(page):
                    await browser.close()
                    return ["__captcha__"]

            # Attente rendu + scroll + extraction
            await page.wait_for_timeout(random.randint(3000, 5000))
            await page.evaluate("window.scrollBy(0, 300)")
            await page.wait_for_timeout(600)
            await page.evaluate("window.scrollBy(0, 500)")
            await page.wait_for_timeout(600)
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(400)

            if await _detect_captcha(page):
                await browser.close()
                return ["__captcha__"]

            raw = await page.evaluate(_JS_ADS) or []
            domains = []
            seen = set()
            for h in raw:
                d = clean(h)
                if d and d not in seen:
                    seen.add(d)
                    domains.append(d)

            if not domains:
                try:
                    ad_links = await page.locator('a').filter(has_text=re.compile(r'Annonce|Sponsorisé|Sponsored')).all()
                    for a in ad_links:
                        href = await a.get_attribute('href')
                        if href:
                            d = clean(href)
                            if d and d not in seen:
                                seen.add(d)
                                domains.append(d)
                except: pass
            if not domains:
                try:
                    all_links = await page.locator('a[href*="://"]:not([href*="google."])').all()
                    for a in all_links:
                        href = await a.get_attribute('href')
                        if href:
                            d = clean(href)
                            if d and d not in seen:
                                seen.add(d)
                                domains.append(d)
                except: pass

            await browser.close()
            return domains
    except Exception as e:
        logger.error(f"  extract_from_captcha_page erreur: {e}")
        return []


async def main():
    keywords = [
        "agent immobilier Paris", "courtier immobilier Paris",
        "medecine esthetique Paris", "centre de formation Paris",
    ]
    all_domains = {}
    for i, kw in enumerate(keywords):
        port = 9400 + i
        logger.info(f"\n[{i+1}/{len(keywords)}] {kw} (port {port})...")
        domains = await search_one(kw, port)
        if domains and domains != ["__captcha__"]:
            logger.info(f"  OK {', '.join(domains)}")
            for d in domains:
                all_domains.setdefault(d, kw)
        else:
            logger.info(f"  - 0 annonces")
        await asyncio.sleep(random.randint(5, 10))

    print(f"\n=== {len(all_domains)} leads ADS trouves ===")
    for i, (d, kw) in enumerate(all_domains.items(), 1):
        print(f"{i:2d}. {d} ({kw})")

if __name__ == "__main__":
    asyncio.run(main())
