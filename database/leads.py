# -*- coding: utf-8 -*-
from datetime import datetime
from .connection import get_conn, logger

# Transitions de statut valides
VALID_TRANSITIONS = {
    'scrape':       ['en_attente', 'audite'],
    'en_attente':   ['audite', 'archive'],
    'audite':       ['email_genere', 'archive'],
    'email_genere': ['scheduled', 'archive'],
    'scheduled':    ['envoye', 'archive'],
    'envoye':       ['repondu', 'bounced', 'archive'],
    'bounced':      ['archive'],
    'repondu':      ['rdv', 'archive'],
}


def insert_lead(lead: dict) -> int | None:
    """
    Insère un lead depuis le scraper. Retourne l'id SQLite.
    Déduplique par nom+ville ou téléphone.
    """
    try:
        with get_conn() as conn:
            nom   = lead.get('nom', '').strip()
            ville = lead.get('ville', '').strip()
            tel   = (lead.get('telephone') or '').strip()

            # Recherche doublon par nom+ville
            existing = conn.execute(
                "SELECT id, email, site_web, telephone, nb_avis FROM leads_bruts "
                "WHERE LOWER(nom)=LOWER(?) AND LOWER(ville)=LOWER(?)",
                (nom, ville)
            ).fetchone()

            # Recherche doublon par téléphone (si non vide)
            if not existing and tel:
                existing = conn.execute(
                    "SELECT id, email, site_web, telephone, nb_avis FROM leads_bruts "
                    "WHERE telephone=? AND telephone != ''",
                    (tel,)
                ).fetchone()

            # Recherche doublon par site_web (clé naturelle pour leads Sniper)
            # Normalisation : strip www. et trailing slash pour éviter les doublons www/no-www
            raw_site = (lead.get('site_web') or '').strip().rstrip('/')
            site = raw_site.lower().replace('://www.', '://')
            if not existing and site:
                existing = conn.execute(
                    "SELECT id, email, site_web, telephone, nb_avis, source, campaign_id FROM leads_bruts "
                    "WHERE REPLACE(TRIM(LOWER(RTRIM(site_web, '/'))), '://www.', '://') = ?",
                    (site,)
                ).fetchone()

            if existing:
                existing = dict(existing)
                # Enrichir avec les nouvelles données si l'existant est vide ou rafraîchir le lead
                updates = {
                    'date_scraping': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                
                # Mise à jour de la source : on garde l'historique (ex: "maps,fb_ads")
                new_source = lead.get('source', 'maps')
                old_source = existing.get('source') or 'maps'
                if new_source not in old_source:
                    updates['source'] = f"{old_source},{new_source}"
                
                # Mise à jour de la campagne pour le suivi actuel
                cid = lead.get('campaign_id')
                if cid is not None:
                    updates['campaign_id'] = cid

                if lead.get('email') and not existing['email']:
                    updates['email'] = lead['email']
                    updates['email_valide'] = lead.get('statut_email', lead.get('email_valide', ''))
                if lead.get('site_web') and (not existing['site_web'] or existing['site_web'] == ''):
                    updates['site_web'] = lead['site_web']
                if tel and not existing['telephone']:
                    updates['telephone'] = tel
                
                new_avis = lead.get('nb_avis') or 0
                if new_avis and (not existing['nb_avis'] or int(new_avis) > int(existing['nb_avis'] or 0)):
                    updates['nb_avis'] = new_avis
                
                # Mise à jour du logo si présent
                if lead.get('logo_url') and not existing.get('logo_url'):
                    updates['logo_url'] = lead['logo_url']
                
                # Mise à jour du pays si nouveau
                new_pays = lead.get('pays')
                if new_pays and not existing.get('pays'):
                    updates['pays'] = new_pays
                
                if updates:
                    set_clause = ', '.join(f"{k}=?" for k in updates)
                    conn.execute(
                        f"UPDATE leads_bruts SET {set_clause} WHERE id=?",
                        list(updates.values()) + [existing['id']]
                    )
                    conn.commit()
                return existing['id']

        # ── Nouveau lead (pas de doublon) ────────────────────────────────
        cur = conn.execute("""
            INSERT INTO leads_bruts
            (campaign_id, nom, adresse, site_web, telephone, email,
             email_valide, rating, nb_avis, category,
             mot_cle, ville, lien_maps, logo_url,
             source, tag_urgence, niveau_urgence, donnees_audit,
             secteur, pays)
            VALUES
            (:campaign_id, :nom, :adresse, :site_web, :telephone, :email,
             :email_valide, :rating, :nb_avis, :category,
             :mot_cle, :ville, :lien_maps, :logo_url,
             :source, :tag_urgence, :niveau_urgence, :donnees_audit,
             :secteur, :pays)
        """, {
            'campaign_id':    lead.get('campaign_id'),
            'nom':            nom,
            'adresse':        lead.get('adresse', ''),
            'site_web':       lead.get('site_web', ''),
            'telephone':      tel,
            'email':          lead.get('email', ''),
            'email_valide':   lead.get('statut_email', lead.get('email_valide', '')),
            'rating':         lead.get('rating'),
            'nb_avis':        int(lead.get('nb_avis') or 0),
            'category':       lead.get('category', ''),
            'mot_cle':        lead.get('mot_cle', ''),
            'ville':          ville,
            'lien_maps':      lead.get('lien_maps', ''),
            'logo_url':       lead.get('logo_url', ''),
            'source':         lead.get('source', 'maps'),
            'tag_urgence':    lead.get('tag_urgence'),
            'niveau_urgence': int(lead.get('niveau_urgence') or 0),
            'donnees_audit':  lead.get('donnees_audit'),
            'secteur':        lead.get('secteur'),
            'pays':           lead.get('pays', 'fr'),
        })
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        logger.error(f"insert_lead → {e}")
        raise


def get_leads_pending(verify_smtp: bool = False) -> list:
    """Retourne les leads non encore audités (pipeline Maps uniquement — exclut Sniper)."""
    try:
        if verify_smtp:
            from utils.email_validator import validate_pending_leads
            validate_pending_leads()
            
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM leads_bruts
                WHERE statut = 'en_attente'
                  AND (email_valide = 'Valide' OR email IS NULL OR email = '')
                  AND (source IS NULL OR source = 'maps' OR source = '')
                ORDER BY id DESC
            """).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_leads_pending → {e}")
        return []


def get_all_leads(statut: str = 'tous', limit: int = 500) -> list:
    """Retourne tous les leads avec leur data d'audit si disponible."""
    try:
        with get_conn() as conn:
            base_sql = """
                SELECT lb.*,
                       la.mobile_score, la.desktop_score, la.score_urgence,
                       la.score_performance, la.score_seo,
                       la.email_objet, la.email_corps, la.approuve,
                       la.lien_rapport, la.lien_pdf,
                       la.probleme_principal, la.service_suggere,
                       la.lcp_ms, la.cms_detected
                FROM leads_bruts lb
                LEFT JOIN leads_audites la ON la.lead_id = lb.id
            """
            if statut == 'tous':
                sql = base_sql + " ORDER BY lb.id DESC LIMIT ?"
                rows = conn.execute(sql, (limit,)).fetchall()
            else:
                sql = base_sql + " WHERE lb.statut = ? ORDER BY lb.id DESC LIMIT ?"
                rows = conn.execute(sql, (statut, limit)).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_all_leads → {e}")
        return []


def update_lead_statut(lead_id: int, statut: str):
    """Met à jour le statut d'un lead."""
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE leads_bruts SET statut=? WHERE id=?",
                (statut, lead_id)
            )
            conn.commit()
    except Exception as e:
        logger.error(f"update_lead_statut({lead_id}, {statut}) → {e}")


def get_lead_by_name(nom: str) -> dict | None:
    """Trouve un lead par son nom."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM leads_bruts WHERE LOWER(nom)=LOWER(?) LIMIT 1",
                (nom,)
            ).fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_lead_by_name({nom}) → {e}")
        return None


def get_lead_by_id(lead_id: int) -> dict | None:
    """Trouve un lead par son ID."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM leads_bruts WHERE id=? LIMIT 1",
                (lead_id,)
            ).fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_lead_by_id({lead_id}) → {e}")
        return None


def delete_lead(lead_id: int):
    """Supprime un lead et ses dépendances en cascade."""
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM leads_bruts WHERE id=?", (lead_id,))
    except Exception as e:
        logger.error(f"delete_lead({lead_id}) → {e}")
        raise


def update_lead(lead_id: int, data: dict):
    """Met à jour les données brutes d'un lead."""
    try:
        allowed = {'nom', 'ville', 'site_web', 'adresse', 'telephone', 'email', 'mot_cle', 'category'}
        update_data = {k: v for k, v in data.items() if k in allowed}
        if not update_data:
            return
        sets = ', '.join(f"{k}=:{k}" for k in update_data)
        update_data['id'] = lead_id
        with get_conn() as conn:
            conn.execute(f"UPDATE leads_bruts SET {sets} WHERE id=:id", update_data)
            conn.commit()
    except Exception as e:
        logger.error(f"update_lead({lead_id}) → {e}")
        raise


def transition_statut(lead_id: int, to_statut: str) -> bool:
    """Transition de statut sécurisée."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT statut FROM leads_bruts WHERE id = ?", (lead_id,)
            ).fetchone()
            
            if not row:
                logger.warning(f"transition_statut: lead #{lead_id} introuvable")
                return False
            
            from_statut = row['statut'] or 'scrape'
            
            valid_next = VALID_TRANSITIONS.get(from_statut, [])
            if to_statut not in valid_next:
                logger.warning(
                    f"transition_statut: transition invalide pour lead #{lead_id}: "
                    f"'{from_statut}' → '{to_statut}' (valides: {valid_next})"
                )
            
            conn.execute(
                "UPDATE leads_bruts SET statut = ? WHERE id = ?",
                (to_statut, lead_id)
            )
            conn.commit()
            logger.info(f"transition_statut: lead #{lead_id}: '{from_statut}' → '{to_statut}'")
            return True
            
    except Exception as e:
        logger.error(f"transition_statut({lead_id}, {to_statut}): {e}")
        return False
