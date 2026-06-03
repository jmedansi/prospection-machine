# -*- coding: utf-8 -*-
"""
sniper/linkedin_agent.py — Canal LinkedIn pour leads catch-all (omnicanalité)

Lire sniper/README.md avant toute modification.

Déclenchement : appelé par scraper/sniper/pipeline.py quand is_catch_all=True
et qu'un CEO a été identifié (ceo_prenom + ceo_nom disponibles).

Flux :
  1. Recherche Google (non authentifiée) → URL profil LinkedIn du dirigeant
  2. Patchright ouvre LinkedIn avec le compte configuré (.env)
  3. Envoie une demande de connexion + message d'accroche
  4. Mise à jour DB : statut_prospection = 'linkedin_envoye'
  5. Notification Telegram

LIMITES DE SÉCURITÉ (LinkedIn anti-bot) :
  - Max LINKEDIN_DAILY_LIMIT connexions par compte par jour (défaut : 15)
  - Rotation automatique entre les comptes configurés
  - Délai aléatoire entre chaque action (2-5s)
  - Abandon immédiat si checkpoint/CAPTCHA détecté

Configuration .env — 1 compte :
  LINKEDIN_EMAIL=compte@email.com
  LINKEDIN_PASSWORD=motdepasse
  LINKEDIN_DAILY_LIMIT=15

Configuration .env — multi-comptes (rotation automatique) :
  LINKEDIN_EMAIL_1=compte1@email.com
  LINKEDIN_PASSWORD_1=motdepasse1
  LINKEDIN_EMAIL_2=compte2@email.com
  LINKEDIN_PASSWORD_2=motdepasse2
  LINKEDIN_DAILY_LIMIT=15   ← limite par compte (total = N comptes × 15)
"""

import logging
import os
import random
import sys
import time
from datetime import date
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logger = logging.getLogger(__name__)

# ─── Message d'accroche ───────────────────────────────────────────────────────

_MESSAGE_TEMPLATE = (
    "Bonjour {prenom},\n\n"
    "J'ai essayé de vous envoyer un audit de {site} par email, "
    "mais c'était impossible.\n\n"
    "Je vous le partage ici — quelques points concrets sur "
    "la performance qui impactent vos campagnes.\n\n"
    "Bonne journée,"
)

# ─── Gestion multi-comptes ────────────────────────────────────────────────────
# Compteurs par compte : {"email": {"date": "2026-04-11", "count": 7}}

_account_counters: dict = {}


def _load_accounts() -> list[dict]:
    """
    Lit les comptes LinkedIn depuis .env.

    Formats supportés :
      - Numérotés  : LINKEDIN_EMAIL_1 / LINKEDIN_PASSWORD_1, _2, _3...
      - Unique     : LINKEDIN_EMAIL / LINKEDIN_PASSWORD  (rétrocompat)

    Retourne une liste de {"email": str, "password": str}.
    """
    from core.config import ensure_env
    ensure_env()

    accounts = []

    # Format numéroté — supporte jusqu'à 10 comptes
    for i in range(1, 11):
        email    = os.getenv(f"LINKEDIN_EMAIL_{i}", "").strip()
        password = os.getenv(f"LINKEDIN_PASSWORD_{i}", "").strip()
        if email and password:
            accounts.append({"email": email, "password": password})

    # Fallback format simple (rétrocompat)
    if not accounts:
        email    = os.getenv("LINKEDIN_EMAIL", "").strip()
        password = os.getenv("LINKEDIN_PASSWORD", "").strip()
        if email and password:
            accounts.append({"email": email, "password": password})

    return accounts


def _get_available_account() -> Optional[dict]:
    """
    Retourne le premier compte qui n'a pas atteint sa limite quotidienne.
    Rotation : compte 1 d'abord, puis 2, etc.
    Retourne None si tous les comptes sont à la limite.
    """
    from core.config import ensure_env
    ensure_env()

    limit = int(os.getenv("LINKEDIN_DAILY_LIMIT", "15"))
    today = str(date.today())
    accounts = _load_accounts()

    if not accounts:
        logger.error("linkedin_agent: aucun compte LinkedIn configuré dans .env")
        return None

    for acc in accounts:
        key = acc["email"]
        if key not in _account_counters or _account_counters[key]["date"] != today:
            _account_counters[key] = {"date": today, "count": 0}

        if _account_counters[key]["count"] < limit:
            return acc

    total = len(accounts) * limit
    logger.info(f"linkedin_agent: limite atteinte sur tous les comptes ({total}/jour)")
    return None


def _increment_counter(email: str):
    today = str(date.today())
    if email not in _account_counters or _account_counters[email]["date"] != today:
        _account_counters[email] = {"date": today, "count": 0}
    _account_counters[email]["count"] += 1


def get_daily_stats() -> dict:
    """Retourne les stats d'envoi du jour par compte (utilisé par le dashboard)."""
    from core.config import ensure_env
    ensure_env()

    limit = int(os.getenv("LINKEDIN_DAILY_LIMIT", "15"))
    today = str(date.today())
    accounts = _load_accounts()
    stats = []

    for acc in accounts:
        key   = acc["email"]
        count = _account_counters.get(key, {}).get("count", 0) if _account_counters.get(key, {}).get("date") == today else 0
        stats.append({
            "email":     key,
            "sent":      count,
            "limit":     limit,
            "remaining": max(0, limit - count),
        })

    return {
        "accounts":  stats,
        "total_sent": sum(s["sent"] for s in stats),
        "total_capacity": len(accounts) * limit,
    }


# ─── Recherche profil LinkedIn via Google ─────────────────────────────────────

def _search_linkedin_profile(page, prenom: str, nom: str, company_name: str) -> Optional[str]:
    """
    Cherche le profil LinkedIn via la recherche interne.
    Doit être appelée depuis une session Patchright déjà connectée.

    Validation stricte :
      - Prénom ET nom requis dans le texte du lien
      - Nom de l'entreprise vérifié dans la carte du résultat (si fourni)
      - Préférence pour les correspondances exactes
    Retourne l'URL du profil ou None.
    """
    try:
        keywords = f"{prenom} {nom} {company_name}".strip()
        search_url = (
            "https://www.linkedin.com/search/results/people/"
            f"?keywords={keywords.replace(' ', '%20')}"
            "&origin=GLOBAL_SEARCH_HEADER"
        )
        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        _human_delay(2, 3)

        prenom_norm = prenom.lower()
        nom_norm    = nom.lower()
        company_words = [w.lower() for w in company_name.split() if len(w) > 3] if company_name else []

        results = page.locator("a[href*='/in/']")
        best_match = None
        best_score = 0

        for i in range(min(results.count(), 20)):
            try:
                loc  = results.nth(i)
                href = loc.get_attribute("href") or ""
                text = loc.inner_text().strip().lower()

                if "/in/" not in href:
                    continue

                # -- Validation stricte : prénom ET nom doivent être présents --
                if prenom_norm not in text or nom_norm not in text:
                    continue

                # -- Scorer le résultat --
                score = 0
                full_name = f"{prenom_norm} {nom_norm}"

                # Bonus : prénom+nom apparaissent côte à côte (exact match)
                if full_name in text:
                    score += 50
                # Bonus : prénom+nom dans le désordre mais présents
                elif prenom_norm in text and nom_norm in text:
                    score += 30

                # Bonus : vérifier le nom de l'entreprise dans la carte parente
                if company_words:
                    try:
                        parent = loc.locator("xpath=ancestor::*[position()<=10]").last
                        card_text = parent.inner_text().lower()
                        company_hits = sum(1 for w in company_words if w in card_text)
                        if company_hits >= len(company_words) * 0.5:
                            score += 40
                        elif company_hits > 0:
                            score += 20
                    except Exception:
                        pass

                # Bonus : lien direct (pas de sous-page ?ref=)
                if "?" not in href.split("/")[-1]:
                    score += 10

                clean = href.split("?")[0]
                if not clean.startswith("http"):
                    clean = "https://www.linkedin.com" + clean

                if score > best_score:
                    best_score = score
                    best_match = clean
                    logger.debug(f"linkedin_agent: candidat score={score} → {clean} \"{text[:80]}\"")

            except Exception:
                continue

        if best_match and best_score >= 30:
            logger.info(f"linkedin_agent: profil trouvé (score={best_score}) → {best_match}")
            return best_match

        logger.info(f"linkedin_agent: aucun profil avec correspondance fiable pour {prenom} {nom}")
        return None

    except Exception as e:
        logger.warning(f"linkedin_agent: recherche interne LinkedIn échouée — {e}")

    return None


# ─── Envoi de la demande via Patchright ───────────────────────────────────────

def _send_connection_request(
    prenom:       str,
    nom:          str,
    company_name: str,
    message:      str,
    account:      dict,
) -> tuple[bool, Optional[str]]:
    """
    Ouvre LinkedIn avec Patchright, cherche le profil, envoie la demande.

    Args:
        account: dict {"email": str, "password": str} — compte à utiliser

    Retourne (True, profile_url) si envoyé, (False, None) sinon.
    """
    li_email    = account.get("email", "")
    li_password = account.get("password", "")

    if not li_email or not li_password:
        logger.error("linkedin_agent: compte invalide (email ou password manquant)")
        return False, None

    from core.browser import cdp_tab

    try:
        with cdp_tab(viewport={"width": 1280, "height": 800}) as page:
            # ── Login (skippé si déjà connecté dans le Chrome Gemini) ────────
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)
            _human_delay(1.5, 2.5)

            current = page.url
            if "feed" not in current and "mynetwork" not in current:
                # Pas encore connecté — on remplit le formulaire
                try:
                    page.fill("#username", li_email)
                    _human_delay(0.3, 0.8)
                    page.fill("#password", li_password)
                    _human_delay(0.5, 1.0)
                    page.click('[type="submit"]')
                    page.wait_for_load_state("domcontentloaded", timeout=20000)
                    _human_delay(2, 3)
                except Exception:
                    pass

                current = page.url
                if "checkpoint" in current or "captcha" in current or "challenge" in current:
                    logger.warning("linkedin_agent: vérification requise — abandon")
                    return False, None
                if "feed" not in current and "mynetwork" not in current:
                    logger.warning(f"linkedin_agent: login suspect — {current}")
                    return False, None

            logger.debug("linkedin_agent: session LinkedIn OK")

            # ── Recherche du profil dans LinkedIn ────────────────────────────
            profile_url = _search_linkedin_profile(page, prenom, nom, company_name)
            if not profile_url:
                logger.info(f"linkedin_agent: profil introuvable pour {prenom} {nom}")
                return False, None

            # ── Navigation vers le profil ─────────────────────────────────────
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            _human_delay(2, 4)

            if page.locator("text=Page introuvable").count() > 0:
                logger.info(f"linkedin_agent: page profil introuvable — {profile_url}")
                return False, None

            # ── Bouton "Se connecter" ────────────────────────────────────────
            # LinkedIn 2026 : le bouton direct "Se connecter" n'existe plus sur le profil.
            # Il faut cliquer "Plus" → "Se connecter" dans le menu déroulant.
            connected = page.evaluate("""
                () => {
                    // 1. Chercher un bouton direct "Se connecter" visible
                    const allBtns = document.querySelectorAll('button');
                    for (const btn of allBtns) {
                        const txt = btn.innerText.trim().toLowerCase();
                        const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                        if ((txt === 'se connecter' || txt === 'connect' || aria.includes('connecter') || aria.includes('connect')) && btn.offsetParent !== null && btn.getBoundingClientRect().top < 600) {
                            btn.click();
                            return 'direct';
                        }
                    }
                    // 2. Cliquer "Plus" / "More" dans la zone du profil (top < 500px)
                    for (const btn of allBtns) {
                        const t = btn.innerText.trim();
                        if ((t === 'Plus' || t === 'More') && btn.offsetParent !== null) {
                            const rect = btn.getBoundingClientRect();
                            if (rect.top < 500) {
                                btn.click();
                                // Attendre que le menu s'ouvre
                                return new Promise(resolve => {
                                    setTimeout(() => {
                                        // Chercher "Se connecter" / "Connect" dans le menu
                                        const menuItems = document.querySelectorAll('[role=\"menu\"] span, [role=\"menu\"] div, [role=\"menu\"] li');
                                        for (const item of menuItems) {
                                            const itxt = item.innerText.trim().toLowerCase();
                                            if (itxt === 'se connecter' || itxt === 'connect' || itxt === 'connecter') {
                                                item.click();
                                                resolve('plus_menu');
                                                return;
                                            }
                                        }
                                        resolve('plus_no_connect');
                                    }, 1500);
                                });
                            }
                        }
                    }
                    return 'none';
                }
            """)
            _human_delay(1.5, 2.5)

            if connected == 'none':
                logger.info(f"linkedin_agent: pas de bouton Connect trouvé — {profile_url}")
                return False, None
            logger.debug(f"linkedin_agent: bouton Connect trouvé via {connected}")

            # ── Ajouter une note (message d'accroche) ────────────────────────
            _human_delay(1, 2)
            add_note = page.locator(
                'button:has-text("Ajouter une note"), button:has-text("Add a note"), '
                'button[aria-label*="note" i]'
            )
            if add_note.count() > 0 and add_note.first.is_visible():
                add_note.first.click()
                _human_delay(0.8, 1.5)
                textarea = page.locator(
                    'textarea, [contenteditable="true"], [role="textbox"]'
                )
                if textarea.count() > 0:
                    textarea.first.click()
                    _human_delay(0.3, 0.6)
                    for char in message:
                        textarea.first.type(char, delay=random.randint(30, 80))
                    _human_delay(0.5, 1.0)

            # ── Envoyer ──────────────────────────────────────────────────────
            send_btn = page.locator(
                'button:has-text("Envoyer"), button:has-text("Send"), '
                'button[aria-label*="Envoyer" i], button[aria-label*="Send" i]'
            ).last
            if send_btn.count() > 0 and send_btn.is_visible():
                send_btn.click()
                _human_delay(1.5, 2.5)
                logger.info(f"linkedin_agent: demande envoyée → {profile_url}")
                return True, profile_url

            logger.warning("linkedin_agent: bouton Envoyer introuvable")
            return False, None

    except Exception as e:
        logger.error(f"linkedin_agent: erreur Patchright — {e}")
        return False, None


def _human_delay(min_s: float, max_s: float):
    """Pause aléatoire pour simuler un comportement humain."""
    time.sleep(random.uniform(min_s, max_s))


# ─── Interface publique ───────────────────────────────────────────────────────

def send_linkedin_outreach(
    audit_id:     int,
    lead_id:      int,
    prenom:       str,
    nom:          str,
    company_name: str,
    domain:       str,
    site_web:     str,
) -> bool:
    """
    Point d'entrée principal : trouve le profil + envoie la demande.

    Appelé depuis scraper/sniper/pipeline.py quand is_catch_all=True.

    Returns:
        True si demande envoyée, False sinon (profil introuvable, limite atteinte, etc.)
    """
    if not prenom or not nom:
        logger.debug(f"linkedin_agent: CEO inconnu pour {domain} — ignoré")
        return False

    # Vérifier qu'un compte est disponible (rotation multi-comptes)
    account = _get_available_account()
    if not account:
        return False

    message = _MESSAGE_TEMPLATE.format(
        prenom = prenom,
        site   = site_web or domain,
    )

    ok, profile_url = _send_connection_request(prenom, nom, company_name, message, account=account)

    if ok and profile_url:
        _increment_counter(account["email"])
        _update_db(audit_id, lead_id, profile_url)
        _notify_telegram(prenom, nom, domain, profile_url)

    return ok


def _update_db(audit_id: int, lead_id: int, profile_url: str):
    """Met à jour statut_prospection = 'linkedin_envoye' et stocke l'URL profil."""
    from database.connection import get_conn
    with get_conn() as conn:
        conn.execute(
            "UPDATE leads_audites SET statut_prospection='linkedin_envoye', linkedin_url=? WHERE id=?",
            (profile_url, audit_id)
        )
        conn.execute(
            "UPDATE leads_bruts SET statut='linkedin_envoye' WHERE id=?",
            (lead_id,)
        )
        conn.commit()


def _notify_telegram(prenom: str, nom: str, domain: str, profile_url: str):
    """Notification Telegram : demande LinkedIn envoyée."""
    try:
        from core.telegram_adapter import notify
        notify(
            f"LinkedIn — {prenom} {nom}",
            f"*Demande LinkedIn envoyée*\n"
            f"Contact : {prenom} {nom}\n"
            f"Domaine : {domain}\n"
            f"Profil : {profile_url}\n\n"
            f"_Email impossible (catch-all) — canal LinkedIn activé_",
        )
    except Exception as e:
        logger.debug(f"linkedin_agent: Telegram notification échouée — {e}")
