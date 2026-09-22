# -*- coding: utf-8 -*-
"""
database/prospects.py — Repo v2 des prospects, rattachés à une liste (campagne).
"""
import json
import re
from datetime import datetime
from email.utils import parseaddr

from database.connection import get_conn, logger

PROSPECT_FIELDS = {
    'nom', 'prenom', 'email', 'telephone', 'entreprise', 'site_web',
    'adresse', 'ville', 'secteur', 'rating', 'nb_avis', 'source', 'score',
    'data_extra', 'note',
}


def _normalize_email(email):
    if not email:
        return ''
    email = (email or '').strip().lower()
    # retire les balises de type "Nom <toto@x.fr>" si présentes
    real = parseaddr(email)[1] or email
    return real.strip().lower()


def _promote_email_keys(d: dict) -> None:
    """Compat v1 / v2 : les brouillons écrits sous email_objet/email_corps ou
    ia_email_objet/ia_email_corps dans data_extra sont exposés au niveau racine (clés
    canoniques attendues par l'UI panneau + table)."""
    extra = d.get('data_extra')
    if not isinstance(extra, dict):
        return
    if not d.get('email_objet'):
        d['email_objet'] = extra.get('email_objet') or extra.get('ia_email_objet') or ''
    if not d.get('email_corps'):
        d['email_corps'] = extra.get('email_corps') or extra.get('ia_email_corps') or ''


def _is_in_suppression_list(conn, email: str) -> bool:
    if not email:
        return False
    row = conn.execute(
        "SELECT id FROM suppression_list WHERE LOWER(email) = ?", (email.lower(),)
    ).fetchone()
    return row is not None


def _resolve_liste(conn, liste_id: int) -> dict | None:
    return conn.execute("SELECT id, campagne_id, nom AS liste_nom FROM listes WHERE id = ?", (liste_id,)).fetchone()


def insert_prospect(liste_id: int, *, source: str = 'import', data_extra=None, **fields) -> dict:
    """Insère un prospect dans une liste (donc dans sa campagne).

    Règles :
      - `liste_id` obligatoire (l'utilisateur/le scraping cible une liste).
      - doublon = même email OU site_web OU téléphone normalisés déjà présents
        DANS LA MÊME CAMPAGNE (même objectif).
      - email présent dans suppression_list (globale) -> prospect refusé.
    Retourne {'success', 'prospect_id', 'statut_dedupe'} avec statut_dedupe dans
    {'created', 'doublon', 'suppression_list'}.
    """
    liste_id = int(liste_id)
    email = _normalize_email(fields.get('email'))
    nom = (fields.get('nom') or '').strip()
    if not email and not nom:
        return {'success': False, 'error': 'Lead sans nom ni email', 'statut_dedupe': None}

    with get_conn() as conn:
        liste = _resolve_liste(conn, liste_id)
        if not liste:
            return {'success': False, 'error': 'Liste introuvable', 'statut_dedupe': None}
        if _is_in_suppression_list(conn, email):
            return {'success': False, 'error': 'Email dans la liste de suppression', 'statut_dedupe': 'suppression_list'}

        # Doublon dans la CAMPAGNE (même objectif) : email OU site_web OU téléphone
        from database.dedup import find_duplicate_in_campagne
        existing = find_duplicate_in_campagne(
            conn, liste['campagne_id'],
            email=email, telephone=fields.get('telephone'), site_web=fields.get('site_web'),
        )
        if existing:
            return {'success': False, 'prospect_id': existing['id'],
                    'error': 'Doublon dans la campagne', 'statut_dedupe': 'doublon'}

        data_extra_json = json.dumps(data_extra, ensure_ascii=False) if data_extra else None
        now = datetime.now().isoformat(timespec='seconds')
        cur = conn.execute(
            """INSERT INTO prospects
               (liste_id, source, nom, prenom, email, telephone, entreprise, site_web,
                adresse, ville, secteur, rating, nb_avis, score, data_extra,
                statut, statut_meta, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'qualifie', ?, ?, ?)""",
            (
                liste_id, source or 'import',
                fields.get('nom'), fields.get('prenom'), email,
                fields.get('telephone'), fields.get('entreprise'), fields.get('site_web'),
                fields.get('adresse'), fields.get('ville'), fields.get('secteur'),
                fields.get('rating'), int(fields.get('nb_avis') or 0), fields.get('score'),
                data_extra_json,
                json.dumps({'created_at': now, 'source': source or 'import'}, ensure_ascii=False),
                now, now,
            ),
        )
        conn.execute(
            "INSERT INTO prospect_events (prospect_id, campagne_id, event_type, payload) VALUES (?, ?, 'creation', ?)",
            (cur.lastrowid, liste['campagne_id'], json.dumps({'source': source or 'import'}, ensure_ascii=False)),
        )
        conn.commit()
    logger.info("Prospect créé #%s dans liste #%s", cur.lastrowid, liste_id)
    return {'success': True, 'prospect_id': cur.lastrowid, 'statut_dedupe': 'created'}


def is_in_suppression_list(email) -> bool:
    """Vérifie si un email est dans la liste de suppression GLOBALE."""
    if not email:
        return False
    with get_conn() as conn:
        return _is_in_suppression_list(conn, email)


def enrich_prospect(conn, prospect_id: int, *, nom='', prenom='', email='', telephone='',
                    site_web='', nb_avis=None, data_extra=None) -> int:
    """Enrichit un prospect existant (jamais de création).

    Remplit uniquement les champs vides, maximise nb_avis, fusionne data_extra
    (clés absentes ou date_scraping). Retourne le nombre de colonnes modifiées.
    """
    row = conn.execute(
        "SELECT id, nom, prenom, email, telephone, site_web, nb_avis, data_extra "
        "FROM prospects WHERE id = ?", (prospect_id,)
    ).fetchone()
    if not row:
        return 0

    updates = {}
    email_n = _normalize_email(email) or _normalize_email(row['email'])
    if email_n != _normalize_email(row['email']):
        updates['email'] = email_n
    if nom and not (row['nom'] or '').strip():
        updates['nom'] = nom
    if prenom and not (row['prenom'] or '').strip():
        updates['prenom'] = prenom
    tel = (telephone or '').strip()
    if tel and not (row['telephone'] or '').strip():
        updates['telephone'] = tel
    site = (site_web or '').strip()
    if site and not (row['site_web'] or '').strip():
        updates['site_web'] = site
    if nb_avis:
        try:
            if not row['nb_avis'] or int(nb_avis) > int(row['nb_avis'] or 0):
                updates['nb_avis'] = int(nb_avis)
        except (TypeError, ValueError):
            pass

    merged = {}
    try:
        merged = json.loads(row['data_extra']) if row['data_extra'] else {}
        if not isinstance(merged, dict):
            merged = {}
    except Exception:
        merged = {}
    if isinstance(data_extra, dict):
        for k, v in data_extra.items():
            if v not in (None, ''):
                if k == 'date_scraping':
                    merged[k] = v
                else:
                    merged.setdefault(k, v)
        updates['data_extra'] = json.dumps(merged, ensure_ascii=False)

    if updates:
        update_cols = [k for k in updates if k != 'data_extra']
        if 'data_extra' in updates and row['data_extra'] == updates['data_extra']:
            del updates['data_extra']
        if updates:
            set_clause = ', '.join(f"{k}=?" for k in updates)
            conn.execute(
                f"UPDATE prospects SET {set_clause}, updated_at = ? WHERE id = ?",
                list(updates.values()) + [datetime.now().isoformat(timespec='seconds'), prospect_id],
            )
    return len(updates)


def bulk_import(liste_id: int, rows: list, source: str = 'import') -> dict:
    """Importe une liste de dicts (adaptateur déjà appliqué) dans une liste.

    Retourne {'importes', 'doublons', 'supprimes', 'errors'}.
    """
    liste_id = int(liste_id)
    stats = {'importes': 0, 'doublons': 0, 'supprimes': 0, 'errors': 0, 'liste': []}
    if not isinstance(rows, list):
        return {**stats, 'errors': 0}

    with get_conn() as conn:
        liste = _resolve_liste(conn, liste_id)
        if not liste:
            return {**stats, 'errors': len(rows) if isinstance(rows, list) else 0}
        suppression_emails = {
            r['email'].lower()
            for r in conn.execute("SELECT email FROM suppression_list").fetchall()
            if r['email']
        }
        existing_emails = {
            r['email'].lower()
            for r in conn.execute(
                "SELECT email FROM prospects WHERE liste_id = ? AND email IS NOT NULL AND email != ''",
                (liste_id,),
            ).fetchall()
            if r['email']
        }
        campagne_id = liste['campagne_id']

    now = datetime.now().isoformat(timespec='seconds')
    base_meta = json.dumps({'created_at': now, 'source': source}, ensure_ascii=False)

    with get_conn() as conn:
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                stats['errors'] += 1
                continue
            email = _normalize_email(row.get('email'))
            nom = (row.get('nom') or '').strip()
            if not email and not nom:
                stats['errors'] += 1
                continue
            if email and email in suppression_emails:
                stats['supprimes'] += 1
                stats['liste'].append({'nom': nom, 'email': email, 'rejet': 'suppression_list'})
                continue
            if email and email in existing_emails:
                stats['doublons'] += 1
                stats['liste'].append({'nom': nom, 'email': email, 'rejet': 'doublon'})
                continue

            data_extra_json = json.dumps(row.get('data_extra'), ensure_ascii=False) if row.get('data_extra') else None
            cur = conn.execute(
                """INSERT INTO prospects
                   (liste_id, source, nom, prenom, email, telephone, entreprise, site_web,
                    adresse, ville, secteur, rating, nb_avis, score, data_extra,
                    statut, statut_meta, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'qualifie', ?, ?, ?)""",
                (
                    liste_id, source or 'import',
                    row.get('nom'), row.get('prenom'), email,
                    row.get('telephone'), row.get('entreprise'), row.get('site_web'),
                    row.get('adresse'), row.get('ville'), row.get('secteur'),
                    row.get('rating'), int(row.get('nb_avis') or 0), row.get('score'),
                    data_extra_json,
                    base_meta, now, now,
                ),
            )
            conn.execute(
                "INSERT INTO prospect_events (prospect_id, campagne_id, event_type, payload) VALUES (?, ?, 'import', ?)",
                (cur.lastrowid, campagne_id, json.dumps({'source': source}, ensure_ascii=False)),
            )
            if email:
                existing_emails.add(email)
            stats['importes'] += 1
            stats['liste'].append({'nom': nom, 'email': email, 'prospect_id': cur.lastrowid})
        conn.commit()
    logger.info("Import dans liste #%s : %s importés, %s doublons, %s supprimés, %s erreurs",
                liste_id, stats['importes'], stats['doublons'], stats['supprimes'], stats['errors'])
    return stats


def list_prospects(liste_id: int | None = None, campagne_id: int | None = None,
                   page: int = 1, limit: int = 50,
                   search: str = '', statut: str = '', include_archives: bool = False,
                   source: str = '', secteur: str = '', site: str = '',
                   email: str = '', notes: str = '', score: str = '',
                   objectif_liste: str = '', ecarte: str = '', desinscrit: str = '') -> dict:
    """Liste paginée des prospects d'une liste, d'une campagne, ou de toutes
    les campagnes si aucun filtre (mode « toutes campagnes » v2).

    Filtres étendus (miroir des filtres UI v2) :
      - source           : p.source exact ('legacy_maps', 'scraping', 'csv', …)
      - secteur          : p.secteur exact (slug, ex 'immobilier')
      - site             : 'with' → site_web présent · 'without' → absent
      - email            : 'with' → email présent · 'without' → absent
      - notes            : 'with' → note présente · 'sans' → note vide
      - score            : 'bad' (<70) · 'good' (≥70) · 'unscored' (NULL)
      - objectif_liste   : 'web' | 'general' → via l.objectif de la liste porteuse
      - ecarte           : '' (tout) · '0' (exclut écartés) · '1' (uniquement écartés)
      - desinscrit       : '' (tout) · '0' (exclut oppositions) · '1' (uniquement oppositions)"""
    scope = listes = None
    clauses = ['p.liste_id = l.id']
    params = []
    if liste_id is not None:
        clauses.append("p.liste_id = ?")
        params.append(int(liste_id))
    elif campagne_id is not None:
        clauses.append("l.campagne_id = ?")
        params.append(int(campagne_id))
    page = max(1, int(page))
    limit = min(10000, max(1, int(limit)))
    if search:
        clause = "(p.nom LIKE ? OR p.email LIKE ? OR p.entreprise LIKE ? OR p.ville LIKE ? OR p.secteur LIKE ?)"
        like = f"%{search}%"
        clauses.append(clause)
        params += [like] * 5
    if statut:
        clauses.append("p.statut = ?")
        params.append(statut)
    if source:
        clauses.append("p.source = ?")
        params.append(source)
    if secteur:
        clauses.append("p.secteur = ?")
        params.append(secteur)
    if site in ('with', 'without'):
        if site == 'with':
            clauses.append("(p.site_web IS NOT NULL AND p.site_web != '')")
        else:
            clauses.append("(p.site_web IS NULL OR p.site_web = '')")
    if email in ('with', 'without'):
        if email == 'with':
            clauses.append("(p.email IS NOT NULL AND LENGTH(TRIM(p.email)) > 0)")
        else:
            clauses.append("(p.email IS NULL OR LENGTH(TRIM(p.email)) = 0)")
    if notes in ('with', 'sans'):
        if notes == 'with':
            clauses.append("(p.note IS NOT NULL AND p.note != '')")
        else:
            clauses.append("(p.note IS NULL OR p.note = '')")
    if score in ('bad', 'good', 'unscored'):
        if score == 'bad':
            clauses.append("(p.score IS NOT NULL AND p.score < 70)")
        elif score == 'good':
            clauses.append("(p.score IS NOT NULL AND p.score >= 70)")
        else:
            clauses.append("p.score IS NULL")
    if objectif_liste in ('web', 'general'):
        clauses.append("l.objectif = ?")
        params.append(objectif_liste)
    if ecarte in ('0', '1'):
        clauses.append("p.ecarte = ?")
        params.append(int(ecarte))
    if desinscrit in ('0', '1'):
        clauses.append("p.ne_plus_contacter = ?")
        params.append(int(desinscrit))

    where = " AND ".join(clauses)
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS n FROM prospects p JOIN listes l ON p.liste_id = l.id WHERE {where}", params).fetchone()['n']
        total_pages = max(1, -(-total // limit))
        offset = (page - 1) * limit
        rows = conn.execute(
            f"""SELECT p.*, l.id AS liste_id, l.nom AS liste_nom, l.objectif, l.campagne_id, c.nom AS campagne_nom
                FROM prospects p
                JOIN listes l ON p.liste_id = l.id
                JOIN campagnes c ON c.id = l.campagne_id
                WHERE {where}
                ORDER BY p.created_at DESC LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
        leads = []
        for r in rows:
            d = dict(r)
            try:
                d['statut_meta'] = json.loads(d.get('statut_meta') or '{}')
            except Exception:
                d['statut_meta'] = {}
            try:
                d['data_extra'] = json.loads(d.get('data_extra') or 'null')
            except Exception:
                pass
            _promote_email_keys(d)
            leads.append(d)
    return {'leads': leads, 'page': page, 'limit': limit, 'total': total, 'total_pages': total_pages}


def get_prospect(prospect_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT p.*, l.id AS liste_id, l.nom AS liste_nom, l.objectif, l.campagne_id,
                      c.nom AS campagne_nom, c.nom AS objectif_nom
               FROM prospects p
               JOIN listes l ON p.liste_id = l.id
               JOIN campagnes c ON c.id = l.campagne_id
               WHERE p.id = ?""",
            (prospect_id,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d['statut_meta'] = json.loads(d.get('statut_meta') or '{}')
        except Exception:
            d['statut_meta'] = {}
        try:
            d['data_extra'] = json.loads(d.get('data_extra') or 'null')
        except Exception:
            pass
        _promote_email_keys(d)
        events = conn.execute(
            "SELECT * FROM prospect_events WHERE prospect_id = ? ORDER BY created_at DESC LIMIT 100",
            (prospect_id,),
        ).fetchall()
        d['events'] = []
        for ev in events:
            e = dict(ev)
            try:
                e['payload'] = json.loads(e['payload'] or '{}')
            except Exception:
                e['payload'] = {}
            d['events'].append(e)

        # ── Dernière touche emails_envoyes (tracking Resend/SMTP) pour le panneau Suivi
        ee = conn.execute(
            """SELECT email_objet AS email_objet_ee, date_envoi, statut_envoi,
                      ouvert, date_ouverture, nb_ouvertures, clique, date_clic,
                      repondu, date_reponse, bounce, spam
               FROM emails_envoyes WHERE lead_id = ?
               ORDER BY COALESCE(date_envoi, id) DESC LIMIT 1""",
            (prospect_id,),
        ).fetchone()
        if ee:
            dee = dict(ee)
            d.setdefault('sent_at', dee.get('date_envoi'))
            d.setdefault('email_status', dee.get('statut_envoi') or '')
            d.setdefault('is_opened', 1 if (dee.get('ouvert') or 0) else 0)
            d.setdefault('opened_at', dee.get('date_ouverture'))
            d.setdefault('is_clicked', 1 if (dee.get('clique') or 0) else 0)
            d.setdefault('is_replied', 1 if (dee.get('repondu') or 0) else 0)
            if dee.get('email_objet_ee') and not d.get('email_objet'):
                d['email_objet'] = dee.get('email_objet_ee')

        # ── Fil complet des emails (touches sortantes + réponses entrantes)
        d['thread'] = get_thread_for_lead(prospect_id)
        return d


def clean_email_reply(text: str) -> dict:
    """Isole le message réel du prospect en supprimant les en-têtes et citations d'anciens mails."""
    if not text:
        return {'clean': '', 'quote': ''}

    quote_patterns = [
        r'(?i)(?:\r?\n|^|\s+)(?:Le\s+[\s\S]+?\s+a\s+[eé\xe9\xc3\xa9]crit\s*:)',
        r'(?i)(?:\r?\n|^|\s+)(?:On\s+[\s\S]+?\s+wrote\s*:)',
        r'(?i)(?:\r?\n|^|\s+)[-]{2,}\s*(?:Original Message|Message d\'origine|Forwarded message)\s*[-]{2,}',
        r'(?i)(?:\r?\n|^|\s+)(?:De\s*:[^\n]+(?:\r?\n|\s+)Envoy[eé\xe9\xc3\xa9]\s*:[^\n]+)',
        r'(?i)(?:\r?\n|^|\s+)(?:From\s*:[^\n]+(?:\r?\n|\s+)Sent\s*:[^\n]+)',
        r'(?i)(?:\r?\n|^|\s+)(?:De\s*:[^\n]+(?:\r?\n|\s+)Date\s*:[^\n]+)',
        r'(?i)(?:\r?\n|^|\s+)(?:From\s*:[^\n]+(?:\r?\n|\s+)Date\s*:[^\n]+)',
        r'(?i)(?:\r?\n|^|\s+)(?:Begin forwarded message:)',
        r'(?:\r?\n|^)\s*>[^\n]*',
    ]

    split_pos = len(text)
    for pat in quote_patterns:
        m = re.search(pat, text)
        if m and m.start() < split_pos:
            split_pos = m.start()

    clean_part = text[:split_pos].strip()
    quote_part = text[split_pos:].strip()

    # Nettoyage des signatures mobiles automatiques
    clean_part = re.sub(r'(?i)(?:\r?\n|^)\s*--\s*[\r\n].*$', '', clean_part)
    clean_part = re.sub(r'(?i)(?:\r?\n|^)\s*(?:Envoy[eé\xe9\xc3\xa9]\s+(?:de\s+mon|depuis\s+mon)|Sent\s+from\s+my|Get\s+Outlook\s+for)\s+.*$', '', clean_part)

    return {'clean': clean_part.strip(), 'quote': quote_part.strip()}


def get_thread_for_lead(lead_id: int) -> list[dict]:
    """Fil de conversation email complet d'un prospect (lead_id = prospect_id).

    Mélange les touches sortantes (initial, relances, réponses manuelles) et les
    événements entrants (réponses du prospect) en ordre chronologique avec
    résolution automatique des contenus (template fallback, custom drafts, emails_envoyes).
    """
    STEP_LABELS = {
        'initial': 'Premier contact',
        'relance_1': 'Relance 1 (J+3)',
        'relance_2': 'Relance 2 (J+7)',
        'relance_3': 'Relance 3 (J+14)',
        'relance_special': 'Dernière relance',
        'reponse': 'Réponse du prospect',
        'reponse_manuelle': 'Réponse envoyée',
        'ndr': 'Rebond (NDR)',
        'auto_reply': 'Répondeur automatique',
    }

    email_events = ('initial', 'relance_1', 'relance_2', 'relance_3', 'relance_special',
                    'reponse', 'reponse_manuelle', 'ndr', 'auto_reply')
    ph = ','.join('?' for _ in email_events)
    
    with get_conn() as conn:
        lead_row = conn.execute(
            "SELECT id, email, nom, data_extra FROM prospects WHERE id = ?",
            (lead_id,),
        ).fetchone()

        rows = conn.execute(
            f"""SELECT id, prospect_id, campagne_id, event_type, payload,
                       mailbox_id, message_id, in_reply_to, references_header,
                       parent_event_id, thread_id, direction, created_at
                FROM prospect_events
                WHERE prospect_id = ? AND event_type IN ({ph})
                ORDER BY created_at ASC, id ASC""",
            (lead_id, *email_events),
        ).fetchall()

        # Également récupérer les lignes d'emails_envoyes pour ce lead (par lead_id, legacy_id ou email)
        legacy_id = None
        lead_email = ''
        if lead_row:
            lead_email = lead_row['email'] or ''
            try:
                extra = json.loads(lead_row['data_extra'] or '{}') if isinstance(lead_row['data_extra'], str) else (lead_row['data_extra'] or {})
                legacy_id = extra.get('legacy_id')
            except Exception:
                pass

        query_ee = """SELECT id, lead_id, message_id_resend, message_id_brevo, date_envoi,
                             email_destinataire, email_objet, email_corps, statut_envoi,
                             ouvert, date_ouverture, nb_ouvertures, clique, date_clic,
                             repondu, date_reponse, bounce, spam
                      FROM emails_envoyes
                      WHERE lead_id = ?"""
        ee_params = [lead_id]
        if legacy_id:
            query_ee += " OR lead_id = ?"
            ee_params.append(legacy_id)
        if lead_email:
            query_ee += " OR email_destinataire = ?"
            ee_params.append(lead_email)
        query_ee += " ORDER BY COALESCE(date_envoi, id) ASC"

        ee_rows = conn.execute(query_ee, ee_params).fetchall()

        # Cache des sequence_templates pour fallback
        templates = {
            r['id']: dict(r)
            for r in conn.execute("SELECT id, nom, objet, corps FROM sequence_templates").fetchall()
        }

    out = []
    seen_msg_ids = set()

    for r in rows:
        d = dict(r)
        try:
            p = json.loads(d['payload'] or '{}') if isinstance(d['payload'], str) else (d['payload'] or {})
        except Exception:
            p = {}
        d['payload'] = p
        
        mid = d.get('message_id') or p.get('rfc_message_id') or ''
        if mid:
            seen_msg_ids.add(mid)

        is_inbound = (d.get('direction') == 'in' or d.get('event_type') == 'reponse')
        d['direction'] = 'in' if is_inbound else 'out'
        d['step_label'] = STEP_LABELS.get(d['event_type'], d['event_type'].replace('_', ' ').capitalize())

        # Trouver la ligne de tracking correspondante dans emails_envoyes
        matching_ee = None
        for ee in ee_rows:
            e_mid = ee['message_id_resend'] or ee['message_id_brevo'] or ''
            if mid and e_mid and mid in e_mid:
                matching_ee = dict(ee)
                break
        if not matching_ee and ee_rows:
            # Match par ordre si un seul envoi
            if len(ee_rows) == 1 and len(rows) == 1:
                matching_ee = dict(ee_rows[0])

        tpl = templates.get(p.get('template_id')) if p.get('template_id') else None

        raw_corps = p.get('corps') or p.get('clean_body') or p.get('body') or (matching_ee.get('email_corps') if matching_ee else '') or (tpl.get('corps') if tpl else '') or ''
        quote_text = p.get('quote') or ''

        # Pour les réponses entrantes, nettoyer les en-têtes et citations imbriquées
        if is_inbound:
            cleaned = clean_email_reply(raw_corps or p.get('snippet') or '')
            d['corps'] = cleaned['clean'] or raw_corps
            d['quote'] = quote_text or cleaned['quote']
            d['snippet'] = (d['corps'][:250] if d['corps'] else '')
        else:
            d['corps'] = raw_corps
            d['quote'] = quote_text
            d['snippet'] = p.get('snippet') or (d['corps'][:250] if d['corps'] else '')

        d['subject'] = p.get('objet') or p.get('subject') or (matching_ee.get('email_objet') if matching_ee else '') or (tpl.get('objet') if tpl else '') or ''
        d['sujet'] = d['subject']
        d['sent_at'] = (matching_ee.get('date_envoi') if matching_ee else None) or d.get('created_at')
        d['is_opened'] = 1 if (matching_ee and matching_ee.get('ouvert')) else 0
        d['opened_at'] = matching_ee.get('date_ouverture') if matching_ee else None
        d['is_clicked'] = 1 if (matching_ee and matching_ee.get('clique')) else 0
        d['is_replied'] = 1 if (is_inbound or (matching_ee and matching_ee.get('repondu'))) else 0
        d['email_status'] = (matching_ee.get('statut_envoi') if matching_ee else None) or ('recu' if is_inbound else 'envoye')
        d['from_addr'] = p.get('from_addr') or p.get('mailbox_email') or ''
        d['from_name'] = p.get('from_name') or ''
        out.append(d)

    # Si certains emails_envoyes n'avaient pas d'événement correspondant, on les ajoute
    for ee in ee_rows:
        dee = dict(ee)
        e_mid = dee.get('message_id_resend') or dee.get('message_id_brevo') or str(dee['id'])
        if e_mid in seen_msg_ids:
            continue
        out.append({
            'id': f"ee_{dee['id']}",
            'prospect_id': lead_id,
            'event_type': 'email_envoye',
            'direction': 'out',
            'step_label': dee.get('statut_envoi') or 'Email envoyé',
            'subject': dee.get('email_objet') or '',
            'sujet': dee.get('email_objet') or '',
            'corps': dee.get('email_corps') or '',
            'snippet': (dee.get('email_corps') or '')[:250],
            'sent_at': dee.get('date_envoi'),
            'is_opened': 1 if dee.get('ouvert') else 0,
            'opened_at': dee.get('date_ouverture'),
            'is_clicked': 1 if dee.get('clique') else 0,
            'is_replied': 1 if dee.get('repondu') else 0,
            'email_status': dee.get('statut_envoi') or 'envoye',
            'created_at': dee.get('date_envoi'),
        })

    out.sort(key=lambda x: x.get('sent_at') or x.get('created_at') or '')
    return out


def update_prospect(prospect_id: int, **fields) -> dict:
    updates = {k: v for k, v in fields.items() if k in PROSPECT_FIELDS}
    if 'email' in updates:
        updates['email'] = _normalize_email(updates['email'])
    if not updates:
        return {'success': False, 'error': 'Aucun champ valide'}
    if 'data_extra' in updates and isinstance(updates['data_extra'], dict):
        updates['data_extra'] = json.dumps(updates['data_extra'], ensure_ascii=False)
    updates['updated_at'] = datetime.now().isoformat(timespec='seconds')
    cols = ", ".join(f"{k} = ?" for k in updates)
    with get_conn() as conn:
        if 'data_extra' in updates:
            # Fusion avec le data_extra existant (évite d'écraser lien_maps, logo_url, etc.)
            prev = conn.execute("SELECT data_extra FROM prospects WHERE id = ?", (prospect_id,)).fetchone()
            base = {}
            if prev and prev['data_extra']:
                try:
                    base = json.loads(prev['data_extra']) or {}
                except Exception:
                    base = {}
            try:
                extra = json.loads(updates['data_extra']) or {}
            except Exception:
                extra = {}
            if isinstance(extra, dict):
                merged = {**base, **extra}
                updates['data_extra'] = json.dumps(merged, ensure_ascii=False)
        cur = conn.execute(f"UPDATE prospects SET {cols} WHERE id = ?", (*updates.values(), prospect_id))
        conn.commit()
        if cur.rowcount == 0:
            return {'success': False, 'error': 'Prospect introuvable'}
    return {'success': True}


def set_ecarte(prospect_id: int, ecarte: bool) -> dict:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE prospects SET ecarte = ?, updated_at = ? WHERE id = ?",
            (1 if ecarte else 0, datetime.now().isoformat(timespec='seconds'), prospect_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return {'success': False, 'error': 'Prospect introuvable'}
    return {'success': True}


def set_ne_plus_contacter(prospect_id: int, ne_plus_contacter: bool, raison: str = 'desinscription') -> dict:
    """Opposition au contact : flag + inscription à la suppression_list GLOBALE + transition d'état.

    Spec §2 : la désinscription met le prospect en `ne_plus_contacter` (définitif,
    toutes campagnes futures), d'où l'appel à la machine à états.
    """
    from core.state_machine import transition_prospect
    with get_conn() as conn:
        row = conn.execute(
            """SELECT p.liste_id, p.email, l.campagne_id
               FROM prospects p JOIN listes l ON p.liste_id = l.id
               WHERE p.id = ?""",
            (prospect_id,),
        ).fetchone()
        if not row:
            return {'success': False, 'error': 'Prospect introuvable'}
        conn.execute(
            "UPDATE prospects SET ne_plus_contacter = ?, updated_at = ? WHERE id = ?",
            (1 if ne_plus_contacter else 0, datetime.now().isoformat(timespec='seconds'), prospect_id),
        )
        conn.execute(
            "INSERT INTO prospect_events (prospect_id, campagne_id, event_type, payload) VALUES (?, ?, 'desinscription', ?)",
            (prospect_id, row['campagne_id'], json.dumps({'raison': raison, 'en': ne_plus_contacter}, ensure_ascii=False)),
        )
        if ne_plus_contacter and row['email']:
            conn.execute(
                "INSERT OR IGNORE INTO suppression_list (email, raison, source_campagne_id) VALUES (?, ?, ?)",
                (row['email'].lower(), raison, row['campagne_id']),
            )
        if not ne_plus_contacter and row['email']:
            conn.execute("DELETE FROM suppression_list WHERE LOWER(email) = ?", (row['email'].lower(),))
        conn.commit()

    if ne_plus_contacter:
        transition_prospect(prospect_id, 'ne_plus_contacter', reason=raison)
    return {'success': True}


def delete_prospect(prospect_id: int) -> dict:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM prospects WHERE id = ?", (prospect_id,))
        conn.commit()
        if cur.rowcount == 0:
            return {'success': False, 'error': 'Prospect introuvable'}
    return {'success': True}