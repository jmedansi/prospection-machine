# -*- coding: utf-8 -*-
"""
sniper/form_sender.py — Canal formulaire de contact (fallback email/LinkedIn)

Flux :
  1. Cherche la page de contact du site (heuristique d'URL + liens internes)
  2. Detecte les champs : nom, email, telephone, sujet, message
  3. Remplit + soumet avec Patchright (anti-bot)
  4. Verifie la soumission (page de confirmation ou pas d'erreur visible)
  5. Mise a jour DB : statut = 'formulaire_envoye'
  6. Notification Telegram

Declenchement :
  Appele quand email introuvable ET LinkedIn a echoue (profil introuvable).
  Necessite site_web sur le lead.

Configuration .env :
  SENDER_NAME=Jean-Marc DANSI   (fallback sur BREVO_SENDER_NAME)
  SENDER_EMAIL=jmedansi@incidenx.com  (fallback sur BREVO_SENDER_EMAIL)
"""

import logging
import os
import random
import sys
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

logger = logging.getLogger(__name__)

# ─── Message d'accroche formulaire ────────────────────────────────────────────

_MESSAGE_TEMPLATE = (
    "Bonjour{prenom_part},\n\n"
    "Je me permets de vous contacter au sujet de votre site internet {site}.\n\n"
    "J'ai realise un audit technique gratuit et j'ai identifie quelques points "
    "concrets qui impactent votre visibilite sur Google et vos performances mobiles.\n\n"
    "Je serais ravi de vous partager les resultats — cela ne prend que quelques minutes.\n\n"
    "Bien cordialement,\n"
    "{sender_name}"
)

_SUBJECT_TEMPLATE = "Audit gratuit de votre site {site}"

# Chemins candidats pour la page de contact (ordre de priorite)
_CONTACT_PATHS = [
    "/contact", "/contact/", "/nous-contacter", "/nous-contacter/",
    "/contactez-nous", "/contactez-nous/", "/contact.html", "/contact.php",
    "/coordonnees", "/joindre-nous", "/get-in-touch", "/contact-us",
]

# Mots-cles pour detecter les champs par label/placeholder/name/id
_FIELD_HINTS = {
    "nom":      ["nom", "name", "prenom", "firstname", "lastname", "votre nom", "full name",
                 "your-name", "your_name", "fullname", "contactname",
                 "contact[name]", "contact[nom]", "fields[name]"],
    "email":    ["email", "e-mail", "mail", "courriel", "votre email",
                 "your-email", "your_email", "emailaddress",
                 "contact[mail]", "contact[email]", "fields[email]"],
    "sujet":    ["sujet", "subject", "objet", "titre", "your-subject", "your_subject",
                 "contact[subject]", "contact[sujet]"],
    "telephone": ["tel", "phone", "telephone", "mobile", "portable", "your-phone",
                  "contact[phone]", "contact[tel]", "fields[phone]"],
    "message":  ["message", "msg", "commentaire", "comment", "texte", "description",
                 "votre message", "contenu", "demande", "your-message", "your_message",
                 "textarea", "content", "contact[message]", "fields[message]"],
}


def _human_delay(min_s: float = 0.3, max_s: float = 0.9):
    time.sleep(random.uniform(min_s, max_s))


# ─── Recherche de la page de contact ──────────────────────────────────────────

def _has_contact_form(page) -> bool:
    """Vérifie si la page courante contient un formulaire de contact utilisable."""
    try:
        result = page.evaluate('''() => {
            const inputs = document.querySelectorAll(
                "input:not([type=hidden]):not([type=submit]):not([type=button])" +
                ":not([type=checkbox]):not([type=radio]):not([type=file])"
            );
            const textareas = document.querySelectorAll("textarea");
            return {inputs: inputs.length, textareas: textareas.length};
        }''')
        # Un formulaire de contact a au moins 1 textarea OU 2+ inputs
        return result.get("textareas", 0) >= 1 or result.get("inputs", 0) >= 2
    except Exception:
        return False


def _find_contact_url(page, base_url: str) -> Optional[str]:
    """
    Cherche la page de contact :
    1. Homepage (formulaire souvent intégré directement)
    2. Liens internes avec mot "contact"
    3. Chemins canoniques /contact, /nous-contacter, etc.
    """
    parsed = urlparse(base_url)
    base   = f"{parsed.scheme}://{parsed.netloc}"

    # 1. Homepage — très souvent le form est là (Contact Form 7, Elementor, lazy-load, etc.)
    try:
        page.goto(base_url, wait_until="networkidle", timeout=20000)
        _human_delay(0.5, 1.0)
        # Scroll pour déclencher les formulaires lazy-loaded
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        _human_delay(0.5, 0.8)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        _human_delay(0.8, 1.2)
        if _has_contact_form(page):
            return base_url
    except Exception:
        pass

    # 2. Liens internes "contact"
    try:
        links = page.locator("a[href]").all()
        for link in links[:80]:
            try:
                href = link.get_attribute("href") or ""
                text = link.inner_text().strip().lower()
                if any(kw in text or kw in href.lower()
                       for kw in ["contact", "nous-contacter", "joindre", "ecrire", "coordonnee"]):
                    full = href if href.startswith("http") else urljoin(base_url, href)
                    if urlparse(full).netloc == parsed.netloc and "#" not in full:
                        page.goto(full, wait_until="networkidle", timeout=15000)
                        _human_delay(0.5, 1.0)
                        if _has_contact_form(page):
                            return full
            except Exception:
                continue
    except Exception:
        pass

    # 3. Chemins canoniques
    for path in _CONTACT_PATHS:
        try:
            url = base + path
            page.goto(url, wait_until="networkidle", timeout=10000)
            _human_delay(0.3, 0.6)
            if _has_contact_form(page):
                return url
        except Exception:
            continue

    return None


# ─── Detection des champs ──────────────────────────────────────────────────────

def _score_field(attr_value: str, hints: list[str]) -> int:
    """Score un attribut contre une liste de mots-cles."""
    if not attr_value:
        return 0
    v = attr_value.lower()
    return sum(1 for h in hints if h in v)


def _detect_fields(page) -> dict:
    """
    Detecte les champs du formulaire.
    Retourne un dict {type: locator} pour les champs trouves.
    """
    fields = {}

    # Scroll pour déclencher les formulaires lazy-loaded
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        _human_delay(0.5, 0.8)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        _human_delay(0.8, 1.2)
    except Exception:
        pass

    try:
        page.wait_for_load_state("networkidle", timeout=4000)
    except Exception:
        pass

    # Cas Wix/sheet : cliquer sur le trigger pour ouvrir le panneau de contact
    trigger_selectors = [
        "[id*='contactSheet']", "[class*='contactSheet']",
        "[id*='ContactTrigger']", "[class*='contact-trigger']",
        "button[class*='contact']", "a[href='#contact']",
    ]
    for sel in trigger_selectors:
        try:
            trigger = page.locator(sel).first
            if trigger.count() > 0 and trigger.is_visible():
                trigger.click()
                _human_delay(1.0, 1.5)
                break
        except Exception:
            continue

    # Attendre que les champs apparaissent (JS + animation)
    try:
        page.wait_for_selector("input[type=text], input[type=email], textarea", timeout=5000)
    except Exception:
        pass

    # Chercher tous les inputs + textareas (avec ou sans <form>)
    exclude = ":not([type=hidden]):not([type=submit]):not([type=button]):not([type=checkbox]):not([type=radio]):not([type=file])"
    inputs    = page.locator(f"input{exclude}").all()
    textareas = page.locator("textarea").all()

    all_elements = inputs + textareas

    for el in all_elements:
        try:
            attrs = {
                "name":        el.get_attribute("name") or "",
                "id":          el.get_attribute("id") or "",
                "placeholder": el.get_attribute("placeholder") or "",
                "type":        el.get_attribute("type") or "",
                "class":       el.get_attribute("class") or "",
            }

            # Chercher le label associe
            el_id = attrs["id"]
            label_text = ""
            if el_id:
                try:
                    label = page.locator(f"label[for='{el_id}']")
                    if label.count() > 0:
                        label_text = label.first.inner_text().lower()
                except Exception:
                    pass

            combined = " ".join([attrs["name"], attrs["id"], attrs["placeholder"],
                                  attrs["type"], label_text])

            best_type  = None
            best_score = 0
            for field_type, hints in _FIELD_HINTS.items():
                score = _score_field(combined, hints)
                if score > best_score:
                    best_score = score
                    best_type  = field_type

            # Email detecte par type="email" meme sans mot-cle
            if attrs["type"] == "email" and "email" not in fields:
                best_type  = "email"
                best_score = 3

            if best_type and best_score > 0 and best_type not in fields:
                fields[best_type] = el
                logger.debug(f"form_sender: champ '{best_type}' detecte (score={best_score}, attrs={attrs})")

        except Exception:
            continue

    return fields


# ─── Soumission du formulaire ──────────────────────────────────────────────────

def _fill_and_submit(page, fields: dict, data: dict) -> bool:
    """
    Remplit les champs detectes et soumet.
    Retourne True si soumission probable (pas d'erreur visible).
    """
    if not fields.get("message"):
        logger.warning("form_sender: champ message introuvable — abandon")
        return False

    fill_map = {
        "nom":       data.get("nom", ""),
        "email":     data.get("email", ""),
        "sujet":     data.get("sujet", ""),
        "telephone": data.get("telephone", ""),
        "message":   data.get("message", ""),
    }

    for field_type, el in fields.items():
        value = fill_map.get(field_type, "")
        if not value:
            continue
        try:
            el.click()
            _human_delay(0.2, 0.5)
            el.fill("")
            for char in value:
                el.type(char, delay=random.randint(20, 60))
            _human_delay(0.2, 0.4)
        except Exception as e:
            logger.warning(f"form_sender: erreur remplissage champ '{field_type}': {e}")

    _human_delay(0.5, 1.2)

    # Chercher le bouton de soumission
    submit_selectors = [
        "form button[type=submit]",
        "form input[type=submit]",
        "form button:not([type=button])",
        "button:has-text('Envoyer')", "button:has-text('Submit')",
        "button:has-text('Valider')", "button:has-text('Send')",
        "input[value*='nvoyer']", "input[value*='ubmit']",
    ]
    submit = None
    for sel in submit_selectors:
        loc = page.locator(sel).first
        try:
            if loc.count() > 0 and loc.is_visible():
                submit = loc
                break
        except Exception:
            continue

    if not submit:
        logger.warning("form_sender: bouton de soumission introuvable")
        return False

    url_before = page.url
    try:
        submit.click()
        _human_delay(2, 3)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        pass

    # Verification soumission : changement d'URL ou message de confirmation
    url_after = page.url
    page_text = page.inner_text("body").lower() if page.locator("body").count() > 0 else ""

    success_signals = [
        "merci", "thank you", "message envoy", "bien recu", "confirmation",
        "nous reviendrons", "pris en compte", "received", "success",
    ]
    error_signals = [
        "erreur", "error", "invalide", "invalid", "required", "obligatoire",
        "veuillez", "please fill",
    ]

    has_success = any(s in page_text for s in success_signals)
    has_error   = any(s in page_text for s in error_signals)
    url_changed = url_after != url_before

    if has_success or (url_changed and not has_error):
        logger.info("form_sender: soumission confirmee")
        return True

    if has_error:
        logger.warning("form_sender: erreur de validation detectee sur le formulaire")
        return False

    # Pas de signal clair — on considere OK si pas d'erreur visible
    logger.info("form_sender: soumission probable (pas d'erreur detectee)")
    return True


# ─── Interface publique ────────────────────────────────────────────────────────

def send_form_outreach(
    lead_id:  int,
    site_web: str,
    prenom:   str = "",
    nom:      str = "",
) -> bool:
    """
    Point d'entree principal : trouve le formulaire, remplit, soumet.

    Returns:
        True si formulaire soumis avec succes, False sinon.
    """
    if not site_web:
        return False

    from core.config import ensure_env
    ensure_env()

    sender_name  = os.getenv("SENDER_NAME") or os.getenv("BREVO_SENDER_NAME", "Jean-Marc DANSI")
    sender_email = os.getenv("SENDER_EMAIL") or os.getenv("BREVO_SENDER_EMAIL", "")
    domain       = urlparse(site_web).netloc.lstrip("www.")

    prenom_part = f" {prenom}" if prenom else ""
    message = _MESSAGE_TEMPLATE.format(
        prenom_part = prenom_part,
        site        = domain,
        sender_name = sender_name,
    )
    sujet = _SUBJECT_TEMPLATE.format(site=domain)

    from core.browser import cdp_tab

    try:
        with cdp_tab(viewport={"width": 1280, "height": 800}) as page:
            # Trouver la page de contact
            contact_url = _find_contact_url(page, site_web)
            if not contact_url:
                logger.info(f"form_sender: aucune page de contact trouvee pour {domain}")
                return False

            logger.info(f"form_sender: page de contact trouvee -> {contact_url}")

            # Naviguer vers la page de contact
            page.goto(contact_url, wait_until="domcontentloaded", timeout=20000)
            _human_delay(1.5, 2.5)

            # Detecter les champs
            fields = _detect_fields(page)
            logger.info(f"form_sender: champs detectes -> {list(fields.keys())}")

            if not fields.get("message"):
                logger.info(f"form_sender: pas de champ message sur {contact_url}")
                return False

            # Remplir et soumettre
            data = {
                "nom":       f"{prenom} {nom}".strip() or sender_name,
                "email":     sender_email,
                "sujet":     sujet,
                "telephone": "",
                "message":   message,
            }

            ok = _fill_and_submit(page, fields, data)

        if ok:
            _update_db(lead_id)
            _notify_telegram(prenom, nom, domain, contact_url)

        return ok

    except Exception as e:
        logger.error(f"form_sender: erreur Playwright pour {domain} — {e}")
        return False


def _update_db(lead_id: int):
    try:
        from database.connection import get_conn
        with get_conn() as conn:
            conn.execute(
                "UPDATE leads_bruts SET statut='formulaire_envoye' WHERE id=?",
                (lead_id,)
            )
            conn.execute(
                "UPDATE leads_audites SET statut_prospection='formulaire_envoye' WHERE lead_id=?",
                (lead_id,)
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"form_sender: DB update echouee — {e}")


def _notify_telegram(prenom: str, nom: str, domain: str, contact_url: str):
    try:
        from core.telegram_adapter import notify
        contact = f"{prenom} {nom}".strip() or domain
        notify(
            f"Formulaire — {contact}",
            f"*Formulaire envoye*\n"
            f"Contact : {contact}\n"
            f"Domaine : {domain}\n"
            f"URL formulaire : {contact_url}\n\n"
            f"_Email introuvable — canal formulaire active_",
        )
    except Exception as e:
        logger.debug(f"form_sender: Telegram echoue — {e}")
