# -*- coding: utf-8 -*-
"""
core/deliverability.py — Module expert délivrabilité email

Point d'entrée unique pour toute validation SMTP, MX et délivrabilité.
Utilisé par les deux pipelines (Maps et Sniper).

Capacités :
  - resolve_mx(domain)            : serveur MX prioritaire
  - check_rcpt(mx, email)         : code SMTP pour une adresse (sans envoi)
  - is_catch_all(mx, domain)      : détection domaine catch-all
  - validate_smtp(email)          : validation simple ('Valide'|'Inconnu'|'Erreur')
  - validate_email_quick(email)   : validation Mailcheck.ai + MX fallback
  - validate_with_permutations()  : validation complète avec permutations CEO

RÈGLE ABSOLUE : Ce module ne doit JAMAIS envoyer d'email réel.
La séquence s'arrête toujours au RCPT TO, aucun DATA ni envoi.
"""

import re
import socket
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SMTP_PORT    = 25
SMTP_TIMEOUT = 8
HELO_DOMAIN  = "incidenx.com"
MAIL_FROM    = "audit@incidenx.com"

_CATCHALL_TEST_PREFIX = "faux-test-xyz99872"

_DISPOSABLE_DOMAINS = {
    "yopmail.com", "guerrillamail.com", "tempmail.com", "throwaway.email",
    "mailinator.com", "sharklasers.com", "guerrillamailblock.com",
    "grr.la", "dispostable.com", "temp-mail.org",
}

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


# ─── DNS / MX ─────────────────────────────────────────────────────────────────

def resolve_mx(domain: str) -> Optional[str]:
    """Résout le serveur MX prioritaire d'un domaine. Retourne None si introuvable."""
    try:
        import dns.resolver
        records = dns.resolver.resolve(domain, "MX")
        sorted_records = sorted(records, key=lambda r: r.preference)
        return str(sorted_records[0].exchange).rstrip(".")
    except Exception as e:
        logger.debug(f"[deliverability] DNS MX {domain}: {e}")
        return None


# ─── SMTP probe ───────────────────────────────────────────────────────────────

def check_rcpt(mx_host: str, email: str) -> Optional[int]:
    """
    Vérifie si une adresse email existe via SMTP (sans envoyer).

    Retourne :
        250  → adresse acceptée
        550  → adresse refusée (user unknown)
        4xx/5xx → autres codes (ex: rejet IP)
        None → erreur réseau / timeout
    """
    try:
        with socket.create_connection((mx_host, SMTP_PORT), timeout=SMTP_TIMEOUT) as sock:
            def recv():
                """Consomme toute la réponse SMTP (gère le multiline)."""
                data = ""
                while True:
                    chunk = sock.recv(4096).decode("utf-8", errors="ignore")
                    if not chunk:
                        break
                    data += chunk
                    # Une réponse SMTP est complète si la dernière ligne commence par 'XXX '
                    lines = data.rstrip().split("\n")
                    if lines and len(lines[-1]) >= 4 and lines[-1][3] == " ":
                        break
                return data

            def send(cmd: str):
                sock.sendall((cmd + "\r\n").encode())

            # 1. Greeting
            recv()
            # 2. HELO
            send(f"EHLO {HELO_DOMAIN}")
            recv()
            # 3. MAIL FROM
            send(f"MAIL FROM:<{MAIL_FROM}>")
            recv()
            # 4. RCPT TO
            send(f"RCPT TO:<{email}>")
            response = recv().strip()
            # 5. QUIT
            send("QUIT")

            # Extraction du code (3 premiers chiffres de la DERNIÈRE ligne)
            last_line = response.split("\n")[-1].strip()
            code_match = re.match(r"^(\d{3})", last_line)
            if code_match:
                code = int(code_match.group(1))
                logger.debug(f"[deliverability] {mx_host} -> {email} : {code}")
                return code

    except socket.timeout:
        logger.debug(f"[deliverability] timeout vers {mx_host} pour {email}")
    except Exception as e:
        logger.debug(f"[deliverability] erreur {mx_host}/{email} — {e}")

    return None


def is_catch_all(mx_host: str, domain: str) -> bool:
    """Retourne True si le domaine accepte n'importe quelle adresse (catch-all)."""
    code = check_rcpt(mx_host, f"{_CATCHALL_TEST_PREFIX}@{domain}")
    return code == 250


# ─── Validation simple (Maps-style) ───────────────────────────────────────────

def validate_smtp(email: str) -> str:
    """
    Validation SMTP simple d'une adresse email.

    Retourne :
        'Valide'  — adresse acceptée (RCPT 250)
        'Inconnu' — domaine MX absent ou réponse ambiguë
        'Erreur'  — timeout ou erreur technique
    """
    if not email or "@" not in email:
        return "Erreur"

    domain = email.split("@")[1]
    mx = resolve_mx(domain)
    if not mx:
        return "Inconnu"

    try:
        code = check_rcpt(mx, email)
        if code == 250:
            return "Valide"
        return "Inconnu"
    except socket.timeout:
        return "Erreur"
    except Exception as e:
        logger.warning(f"[deliverability] validate_smtp {email}: {e}")
        return "Erreur"


def validate_email_quick(email: str) -> str:
    """
    Validation rapide via Mailcheck.ai (API gratuite, sans clé).
    Fallback sur résolution MX si l'API est indisponible (ou 429).

    Retourne 'Valide', 'Invalide' ou 'Inconnu'.
    """
    if not email or "@" not in email:
        return "Invalide"

    if not _EMAIL_RE.match(email):
        return "Invalide"

    domain = email.split("@")[1].lower()
    if domain in _DISPOSABLE_DOMAINS:
        return "Invalide"

    import time
    import requests

    # Tentative API (sans retry sur 429 pour éviter de bloquer l'audit)
    try:
        resp = requests.get(
            f"https://api.mailcheck.ai/email/{email}",
            timeout=2,
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("disposable", False):
                return "Invalide"
            return "Valide" if data.get("mx", False) else "Invalide"
        elif resp.status_code == 429:
            logger.warning(f"[deliverability] Mailcheck 429 — API limitée, passage au fallback MX")
    except Exception as e:
        logger.debug(f"[deliverability] Mailcheck API erreur/timeout: {e}")

    # Fallback MX (Si API 429 ou erreur)
    try:
        import dns.resolver
        dns.resolver.resolve(domain, "MX")
        return "Valide"
    except Exception:
        return "Inconnu"


# ─── Validation complète avec permutations (Sniper-style) ─────────────────────

def validate_with_permutations(
    permutations: list[str],
    domain: str,
    email_contact_fallback: Optional[str] = None,
) -> dict:
    """
    Valide les permutations email par SMTP (séquence catch-all + RCPT TO).

    Args:
        permutations:           Emails candidats (jean.dupont@domain.fr, etc.)
        domain:                 Domaine cible
        email_contact_fallback: Email contact@ si aucune permutation valide

    Returns:
        {
            "email_valide":      str | None,
            "email_source":      str,   # 'smtp_verified'|'catch_all_contact'|'not_found'
            "copywriting_mode":  str,   # 'direct'|'transfert'
            "is_catch_all":      bool,
            "mx_host":           str | None,
        }
    """
    result = {
        "email_valide":     None,
        "email_source":     "not_found",
        "copywriting_mode": "transfert",
        "is_catch_all":     False,
        "mx_host":          None,
    }

    if not permutations and not email_contact_fallback:
        return result

    mx_host = resolve_mx(domain)
    if not mx_host:
        logger.warning(f"[deliverability] pas de MX pour {domain}")
        if email_contact_fallback:
            result["email_valide"]     = email_contact_fallback
            result["email_source"]     = "no_mx_fallback"
            result["copywriting_mode"] = "transfert"
        return result

    result["mx_host"] = mx_host
    logger.debug(f"[deliverability] MX {domain} → {mx_host}")

    # Test catch-all
    if is_catch_all(mx_host, domain):
        logger.info(f"[deliverability] {domain} est en catch-all")
        result["is_catch_all"] = True
        if email_contact_fallback:
            result["email_valide"]     = email_contact_fallback
            result["email_source"]     = "catch_all_contact"
            result["copywriting_mode"] = "transfert"
        return result

    # Domaine strict → tester les permutations
    if not permutations:
        if email_contact_fallback:
            result["email_valide"]     = email_contact_fallback
            result["email_source"]     = "no_permutations_fallback"
            result["copywriting_mode"] = "transfert"
        return result

    # Liste des erreurs bloquantes d'IP (rejet host, absence rDNS, etc.)
    _BLOCK_CODES = {450, 550, 554, 571} 
    blocked_by_ip = False

    for candidate in permutations:
        code = check_rcpt(mx_host, candidate)
        if code == 250:
            logger.info(f"[deliverability] {candidate} VALIDE (SMTP)")
            result["email_valide"]     = candidate
            result["email_source"]     = "smtp_verified"
            result["copywriting_mode"] = "direct"
            return result
        
        # Si le serveur nous rejette nous (l'IP), pas la peine d'insister sur les autres permutations
        # Note : 550 peut être "User Unknown" (pas bloquant) ou "Access Denied" (bloquant)
        # Mais dans le doute, si on a un 450/554/571 on arrête.
        if code in _BLOCK_CODES:
             blocked_by_ip = True
             break

    # --- FALLBACK : Si SMTP bloqué ou aucune permutation trouvée ---
    logger.info(f"[deliverability] SMTP direct échoué ou bloqué pour {domain}")
    
    # 1. Si on avait un email contact@ trouvé sur le site, on le valide par API/MX
    if email_contact_fallback:
        status = validate_email_quick(email_contact_fallback)
        if status == "Valide":
            result["email_valide"]     = email_contact_fallback
            result["email_source"]     = "site_validated"
            result["copywriting_mode"] = "transfert"
            return result

    # 2. Si on est bloqués par l'IP mais qu'on a des permutations, 
    #    on valide la 1ère par API (probabilité max)
    if blocked_by_ip and permutations:
        best_candidate = permutations[0]
        status = validate_email_quick(best_candidate)
        if status == "Valide":
            logger.info(f"[deliverability] {best_candidate} VALIDE (API Fallback)")
            result["email_valide"]     = best_candidate
            result["email_source"]     = "api_fallback"
            result["copywriting_mode"] = "direct"
            return result

    return result
