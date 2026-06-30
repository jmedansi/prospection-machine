import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from envoi.resend_sender import send_prospecting_email

DB = ROOT / 'data' / 'prospection.db'
LIST_NAMES = [
    'Cliniques Esthétiques — 25 leads non contactés (9/13)'
]


def is_valid_email(email: str) -> bool:
    return bool(email and '@' in email and '.' in email)


def is_already_sent_or_scheduled(conn: sqlite3.Connection, lead_id: int) -> bool:
    cur = conn.cursor()
    row = cur.execute(
        "SELECT 1 FROM emails_envoyes WHERE lead_id=? AND statut_envoi IN ('envoye','scheduled') LIMIT 1",
        (lead_id,),
    ).fetchone()
    return bool(row)


def send_list(list_name: str, conn: sqlite3.Connection):
    cur = conn.cursor()
    lid_row = cur.execute('SELECT id FROM lead_lists WHERE nom=?', (list_name,)).fetchone()
    if not lid_row:
        print(f'[ERROR] Liste introuvable: {list_name}')
        return

    list_id = lid_row[0]
    lead_ids = [row[0] for row in cur.execute('SELECT lead_id FROM lead_list_items WHERE list_id=? ORDER BY lead_id', (list_id,)).fetchall()]
    print(f'Envoi direct pour {list_name}: {len(lead_ids)} leads')

    results = {'sent': 0, 'skipped': 0, 'failed': 0}

    for lead_id in lead_ids:
        row = cur.execute(
            '''SELECT lb.id, lb.nom, lb.email, lb.email_2, la.email_objet, la.email_corps, la.lien_rapport, la.template_variant
               FROM leads_bruts lb
               JOIN leads_audites la ON la.lead_id = lb.id
               WHERE lb.id = ? AND la.approuve = 1 AND la.email_corps IS NOT NULL AND la.email_corps != '' ''',
            (lead_id,),
        ).fetchone()
        if not row:
            results['skipped'] += 1
            continue

        lead = dict(row)
        if is_already_sent_or_scheduled(conn, lead_id):
            results['skipped'] += 1
            continue

        email = lead['email'] or ''
        if not is_valid_email(email):
            results['skipped'] += 1
            continue

        to_email = email.strip()
        response = send_prospecting_email(
            prospect_email=to_email,
            prospect_nom=lead['nom'] or '',
            email_objet=lead['email_objet'],
            email_corps=lead['email_corps'],
            lien_rapport=lead['lien_rapport'],
            dry_run=False,
        )

        if response.get('success'):
            results['sent'] += 1
            cur.execute(
                '''INSERT INTO emails_envoyes
                   (lead_id, message_id_resend, email_objet, email_corps, lien_rapport,
                    email_destinataire, statut_envoi, template_variant)
                   VALUES (?, ?, ?, ?, ?, ?, 'envoye', ?)''',
                (
                    lead_id,
                    response.get('message_id'),
                    lead['email_objet'],
                    lead['email_corps'],
                    lead['lien_rapport'],
                    to_email,
                    lead.get('template_variant') or 'v1',
                ),
            )
            cur.execute("UPDATE leads_bruts SET statut='envoye' WHERE id=?", (lead_id,))
        else:
            results['failed'] += 1
            cur.execute(
                '''INSERT INTO emails_envoyes
                   (lead_id, email_objet, email_corps, lien_rapport, email_destinataire,
                    statut_envoi, message_erreur, template_variant)
                   VALUES (?, ?, ?, ?, ?, 'erreur', ?, ?)''',
                (
                    lead_id,
                    lead['email_objet'],
                    lead['email_corps'],
                    lead['lien_rapport'],
                    to_email,
                    response.get('erreur') or 'unknown',
                    lead.get('template_variant') or 'v1',
                ),
            )
        conn.commit()

    print(f"  résultat {list_name}: sent={results['sent']}, skipped={results['skipped']}, failed={results['failed']}")


def main():
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        for name in LIST_NAMES:
            send_list(name, conn)


if __name__ == '__main__':
    main()
