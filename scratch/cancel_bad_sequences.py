# -*- coding: utf-8 -*-
"""
scratch/cancel_bad_sequences.py
Annule les sequences dont l'email destinataire est invalide ou non pertinent.
"""
import sys
sys.path.insert(0, r'd:\prospection-machine')

from database.connection import get_conn

# IDs a annuler : emails invalides ou plateformes/grandes marques
TO_CANCEL = [2, 3, 5, 7, 13, 21, 25, 37, 47, 51, 57, 59]

with get_conn() as conn:
    placeholders = ','.join('?' * len(TO_CANCEL))
    sql = f"UPDATE email_sequences SET statut='cancelled' WHERE id IN ({placeholders})"
    conn.execute(sql, TO_CANCEL)
    conn.commit()
    remaining = conn.execute(
        "SELECT COUNT(*) FROM email_sequences WHERE statut='pending_approval'"
    ).fetchone()[0]
    print(f"[OK] {len(TO_CANCEL)} sequences annulees.")
    print(f"     Restantes en attente d'envoi : {remaining}")
    
    print("\nListe des sequences encore en attente :")
    rows = conn.execute("""
        SELECT seq.id, ee.email_destinataire, lb.nom
        FROM email_sequences seq
        JOIN emails_envoyes ee ON ee.id = seq.email_record_id
        JOIN leads_audites la ON la.id = seq.lead_id
        JOIN leads_bruts lb ON lb.id = la.lead_id
        WHERE seq.statut = 'pending_approval'
        ORDER BY seq.id
    """).fetchall()
    for r in rows:
        print(f"  #{r['id']:3d} | {r['email_destinataire']:<50s} | {r['nom']}")
