# -*- coding: utf-8 -*-
"""
Module envoi/resend_sender.py
Envoi d'emails de prospection via l'API Resend.
Lit RESEND_API_KEY, BREVO_SENDER_EMAIL, BREVO_SENDER_NAME depuis .env
Logs dans errors.log.
"""

import os
import logging
import requests
from typing import Dict, Any, Optional

from dotenv import load_dotenv

# Chargement du .env (dossier parent)
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Logging vers errors.log à la racine du projet
log_path = os.path.join(os.path.dirname(__file__), '..', 'errors.log')
logging.basicConfig(
    filename=log_path,
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# URL de l'API Resend
RESEND_API_URL = "https://api.resend.com/emails"


def get_next_resend_account():
    """Récupère le prochain compte disponible avec du quota."""
    from database.db_manager import get_conn
    with get_conn() as conn:
        conn.execute("UPDATE resend_accounts SET daily_usage = 0, last_reset = date('now') WHERE last_reset != date('now')")
        conn.commit()
        
        acc = conn.execute("""
            SELECT * FROM resend_accounts 
            WHERE actif = 1 AND daily_usage < 100 
            ORDER BY daily_usage ASC LIMIT 1
        """).fetchone()
        return dict(acc) if acc else None


def send_prospecting_email(
    prospect_email: str,
    prospect_nom: str,
    email_objet: str,
    email_corps: str,
    lien_rapport: Optional[str] = None,
    dry_run: bool = False,
    compte_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Envoie un email de prospection via Resend.

    Args:
        prospect_email  : Adresse email du destinataire
        prospect_nom    : Nom de l'établissement / prospect
        email_objet     : Objet de l'email
        email_corps     : Corps du mail
        lien_rapport    : Lien vers le rapport PDF (optionnel)
        dry_run         : Si True, simule l'envoi
        compte_id       : Pour compatibilité (non utilisé pour Resend pour l'instant)

    Returns:
        Dict avec clés : success (bool), statut (str), message_id (str|None), erreur (str|None)
    """

    # --- Substitution du lien rapport ---
    if lien_rapport and "[lien rapport]" in email_corps:
        email_corps = email_corps.replace("[lien rapport]", lien_rapport)

    # --- Mode dry run ---
    if dry_run:
        print(f"[DRY RUN RESEND] À : {prospect_email}")
        print(f"[DRY RUN RESEND] Objet : {email_objet}")
        return {
            "success": True,
            "statut": "dry_run",
            "message_id": None,
            "erreur": None
        }

    # --- Lecture des clés ---
    try:
        acc = get_next_resend_account()
        if not acc:
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from config_manager import get_config
            config = get_config()
            resend_key = config.get("resend_key")
            sender_email = os.getenv("BREVO_SENDER_EMAIL", "jmedansi@incidenx.com")
            sender_name = os.getenv("BREVO_SENDER_NAME", "Jean-Marc DANSI")
        else:
            resend_key = acc['api_key']
            sender_email = acc['sender_email']
            sender_name = acc['sender_name']
            account_id = acc['id']
    except Exception as e:
        msg = f"Erreur chargement config : {e}"
        logger.error(msg)
        return {"success": False, "statut": "erreur_config", "message_id": None, "erreur": msg}

    if not resend_key:
        msg = "RESEND_API_KEY manquante dans config_manager / .env"
        logger.error(msg)
        return {"success": False, "statut": "erreur_config", "message_id": None, "erreur": msg}

    # --- Payload Resend ---
    headers = {
        "Authorization": f"Bearer {resend_key}",
        "Content-Type": "application/json"
    }
    
    # Resend préfère HTML
    # Si le corps contient déjà de l'HTML (via email_builder), on l'utilise tel quel
    if email_corps.strip().startswith("<!DOCTYPE html>") or "<html" in email_corps.lower():
        html_content = email_corps
    else:
        html_content = email_corps.replace("\n", "<br>")
    
    payload = {
        "from": f"{sender_name} <onboarding@resend.dev>" if "resend.dev" in sender_email else f"{sender_name} <{sender_email}>",
        "to": [prospect_email],
        "subject": email_objet,
        "html": html_content
    }

    # Note: Si le domaine n'est pas vérifié sur Resend, il faut utiliser "onboarding@resend.dev"
    # L'utilisateur a probablement configuré son domaine, mais par sécurité je garde un fallback
    # si le sender_email n'est pas encore prêt.
    
    # --- Envoi ---
    try:
        response = requests.post(RESEND_API_URL, json=payload, headers=headers, timeout=15)
        response.raise_for_status()

        data = response.json()
        message_id = data.get("id", "")

        if 'account_id' in locals():
            from database.db_manager import get_conn
            with get_conn() as conn:
                conn.execute("UPDATE resend_accounts SET daily_usage = daily_usage + 1 WHERE id = ?", (account_id,))
                conn.commit()

        return {
            "success": True,
            "statut": "envoye",
            "message_id": message_id,
            "erreur": None
        }

    except Exception as e:
        msg = f"Erreur envoi Resend: {e}"
        if 'response' in locals():
            msg += f" | {response.text}"
        logger.error(f"send_prospecting_email → {msg}")
        return {"success": False, "statut": "erreur_inattendue", "message_id": None, "erreur": msg}


def schedule_email_batch(lead_ids: list, scheduled_at) -> list:
    """
    Programme l'envoi de N emails sur Resend à l'heure scheduled_at (datetime Europe/Paris).
    Enregistre chaque email dans emails_envoyes avec statut 'scheduled'.
    Retourne la liste des message_ids Resend (un par email réussi).
    """
    import sys, json
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from config_manager import get_config
    from database.db_manager import get_conn

    acc = get_next_resend_account()
    if not acc:
        config   = get_config()
        api_key  = config.get("resend_key")
        sender_email = os.getenv("BREVO_SENDER_EMAIL", "jmedansi@incidenx.com")
        sender_name  = os.getenv("BREVO_SENDER_NAME", "Jean-Marc DANSI")
        current_account_id = None
    else:
        api_key = acc['api_key']
        sender_email = acc['sender_email']
        sender_name = acc['sender_name']
        current_account_id = acc['id']

    if not api_key:
        logger.error("schedule_email_batch: RESEND_API_KEY manquante")
        return []

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    scheduled_at_str = scheduled_at.isoformat() if hasattr(scheduled_at, 'isoformat') else str(scheduled_at)

    message_ids = []
    with get_conn() as conn:
        for lead_id in lead_ids:
            row = conn.execute("""
                SELECT lb.email, lb.nom, la.email_objet, la.email_corps, la.lien_rapport, la.template_variant
                FROM leads_bruts lb
                JOIN leads_audites la ON la.lead_id = lb.id
                WHERE lb.id = ?
                  AND la.approuve = 1
                  AND la.email_corps IS NOT NULL AND la.email_corps != ''
            """, (lead_id,)).fetchone()

            if not row or not row['email'] or not row['email_corps']:
                continue

            # Guard : ne pas re-programmer un lead déjà schedulé ou envoyé
            already = conn.execute(
                "SELECT id FROM emails_envoyes WHERE lead_id=? AND statut_envoi NOT IN ('cancelled','bounced')",
                (lead_id,)
            ).fetchone()
            if already:
                logger.warning(f"schedule_email_batch: lead #{lead_id} déjà dans emails_envoyes — ignoré")
                continue

            payload = {
                "from":         f"{sender_name} <{sender_email}>",
                "to":           [row['email']],
                "subject":      row['email_objet'] or "(sans objet)",
                "html":         row['email_corps'],
                "scheduled_at": scheduled_at_str,
            }
            try:
                r = requests.post(RESEND_API_URL, json=payload, headers=headers, timeout=15)
                r.raise_for_status()
                msg_id = r.json().get("id", "")
                if msg_id:
                    message_ids.append(msg_id)
                    conn.execute("""
                        INSERT INTO emails_envoyes
                            (lead_id, message_id_resend, email_objet, email_corps,
                             lien_rapport, email_destinataire, statut_envoi, template_variant)
                        VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?)
                    """, (lead_id, msg_id, row['email_objet'], row['email_corps'],
                          row['lien_rapport'], row['email'], row.get('template_variant', 'v1')))
                    conn.execute("UPDATE leads_bruts SET statut='scheduled' WHERE id=?", (lead_id,))
                    if current_account_id:
                        conn.execute("UPDATE resend_accounts SET daily_usage = daily_usage + 1 WHERE id = ?", (current_account_id,))
            except Exception as e:
                logger.error(f"schedule_email_batch lead #{lead_id}: {e}")

        conn.commit()

    logger.info(f"schedule_email_batch: {len(message_ids)}/{len(lead_ids)} emails programmés pour {scheduled_at_str}")
    return message_ids


def cancel_batch(message_ids: list) -> int:
    """
    Annule des emails schedulés sur Resend avant leur envoi.
    Retourne le nombre d'annulations réussies.
    """
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from config_manager import get_config

    api_key = get_config().get("resend_key")
    headers = {"Authorization": f"Bearer {api_key}"}
    cancelled = 0

    for msg_id in message_ids:
        try:
            r = requests.post(
                f"https://api.resend.com/emails/{msg_id}/cancel",
                headers=headers, timeout=10
            )
            if r.status_code in (200, 204):
                cancelled += 1
                logger.info(f"cancel_batch: {msg_id} annulé")
            else:
                logger.warning(f"cancel_batch: {msg_id} → {r.status_code} {r.text[:100]}")
        except Exception as e:
            logger.error(f"cancel_batch {msg_id}: {e}")

    return cancelled


def list_scheduled_emails() -> dict:
    """
    Interroge l'API Resend pour lister tous les emails programmés (scheduled).
    Retourne un dict avec la liste des emails et compteurs.
    """
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from config_manager import get_config

    config = get_config()
    resend_key = config.get("resend_key")
    if not resend_key:
        return {"error": "RESEND_API_KEY manquante"}

    headers = {"Authorization": f"Bearer {resend_key}"}
    result = {"scheduled": [], "sent": [], "errors": 0}

    try:
        r = requests.get("https://api.resend.com/emails", headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        for email in data.get("data", []):
            if email.get("scheduled_at"):
                result["scheduled"].append({
                    "id": email.get("id"),
                    "to": email.get("to"),
                    "subject": email.get("subject"),
                    "scheduled_at": email.get("scheduled_at"),
                    "last_event": email.get("last_event"),
                })
            else:
                result["sent"].append({
                    "id": email.get("id"),
                    "to": email.get("to"),
                    "subject": email.get("subject"),
                    "last_event": email.get("last_event"),
                })
        
        result["total_scheduled"] = len(result["scheduled"])
        result["total_sent"] = len(result["sent"])
        
    except Exception as e:
        result["error"] = str(e)

    return result


def sync_tracking() -> dict:
    """
    Sync complet du tracking depuis l'API Resend.
    Récupère tous les emails envoyés et met à jour la DB avec leur statut.
    
    Statuts Resend: sent, delivered, opened, clicked, bounced, complained
    """
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from config_manager import get_config
    from database.db_manager import get_conn

    config = get_config()
    resend_key = config.get("resend_key")
    if not resend_key:
        return {"error": "RESEND_API_KEY manquante"}

    headers = {"Authorization": f"Bearer {resend_key}"}
    stats = {"checked": 0, "updated": 0, "errors": 0, "not_found": 0}

    all_emails = []
    cursor = None

    while True:
        url = "https://api.resend.com/emails?limit=100"
        if cursor:
            url += f"&cursor={cursor}"
        try:
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            return {"error": f"API Resend: {e}"}

        all_emails.extend(data.get("data", []))
        cursor = data.get("next_cursor")
        if not cursor:
            break

    with get_conn() as conn:
        for email in all_emails:
            recipients = email.get("to", [])
            if not recipients:
                continue
            
            recipient_email = recipients[0]
            last_event = email.get("last_event", "")
            created_at = email.get("created_at", "")
            
            row = conn.execute("""
                SELECT id FROM emails_envoyes 
                WHERE email_destinataire = ? AND message_id_resend = ?
            """, (recipient_email, email.get("id"))).fetchone()

            if not row:
                stats["not_found"] += 1
                continue

            email_id = row["id"]
            stats["checked"] += 1

            updates = []
            params = []

            if not last_event or last_event == "sent":
                continue

            if last_event == "opened":
                updates.extend(["ouvert = 1", "nb_ouvertures = nb_ouvertures + 1"])
                if created_at:
                    updates.append("date_ouverture = ?")
                    params.append(created_at)
            elif last_event == "clicked":
                updates.extend(["clique = 1"])
                if created_at:
                    updates.append("date_clic = ?")
                    params.append(created_at)
            elif last_event in ("bounced", "delivery_delayed"):
                updates.extend(["bounce = 1", "statut_envoi = ?"])
                params.append("bounced")
            elif last_event == "complained":
                updates.extend(["spam = 1", "statut_envoi = ?"])
                params.append("spam")
            elif last_event == "delivered":
                updates.append("statut_envoi = ?")
                params.append("delivré")
            
            if updates:
                params.append(email_id)
                try:
                    conn.execute(f"UPDATE emails_envoyes SET {', '.join(updates)} WHERE id = ?", params)
                    stats["updated"] += 1
                except Exception as e:
                    stats["errors"] += 1

        conn.commit()

    print(f"Sync terminée — {stats['checked']} vérifiés, {stats['updated']} mis à jour, {stats['not_found']} non trouvés")
    return stats


def check_bounces() -> dict:
    """
    Interroge l'API Resend pour mettre à jour les statuts bounce/spam
    de tous les emails envoyés qui ont un message_id_resend.

    Nécessite une clé API Resend avec permission de lecture (pas juste 'send').
    Créer une clé full-access dans : resend.com/api-keys

    Retourne un dict avec les compteurs : checked, bounced, spam, errors
    """
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from config_manager import get_config
    from database.db_manager import get_conn

    config = get_config()
    resend_key = config.get("resend_key")
    if not resend_key:
        return {"error": "RESEND_API_KEY manquante"}

    headers = {"Authorization": f"Bearer {resend_key}"}
    stats = {"checked": 0, "bounced": 0, "spam": 0, "errors": 0}

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, message_id_resend FROM emails_envoyes WHERE message_id_resend IS NOT NULL AND bounce=0 AND spam=0"
        ).fetchall()

        for row in rows:
            try:
                r = requests.get(
                    f"https://api.resend.com/emails/{row['message_id_resend']}",
                    headers=headers,
                    timeout=10
                )
                if r.status_code == 401:
                    return {"error": "Clé API sans permission lecture — créer une clé full-access sur resend.com/api-keys"}
                if r.status_code != 200:
                    stats["errors"] += 1
                    continue

                data = r.json()
                last_event = data.get("last_event", "")
                stats["checked"] += 1

                is_bounce = last_event in ("bounced", "delivery_delayed")
                is_spam = last_event in ("complained",)

                if is_bounce or is_spam:
                    conn.execute(
                        "UPDATE emails_envoyes SET bounce=?, spam=?, statut_envoi=? WHERE id=?",
                        (1 if is_bounce else 0, 1 if is_spam else 0, last_event, row["id"])
                    )
                    if is_bounce:
                        stats["bounced"] += 1
                        print(f"  [BOUNCE] email_id={row['id']} | event={last_event}")
                    if is_spam:
                        stats["spam"] += 1
                        print(f"  [SPAM]   email_id={row['id']} | event={last_event}")

            except Exception as e:
                stats["errors"] += 1
                logger.error(f"check_bounces: {e}")

        conn.commit()

    return stats


if __name__ == "__main__":
    import argparse
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

    parser = argparse.ArgumentParser(description="Resend sender - CLI")
    parser.add_argument("--lead-id", type=int, help="ID du lead dans leads_bruts")
    parser.add_argument("--dry-run", action="store_true", help="Simulation sans envoi réel")
    parser.add_argument("--sync-tracking", action="store_true", help="Sync le tracking depuis Resend")
    args = parser.parse_args()

    if args.sync_tracking:
        result = sync_tracking()
        if "error" in result:
            print(f"[ERROR] {result['error']}")
            sys.exit(1)
        sys.exit(0)

    if not args.lead_id:
        parser.error("--lead-id requis (ou --sync-tracking)")

    from database.db_manager import get_conn

    with get_conn() as conn:
        row = conn.execute("""
            SELECT lb.email, lb.nom, la.email_objet, la.email_corps, la.lien_rapport, la.template_variant
            FROM leads_bruts lb
            JOIN leads_audites la ON la.lead_id = lb.id
            WHERE lb.id = ? AND la.approuve = 1
              AND (la.email_objet IS NOT NULL AND la.email_objet != '')
        """, (args.lead_id,)).fetchone()

    if not row:
        print(f"[ERROR] Lead #{args.lead_id} introuvable ou non approuvé.")
        sys.exit(1)

    d = dict(row)
    result = send_prospecting_email(
        prospect_email=d['email'],
        prospect_nom=d['nom'],
        email_objet=d['email_objet'],
        email_corps=d['email_corps'],
        lien_rapport=d.get('lien_rapport'),
        dry_run=args.dry_run,
    )

    if result['success']:
        if not args.dry_run:
            with get_conn() as conn:
                conn.execute("""
                    INSERT INTO emails_envoyes
                        (lead_id, message_id_resend, email_objet, email_corps, lien_rapport, template_variant)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (args.lead_id, result.get('message_id'),
                      d['email_objet'], d['email_corps'], d.get('lien_rapport'), d.get('template_variant', 'v1')))
                conn.execute(
                    "UPDATE leads_bruts SET statut='envoye' WHERE id=?",
                    (args.lead_id,)
                )
                conn.commit()
        print(f"[OK] Email envoyé à {d['email']}")
        sys.exit(0)
    else:
        print(f"[ERROR] {result.get('erreur')}")
        sys.exit(1)
