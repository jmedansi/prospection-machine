# -*- coding: utf-8 -*-
"""
database/db_manager.py — Source de vérité principale SQLite
Remplace Google Sheets pour toutes les opérations de lecture/écriture.
Sheets devient un miroir en lecture seule (sync toutes les heures).
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path

# --- Chemin vers la base de données ---
DB_PATH = Path(__file__).parent.parent / "data" / "prospection.db"

# --- Logging ---
logging.basicConfig(
    filename=str(Path(__file__).parent.parent / "errors.log"),
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ===========================================================
# CONNEXION
# ===========================================================

def get_conn() -> sqlite3.Connection:
    """Retourne une connexion SQLite avec row_factory et WAL activé."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Lectures et écritures simultanées
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ===========================================================
# INITIALISATION DES TABLES
# ===========================================================

def migrate_db():
    """Ajoute les colonnes manquantes aux tables existantes."""
    with get_conn() as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]
        
        if 'emails_envoyes' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(emails_envoyes)").fetchall()]
            migrations = [
                ("clique", "INTEGER DEFAULT 0"),
                ("date_clic", "TEXT"),
                ("bounce", "INTEGER DEFAULT 0"),
                ("spam", "INTEGER DEFAULT 0"),
                ("message_id_resend", "TEXT"),
            ]
            for col_name, col_def in migrations:
                if col_name not in cols:
                    try:
                        conn.execute(f"ALTER TABLE emails_envoyes ADD COLUMN {col_name} {col_def}")
                        print(f"  [MIGRATION] Colonne ajoutée: emails_envoyes.{col_name}")
                    except Exception as e:
                        pass
        
        if 'leads_bruts' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(leads_bruts)").fetchall()]
            if 'email_valide' not in cols:
                try:
                    conn.execute("ALTER TABLE leads_bruts ADD COLUMN email_valide TEXT DEFAULT ''")
                except: pass
            if 'campaign_id' not in cols:
                try:
                    conn.execute("ALTER TABLE leads_bruts ADD COLUMN campaign_id INTEGER REFERENCES campagnes(id) ON DELETE SET NULL")
                except: pass

        if 'campagnes' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(campagnes)").fetchall()]
            if 'nb_demande' not in cols:
                try:
                    conn.execute("ALTER TABLE campagnes ADD COLUMN nb_demande INTEGER DEFAULT 0")
                    print("  [MIGRATION] Colonne ajoutée: campagnes.nb_demande")
                except: pass
                
        if 'leads_audites' not in table_names:
            pass


def init_db():
    """Crée les tables et index si ils n'existent pas encore."""
    Path(DB_PATH.parent).mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""

        -- ─── CAMPAGNES ──────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS campagnes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nom             TEXT    NOT NULL,
            secteur         TEXT,
            ville           TEXT,
            date_creation   TEXT    DEFAULT (datetime('now')),
            total_leads     INTEGER DEFAULT 0,
            nb_demande      INTEGER DEFAULT 0,
            statut          TEXT    DEFAULT 'actif'
            -- statut: actif | archive
        );

        -- ─── LEADS BRUTS (scraper) ───────────────────────────────────────
        CREATE TABLE IF NOT EXISTS leads_bruts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id     INTEGER REFERENCES campagnes(id) ON DELETE SET NULL,
            nom             TEXT    NOT NULL,
            adresse         TEXT,
            site_web        TEXT,
            telephone       TEXT,
            email           TEXT,
            email_valide    TEXT    DEFAULT '',
            -- email_valide: Valide | Inconnu | Erreur | ''
            rating          REAL,
            nb_avis         INTEGER DEFAULT 0,
            category        TEXT,
            mot_cle         TEXT,
            ville           TEXT,
            lien_maps       TEXT,
            date_scraping   TEXT    DEFAULT (datetime('now')),
            statut          TEXT    DEFAULT 'en_attente',
            -- statut: en_attente | audite | audit_echoue | email_genere | envoye | archive
            sheets_synced   INTEGER DEFAULT 0
        );

        -- ─── LEADS AUDITÉS (auditeur + copywriter) ───────────────────────
        CREATE TABLE IF NOT EXISTS leads_audites (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id                     INTEGER REFERENCES leads_bruts(id) ON DELETE CASCADE,
            -- Performance Web (web_analyzer.py)
            mobile_score                INTEGER DEFAULT 0,
            desktop_score               INTEGER DEFAULT 0,
            tablet_score                INTEGER DEFAULT 0,
            lcp_ms                      REAL    DEFAULT 0,
            fcp_ms                      REAL    DEFAULT 0,
            cls                         REAL    DEFAULT 0,
            render_blocking_scripts     INTEGER DEFAULT 0,
            uses_cache                  INTEGER DEFAULT 0,
            page_size_kb                REAL    DEFAULT 0,
            -- SEO (parse_html)
            has_https                   INTEGER DEFAULT 0,
            has_meta_description        INTEGER DEFAULT 0,
            title_length                INTEGER DEFAULT 0,
            h1_count                    INTEGER DEFAULT 0,
            has_schema                  INTEGER DEFAULT 0,
            has_contact_button          INTEGER DEFAULT 0,
            tel_link                    INTEGER DEFAULT 0,
            images_without_alt          INTEGER DEFAULT 0,
            has_analytics               INTEGER DEFAULT 0,
            has_robots                  INTEGER DEFAULT 0,
            has_sitemap                 INTEGER DEFAULT 0,
            has_responsive_meta         INTEGER DEFAULT 0,
            cms_detected                TEXT,
            visible_text_words          INTEGER DEFAULT 0,
            -- Scores calculés
            score_performance           INTEGER DEFAULT 0,
            score_seo                   INTEGER DEFAULT 0,
            score_gmb                   INTEGER DEFAULT 0,
            score_urgence               REAL    DEFAULT 0,
            -- score_urgence: 0-10 (anciennement score_priorite)
            -- Copywriting Jean-Marc
            top3_problems               TEXT,   -- JSON array
            service_suggere             TEXT,
            probleme_principal          TEXT,
            arguments                   TEXT,   -- JSON array
            rapport_resume              TEXT,
            email_objet                 TEXT,
            email_corps                 TEXT,
            approuve                    INTEGER DEFAULT 0,
            -- Rapport PDF
            lien_rapport                TEXT,
            lien_pdf                    TEXT,
            template_used               TEXT,
            -- Meta
            date_audit                  TEXT    DEFAULT (datetime('now')),
            statut                      TEXT    DEFAULT 'audite',
            sheets_synced               INTEGER DEFAULT 0
        );

        -- ─── EMAILS ENVOYÉS (brevo_sender.py) ────────────────────────────
        CREATE TABLE IF NOT EXISTS emails_envoyes (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id             INTEGER REFERENCES leads_bruts(id) ON DELETE SET NULL,
            message_id_brevo    TEXT,
            message_id_resend   TEXT,
            date_envoi          TEXT    DEFAULT (datetime('now')),
            -- Email envoyé
            email_destinataire  TEXT,
            email_objet         TEXT,
            email_corps         TEXT,
            lien_rapport        TEXT,
            statut_envoi        TEXT    DEFAULT 'envoye',
            -- Tracking (webhooks)
            ouvert              INTEGER DEFAULT 0,
            date_ouverture      TEXT,
            nb_ouvertures       INTEGER DEFAULT 0,
            clique              INTEGER DEFAULT 0,
            date_clic           TEXT,
            bounce              INTEGER DEFAULT 0,
            spam                INTEGER DEFAULT 0,
            -- Réponse commerciale
            repondu             INTEGER DEFAULT 0,
            date_reponse        TEXT,
            type_reponse        TEXT,
            -- type_reponse: positive | negative | neutre | rdv
            -- CRM
            rdv_confirme        INTEGER DEFAULT 0,
            date_rdv            TEXT,
            notes               TEXT,
            sheets_synced       INTEGER DEFAULT 0
        );

        -- ─── LOG DE SYNCHRONISATION ───────────────────────────────────────
        CREATE TABLE IF NOT EXISTS sync_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name  TEXT,
            direction   TEXT,   -- sheets_to_sqlite | sqlite_to_sheets
            rows_synced INTEGER DEFAULT 0,
            date_sync   TEXT    DEFAULT (datetime('now')),
            statut      TEXT,   -- ok | erreur
            erreur      TEXT
        );

        -- ─── INDEX ────────────────────────────────────────────────────────
        CREATE INDEX IF NOT EXISTS idx_leads_statut
            ON leads_bruts(statut);
        CREATE INDEX IF NOT EXISTS idx_leads_date
            ON leads_bruts(date_scraping DESC);
        CREATE INDEX IF NOT EXISTS idx_leads_ville
            ON leads_bruts(ville);
        CREATE INDEX IF NOT EXISTS idx_audits_score
            ON leads_audites(score_urgence DESC);
        CREATE INDEX IF NOT EXISTS idx_audits_lead
            ON leads_audites(lead_id);
        CREATE INDEX IF NOT EXISTS idx_emails_date
            ON emails_envoyes(date_envoi DESC);
        CREATE INDEX IF NOT EXISTS idx_emails_repondu
            ON emails_envoyes(repondu);

        """)
    print(f"[OK] Base SQLite: {DB_PATH}")
    migrate_db()


# ===========================================================
# HELPERS INTERNES
# ===========================================================

def _serialize_json(data: dict, keys: list) -> dict:
    """Sérialise les champs de type liste en JSON string."""
    result = dict(data)
    for key in keys:
        if isinstance(result.get(key), (list, dict)):
            result[key] = json.dumps(result[key], ensure_ascii=False)
    return result


def _deserialize_json(row: dict, keys: list) -> dict:
    """Désérialise les champs JSON string en objets Python."""
    result = dict(row)
    for key in keys:
        val = result.get(key)
        if val and isinstance(val, str):
            try:
                result[key] = json.loads(val)
            except Exception:
                pass
    return result


# ===========================================================
# LEADS BRUTS
# ===========================================================

def insert_lead(lead: dict) -> int | None:
    """
    Insère un lead depuis le scraper. Retourne l'id SQLite.
    Ignore les doublons (même nom + ville).
    """
    try:
        with get_conn() as conn:
            # Vérifier doublon
            existing = conn.execute(
                "SELECT id FROM leads_bruts WHERE LOWER(nom)=LOWER(?) AND LOWER(ville)=LOWER(?)",
                (lead.get('nom', ''), lead.get('ville', ''))
            ).fetchone()
            if existing:
                return existing['id']

            cur = conn.execute("""
                INSERT INTO leads_bruts
                (campaign_id, nom, adresse, site_web, telephone, email,
                 email_valide, rating, nb_avis, category,
                 mot_cle, ville, lien_maps)
                VALUES
                (:campaign_id, :nom, :adresse, :site_web, :telephone, :email,
                 :email_valide, :rating, :nb_avis, :category,
                 :mot_cle, :ville, :lien_maps)
            """, {
                'campaign_id':  lead.get('campaign_id'),
                'nom':          lead.get('nom', ''),
                'adresse':      lead.get('adresse', ''),
                'site_web':     lead.get('site_web', ''),
                'telephone':    lead.get('telephone', ''),
                'email':        lead.get('email', ''),
                'email_valide': lead.get('statut_email', lead.get('email_valide', '')),
                'rating':       lead.get('rating'),
                'nb_avis':      lead.get('nb_avis', 0),
                'category':     lead.get('category', ''),
                'mot_cle':      lead.get('mot_cle', ''),
                'ville':        lead.get('ville', ''),
                'lien_maps':    lead.get('lien_maps', ''),
            })
            return cur.lastrowid
    except Exception as e:
        logger.error(f"insert_lead → {e}")
        raise


def get_leads_pending() -> list:
    """Retourne les leads non encore audités."""
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM leads_bruts
                WHERE statut = 'en_attente'
                ORDER BY date_scraping DESC
            """).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_leads_pending → {e}")
        return []


def get_all_leads(statut: str = 'tous', limit: int = 500) -> list:
    """Retourne tous les leads avec leur data d'audit si disponible."""
    try:
        with get_conn() as conn:
            if statut == 'tous':
                sql = """
                    SELECT lb.*,
                           la.mobile_score, la.desktop_score, la.score_urgence,
                           la.score_performance, la.score_seo,
                           la.email_objet, la.email_corps, la.approuve,
                           la.lien_rapport, la.lien_pdf,
                           la.probleme_principal, la.service_suggere,
                           la.lcp_ms, la.cms_detected
                    FROM leads_bruts lb
                    LEFT JOIN leads_audites la ON la.lead_id = lb.id
                    ORDER BY lb.date_scraping DESC
                    LIMIT ?
                """
                rows = conn.execute(sql, (limit,)).fetchall()
            else:
                sql = """
                    SELECT lb.*,
                           la.mobile_score, la.desktop_score, la.score_urgence,
                           la.score_performance, la.score_seo,
                           la.email_objet, la.email_corps, la.approuve,
                           la.lien_rapport, la.lien_pdf,
                           la.probleme_principal, la.service_suggere,
                           la.lcp_ms, la.cms_detected
                    FROM leads_bruts lb
                    LEFT JOIN leads_audites la ON la.lead_id = lb.id
                    WHERE lb.statut = ?
                    ORDER BY lb.date_scraping DESC
                    LIMIT ?
                """
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
    except Exception as e:
        logger.error(f"update_lead_statut({lead_id}, {statut}) → {e}")


def get_lead_by_name(nom: str) -> dict | None:
    """Trouve un lead par son nom (insensible à la casse)."""
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
    """Supprime un lead et ses dépendances (audits, emails) en cascade."""
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM leads_bruts WHERE id=?", (lead_id,))
    except Exception as e:
        logger.error(f"delete_lead({lead_id}) → {e}")
        raise


def update_lead(lead_id: int, data: dict):
    """Met à jour les données brutes d'un lead (nom, ville, site_web, email...)."""
    try:
        allowed = {'nom', 'ville', 'site_web', 'adresse', 'telephone', 'email', 'mot_cle', 'category'}
        update_data = {k: v for k, v in data.items() if k in allowed}
        if not update_data:
            return
        sets = ', '.join(f"{k}=:{k}" for k in update_data)
        update_data['id'] = lead_id
        with get_conn() as conn:
            conn.execute(f"UPDATE leads_bruts SET {sets} WHERE id=:id", update_data)
    except Exception as e:
        logger.error(f"update_lead({lead_id}) → {e}")
        raise


# ===========================================================
# LEADS AUDITÉS
# ===========================================================

def insert_audit(audit: dict) -> int | None:
    """
    Insère un audit complet. Retourne l'id.
    Si un audit existe déjà pour ce lead_id, le remplace (UPDATE).
    """
    try:
        audit = _serialize_json(audit, ['top3_problems', 'arguments'])
        with get_conn() as conn:
            # Vérifier si audit existant
            existing = conn.execute(
                "SELECT id FROM leads_audites WHERE lead_id=?",
                (audit.get('lead_id'),)
            ).fetchone()

            if existing:
                # Mise à jour
                conn.execute("""
                    UPDATE leads_audites SET
                        mobile_score=:mobile_score,
                        desktop_score=:desktop_score,
                        tablet_score=:tablet_score,
                        lcp_ms=:lcp_ms, fcp_ms=:fcp_ms, cls=:cls,
                        render_blocking_scripts=:render_blocking_scripts,
                        uses_cache=:uses_cache, page_size_kb=:page_size_kb,
                        has_https=:has_https,
                        has_meta_description=:has_meta_description,
                        title_length=:title_length, h1_count=:h1_count,
                        has_schema=:has_schema,
                        has_contact_button=:has_contact_button,
                        tel_link=:tel_link,
                        images_without_alt=:images_without_alt,
                        has_analytics=:has_analytics,
                        has_robots=:has_robots, has_sitemap=:has_sitemap,
                        has_responsive_meta=:has_responsive_meta,
                        cms_detected=:cms_detected,
                        visible_text_words=:visible_text_words,
                        score_performance=:score_performance,
                        score_seo=:score_seo, score_gmb=:score_gmb,
                        score_urgence=:score_urgence,
                        top3_problems=:top3_problems,
                        service_suggere=:service_suggere,
                        probleme_principal=:probleme_principal,
                        arguments=:arguments,
                        rapport_resume=:rapport_resume,
                        email_objet=:email_objet,
                        email_corps=:email_corps,
                        approuve=:approuve,
                        lien_rapport=:lien_rapport,
                        lien_pdf=:lien_pdf,
                        template_used=:template_used,
                        nb_avis=:nb_avis,
                        date_audit=datetime('now'),
                        sheets_synced=0
                    WHERE lead_id=:lead_id
                """, _build_audit_params(audit))
                return existing['id']
            else:
                # Insertion
                cur = conn.execute("""
                    INSERT INTO leads_audites
                    (lead_id, mobile_score, desktop_score, tablet_score,
                     lcp_ms, fcp_ms, cls, render_blocking_scripts,
                     uses_cache, page_size_kb, has_https,
                     has_meta_description, title_length, h1_count,
                     has_schema, has_contact_button, tel_link,
                     images_without_alt, has_analytics,
                     has_robots, has_sitemap, has_responsive_meta,
                     cms_detected, visible_text_words,
                     score_performance, score_seo, score_gmb, score_urgence,
                     top3_problems, service_suggere, probleme_principal,
                     arguments, rapport_resume, email_objet, email_corps,
                     approuve, lien_rapport, lien_pdf, template_used, nb_avis)
                    VALUES
                    (:lead_id, :mobile_score, :desktop_score, :tablet_score,
                     :lcp_ms, :fcp_ms, :cls, :render_blocking_scripts,
                     :uses_cache, :page_size_kb, :has_https,
                     :has_meta_description, :title_length, :h1_count,
                     :has_schema, :has_contact_button, :tel_link,
                     :images_without_alt, :has_analytics,
                     :has_robots, :has_sitemap, :has_responsive_meta,
                     :cms_detected, :visible_text_words,
                     :score_performance, :score_seo, :score_gmb, :score_urgence,
                     :top3_problems, :service_suggere, :probleme_principal,
                     :arguments, :rapport_resume, :email_objet, :email_corps,
                     :approuve, :lien_rapport, :lien_pdf, :template_used, :nb_avis)
                """, _build_audit_params(audit))
                return cur.lastrowid
    except Exception as e:
        logger.error(f"insert_audit → {e}")
        raise


def _build_audit_params(audit: dict) -> dict:
    """Construit le dict de paramètres pour un audit, avec valeurs par défaut."""
    return {
        'lead_id':                  audit.get('lead_id'),
        'mobile_score':             audit.get('mobile_score', 0),
        'desktop_score':            audit.get('desktop_score', 0),
        'tablet_score':             audit.get('tablet_score', 0),
        'lcp_ms':                   audit.get('lcp_ms', audit.get('mobile_lcp_ms', 0)),
        'fcp_ms':                   audit.get('fcp_ms', 0),
        'cls':                      audit.get('cls', 0),
        'render_blocking_scripts':  audit.get('render_blocking_scripts', 0),
        'uses_cache':               int(bool(audit.get('uses_cache', False))),
        'page_size_kb':             audit.get('page_size_kb', 0),
        'has_https':                int(bool(audit.get('has_https', False))),
        'has_meta_description':     int(bool(audit.get('has_meta_description', False))),
        'title_length':             audit.get('title_length', 0),
        'h1_count':                 audit.get('h1_count', 0),
        'has_schema':               int(bool(audit.get('has_schema', False))),
        'has_contact_button':       int(bool(audit.get('has_contact_button', False))),
        'tel_link':                 int(bool(audit.get('tel_link', False))),
        'images_without_alt':       audit.get('images_without_alt', 0),
        'has_analytics':            int(bool(audit.get('has_analytics', False))),
        'has_robots':               int(bool(audit.get('has_robots', False))),
        'has_sitemap':              int(bool(audit.get('has_sitemap', False))),
        'has_responsive_meta':      int(bool(audit.get('has_responsive_meta', False))),
        'cms_detected':             audit.get('cms_detected'),
        'visible_text_words':       audit.get('visible_text_words', 0),
        'score_performance':        audit.get('score_performance', audit.get('mobile_score', 0)),
        'score_seo':                audit.get('score_seo', 0),
        'score_gmb':                audit.get('score_gmb', 0),
        'score_urgence':            audit.get('score_urgence', audit.get('score_priorite', 0)),
        'top3_problems':            audit.get('top3_problems'),
        'service_suggere':          audit.get('service_suggere', ''),
        'probleme_principal':       audit.get('probleme_principal', ''),
        'arguments':                audit.get('arguments'),
        'rapport_resume':           audit.get('rapport_resume', ''),
        'email_objet':              audit.get('email_objet', ''),
        'email_corps':              audit.get('email_corps', ''),
        'approuve':                 int(bool(audit.get('approuve', False))),
        'lien_rapport':             audit.get('lien_rapport', ''),
        'lien_pdf':                 audit.get('lien_pdf', audit.get('lien_rapport', '')),
        'template_used':            audit.get('template_used', ''),
        'nb_avis':                 audit.get('nb_avis', 0),
    }


def get_audits_ready_for_email() -> list:
    """Leads audités avec email généré et approuvé, non encore envoyés."""
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT
                    lb.id as lead_id, lb.nom, lb.email,
                    lb.ville, lb.category, lb.site_web, lb.rating, lb.nb_avis,
                    la.id as audit_id,
                    la.mobile_score, la.score_performance, la.score_seo, la.score_urgence,
                    la.lcp_ms, la.email_objet, la.email_corps, la.approuve,
                    la.lien_rapport, la.lien_pdf, la.probleme_principal
                FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                WHERE la.email_corps IS NOT NULL
                AND la.email_corps != ''
                AND lb.email IS NOT NULL
                AND lb.email != ''
                AND lb.statut != 'envoye'
                ORDER BY la.score_urgence DESC
            """).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_audits_ready_for_email → {e}")
        return []


def get_audits_with_reports(date_start: str | None = None, date_end: str | None = None) -> list:
    """Leads audités ayant un rapport PDF généré."""
    try:
        params = []
        date_filter = ""
        if date_start and date_end:
            date_filter = " AND DATE(la.date_audit) >= ? AND DATE(la.date_audit) <= ?"
            params.extend([date_start, date_end])
        with get_conn() as conn:
            rows = conn.execute(f"""
                SELECT
                    lb.id, lb.nom, lb.ville, lb.category,
                    la.score_urgence, la.lien_rapport,
                    la.lien_pdf, la.date_audit
                FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                WHERE la.lien_rapport IS NOT NULL
                AND la.lien_rapport != ''
                {date_filter}
                ORDER BY la.score_urgence DESC
            """, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_audits_with_reports → {e}")
        return []


def update_audit_email(lead_id: int, email_objet: str, email_corps: str, approuve: bool = False):
    """Met à jour l'email généré pour un lead audité."""
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE leads_audites
                SET email_objet=?, email_corps=?, approuve=?
                WHERE lead_id=?
            """, (email_objet, email_corps, int(approuve), lead_id))
    except Exception as e:
        logger.error(f"update_audit_email({lead_id}) → {e}")


def update_audit_approval(lead_nom: str, approuve: bool):
    """Approuve ou rejette un email depuis le dashboard."""
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE leads_audites
                SET approuve=?
                WHERE lead_id = (
                    SELECT id FROM leads_bruts
                    WHERE LOWER(nom)=LOWER(?) LIMIT 1
                )
            """, (int(approuve), lead_nom))
    except Exception as e:
        logger.error(f"update_audit_approval({lead_nom}) → {e}")


def update_audit_email_content(lead_nom: str, email_objet: str, email_corps: str):
    """Met à jour manuellement le sujet et le corps de l'email généré."""
    try:
        with get_conn() as conn:
            conn.execute("""
                UPDATE leads_audites
                SET email_objet=?, email_corps=?
                WHERE lead_id = (
                    SELECT id FROM leads_bruts
                    WHERE LOWER(nom)=LOWER(?) LIMIT 1
                )
            """, (email_objet, email_corps, lead_nom))
    except Exception as e:
        logger.error(f"update_audit_email_content({lead_nom}) → {e}")


# ===========================================================
# EMAILS ENVOYÉS
# ===========================================================

def insert_email_sent(data: dict) -> int | None:
    """Enregistre un email envoyé. Retourne l'id."""
    try:
        with get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO emails_envoyes
                (lead_id, message_id_brevo, message_id_resend, email_destinataire,
                 email_objet, email_corps, lien_rapport, statut_envoi)
                VALUES
                (:lead_id, :message_id_brevo, :message_id_resend, :email_destinataire,
                 :email_objet, :email_corps, :lien_rapport, :statut_envoi)
            """, {
                'lead_id':          data.get('lead_id'),
                'message_id_brevo': data.get('message_id_brevo', ''),
                'message_id_resend': data.get('message_id_resend', data.get('message_id', '')),
                'email_destinataire': data.get('email_destinataire', ''),
                'email_objet':      data.get('email_objet', ''),
                'email_corps':      data.get('email_corps', ''),
                'lien_rapport':     data.get('lien_rapport', ''),
                'statut_envoi':     data.get('statut_envoi', 'envoye'),
            })
            return cur.lastrowid
    except Exception as e:
        logger.error(f"insert_email_sent → {e}")
        raise


def update_email_tracking(message_id: str, data: dict):
    """Mise à jour tracking depuis un webhook (Resend ou Brevo)."""
    try:
        allowed = {
            'ouvert', 'date_ouverture', 'nb_ouvertures',
            'clique', 'date_clic', 'bounce', 'spam',
            'statut_envoi', 'repondu', 'date_reponse', 'type_reponse'
        }
        data = {k: v for k, v in data.items() if k in allowed}
        if not data:
            return
        sets = ', '.join(f"{k}=:{k}" for k in data)
        with get_conn() as conn:
            cur = conn.execute(
                f"UPDATE emails_envoyes SET {sets} "
                f"WHERE message_id_resend=:message_id OR message_id_brevo=:message_id",
                {'message_id': message_id, **data}
            )
            if cur.rowcount > 0:
                logger.info(f"SQL Update: Tracking mis à jour pour {message_id} ({cur.rowcount} lignes)")
            else:
                logger.warning(f"SQL Update: Aucun email trouvé pour l'ID {message_id}")
    except Exception as e:
        logger.error(f"update_email_tracking({message_id}) → {e}")


def update_crm_manual(email_id: int, data: dict):
    """Mise à jour manuelle CRM depuis le dashboard."""
    try:
        allowed = {'type_reponse', 'rdv_confirme', 'date_rdv',
                   'notes', 'repondu', 'date_reponse'}
        data = {k: v for k, v in data.items() if k in allowed}
        if not data:
            return
        sets = ', '.join(f"{k}=:{k}" for k in data)
        data['id'] = email_id
        with get_conn() as conn:
            conn.execute(
                f"UPDATE emails_envoyes SET {sets} WHERE id=:id", data
            )
    except Exception as e:
        logger.error(f"update_crm_manual({email_id}) → {e}")


def update_audit_pdf(lead_id: int, pdf_path: str):
    """Met à jour le chemin du PDF local pour un lead audité."""
    try:
        with get_conn() as conn:
            conn.execute(
                "UPDATE leads_audites SET lien_pdf = ? WHERE lead_id = ?",
                (pdf_path, lead_id)
            )
            # Marquer aussi le statut comme audité au cas où
            conn.execute("UPDATE leads_bruts SET statut='audite' WHERE id=?", (lead_id,))
            logger.info(f"Audit PDF mis à jour pour lead {lead_id}: {pdf_path}")
    except Exception as e:
        logger.error(f"update_audit_pdf({lead_id}) → {e}")


def get_crm_data(filter_type: str = 'tous', date_start: str | None = None, date_end: str | None = None) -> list:
    """Retourne les données CRM filtrées par statut."""
    try:
        with get_conn() as conn:
            where_clauses = []
            params = []
            
            if filter_type == 'ouverts':
                where_clauses.append("ee.ouvert = 1")
            elif filter_type == 'cliques':
                where_clauses.append("ee.clique = 1")
            elif filter_type == 'repondus':
                where_clauses.append("ee.repondu = 1")
            elif filter_type == 'positifs':
                where_clauses.append("ee.type_reponse = 'positive'")
            elif filter_type == 'rdv':
                where_clauses.append("ee.rdv_confirme = 1")
            elif filter_type == 'bounces':
                where_clauses.append("(ee.bounce = 1 OR ee.statut_envoi = 'bounced')")
            elif filter_type == 'spam':
                where_clauses.append("(ee.spam = 1 OR ee.statut_envoi = 'spam')")
                
            if date_start and date_end:
                where_clauses.append("DATE(ee.date_envoi) >= ?")
                where_clauses.append("DATE(ee.date_envoi) <= ?")
                params.extend([date_start, date_end])
            
            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
            sql = f"""
                SELECT
                    COALESCE(lb.nom, 'Test') AS nom, 
                    COALESCE(lb.email, ee.email_objet) AS prospect_email, 
                    COALESCE(lb.ville, '-') AS ville,
                    ee.id AS email_id,
                    ee.date_envoi, ee.email_objet,
                    ee.ouvert, ee.date_ouverture, ee.nb_ouvertures,
                    ee.clique, ee.date_clic,
                    ee.bounce, ee.spam,
                    ee.repondu, ee.date_reponse, ee.type_reponse,
                    ee.rdv_confirme, ee.date_rdv, ee.notes,
                    ee.statut_envoi, ee.lien_rapport
                FROM emails_envoyes ee
                LEFT JOIN leads_bruts lb ON lb.id = ee.lead_id
                {where_sql}
                ORDER BY ee.date_envoi DESC
            """
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_crm_data({filter_type}) → {e}")
        return []


# ===========================================================
# GESTION DES CAMPAGNES
# ===========================================================

def insert_campaign(nom: str, secteur: str = "", ville: str = "", nb_demande: int = 0) -> int:
    """Crée une nouvelle campagne et retourne son ID."""
    try:
        with get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO campagnes (nom, secteur, ville, nb_demande)
                VALUES (?, ?, ?, ?)
            """, (nom, secteur, ville, nb_demande))
            return cur.lastrowid
    except Exception as e:
        logger.error(f"insert_campaign({nom}) → {e}")
        raise


def get_all_campaigns(date_start: str | None = None, date_end: str | None = None) -> list:
    """Retourne la liste de toutes les campagnes avec leurs stats de base, filtrables par date."""
    try:
        where_clause = "WHERE 1=1"
        params = []
        if date_start:
            where_clause += " AND date(c.date_creation) >= ?"
            params.append(date_start)
        if date_end:
            where_clause += " AND date(c.date_creation) <= ?"
            params.append(date_end)

        with get_conn() as conn:
            rows = conn.execute(f"""
                SELECT 
                    c.*,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id) as leads_total,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id AND site_web IS NOT NULL AND site_web != '') as leads_with_site,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id AND email IS NOT NULL AND email != '') as leads_with_email,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = c.id AND statut IN ('audite','email_genere','envoye')) as nb_audites,
                    (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id = lb.id WHERE lb.campaign_id = c.id) as emails_envoyes,
                    (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id = lb.id WHERE lb.campaign_id = c.id AND ee.ouvert=1) as nb_ouverts,
                    (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id = lb.id WHERE lb.campaign_id = c.id AND ee.clique=1) as nb_cliques,
                    (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id = lb.id WHERE lb.campaign_id = c.id AND ee.repondu=1) as nb_reponses,
                    (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id = lb.id WHERE lb.campaign_id = c.id AND ee.rdv_confirme=1) as nb_rdv
                FROM campagnes c
                {where_clause}
                ORDER BY c.date_creation DESC
                LIMIT 100
            """, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_all_campaigns → {e}")
        return []


def get_campaign_by_id(camp_id: int) -> dict | None:
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM campagnes WHERE id = ?", (camp_id,)).fetchone()
            if not row:
                return None
            cols = [r[1] for r in conn.execute('PRAGMA table_info(campagnes)').fetchall()]
            campaign = dict(zip(cols, row))
            stats = conn.execute("""
                SELECT
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = ?) as leads_total,
                    (SELECT COUNT(*) FROM leads_bruts WHERE campaign_id = ? AND statut IN ('audite','email_genere','envoye')) as nb_audites,
                    (SELECT COUNT(*) FROM emails_envoyes ee JOIN leads_bruts lb ON ee.lead_id = lb.id WHERE lb.campaign_id = ?) as emails_envoyes
            """, (camp_id, camp_id, camp_id)).fetchone()
            campaign['leads_total'] = stats[0]
            campaign['nb_audites'] = stats[1]
            campaign['emails_envoyes'] = stats[2]
            return campaign
    except Exception as e:
        logger.error(f"get_campaign_by_id({camp_id}) → {e}")
        return None


def delete_campaign(camp_id: int):
    """Supprime une campagne. Les leads bruts associés auront leur campaign_id mis à NULL (ON DELETE SET NULL)."""
    try:
        with get_conn() as conn:
            conn.execute("DELETE FROM campagnes WHERE id = ?", (camp_id,))
    except Exception as e:
        logger.error(f"delete_campaign({camp_id}) → {e}")
        raise


# ===========================================================
# STATS DASHBOARD (cockpit)
# ===========================================================

def get_dashboard_stats(campaign_id: int | None = None, date_start: str | None = None, date_end: str | None = None, campaign_ids: str | None = None) -> dict:
    """Toutes les métriques cockpit en une seule requête SQLite."""
    try:
        with get_conn() as conn:
            stats = {}
            where_lead = "WHERE 1=1"
            where_email = "WHERE 1=1"
            params = []
            
            if campaign_ids:
                ids = [int(x.strip()) for x in campaign_ids.split(',') if x.strip().isdigit()]
                if ids:
                    placeholders = ','.join('?' * len(ids))
                    where_lead += f" AND campaign_id IN ({placeholders})"
                    where_email = f"JOIN leads_bruts lb ON emails_envoyes.lead_id = lb.id WHERE lb.campaign_id IN ({placeholders})"
                    params.extend(ids)
            elif campaign_id:
                where_lead += " AND campaign_id = ?"
                where_email = "JOIN leads_bruts lb ON emails_envoyes.lead_id = lb.id WHERE lb.campaign_id = ?"
                params.append(campaign_id)
                
            if date_start and date_end:
                where_lead += " AND DATE(date_scraping) >= ? AND DATE(date_scraping) <= ?"
                if "JOIN" in where_email:
                    where_email += " AND DATE(emails_envoyes.date_envoi) >= ? AND DATE(emails_envoyes.date_envoi) <= ?"
                else:
                    where_email += " AND DATE(date_envoi) >= ? AND DATE(date_envoi) <= ?"
                params.extend([date_start, date_end])

            # ── Pipeline leads ──
            sql_leads = f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN statut='en_attente' THEN 1 ELSE 0 END) AS en_attente,
                    SUM(CASE WHEN statut IN ('audite','email_genere','envoye') THEN 1 ELSE 0 END) AS audites,
                    SUM(CASE WHEN site_web IS NOT NULL AND site_web != '' THEN 1 ELSE 0 END) AS avec_site,
                    SUM(CASE WHEN email IS NOT NULL AND email != '' THEN 1 ELSE 0 END) AS avec_email
                FROM leads_bruts
                {where_lead}
            """
            r = conn.execute(sql_leads, params).fetchone()

            stats['leads_scrapes']   = r['total'] or 0
            stats['leads_attente']   = r['en_attente'] or 0
            stats['leads_audites']   = r['audites'] or 0
            stats['leads_site']      = r['avec_site'] or 0
            stats['emails_trouves']  = r['avec_email'] or 0

            # ── Emails envoyés ──
            sql_emails = f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN ouvert=1 THEN 1 ELSE 0 END) AS ouverts,
                    SUM(CASE WHEN repondu=1 THEN 1 ELSE 0 END) AS repondus,
                    SUM(CASE WHEN clique=1 THEN 1 ELSE 0 END) AS cliques,
                    SUM(CASE WHEN type_reponse='positive' THEN 1 ELSE 0 END) AS positifs,
                    SUM(CASE WHEN rdv_confirme=1 THEN 1 ELSE 0 END) AS rdv
                FROM emails_envoyes ee
                JOIN leads_bruts lb ON ee.lead_id = lb.id
                {where_email}
                AND statut_envoi IN ('envoye', 'delivré', 'test')
            """
            r = conn.execute(sql_emails, params).fetchone()

            envoyes = r['total'] or 0
            stats['envoyes']             = envoyes
            stats['emails_ouverts']      = r['ouverts'] or 0
            stats['emails_repondus']     = r['repondus'] or 0
            stats['reponses_positives']  = r['positifs'] or 0
            stats['rdv_obtenus']         = r['rdv'] or 0

            if envoyes > 0:
                stats['taux_ouverture'] = round((r['ouverts'] or 0) / envoyes * 100)
                stats['taux_clic']      = round((r['cliques'] or 0) / envoyes * 100)
                stats['taux_reponse']   = round((r['repondus'] or 0) / envoyes * 100)
                stats['taux_rdv']       = round((r['rdv'] or 0) / envoyes * 100)
                stats['indice_perf']    = round(
                    stats.get('taux_ouverture', 0) * 0.15 +
                    stats.get('taux_clic', 0)      * 0.15 +
                    stats.get('taux_reponse', 0)   * 0.35 +
                    stats.get('taux_rdv', 0)       * 0.35
                )
            else:
                stats['taux_ouverture'] = 0
                stats['taux_clic']      = 0
                stats['taux_reponse']   = 0
                stats['taux_rdv']       = 0
                stats['indice_perf']    = 0

            # ── Audits & Rapports ──
            sql_audits = f"""
                SELECT
                    AVG(mobile_score) AS avg_mobile,
                    AVG(score_seo) AS avg_seo,
                    AVG(score_urgence) AS avg_score,
                    SUM(CASE WHEN score_urgence >= 7 THEN 1 ELSE 0 END) AS prioritaires,
                    SUM(CASE WHEN email_corps IS NOT NULL AND email_corps != '' THEN 1 ELSE 0 END) AS avec_email_genere,
                    SUM(CASE WHEN lien_rapport IS NOT NULL AND lien_rapport != '' THEN 1 ELSE 0 END) AS avec_rapport
                FROM leads_audites
                JOIN leads_bruts lb ON leads_audites.lead_id = lb.id
                {where_lead.replace('campaign_id', 'lb.campaign_id')}
            """
            r = conn.execute(sql_audits, params).fetchone()

            stats['score_moyen']         = round(r['avg_score'] or 0, 1)
            stats['mobile_moyen']        = round(r['avg_mobile'] or 0, 1)
            stats['seo_moyen']           = round(r['avg_seo'] or 0, 1)
            stats['leads_prioritaires']  = r['prioritaires'] or 0
            stats['emails_prets']        = r['avec_email_genere'] or 0
            stats['pdfs_generes']        = r['avec_rapport'] or 0

            # ── Quotas API ──
            # Compter les audits du jour (proxy pour usage Groq)
            r_groq = conn.execute("SELECT COUNT(*) FROM leads_audites WHERE DATE(date_audit) = DATE('now')").fetchone()
            
            # Lire les usages réels depuis config_manager
            from config_manager import get_config
            cfg = get_config()
            hunter_usage = cfg.get('hunter_usage', 0) or 0
            carbone_usage = cfg.get('carbone_usage', 0) or 0
            brevo_usage = cfg.get('brevo_usage', 0) or 0
            
            stats['quotas'] = {
                'groq':   r_groq[0] if r_groq else 0,  # Audits du jour (proxy usage)
                'resend': envoyes,  # Emails envoyés via Resend
                'brevo':  brevo_usage,  # Emails envoyés via Brevo
                'hunter': hunter_usage,  # Appels API Hunter réels
                'carbone': carbone_usage,  # PDFs générés
                'gemini': cfg.get('gemini_usage', 0) or 0,  # Google AI
                'anthropic': cfg.get('anthropic_usage', 0) or 0,  # Claude
                'pagespeed': cfg.get('pagespeed_usage', 0) or 0  # PageSpeed API
            }

            return stats

    except Exception as e:
        logger.error(f"get_dashboard_stats → {e}")
        return {
            'leads_scrapes': 0, 'leads_audites': 0, 'emails_prets': 0, 'envoyes': 0,
            'leads_site': 0, 'emails_trouves': 0, 'score_moyen': 0,
            'leads_prioritaires': 0, 'pdfs_generes': 0,
            'quotas': {'groq': 0, 'brevo': 0, 'hunter': 0}
        }


def get_leads_for_dashboard(
    campaign_id: int | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    campaign_ids: str | None = None,
    limit: int = 500
) -> list:
    """
    Retourne les leads enrichis avec données d'audit pour le dashboard.
    campaign_ids: string CSV d'IDs (ex: "1,2,3") pour filtrer plusieurs collectes.
    """
    try:
        where_clause = "WHERE 1=1"
        params = []
        
        if campaign_ids:
            ids = [int(x.strip()) for x in campaign_ids.split(',') if x.strip().isdigit()]
            if ids:
                placeholders = ','.join('?' * len(ids))
                where_clause += f" AND lb.campaign_id IN ({placeholders})"
                params.extend(ids)
        elif campaign_id:
            where_clause += " AND lb.campaign_id = ?"
            params.append(campaign_id)
            
        if date_start and date_end:
            where_clause += " AND DATE(lb.date_scraping) >= ? AND DATE(lb.date_scraping) <= ?"
            params.extend([date_start, date_end])
            
        with get_conn() as conn:
            sql = f"""
                SELECT
                    lb.id, lb.nom, lb.ville,
                    lb.category AS secteur,
                    lb.site_web, lb.email, lb.telephone,
                    lb.rating AS note, lb.nb_avis AS avis,
                    lb.statut, lb.date_scraping,
                    lb.campaign_id,
                    CASE WHEN lb.site_web != '' AND lb.site_web IS NOT NULL THEN 1 ELSE 0 END AS a_site,
                    CASE WHEN lb.email != '' AND lb.email IS NOT NULL THEN 1 ELSE 0 END AS a_email,
                    la.score_performance AS score_perf,
                    la.score_seo,
                    la.score_urgence,
                    la.lcp_ms AS lcp,
                    la.lien_rapport,
                    la.email_corps,
                    la.email_objet,
                    la.date_audit,
                    la.approuve,
                    la.probleme_principal
                FROM leads_bruts lb
                LEFT JOIN leads_audites la ON la.lead_id = lb.id
                {where_clause}
                ORDER BY lb.date_scraping DESC
                LIMIT {limit}
            """
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_leads_for_dashboard → {e}")
        return []


def get_emails_for_dashboard(campaign_id: int | None = None, date_start: str | None = None, date_end: str | None = None) -> list:
    """
    Retourne les emails générés pour la section Campagnes.
    """
    try:
        where_clause = "WHERE la.email_corps IS NOT NULL AND la.email_corps != ''"
        params = []
        if campaign_id:
            where_clause += " AND lb.campaign_id = ?"
            params.append(campaign_id)
            
        if date_start and date_end:
            where_clause += " AND DATE(la.date_audit) >= ? AND DATE(la.date_audit) <= ?"
            params.extend([date_start, date_end])

        with get_conn() as conn:
            sql = f"""
                SELECT
                    lb.nom, lb.email, lb.ville,
                    la.email_objet AS objet,
                    la.email_corps AS corps,
                    la.score_urgence,
                    la.approuve,
                    la.lien_rapport
                FROM leads_audites la
                JOIN leads_bruts lb ON lb.id = la.lead_id
                {where_clause}
                AND (
                    la.mobile_score IS NOT NULL 
                    OR la.score_seo IS NOT NULL 
                    OR la.lien_rapport IS NOT NULL 
                    OR la.lien_rapport != ''
                )
                ORDER BY la.score_urgence DESC
                LIMIT 200
            """
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_emails_for_dashboard → {e}")
        return []


# ===========================================================
# SYNC LOG
# ===========================================================

def log_sync(table_name: str, direction: str, rows_synced: int,
             statut: str = 'ok', erreur: str | None = None):
    """Enregistre une opération de synchronisation."""
    try:
        with get_conn() as conn:
            conn.execute("""
                INSERT INTO sync_log (table_name, direction, rows_synced, statut, erreur)
                VALUES (?, ?, ?, ?, ?)
            """, (table_name, direction, rows_synced, statut, erreur))
    except Exception as e:
        logger.error(f"log_sync → {e}")


# ===========================================================
# POINT D'ENTRÉE (test)
# ===========================================================

if __name__ == "__main__":
    init_db()
    stats = get_dashboard_stats()
    print(f"\nStats:")
    for k, v in stats.items():
        if k != 'quotas':
            print(f"   {k}: {v}")
