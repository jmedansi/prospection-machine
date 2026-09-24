# -*- coding: utf-8 -*-
"""
core/state_machine.py — Machine à états explicite du prospect (spec §2).

Statuts et transitions de `prompt-prospection-machine-saas.md` :

    qualifie -> en_sequence -> relance_1 -> relance_2 -> relance_N -> sans_reponse
    en_sequence/relance_* -> (réponse) -> a_traiter_humain -> {rdv_obtenu | pas_interesse | a_relancer_plus_tard}
    * -> ne_plus_contacter      (désinscription — définitif, toutes campagnes futures)
    * -> adresse_invalide       (bounce dur — fermé, retiré de la base)

Règle de sécurité (spec §2) : toute réponse entrante doit suspendre immédiatement
les relances automatiques -> transition vers `a_traiter_humain`.

Aucune logique d'état ne doit vivre ailleurs que dans ce module.
"""
import json
import logging
from datetime import datetime

from database.connection import get_conn

logger = logging.getLogger(__name__)

STATUT_INITIAL = 'qualifie'

STATUTS = {
    'qualifie',             # entré en base, pas encore séquencé
    'en_sequence',          # email initial envoyé, relances programmées
    'relance_1',
    'relance_2',
    'relance_3',
    'sans_reponse',         # fin de cycle sans réponse -> fermé automatiquement
    'a_traiter_humain',     # réponse détectée -> file humaine unifiée
    'rdv_obtenu',
    'pas_interesse',
    'a_relancer_plus_tard',
    'ne_plus_contacter',    # transactionnel: désinscription / opposition
    'adresse_invalide',     # transactionnel: bounce dur
}

# statuts qui mettent fin au cycle d'envoi automatique
FINAL_STATUTS = {
    'sans_reponse',
    'rdv_obtenu',
    'pas_interesse',
    'a_relancer_plus_tard',
    'ne_plus_contacter',
    'adresse_invalide',
}

# statuts "réponse" qui doivent suspendre toute relance
REPLY_STATUTS = {'a_traiter_humain', 'rdv_obtenu', 'pas_interesse', 'a_relancer_plus_tard'}

# transitions transactionnelles : valables depuis N'IMPORTE QUEL état (définitif)
OVERRIDE_TRANSITIONS = {'ne_plus_contacter', 'adresse_invalide'}

VALID_TRANSITIONS = {
    'qualifie':             {'en_sequence', 'ecarte', 'ne_plus_contacter', 'adresse_invalide', 'sans_reponse'},
    'en_sequence':          {'qualifie', 'relance_1', 'a_traiter_humain', 'ne_plus_contacter', 'adresse_invalide', 'sans_reponse'},
    'relance_1':            {'relance_2', 'a_traiter_humain', 'ne_plus_contacter', 'adresse_invalide', 'sans_reponse'},
    'relance_2':            {'relance_3', 'a_traiter_humain', 'ne_plus_contacter', 'adresse_invalide', 'sans_reponse'},
    'relance_3':            {'a_traiter_humain', 'ne_plus_contacter', 'adresse_invalide', 'sans_reponse'},
    'a_traiter_humain':     {'en_sequence', 'relance_1', 'rdv_obtenu', 'pas_interesse', 'a_relancer_plus_tard', 'ne_plus_contacter', 'adresse_invalide'},
    'rdv_obtenu':           set(),
    'pas_interesse':        set(),
    'a_relancer_plus_tard': {'en_sequence', 'ne_plus_contacter'},
    'sans_reponse':         {'a_traiter_humain', 'rdv_obtenu', 'pas_interesse', 'a_relancer_plus_tard'},
    'ne_plus_contacter':    set(),
    'adresse_invalide':     set(),
}

STATUT_LABELS = {
    'qualifie': 'Qualifié',
    'en_sequence': 'En séquence',
    'relance_1': 'Relance 1',
    'relance_2': 'Relance 2',
    'relance_3': 'Relance 3',
    'sans_reponse': 'Sans réponse',
    'a_traiter_humain': 'À traiter',
    'rdv_obtenu': 'RDV obtenu',
    'pas_interesse': 'Pas intéressé',
    'a_relancer_plus_tard': 'À relancer plus tard',
    'ne_plus_contacter': 'Ne plus contacter',
    'adresse_invalide': 'Adresse invalide',
}

STATUT_COLORS = {
    'qualifie': '#3b82f6',
    'en_sequence': '#06b6d4',
    'relance_1': '#06b6d4',
    'relance_2': '#f59e0b',
    'relance_3': '#f97316',
    'sans_reponse': '#64748b',
    'a_traiter_humain': '#a855f7',
    'rdv_obtenu': '#10b981',
    'pas_interesse': '#ef4444',
    'a_relancer_plus_tard': '#8b5cf6',
    'ne_plus_contacter': '#6b7280',
    'adresse_invalide': '#ef4444',
}


def statut_display(statut):
    """Retourne {label, color} pour l'affichage UI."""
    if not statut:
        statut = STATUT_INITIAL
    return {
        'label': STATUT_LABELS.get(statut, statut),
        'color': STATUT_COLORS.get(statut, '#64748b'),
    }


def is_valid_transition(ancien: str, nouveau: str) -> bool:
    if nouveau == 'ecarte':
        return True  # flag manuel, pas un statut "état"
    if ancien == nouveau:
        return True
    if nouveau in OVERRIDE_TRANSITIONS:
        return True  # désinscription / bounce dur : définitif, depuis n'importe quel état
    return nouveau in VALID_TRANSITIONS.get(ancien, set())


def transition_prospect(prospect_id: int, nouveau_statut: str, reason: str = '', payload: dict = None) -> dict:
    """Applique une transition validée : met à jour statut + statut_meta + journalise l'événement.

    Retourne {'success': bool, 'ancien_statut': str, 'statut': str, 'error': str | None}
    """
    payload = payload or {}
    with get_conn() as conn:
        row = conn.execute(
            """SELECT p.id, l.campagne_id, p.statut, p.statut_meta
               FROM prospects p JOIN listes l ON p.liste_id = l.id
               WHERE p.id = ?""",
            (prospect_id,),
        ).fetchone()
        if not row:
            return {'success': False, 'error': f'Prospect {prospect_id} introuvable'}

        ancien = row['statut'] or STATUT_INITIAL
        if nouveau_statut != 'ecarte' and not is_valid_transition(ancien, nouveau_statut):
            return {
                'success': False,
                'ancien_statut': ancien,
                'statut': ancien,
                'error': f"Transition interdite {ancien} -> {nouveau_statut}",
            }

        now = datetime.now().isoformat(timespec='seconds')
        try:
            meta = json.loads(row['statut_meta'] or '{}')
        except Exception:
            meta = {}
        meta['previous_statut'] = ancien
        meta['reason'] = reason
        meta['updated_at'] = now
        meta['touch'] = meta.get('touch', 0) + (1 if nouveau_statut and nouveau_statut.startswith('relance') else 0)

        conn.execute(
            "UPDATE prospects SET statut = ?, statut_meta = ?, updated_at = ? WHERE id = ?",
            (nouveau_statut, json.dumps(meta, ensure_ascii=False), now, prospect_id),
        )
        conn.execute(
            "INSERT INTO prospect_events (prospect_id, campagne_id, event_type, payload) VALUES (?, ?, 'status_change', ?)",
            (prospect_id, row['campagne_id'], json.dumps({
                'from': ancien,
                'to': nouveau_statut,
                'reason': reason,
                **payload,
            }, ensure_ascii=False)),
        )
        conn.commit()

    logger.info("Transition prospect #%s : %s -> %s (%s)", prospect_id, ancien, nouveau_statut, reason)
    return {'success': True, 'ancien_statut': ancien, 'statut': nouveau_statut, 'error': None}