# -*- coding: utf-8 -*-
"""
scratch/retroactive_sequences.py
Rattrapage des sequences de relances pour les leads déjà contactés.

Ce script :
  1. Supprime TOUTES les séquences existantes non encore envoyées (mal créées lors des tests)
  2. Pour chaque email envoyé sans aucune séquence 'sent', crée UNIQUEMENT la relance_1
     avec date_planifiee = maintenant (pour déclenchement immédiat par le worker)
  3. N'envoie rien — c'est le worker + Telegram qui déclenchent l'envoi
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, r'd:\prospection-machine')

from database.connection import get_conn

NOW = datetime.now().isoformat()


def run():
    with get_conn() as conn:
        # ──────────────────────────────────────────────────────────────────────
        # ÉTAPE 1 : Nettoyage des séquences planned / pending_approval existantes
        # ──────────────────────────────────────────────────────────────────────
        deleted = conn.execute(
            "DELETE FROM email_sequences WHERE statut IN ('planned', 'pending_approval')"
        ).rowcount
        conn.commit()
        print(f"[NETTOYAGE] {deleted} séquences en attente supprimées.")

        # ──────────────────────────────────────────────────────────────────────
        # ÉTAPE 2 : Identifier les emails envoyés sans AUCUNE relance 'sent'
        # ──────────────────────────────────────────────────────────────────────
        # On cherche les emails envoyés dont le lead n'a PAS reçu de relance déjà
        # transmise (statut='sent'). On joint avec leads_audites pour avoir le
        # bon lead_id (FK vers leads_audites.id, pas leads_bruts.id).
        rows = conn.execute("""
            SELECT
                ee.id  AS email_record_id,
                la.id  AS la_id,
                lb.nom,
                ee.email_destinataire,
                ee.date_envoi
            FROM emails_envoyes ee
            JOIN leads_bruts   lb ON lb.id = ee.lead_id
            JOIN leads_audites la ON la.lead_id = ee.lead_id
            WHERE ee.lead_id IS NOT NULL
              AND ee.statut_envoi IN ('envoye', 'scheduled', 'sent', '')
              AND ee.email_destinataire IS NOT NULL
              AND ee.email_destinataire != ''
              -- Exclure les leads qui ont deja une relance envoyee
              AND la.id NOT IN (
                  SELECT lead_id FROM email_sequences WHERE statut = 'sent'
              )
            GROUP BY la.id          -- UN seul enregistrement par lead_audite
            HAVING ee.id = MAX(ee.id)  -- garder le dernier email envoye
            ORDER BY ee.date_envoi ASC
        """).fetchall()

        if not rows:
            print("[INFO] Aucun email trouvé à rattraper.")
            return

        print(f"\n[RATTRAPAGE] {len(rows)} leads à rattraper avec relance_1...\n")

        # ──────────────────────────────────────────────────────────────────────
        # ÉTAPE 3 : Créer uniquement la relance_1 avec date = maintenant
        # ──────────────────────────────────────────────────────────────────────
        inserted = 0
        for row in rows:
            email_record_id = row['email_record_id']
            la_id           = row['la_id']
            nom             = row['nom'] or '?'
            email           = row['email_destinataire'] or '?'

            try:
                conn.execute("""
                    INSERT INTO email_sequences
                        (lead_id, email_record_id, email_type, statut,
                         date_planifiee, condition_envoi, created_at)
                    VALUES (?, ?, 'relance_1', 'planned', ?, ?, ?)
                """, (
                    la_id,
                    email_record_id,
                    NOW,                               # date = maintenant → éligible immédiatement
                    json.dumps({'nb_clics': 0}),
                    NOW,
                ))
                inserted += 1
                print(f"  [OK] Lead #{la_id} ({nom} / {email})")
            except Exception as e:
                print(f"  [ERR] Erreur pour la_id={la_id} email_id={email_record_id}: {e}")

        conn.commit()
        print(f"\n[DONE] {inserted}/{len(rows)} séquences relance_1 créées.")
        print(
            "\nProchaine etape : lancer le sequence_worker pour generer les emails\n"
            "  -> python -m workers.sequence_worker\n"
            "Ensuite, valide sur Telegram avec le bouton '[OK] Tout approuver'."
        )


if __name__ == '__main__':
    run()
