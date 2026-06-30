import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from envoi.resend_sender import get_message_status

DB = ROOT / 'data' / 'prospection.db'


def pretty_print(data):
    import json
    print(json.dumps(data, indent=2, ensure_ascii=False))


def get_message_id_for_lead(conn, lead_id):
    row = conn.execute(
        'SELECT message_id_resend, email_destinataire, statut_envoi FROM emails_envoyes WHERE lead_id=? ORDER BY id DESC LIMIT 1',
        (lead_id,),
    ).fetchone()
    return row


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Vérifie le statut Resend d un message envoyé')
    parser.add_argument('--lead-id', type=int, help='ID du lead dans leads_bruts')
    parser.add_argument('--message-id', help='message_id_resend dans emails_envoyes')
    args = parser.parse_args()

    if not args.lead_id and not args.message_id:
        parser.error('Il faut préciser --lead-id ou --message-id')

    message_id = args.message_id
    if args.lead_id:
        with sqlite3.connect(DB) as conn:
            conn.row_factory = sqlite3.Row
            row = get_message_id_for_lead(conn, args.lead_id)
            if not row:
                print(f'Pas de record emails_envoyes pour lead_id={args.lead_id}')
                sys.exit(1)
            message_id = row['message_id_resend']
            print(f"Lead {args.lead_id} → message_id_resend={message_id}, statut_envoi={row['statut_envoi']}, destinataire={row['email_destinataire']}")

    result = get_message_status(message_id)
    if not result.get('success'):
        print(f"[ERROR] {result.get('error')}")
        sys.exit(1)

    pretty_print(result['data'])


if __name__ == '__main__':
    main()
