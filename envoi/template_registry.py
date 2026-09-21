# -*- coding: utf-8 -*-
"""
envoi/template_registry.py — registre de templates & variables de fusion.

La table `sequence_templates` (schéma v2) contient objet/corps avec variables
{{prenom}}, {{entreprise}}, {{secteur}}, {{offre}}, {{nom}}, {{site_web}}, {{ville}},
{{rating}}, {{nb_avis}}. Un template peut être global (campagne_id NULL) ou dédié
à une campagne. Position = ordre dans la séquence (0 = email initial).

Ce module est LA porte d'entrée pour lire/modifier/rendre les templates :
jamais de requête `sequence_templates` hors d'ici.
"""
import re
from datetime import datetime

from database.connection import get_conn, logger

CANONICAL_VARIABLES = ['prenom', 'nom', 'entreprise', 'secteur', 'offre',
                       'site_web', 'ville', 'rating', 'nb_avis', 'date']
VARIABLE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

# Corps « par défaut » utilisé pour substituer le placeholder {{corps}}
# quand aucune passe LLM ne fournit de corps (aperçu / email de TEST).
_DEFAULT_BODY_CONTENT = (
    "En regardant le site de {{entreprise}} ({{secteur}}), j'ai remarqué quelques points "
    "qui mériteraient un coup d'œil : j'ai préparé une ébauche et quelques idées de "
    "modernisation — pas d'obligation, juste un aperçu si ça vous intéresse.\n\n"
    "{{site_web}}\n\n"
    "Bien à vous,\nJean-Marc"
)


# ─── Lecture ───────────────────────────────────────────────────────────────────

def get_templates(campagne_id=None, include_inactifs=False) -> list:
    """Templates actifs (ou tous) applicables à une campagne.

    Priorité : dédiés campagne (campagne_id exact), puis génériques (NULL).
    Triés par `position` puis `delai_jours`.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sequence_templates ORDER BY COALESCE(campagne_id, 999999), position, delai_jours"
        ).fetchall()
    out = []
    for r in rows:
        t = {k: r[k] for k in r.keys()}
        if t.get('campagne_id') is not None and campagne_id is not None and t['campagne_id'] != campagne_id:
            continue
        if not include_inactifs and not t.get('actif'):
            continue
        out.append(t)
    return out


def get_step(campagne_id=None, position=0) -> dict:
    """Template pour une position donnée : dédié campagne sinon générique. None si absent."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM sequence_templates WHERE campagne_id = ? AND position = ? AND actif = 1",
            (campagne_id, position),
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT * FROM sequence_templates WHERE campagne_id IS NULL AND position = ? AND actif = 1",
                (position,),
            ).fetchone()
    return dict(row) if row else None


# ─── CRUD ──────────────────────────────────────────────────────────────────────

def add_or_update(campagne_id=None, nom=None, objet=None, corps=None, position=0,
                  delai_jours=0, canal='email'):
    """Crée ou remplace le template (campagne_id, position, canal) à la position cible.

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
                   (campagne_id, nom, objet, corps, canal, position, delai_jours, actif)
                   VALUES (?,?,?,?,?,?,?,1)""",
                (campagne_id, nom, objet, corps, canal, int(position), int(delai_jours)),
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
    nom = str(prospect.get('nom') or '').strip()
    prenom = str(prospect.get('prenom') or '').strip()
    entreprise = str(prospect.get('entreprise') or '').strip()
    ctx = {}
    for v in CANONICAL_VARIABLES:
        ctx[v] = str(prospect.get(v) or '').strip()
    # Fallbacks propres pour les prospects « entités » sans prénom (ex. 8836) :
    # saluer par le nom de la société plutôt que de laisser « Bonjour , ».
    if not prenom:
        prenom = nom or entreprise
    if not entreprise and nom:
        entreprise = nom
    ctx['prenom'], ctx['entreprise'] = prenom, entreprise
    if not ctx['secteur'] and ctx['entreprise']:
        ctx['secteur'] = ctx['entreprise']
    if not ctx['offre']:
        # tentative de déduction depuis la campagne si disponible
        o = prospect.get('_campagne') or {}
        ctx['offre'] = str(o.get('description') or o.get('objectif_principale') or '').strip()
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
    """Rend objet + corps d'un template : retourne {'objet', 'corps', 'vars_inconnues'}.

    Le placeholder `{{corps}}` (là où la passe LLM insérerait sa production) est
    substitué par le corps par défaut quand aucune passe n'a fourni de contenu
    (aperçu, email de test, envoi humanize off) — jamais laissé littéral.
    """
    objet = render(template.get('objet') or '', prospect)
    corps = render(template.get('corps') or '', prospect)
    if '{{corps}}' in corps:
        corps = corps.replace('{{corps}}', render(_DEFAULT_BODY_CONTENT, prospect))
    used = set(VARIABLE_RE.findall((template.get('objet') or '') + (template.get('corps') or '')))
    known = set(CANONICAL_VARIABLES + ['corps'])
    unknown = sorted(used - known)
    return {'objet': objet, 'corps': corps, 'vars_inconnues': unknown}


def unknown_variables(template: dict) -> list:
    used = set(VARIABLE_RE.findall((template.get('objet') or '') + (template.get('corps') or '')))
    return sorted(used - set(CANONICAL_VARIABLES + ['corps']))


def count_touches(campagne_id):
    """Positions max du template actif pour la campagne (inclut générique)."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(position) FROM sequence_templates WHERE actif = 1 AND (campagne_id IS NULL OR campagne_id = ?)",
            (campagne_id,),
        ).fetchone()
    return int(row[0] or 0)


# ─── Exemples fournis avec le registre ─────────────────────────────────────────

DEFAULT_INITIAL_OBJET = "{{prenom}}, un mot sur le site de {{entreprise}}"
DEFAULT_INITIAL_CORPS = "Bonjour {{prenom}},\n\n" + _DEFAULT_BODY_CONTENT