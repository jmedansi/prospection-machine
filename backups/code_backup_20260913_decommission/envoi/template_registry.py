# -*- coding: utf-8 -*-
"""
envoi/template_registry.py — registre de templates & variables de fusion.

La table `sequence_templates` (schéma v2) contient objet/corps avec variables
{{prenom}}, {{entreprise}}, {{secteur}}, {{offre}}, {{nom}}, {{site_web}}, {{ville}},
{{rating}}, {{nb_avis}}. Un template peut être global (objectif_id NULL) ou dédié
à un objectif. Position = ordre dans la séquence (0 = email initial).

Ce module est LA porte d'entrée pour lire/modifier/rendre les templates :
jamais de requête `sequence_templates` hors d'ici.
"""
import re
from datetime import datetime

from database.connection import get_conn, logger

CANONICAL_VARIABLES = ['prenom', 'nom', 'entreprise', 'secteur', 'offre',
                       'site_web', 'ville', 'rating', 'nb_avis', 'date']
VARIABLE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


# ─── Lecture ───────────────────────────────────────────────────────────────────

def get_templates(objectif_id=None, include_inactifs=False) -> list:
    """Templates actifs (ou tous) applicables à un objectif.

    Priorité : dédiés objectif (objectif_id exact), puis génériques (NULL).
    Triés par `position` puis `delai_jours`.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sequence_templates ORDER BY COALESCE(objectif_id, 999999), position, delai_jours"
        ).fetchall()
    out = []
    for r in rows:
        t = {k: r[k] for k in r.keys()}
        if t.get('objectif_id') is not None and objectif_id is not None and t['objectif_id'] != objectif_id:
            continue
        if not include_inactifs and not t.get('actif'):
            continue
        out.append(t)
    return out


def get_step(objectif_id=None, position=0) -> dict:
    """Template pour une position donnée : dédié objectif sinon générique. None si absent."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM sequence_templates WHERE objectif_id = ? AND position = ? AND actif = 1",
            (objectif_id, position),
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT * FROM sequence_templates WHERE objectif_id IS NULL AND position = ? AND actif = 1",
                (position,),
            ).fetchone()
    return dict(row) if row else None


# ─── CRUD ──────────────────────────────────────────────────────────────────────

def add_or_update(objectif_id=None, nom=None, objet=None, corps=None, position=0,
                  delai_jours=0, canal='email'):
    """Crée ou remplace le template (objectif_id, position, canal) à la position cible.

    Retourne {'success': bool, 'id': int|None, 'error': str|None}.
    """
    nom = (nom or '').strip() or f"Template pos {position}"
    objet = (objet or '').strip()
    corps = (corps or '').strip()
    if not objet and not corps:
        return {'success': False, 'id': None, 'error': 'objet et corps vides'}
    try:
        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO sequence_templates
                   (objectif_id, nom, objet, corps, canal, position, delai_jours, actif)
                   VALUES (?,?,?,?,?,?,?,1)""",
                (objectif_id, nom, objet, corps, canal, int(position), int(delai_jours)),
            )
            conn.commit()
            return {'success': True, 'id': cur.lastrowid, 'error': None}
    except Exception as e:
        logger.error("[template_registry] add/update: %s", e)
        return {'success': False, 'id': None, 'error': str(e)}


def update(template_id, *, nom=None, objet=None, corps=None, delai_jours=None,
           canal=None, actif=None) -> dict:
    """Met à jour un template par son id (champs partiels acceptés).

    Retourne {'success': bool, 'id': int|None, 'error': str|None}.
    """
    fields = {}
    if nom is not None:
        fields['nom'] = str(nom).strip()
    if objet is not None:
        fields['objet'] = str(objet).strip()
    if corps is not None:
        fields['corps'] = str(corps).strip()
    if delai_jours is not None:
        fields['delai_jours'] = int(delai_jours)
    if canal is not None:
        fields['canal'] = str(canal)
    if actif is not None:
        fields['actif'] = 1 if actif else 0
    if not fields:
        return {'success': False, 'id': None, 'error': 'aucun champ à mettre à jour'}
    try:
        with get_conn() as conn:
            cur = conn.execute(
                "UPDATE sequence_templates SET " + ", ".join(f"{k} = ?" for k in fields) + " WHERE id = ?",
                (*fields.values(), template_id),
            )
            conn.commit()
            if cur.rowcount == 0:
                return {'success': False, 'id': None, 'error': 'template introuvable'}
            return {'success': True, 'id': template_id, 'error': None}
    except Exception as e:
        logger.error("[template_registry] update: %s", e)
        return {'success': False, 'id': None, 'error': str(e)}


def set_actif(template_id, actif=True):
    with get_conn() as conn:
        conn.execute("UPDATE sequence_templates SET actif = ? WHERE id = ?", (1 if actif else 0, template_id))
        conn.commit()
    return True


def delete(template_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM sequence_templates WHERE id = ?", (template_id,))
        conn.commit()
    return True


# ─── Rendu / variables ─────────────────────────────────────────────────────────

def _ctx_for(prospect: dict) -> dict:
    """Construit le contexte de fusion depuis un prospect v2 (ou dict équivalent)."""
    ctx = {}
    for v in CANONICAL_VARIABLES:
        ctx[v] = str(prospect.get(v) or '').strip()
    if not ctx['offre']:
        # tentative de déduction depuis l'objectif si disponible
        o = prospect.get('_objectif') or {}
        ctx['offre'] = str(o.get('objectif_principale') or o.get('description') or '').strip()
    if not ctx['secteur'] and ctx['offre']:
        ctx['secteur'] = ctx['offre']
    return {k: (v or '') for k, v in ctx.items()}


def render(text: str, prospect: dict) -> str:
    """Substitue {{variable}} dans `text` à partir du prospect."""
    if not text:
        return text
    ctx = _ctx_for(prospect)

    def _sub(m):
        return ctx.get(m.group(1), m.group(0))

    return VARIABLE_RE.sub(_sub, text)


def render_template(template: dict, prospect: dict) -> dict:
    """Rend objet + corps d'un template : retourne {'objet', 'corps', 'vars_inconnues'}."""
    objet = render(template.get('objet') or '', prospect)
    corps = render(template.get('corps') or '', prospect)
    used = set(VARIABLE_RE.findall((template.get('objet') or '') + (template.get('corps') or '')))
    known = set(CANONICAL_VARIABLES + ['corps'])
    unknown = sorted(used - known)
    return {'objet': objet, 'corps': corps, 'vars_inconnues': unknown}


def unknown_variables(template: dict) -> list:
    used = set(VARIABLE_RE.findall((template.get('objet') or '') + (template.get('corps') or '')))
    return sorted(used - set(CANONICAL_VARIABLES + ['corps']))


def count_touches(objectif_id):
    """Positions max du template actif pour l'objectif (inclut générique)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(position) FROM sequence_templates WHERE actif = 1 AND (objectif_id IS NULL OR objectif_id = ?)",
            (objectif_id,),
        ).fetchone()
    return int(row[0] or 0)


# ─── Exemples fournis avec le registre ─────────────────────────────────────────

DEFAULT_INITIAL_OBJET = "{{prenom}}, un mot sur le site de {{entreprise}}"
DEFAULT_INITIAL_CORPS = (
    "Bonjour {{prenom}},\n\n"
    "En regardant le site de {{entreprise}} ({{secteur}}), j'ai remarqué quelques points "
    "qui mériteraient un coup d'œil : j'ai préparé une ébauche et quelques idées de "
    "modernisation — pas d'obligation, juste un aperçu si ça vous intéresse.\n\n"
    "{{site_web}}\n\n"
    "Bien à vous,\nJean-Marc"
)