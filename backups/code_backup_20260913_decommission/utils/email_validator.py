# -*- coding: utf-8 -*-
"""
utils/email_validator.py — Façade vers core/deliverability

La logique de validation email est centralisée dans core/deliverability.py.
Ce module expose l'interface Maps inchangée pour la compatibilité.
"""
from core.deliverability import validate_smtp, validate_email_quick
import logging

logger = logging.getLogger(__name__)


def verify_email_smtp(email: str, sender_domain: str = "incidenx.com") -> str:  # noqa: ARG001
    """
    Vérifie si un email est valide via connexion SMTP.

    Retourne 'Valide', 'Inconnu' ou 'Erreur'.
    `sender_domain` conservé pour compatibilité — core/deliverability utilise incidenx.com.
    """
    return validate_smtp(email)


def validate_pending_leads(limit: int = 50) -> dict:
    """
    Valide par lot les leads avec email non vérifié en base.

    Retourne {validated, invalid, errors, remaining}.
    """
    from database.db_manager import get_conn

    stats = {"validated": 0, "invalid": 0, "errors": 0, "remaining": 0}

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, email FROM leads_bruts
            WHERE email IS NOT NULL AND email != ''
              AND (email_valide != 'Valide' OR email_valide IS NULL OR email_valide = '')
            LIMIT ?
        """, (limit,)).fetchall()
        leads_to_check = [{"id": r["id"], "email": r["email"]} for r in rows]

    for lead in leads_to_check:
        result = validate_email_quick(lead["email"])
        status = "Valide" if result == "Valide" else ("Inconnu" if result == "Inconnu" else "Erreur")
        
        # Mettre à jour individuellement pour ne pas bloquer la DB
        try:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE leads_bruts SET email_valide = ? WHERE id = ?",
                    (status, lead["id"]),
                )
                conn.commit()
        except Exception as e:
            logger.error(f"[email_validator] Erreur DB MAJ email lead {lead['id']}: {e}")
            
        if status == "Valide":
            stats["validated"] += 1
        elif status == "Inconnu":
            stats["invalid"] += 1
        else:
            stats["errors"] += 1
        
        import time
        time.sleep(0.5)

    with get_conn() as conn:
        stats["remaining"] = conn.execute("""
            SELECT COUNT(*) FROM leads_bruts
            WHERE email IS NOT NULL AND email != ''
              AND (email_valide != 'Valide' OR email_valide IS NULL OR email_valide = '')
        """).fetchone()[0]

    return stats
