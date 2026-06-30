import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from envoi.resend_sender import schedule_email_batch

DB = 'data/prospection.db'

EMAIL_SUBJECT = 'Vos patientes du soir et du weekend'
EMAIL_BODY_TEXT = '''Bonjour,

Quand une patiente demande un renseignement sur une prestation un soir ou un weekend, que se passe-t-il ensuite ?
La plupart des cliniques envoient une réponse automatique. Mais sans relance, elle prend rendez-vous ailleurs dans les 24 heures.

Je mets en place un système complet : réponse en moins de 2 minutes, relances automatiques à J+1, J+3 et J+7, notification à votre équipe quand la patiente est prête à réserver.

Résultat : vous ne perdez plus aucune patiente faute de suivi.

15 minutes pour voir si c'est pertinent pour vous ?

Jean-Marc DANSI'''

LIST_SCHEDULES = {
    'Cliniques Esthétiques — 25 leads non contactés (7/13)': 6,
    'Cliniques Esthétiques — 25 leads non contactés (8/13)': 10,
    'Cliniques Esthétiques — 25 leads non contactés (9/13)': 15,
}

PARIS = ZoneInfo('Europe/Paris')

EMAIL_BODY_HTML = '<p>' + EMAIL_BODY_TEXT.replace('\n\n', '</p><p>').replace('\n', '<br>') + '</p>'

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def is_valid_email(email: str) -> bool:
    return bool(email and EMAIL_RE.match(email.strip()))


def next_scheduled_at(hour: int) -> datetime:
    now = datetime.now(PARIS)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def prepare_leads_audites(conn, lead_ids):
    for lead_id in lead_ids:
        row = conn.execute('SELECT id, nom, email, email_valide FROM leads_bruts WHERE id=?', (lead_id,)).fetchone()
        if not row:
            continue

        email = row['email'] or ''
        if not is_valid_email(email) and is_valid_email(row['email_valide'] or ''):
            email = row['email_valide'].strip()
            conn.execute('UPDATE leads_bruts SET email=? WHERE id=?', (email, lead_id))

        if not is_valid_email(email):
            continue

        # Ensure a leads_audites row exists with approved email content.
        existing = conn.execute('SELECT id FROM leads_audites WHERE lead_id=?', (lead_id,)).fetchone()
        lien_rapport = f"https://audit.incidenx.com/{re.sub(r'[^a-zA-Z0-9]+', '-', (row['nom'] or '').lower()).strip('-')}"
        if existing:
            conn.execute(
                '''UPDATE leads_audites SET email_objet=?, email_corps=?, approuve=1, lien_rapport=?, statut='audite' WHERE lead_id=?''',
                (EMAIL_SUBJECT, EMAIL_BODY_HTML, lien_rapport, lead_id)
            )
        else:
            conn.execute(
                '''INSERT INTO leads_audites (lead_id, email_objet, email_corps, approuve, lien_rapport, statut, template_variant) VALUES (?, ?, ?, 1, ?, 'audite', 'v1')''',
                (lead_id, EMAIL_SUBJECT, EMAIL_BODY_HTML, lien_rapport)
            )


def get_lead_ids_for_list(conn, list_name):
    row = conn.execute('SELECT id FROM lead_lists WHERE nom=?', (list_name,)).fetchone()
    if not row:
        return []
    list_id = row['id']
    return [r[0] for r in conn.execute('SELECT lead_id FROM lead_list_items WHERE list_id=? ORDER BY lead_id', (list_id,)).fetchall()]


def main():
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        results = {}
        for list_name, hour in LIST_SCHEDULES.items():
            lead_ids = get_lead_ids_for_list(conn, list_name)
            if not lead_ids:
                print(f'Liste introuvable ou vide: {list_name}')
                continue

            prepare_leads_audites(conn, lead_ids)
            scheduled_at = next_scheduled_at(hour)
            print(f"Programmation de {len(lead_ids)} leads de '{list_name}' pour {scheduled_at.isoformat()}")

            message_ids = schedule_email_batch(lead_ids, scheduled_at)
            results[list_name] = {
                'scheduled_at': scheduled_at.isoformat(),
                'lead_count': len(lead_ids),
                'scheduled_messages': len(message_ids),
            }

        print('\nRécapitulatif:')
        for list_name, result in results.items():
            print(f"- {list_name}: {result['scheduled_messages']}/{result['lead_count']} programmés à {result['scheduled_at']}")


if __name__ == '__main__':
    main()
