# -*- coding: utf-8 -*-
"""
scripts/catchup_relances.py — Script sécurisé d'audit et de rattrapage des relances en retard.

Usage:
    # 1. Audit en mode simulation (zéro envoi, mode par défaut) :
    python scripts/catchup_relances.py --dry-run

    # 2. Audit ciblé sur une liste spécifique :
    python scripts/catchup_relances.py --liste-id 155 --dry-run
    python scripts/catchup_relances.py --liste-id 180 --dry-run
    python scripts/catchup_relances.py --liste-id 181 --dry-run

    # 3. Réinitialiser les verrous Telegram bloqués :
    python scripts/catchup_relances.py --reset-locks

    # 4. Envoi réel et sécurisé (exige --send ET --confirm) :
    python scripts/catchup_relances.py --liste-id 155 --send --confirm
"""
import os
import sys
import sqlite3
import argparse
from datetime import datetime, timedelta

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ajouter la racine du projet au path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from database.connection import get_conn
from core.config import HUB_TELEGRAM
from core.orchestration import relances_due, is_business_day, add_business_days
from envoi import sequence_engine, template_registry


def get_overdue_relances(campagne_id=None, liste_id=None):
    """Récupère tous les prospects dont la relance est due, avec le détail des étapes."""
    due = relances_due(campagne_id=campagne_id, liste_id=liste_id)
    now = datetime.now()

    enriched = []
    for item in due:
        pid = item['id']
        st = item['statut']
        position = item['position']
        lid = item['liste_id']
        lnom = item['liste_nom']
        last_touch = item['last_touch_at']

        # Infos prospect
        with get_conn() as conn:
            p = conn.execute(
                "SELECT nom, email, entreprise FROM prospects WHERE id = ?", (pid,)
            ).fetchone()
            cid_row = conn.execute(
                "SELECT campagne_id FROM listes WHERE id = ?", (lid,)
            ).fetchone()
        cid = cid_row['campagne_id'] if cid_row else campagne_id

        # Template de l'étape courante à envoyer
        tpl_cur = template_registry.get_step(cid, position=position)
        step_name = f"Relance {position}"
        step_objet = (tpl_cur.get('objet') or '') if tpl_cur else ''

        # Template de l'étape SUIVANTE pour calculer la date future si envoyé aujourd'hui
        next_pos = position + 1
        tpl_next = template_registry.get_step(cid, position=next_pos)
        if tpl_next:
            delai_suiv = int(tpl_next.get('delai_jours') or 0)
            date_suivante = add_business_days(now, delai_suiv)
            date_suivante_str = date_suivante.strftime('%Y-%m-%d (%A)')
            delai_info = f"+{delai_suiv} j ouvrés → {date_suivante_str}"
        else:
            delai_info = "Fin de cycle (dernière étape)"

        enriched.append({
            'prospect_id': pid,
            'nom': p['nom'] if p else '—',
            'entreprise': p['entreprise'] if p else '—',
            'email': p['email'] if p else '—',
            'statut_actuel': st,
            'position': position,
            'step_name': step_name,
            'step_objet': step_objet,
            'liste_id': lid,
            'liste_nom': lnom,
            'campagne_id': cid,
            'last_touch_at': last_touch,
            'prochaine_relance_si_envoye_ajd': delai_info,
        })
    return enriched


def reset_stuck_locks(liste_ids=None):
    """Purge les verrous Telegram et les lots figés dans relance_batches et pending.db."""
    print("\n[LOCKS] Réinitialisation des verrous de relances...")
    with get_conn() as conn:
        if liste_ids:
            ph = ",".join("?" * len(liste_ids))
            cur = conn.execute(f"DELETE FROM relance_batches WHERE liste_id IN ({ph})", liste_ids)
        else:
            cur = conn.execute("DELETE FROM relance_batches")
        conn.commit()
        print(f"  → relance_batches : {cur.rowcount} enregistrement(s) réinitialisé(s).")

    # Purge pending.db dans HUB_TELEGRAM
    pending_path = os.path.join(HUB_TELEGRAM, 'pending.db')
    if os.path.exists(pending_path):
        try:
            hconn = sqlite3.connect(pending_path)
            if liste_ids:
                for lid in liste_ids:
                    cb = f"%_{lid}"
                    hconn.execute("DELETE FROM pending WHERE callback_id LIKE ?", (cb,))
            else:
                hconn.execute("DELETE FROM pending WHERE callback_id LIKE 'v2_batch_%'")
            hconn.commit()
            hconn.close()
            print("  → pending.db (Hub Telegram) : callbacks purgés avec succès.")
        except Exception as e:
            print(f"  ⚠️ pending.db erreur purge : {e}")
    print("[LOCKS] Terminé.\n")


def display_audit_table(items):
    """Affiche un tableau lisible et clair des prospects en retard."""
    if not items:
        print("\n✅ Aucune relance en retard trouvée.")
        return

    print(f"\n{'='*110}")
    print(f"  AUDIT DES RELANCES EN RETARD : {len(items)} prospect(s) éligible(s)")
    print(f"{'='*110}")

    # Regrouper par liste
    by_list = {}
    for it in items:
        by_list.setdefault((it['liste_id'], it['liste_nom']), []).append(it)

    for (lid, lnom), leads in by_list.items():
        print(f"\n📂 Liste #{lid} : « {lnom} » — {len(leads)} prospect(s)")
        print(f"   {'-'*104}")
        print(f"   {'ID':<6} | {'Nom / Société':<28} | {'Étape due':<11} | {'Dernier contact':<19} | {'Prochaine relance si envoyé ajd'}")
        print(f"   {'-'*104}")
        for l in leads:
            nom = (l['nom'] or l['entreprise'] or '—')[:26]
            print(f"   #{l['prospect_id']:<5} | {nom:<28} | {l['step_name']:<11} | {str(l['last_touch_at'])[:19]:<19} | {l['prochaine_relance_si_envoye_ajd']}")

    print(f"\n{'='*110}\n")


def run_send(items, max_count=None):
    """Exécute l'envoi contrôlé avec respect des sécurités et des pauses."""
    from envoi import gateway
    from core import orchestration

    # Vérification du master killswitch
    if not gateway.live_email_allowed():
        print("\n🚨 ERREUR CRITIQUE DE SÉCURITÉ :")
        print("  L'envoi réel est désactivé par sécurité.")
        print("  Pour autoriser l'envoi réel, définissez la variable d'environnement :")
        print("     $env:ALLOW_LIVE_EMAILS=\"1\"   (PowerShell)")
        print("     set ALLOW_LIVE_EMAILS=1        (CMD)\n")
        return

    # Vérification de la fenêtre horaire
    if not orchestration.is_fenetre_relances():
        print("\n⚠️ ATTENTION : Vous êtes hors de la fenêtre d'envoi habituelle (9h-18h ouvrés).")
        rep = input("Voulez-vous tout de même forcer l'envoi maintenant ? (oui/non) : ").strip().lower()
        if rep not in ('oui', 'o', 'yes', 'y'):
            print("Envoi annulé.")
            return

    to_process = items[:max_count] if max_count else items
    print(f"\n🚀 DÉMARRAGE DE L'ENVOI pour {len(to_process)} prospect(s)...")

    # Regrouper par liste pour exécuter via l'orchestrateur sécurisé
    by_list = {}
    for it in to_process:
        by_list.setdefault((it['campagne_id'], it['liste_id'], it['liste_nom']), []).append(it['prospect_id'])

    total_envoyes = 0
    total_bloques = 0

    for (cid, lid, lnom), pids in by_list.items():
        print(f"\n--- Traitement de la liste #{lid} : « {lnom} » ({len(pids)} leads) ---")
        res = orchestration.run_relances(
            campagne_id=cid,
            liste_id=lid,
            prospect_ids=pids,
            approval='auto',
            manual=True,
            limit_per_campagne=len(pids),
        )

        for r in res.get('runs', []):
            for d in r.get('details', []):
                st = d.get('statut')
                pid = d.get('prospect_id')
                if st == 'envoye':
                    total_envoyes += 1
                    print(f"  ✅ Prospect #{pid} : Relance envoyée avec succès.")
                else:
                    total_bloques += 1
                    print(f"  ⚠️ Prospect #{pid} : Statut = {st} ({d.get('message')})")

    print(f"\n{'='*60}")
    print(f"  BILAN : {total_envoyes} email(s) envoyé(s), {total_bloques} ignoré(s)/bloqué(s).")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Audit et rattrapage des relances en retard.")
    parser.add_argument('--campagne-id', type=int, default=44, help="ID de la campagne (défaut 44)")
    parser.add_argument('--liste-id', type=int, help="Filtrer sur une liste spécifique (ex: 155, 180, 181)")
    parser.add_argument('--dry-run', action='store_true', default=True, help="Mode audit / simulation (défaut)")
    parser.add_argument('--send', action='store_true', help="Déclencher l'envoi réel")
    parser.add_argument('--confirm', action='store_true', help="Confirmer l'envoi réel sans invite")
    parser.add_argument('--limit', type=int, help="Nombre max d'emails à envoyer")
    parser.add_argument('--reset-locks', action='store_true', help="Réinitialiser les verrous Telegram bloqués")

    args = parser.parse_args()

    # Si --reset-locks est demandé
    if args.reset_locks:
        lids = [args.liste_id] if args.liste_id else [155, 180, 181]
        reset_stuck_locks(lids)

    # Récupérer les relances dues
    items = get_overdue_relances(campagne_id=args.campagne_id, liste_id=args.liste_id)

    # Affichage du rapport
    display_audit_table(items)

    # Si --send est demandé
    if args.send:
        if not args.confirm:
            print("⚠️ Pour exécuter l'envoi réel, vous devez ajouter l'option --confirm.")
            return
        run_send(items, max_count=args.limit)


if __name__ == '__main__':
    main()
