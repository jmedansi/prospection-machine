# -*- coding: utf-8 -*-
"""
core/browser.py — Connexion CDP partagée vers le Chrome Gemini dashboard

Tous les modules qui ont besoin d'un navigateur passent par ici.
Aucun module ne lance son propre Chrome — un seul Chrome, un onglet par tâche.

Prérequis : Chrome lancé avec --remote-debugging-port=9222
  (le Chrome du Gemini dashboard tourne déjà avec ce flag)

Usage sync :
    from core.browser import cdp_tab
    with cdp_tab() as page:
        page.goto("https://example.com")

Usage async :
    from core.browser import cdp_tab_async
    async with cdp_tab_async() as page:
        await page.goto("https://example.com")

Usage avancé (onglet persistant sur toute une session) :
    from core.browser import get_async_browser
    browser = await get_async_browser()
    page = await browser.new_page()
    # ... utiliser page sans la fermer entre les itérations ...
    await page.close()  # fermer seulement à la fin

RÈGLE ABSOLUE :
    Les scrapers NE doivent JAMAIS appeler close_async_browsers() / browser.close().
    La connexion CDP au profil Chrome (cookies, session Google) doit rester ouverte
    pendant toute la durée du process.
    Seul le dashboard peut appeler close_async_browsers() en fin de session complète.

Gestion captcha (valable pour tous les modules) :
    from core.browser import handle_captcha_async, handle_captcha_sync

    # async
    page = await handle_captcha_async(page, label="Google Ads")

    # sync
    page = handle_captcha_sync(page, label="LinkedIn")

    Comportement :
      - Notification Telegram immédiate
      - Attend jusqu'à résolution (2h max async, 15 min sync)
      - Si résolu → retourne le même onglet, scraping reprend
      - Si timeout → retourne le même onglet (on ne tente PAS un new_page — il aurait aussi le captcha)
"""

import asyncio
import logging
import os
import socket
import threading
import time
from contextlib import asynccontextmanager, contextmanager

logger = logging.getLogger(__name__)

# ── Verrou captcha global ─────────────────────────────────────────────────────
# Un seul captcha peut être actif à la fois — tous les scrapers attendent.
# threading.Event : compatible sync ET async (pas de loop-per-thread issues).

_captcha_gate = threading.Event()
_captcha_gate.set()   # "ouvert" = pas de captcha en cours


def captcha_is_active() -> bool:
    return not _captcha_gate.is_set()


def _set_captcha_active():
    _captcha_gate.clear()


def _set_captcha_resolved():
    _captcha_gate.set()


async def wait_for_captcha_clear(poll_s: float = 5.0):
    """
    Coroutine à appeler AVANT chaque navigation Google.
    Bloque tant qu'un captcha est en cours de résolution sur un autre onglet.
    Retourne immédiatement si aucun captcha actif.
    """
    if _captcha_gate.is_set():
        return
    logger.info("[browser] Captcha actif — attente résolution avant navigation...")
    while not _captcha_gate.is_set():
        await asyncio.sleep(poll_s)
    logger.info("[browser] Captcha résolu — navigation autorisée.")


# ── Détection captcha (JS injecté dans la page) ───────────────────────────────

_JS_IS_CAPTCHA = """
    () => {
        const h = document.body.innerHTML;
        return (
            h.includes('g-recaptcha') ||
            h.includes('recaptcha/api.js') ||
            h.includes('/sorry/index') ||
            h.includes('detected unusual traffic') ||
            h.includes('trafic inhabituel') ||
            document.querySelector(
                'form#captcha-form, #recaptcha, iframe[src*="recaptcha"]'
            ) !== null
        );
    }
"""

_CAPTCHA_WAIT_S   = 15 * 60   # 15 minutes
_CAPTCHA_POLL_S   = 5         # vérifier toutes les 5s


def _tg_notify(msg: str):
    """Notification Telegram best-effort — ne bloque jamais."""
    try:
        from core.telegram_adapter import notify
        notify("Browser / Captcha", msg)
    except Exception:
        pass

_CDP_PORT = int(os.getenv("GOOGLE_ADS_CDP_PORT", "9222"))
_ensure_lock = threading.Lock()


def _port_open(port: int = _CDP_PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _is_cdp_responding() -> bool:
    """Vérifie si Chrome répond réellement aux requêtes CDP (pas juste le port ouvert)."""
    import requests
    try:
        r = requests.get(f"http://127.0.0.1:{_CDP_PORT}/json/version", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _ensure_chrome(force_restart: bool = False):
    """Connecte au Chrome existant sur le port CDP, ou le lance si fermé/planté."""
    with _ensure_lock:
        if not force_restart and _port_open():
            if _is_cdp_responding():
                return
            else:
                logger.warning(f"[browser] Port {_CDP_PORT} ouvert mais CDP ne répond pas — tentative de redémarrage force.")
                force_restart = True

        # Si on force le redémarrage, on doit invalider les caches du thread courant
        if force_restart:
            if hasattr(_sync_local, 'browser'):
                del _sync_local.browser
            # Note: Les autres threads devront aussi invalider leur cache s'ils échouent

        from core.open_chrome import launch_chrome
        logger.info(f"[browser] Chrome absent ou instable sur port {_CDP_PORT} — lancement (force={force_restart})")
        launch_chrome(force_restart=force_restart)
        
        for i in range(30):
            time.sleep(0.5)
            if _port_open() and _is_cdp_responding():
                logger.info(f"[browser] Chrome prêt sur port {_CDP_PORT} (après {(i+1)*0.5}s)")
                return
        
        raise RuntimeError(f"Chrome n'a pas démarré ou ne répond pas sur le port {_CDP_PORT} après 15s.")


# ── Sync ──────────────────────────────────────────────────────────────────────

# Gestionnaires de ressources Playwright (un par thread pour la sécurité sync)
_sync_local = threading.local()

def _get_sync_pw():
    """Récupère ou démarre une instance Playwright sync pour le thread courant."""
    if not hasattr(_sync_local, 'pw'):
        try:
            from patchright.sync_api import sync_playwright as _sp
        except ImportError:
            from playwright.sync_api import sync_playwright as _sp
        _sync_local.pw = _sp().start()
    return _sync_local.pw


def get_sync_browser(force_restart: bool = False):
    """Retourne le browser CDP sync — réutilise la connexion si possible."""
    _ensure_chrome(force_restart=force_restart)
    
    pw = _get_sync_pw()
    if not hasattr(_sync_local, 'browser') or force_restart:
        try:
            if hasattr(_sync_local, 'browser'):
                try: _sync_local.browser.close()
                except: pass
            _sync_local.browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{_CDP_PORT}")
        except Exception as e:
            logger.error(f"[browser] Erreur connexion CDP: {e}")
            raise
    return _sync_local.browser


def cleanup_sync_thread():
    """Nettoie les instances Playwright du thread courant pour éviter les zombies."""
    if hasattr(_sync_local, 'headless_browser'):
        try: _sync_local.headless_browser.close()
        except: pass
        del _sync_local.headless_browser

    if hasattr(_sync_local, 'browser'):
        try: _sync_local.browser.close()
        except: pass
        del _sync_local.browser
        
    if hasattr(_sync_local, 'pw'):
        try: _sync_local.pw.stop()
        except: pass
        del _sync_local.pw


@contextmanager
def cdp_tab(viewport: dict = None):
    """
    Context manager sync : ouvre un onglet dans le Chrome Gemini, yield la page, ferme l'onglet.
    Utilise browser.contexts[0].new_page() → profil par défaut (pas incognito).
    """
    try:
        browser = get_sync_browser()
        page = browser.contexts[0].new_page()
        if viewport:
            page.set_viewport_size(viewport)
        try:
            yield page
        finally:
            try:
                page.close()
            except:
                pass
    except Exception as e:
        logger.error(f"[browser] Erreur cdp_tab: {e}")
        # En cas d'erreur de connexion, on tente de reset le browser pour le prochain appel
        cleanup_sync_thread()
        raise


@contextmanager
def cdp_tab_headless(viewport: dict = None):
    """
    Ouvre un onglet dans une instance Chromium local 100% HEADLESS (Synchrone).
    Réutilise une instance thread-local pour éviter les crashs inter-threads.
    """
    pw = _get_sync_pw()
    
    if not hasattr(_sync_local, 'headless_browser'):
        logger.info(f"[browser] Lancement du headless sync pour le thread {threading.get_ident()}...")
        _sync_local.headless_browser = pw.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox', 
                '--disable-dev-shm-usage', 
                '--disable-gpu', 
                '--no-zygote',
                '--disable-blink-features=AutomationControlled',
            ]
        )
    
    ctx = None
    try:
        ctx = _sync_local.headless_browser.new_context(locale="fr-FR", viewport=viewport)
        page = ctx.new_page()
        yield page
    except Exception as e:
        logger.error(f"[browser] Erreur cdp_tab_headless: {e}")
        if "Target page, context or browser has been closed" in str(e) or "Event loop is closed" in str(e):
            cleanup_sync_thread()
        raise
    finally:
        if ctx:
            try:
                ctx.close() # Ferme l'onglet et le contexte, mais pas le browser
            except:
                pass


def close_all_browsers_sync():
    """Ferme proprement les instances Playwright du thread courant."""
    cleanup_sync_thread()


def close_all_pages():
    """Ferme TOUS les onglets ouverts dans le Chrome Gemini (emergency stop)."""
    try:
        browser = get_sync_browser()
        for ctx in browser.contexts:
            for page in ctx.pages:
                try: page.close()
                except: pass
        logger.info("[browser] Tous les onglets ont été fermés (emergency stop)")
    except Exception as e:
        logger.error(f"[browser] Erreur close_all_pages: {e}")


# ── Async ─────────────────────────────────────────────────────────────────────

# Singleton : une seule connexion CDP partagée entre tous les appels
# Pas de cache par-loop pour éviter les fuites de connexions CDP
_async_browser_instance = None
_async_pw_instance = None


def _is_cdp_browser_valid(browser) -> bool:
    """Vérifie que la connexion CDP est encore vivante sans lever d'exception."""
    try:
        _ = browser.contexts  # appel léger — lève si connexion morte
        return True
    except Exception:
        return False


async def get_async_browser(force_restart: bool = False):
    """
    Retourne l'instance Browser connectée par CDP (Async).
    Singleton : une seule connexion pour tout le process.
    Les anciennes connexions sont fermées avant d'en créer une nouvelle.
    """
    global _async_browser_instance, _async_pw_instance

    # Fast path : connexion existante et valide
    if not force_restart and _async_browser_instance is not None and _is_cdp_browser_valid(_async_browser_instance):
        return _async_browser_instance

    # Nouvelle connexion : fermer l'ancienne (évite les fuites CDP)
    if _async_pw_instance is not None:
        logger.info("[browser] Fermeture ancienne connexion CDP avant réouverture...")
        try:
            await _async_browser_instance.close()
        except Exception:
            pass
        try:
            await _async_pw_instance.stop()
        except Exception:
            pass
        _async_browser_instance = None
        _async_pw_instance = None

    _ensure_chrome(force_restart=force_restart)

    try:
        from patchright.async_api import async_playwright as _ap
    except ImportError:
        from playwright.async_api import async_playwright as _ap

    pw = await _ap().start()
    try:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{_CDP_PORT}")
        _async_browser_instance = browser
        _async_pw_instance = pw
        logger.info(f"[browser] CDP async connecté (port {_CDP_PORT}, singleton)")
        return browser
    except Exception as e:
        await pw.stop()
        logger.error(f"[browser] Erreur connexion CDP async: {e}")
        raise


_STEALTH_JS = """
    () => {
        // Masquer le signal CDP le plus évident
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        // Supprimer les traces CDP/injection de Chrome
        try { delete window.cdc_adoQpoasnfa76pfcZLihem; } catch(e) {}
        try { delete window.__playwright; } catch(e) {}
        try { delete window.__pw_manual; } catch(e) {}
        // Simuler des plugins (Chrome sans plugins = suspect)
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        // Langue cohérente
        Object.defineProperty(navigator, 'languages', {
            get: () => ['fr-FR', 'fr', 'en-US', 'en'],
        });
        // Environnement Chrome normal
        window.chrome = { runtime: {} };
        // Permissions normales
        const origQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (params) => (
            params.name === 'notifications'
                ? Promise.resolve({ state: 'prompt', onchange: null })
                : origQuery(params)
        );
    }
"""


async def patch_page(page):
    """Applique le script anti-détection sur une page Playwright."""
    try:
        await page.add_init_script(_STEALTH_JS)
    except Exception:
        pass


@asynccontextmanager
async def cdp_tab_async(viewport: dict = None):
    """
    Context manager async : ouvre un onglet dans le Chrome Gemini, yield la page, ferme l'onglet.
    Utilise browser.contexts[0].new_page() → profil par défaut (pas incognito).
    NE ferme PAS la connexion CDP — seulement l'onglet.
    """
    browser = await get_async_browser()
    page = await browser.contexts[0].new_page()
    await patch_page(page)
    if viewport:
        await page.set_viewport_size(viewport)
    try:
        yield page
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def close_async_browsers():
    """
    Ferme la connexion CDP async.
    Chrome (Profile 1) continue de tourner — les cookies/sessions sont préservées.
    Appelé automatiquement après chaque pipeline run pour éviter l'accumulation CDP.
    """
    global _async_browser_instance, _async_pw_instance
    if _async_pw_instance is not None:
        try:
            await _async_browser_instance.close()
        except Exception:
            pass
        try:
            await _async_pw_instance.stop()
        except Exception:
            pass
        _async_browser_instance = None
        _async_pw_instance = None
        logger.info("[browser] Connexion CDP async fermée (singleton)")


async def close_all_pages_async():
    """Ferme TOUS les onglets ouverts dans le Chrome Gemini (emergency stop async)."""
    try:
        browser = await get_async_browser()
        for ctx in browser.contexts:
            for page in ctx.pages:
                try: await page.close()
                except: pass
        logger.info("[browser] Tous les onglets ont été fermés (emergency stop async)")
    except Exception as e:
        logger.error(f"[browser] Erreur close_all_pages_async: {e}")


# ── Headless local (Performance optimization) ────────────────────────────────

# Cache pour le browser headless singleton async
_headless_browser_async = None
_headless_pw_async = None


@asynccontextmanager
async def cdp_tab_headless_async(viewport: dict = None):
    """
    Ouvre un onglet dans une instance Chromium local 100% HEADLESS (Async).
    Réutilise une instance unique pour économiser les ressources.
    """
    global _headless_browser_async, _headless_pw_async

    try:
        from patchright.async_api import async_playwright as _ap
    except ImportError:
        from playwright.async_api import async_playwright as _ap

    if _headless_browser_async is None:
        try:
            _headless_pw_async = await _ap().__aenter__()
            _headless_browser_async = await _headless_pw_async.chromium.launch(headless=True)
            logger.info("[browser] Singleton headless async démarré")
        except Exception as e:
            logger.error(f"[browser] Erreur démarrage singleton headless async: {e}")
            async with _ap() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    ctx = await browser.new_context(locale="fr-FR", viewport=viewport)
                    page = await ctx.new_page()
                    yield page
                finally:
                    await browser.close()
            return

    try:
        context = await _headless_browser_async.new_context(locale="fr-FR", viewport=viewport)
        page = await context.new_page()
        yield page
    finally:
        try:
            await page.close()
            await context.close()
        except:
            pass


# ── Gestion captcha ───────────────────────────────────────────────────────────

async def handle_captcha_async(page, label: str = "") -> object:
    """
    Appelé dès qu'un captcha est détecté dans un onglet async.

    1. Pose le verrou global — tous les autres scrapers s'arrêtent d'ouvrir des onglets
    2. Notification Telegram unique (pas de spam si plusieurs scrapers tournent)
    3. Poll le même onglet toutes les 5s jusqu'à résolution (2h max)
    4. Si résolu → lève le verrou global, retourne le même onglet
    5. Si timeout → laisse le verrou actif (scraping bloqué), retourne le même onglet
       NB : pas de nouvel onglet — un nouvel onglet aurait aussi le captcha

    Usage :
        if await page.evaluate(_JS_IS_CAPTCHA):
            page = await handle_captcha_async(page, label="Google Ads")
    """
    tag = f"[{label}] " if label else ""

    # Pose le verrou seulement si pas déjà posé (évite le double Telegram)
    first_captcha = not captcha_is_active()
    if first_captcha:
        _set_captcha_active()
        logger.warning(f"{tag}CAPTCHA détecté — verrou global posé, attente résolution")
        _tg_notify(
            f"⚠️ CAPTCHA détecté — {label}\n\n"
            f"Résous-le dans Chrome (onglet actif).\n"
            f"Reprise automatique de TOUS les scrapers dès que c'est fait."
        )
    else:
        logger.warning(f"{tag}CAPTCHA détecté (verrou déjà actif) — attente en cours")

    # Poll pendant 2h max sur le même onglet — pas de nouvel onglet
    _MAX_WAIT_S = 2 * 60 * 60
    polls = _MAX_WAIT_S // _CAPTCHA_POLL_S
    for i in range(polls):
        await asyncio.sleep(_CAPTCHA_POLL_S)
        try:
            if not await page.evaluate(_JS_IS_CAPTCHA):
                elapsed = (i + 1) * _CAPTCHA_POLL_S
                logger.info(f"{tag}CAPTCHA résolu après {elapsed}s — verrou levé, reprise")
                _set_captcha_resolved()
                _tg_notify(f"✅ CAPTCHA résolu ({label}) — tous les scrapers reprennent.")
                return page
        except Exception:
            pass

    # Timeout 2h — verrou reste actif, scraping s'arrête naturellement
    logger.error(f"{tag}CAPTCHA non résolu après 2h — scraping bloqué")
    _tg_notify(
        f"⏸️ CAPTCHA non résolu après 2h ({label}).\n"
        f"Scraping en pause. Résous dans Chrome puis relance depuis le dashboard."
    )
    return page


def handle_captcha_sync(page, label: str = "") -> object:
    """
    Version synchrone de handle_captcha_async.
    Même comportement : attend 15 min sur le même onglet.

    Usage :
        if page.evaluate(_JS_IS_CAPTCHA):
            page = handle_captcha_sync(page, label="LinkedIn")
    """
    tag = f"[{label}] " if label else ""
    logger.warning(f"{tag}CAPTCHA détecté — attente résolution (15 min max)")
    _tg_notify(
        f"⚠️ CAPTCHA détecté — {label}\n\n"
        f"Résous-le dans Chrome.\n"
        f"Reprise automatique dès que c'est fait (15 min max)."
    )

    polls = _CAPTCHA_WAIT_S // _CAPTCHA_POLL_S
    for i in range(polls):
        time.sleep(_CAPTCHA_POLL_S)
        try:
            if not page.evaluate(_JS_IS_CAPTCHA):
                elapsed = (i + 1) * _CAPTCHA_POLL_S
                logger.info(f"{tag}CAPTCHA résolu après {elapsed}s — reprise sur même onglet")
                return page
        except Exception:
            pass

    logger.warning(f"{tag}CAPTCHA non résolu après 15 min — on continue sur le même onglet")
    _tg_notify(f"⏱️ CAPTCHA non résolu après 15 min ({label}) — reprise sur même onglet.")
    return page
