# -*- coding: utf-8 -*-
from pathlib import Path
from .connection import get_conn, DB_PATH, logger


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
                ("ouverture", "INTEGER DEFAULT 0"),
                ("date_ouverture", "TEXT"),
                ("bounce", "INTEGER DEFAULT 0"),
                ("spam", "INTEGER DEFAULT 0"),
                ("message_id_resend", "TEXT"),
                ("template_variant", "TEXT DEFAULT 'v1'"),
            ]
            for col_name, col_def in migrations:
                if col_name not in cols:
                    try:
                        conn.execute(f"ALTER TABLE emails_envoyes ADD COLUMN {col_name} {col_def}")
                        print(f"  [MIGRATION] Colonne ajoutée: emails_envoyes.{col_name}")
                    except Exception:
                        pass

        # Ajout : champs critiques phase 1
        migrate_emails_envoyes_critical_fields()
        migrate_emails_envoyes_tracking_fields()

        if 'leads_bruts' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(leads_bruts)").fetchall()]
            if 'email_valide' not in cols:
                try:
                    conn.execute("ALTER TABLE leads_bruts ADD COLUMN email_valide TEXT DEFAULT ''")
                except Exception:
                    pass
            if 'campaign_id' not in cols:
                try:
                    conn.execute("ALTER TABLE leads_bruts ADD COLUMN campaign_id INTEGER REFERENCES campagnes(id) ON DELETE SET NULL")
                except Exception:
                    pass
            if 'logo_url' not in cols:
                try:
                    conn.execute("ALTER TABLE leads_bruts ADD COLUMN logo_url TEXT DEFAULT ''")
                    print("  [MIGRATION] Colonne ajoutée: leads_bruts.logo_url")
                except Exception:
                    pass

        if 'leads_audites' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(leads_audites)").fetchall()]
            if 'template_variant' not in cols:
                try:
                    conn.execute("ALTER TABLE leads_audites ADD COLUMN template_variant TEXT DEFAULT 'v1'")
                    print("  [MIGRATION] Colonne ajoutée: leads_audites.template_variant")
                except Exception:
                    pass
            if 'statut_prospection' not in cols:
                try:
                    conn.execute("ALTER TABLE leads_audites ADD COLUMN statut_prospection TEXT DEFAULT 'a_contacter'")
                    print("  [MIGRATION] Colonne ajoutée: leads_audites.statut_prospection")
                except Exception:
                    pass
            # Sniper enrichment columns
            sniper_audit_cols = [
                ("email_valide",       "TEXT"),
                ("email_source",       "TEXT"),
                ("copywriting_mode",   "TEXT DEFAULT 'transfert'"),
                ("ceo_prenom",         "TEXT"),
                ("ceo_nom",            "TEXT"),
                ("ceo_source",         "TEXT"),
                ("telephone_sniper",   "TEXT"),
                ("mx_host",            "TEXT"),
                ("is_catch_all",       "INTEGER DEFAULT 0"),
                ("linkedin_url",       "TEXT"),
                ("score_temperature",  "INTEGER DEFAULT 0"),
            ]
            for col_name, col_def in sniper_audit_cols:
                if col_name not in cols:
                    try:
                        conn.execute(f"ALTER TABLE leads_audites ADD COLUMN {col_name} {col_def}")
                        print(f"  [MIGRATION] Colonne ajoutée: leads_audites.{col_name}")
                    except Exception:
                        pass

            # Colonnes pour le reporter (HTML local + screenshots)
            reporter_cols = [
                ("rapport_html", "TEXT"),
                ("screenshot_desktop", "TEXT"),
                ("screenshot_mobile", "TEXT"),
            ]
            for col_name, col_def in reporter_cols:
                if col_name not in cols:
                    try:
                        conn.execute(f"ALTER TABLE leads_audites ADD COLUMN {col_name} {col_def}")
                        print(f"  [MIGRATION] Colonne ajoutée: leads_audites.{col_name}")
                    except Exception:
                        pass

            # Colonnes d'audit additionnelles et notifications
            extra_audit_cols = [
                ("audit_partial", "INTEGER DEFAULT 0"),
                ("audit_error", "TEXT"),
                ("notified_at", "TEXT"),
            ]
            for col_name, col_def in extra_audit_cols:
                if col_name not in cols:
                    try:
                        conn.execute(f"ALTER TABLE leads_audites ADD COLUMN {col_name} {col_def}")
                        print(f"  [MIGRATION] Colonne ajoutée: leads_audites.{col_name}")
                    except Exception:
                        pass

            # Colonnes de contact (prospection tracking)
            # NB: contact_mail/wp/li/fb/autres existent déjà dans certaines DB, on ne migre que ce qui manque
            contact_cols = [
                ("contact_mail",    "INTEGER DEFAULT 0"),
                ("contact_wp",      "INTEGER DEFAULT 0"),
                ("contact_li",      "INTEGER DEFAULT 0"),
                ("contact_fb",      "INTEGER DEFAULT 0"),
                ("contact_appel",   "INTEGER DEFAULT 0"),
                ("contact_autres",  "INTEGER DEFAULT 0"),
            ]
            for col_name, col_def in contact_cols:
                if col_name not in cols:
                    try:
                        conn.execute(f"ALTER TABLE leads_audites ADD COLUMN {col_name} {col_def}")
                        print(f"  [MIGRATION] Colonne ajoutée: leads_audites.{col_name}")
                    except Exception:
                        pass

        if 'campagnes' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(campagnes)").fetchall()]
            if 'nb_demande' not in cols:
                try:
                    conn.execute("ALTER TABLE campagnes ADD COLUMN nb_demande INTEGER DEFAULT 0")
                    print("  [MIGRATION] Colonne ajoutée: campagnes.nb_demande")
                except Exception:
                    pass

            # ─── Status Registry : suivi granulaire des campagnes ─────────
            campaign_tracker_cols = [
                ("source",         "TEXT DEFAULT 'maps'"),         # maps | ads | fb_ads | tech | jobs | bodacc
                ("phase",          "TEXT DEFAULT 'pending'"),      # pending | scraping | enrichment | audit | email_gen | done | failed | stopped
                ("error_message",  "TEXT"),                        # Raison de l'arrêt brutal
                ("stopped_at",     "TEXT"),                        # Timestamp arrêt
                ("started_at",     "TEXT"),                        # Timestamp début
                ("finished_at",    "TEXT"),                        # Timestamp fin
                ("progress_data",  "TEXT"),                        # JSON: {processed, total, emails_found, phase_detail}
            ]
            for col_name, col_def in campaign_tracker_cols:
                if col_name not in cols:
                    try:
                        conn.execute(f"ALTER TABLE campagnes ADD COLUMN {col_name} {col_def}")
                        print(f"  [MIGRATION] Colonne ajoutée: campagnes.{col_name}")
                    except Exception:
                        pass

        # ─── Sniper columns (Source 1 high-ticket pipeline) ──────────────────
        if 'leads_bruts' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(leads_bruts)").fetchall()]
            sniper_cols = [
                ("source",          "TEXT DEFAULT 'maps'"),        # 'maps' | 'ads' | 'tech' | 'jobs'
                ("tag_urgence",     "TEXT"),                        # 'perf' | 'securite' | 'automatisation'
                ("niveau_urgence",  "INTEGER DEFAULT 0"),           # 0-5
                ("donnees_audit",   "TEXT"),                        # JSON pré-qualification
                ("secteur",         "TEXT"),                        # étiquette secteur pour filtrage
            ]
            for col_name, col_def in sniper_cols:
                if col_name not in cols:
                    try:
                        conn.execute(f"ALTER TABLE leads_bruts ADD COLUMN {col_name} {col_def}")
                        print(f"  [MIGRATION] Colonne ajoutée: leads_bruts.{col_name}")
                    except Exception:
                        pass

        # ─── Planned Campaigns & Scraping Priorities ──────────────────
        if 'planned_campaigns' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(planned_campaigns)").fetchall()]
            if 'source' not in cols:
                try:
                    conn.execute("ALTER TABLE planned_campaigns ADD COLUMN source TEXT DEFAULT 'maps'")
                    print("  [MIGRATION] Colonne ajoutée: planned_campaigns.source")
                except Exception:
                    pass

        if 'scraping_priorities' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(scraping_priorities)").fetchall()]
            if 'source' not in cols:
                try:
                    conn.execute("ALTER TABLE scraping_priorities ADD COLUMN source TEXT DEFAULT 'maps'")
                    print("  [MIGRATION] Colonne ajoutée: scraping_priorities.source")
                except Exception:
                    pass
            try:
                # Re-créer l'index pour inclure 'source'
                conn.execute("DROP INDEX IF EXISTS idx_scraping_prio_uniq")
                conn.execute("CREATE UNIQUE INDEX idx_scraping_prio_uniq ON scraping_priorities(keyword, ville, source)")
            except Exception:
                pass

        migrate_email_events_table()
        migrate_lead_lists()

        # ─── Migration: pays pour leads_bruts et campagnes ───────────
        if 'leads_bruts' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(leads_bruts)").fetchall()]
            if 'pays' not in cols:
                try:
                    conn.execute("ALTER TABLE leads_bruts ADD COLUMN pays TEXT DEFAULT 'fr'")
                    print("  [MIGRATION] Colonne ajoutée: leads_bruts.pays")
                except Exception:
                    pass

        if 'campagnes' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(campagnes)").fetchall()]
            if 'pays' not in cols:
                try:
                    conn.execute("ALTER TABLE campagnes ADD COLUMN pays TEXT DEFAULT 'fr'")
                    print("  [MIGRATION] Colonne ajoutée: campagnes.pays")
                except Exception:
                    pass

        # ─── Migration: campaign_id dans lead_lists pour auto-listes ──
        if 'lead_lists' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(lead_lists)").fetchall()]
            if 'campaign_id' not in cols:
                try:
                    conn.execute("ALTER TABLE lead_lists ADD COLUMN campaign_id INTEGER REFERENCES campagnes(id) ON DELETE SET NULL")
                    print("  [MIGRATION] Colonne ajoutée: lead_lists.campaign_id")
                except Exception:
                    pass

        # ─── Migration: colonnes note/relance/archivage pour lead_lists ──
        if 'lead_lists' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(lead_lists)").fetchall()]
            new_cols = {
                'note': "ALTER TABLE lead_lists ADD COLUMN note TEXT DEFAULT ''",
                'contactee': "ALTER TABLE lead_lists ADD COLUMN contactee INTEGER DEFAULT 0",
                'contacted_at': "ALTER TABLE lead_lists ADD COLUMN contacted_at TEXT",
                'relance_j3': "ALTER TABLE lead_lists ADD COLUMN relance_j3 INTEGER DEFAULT 0",
                'relance_j7': "ALTER TABLE lead_lists ADD COLUMN relance_j7 INTEGER DEFAULT 0",
                'relance_j14': "ALTER TABLE lead_lists ADD COLUMN relance_j14 INTEGER DEFAULT 0",
                'archived': "ALTER TABLE lead_lists ADD COLUMN archived INTEGER DEFAULT 0",
                'archived_at': "ALTER TABLE lead_lists ADD COLUMN archived_at TEXT",
            }
            for col_name, sql in new_cols.items():
                if col_name not in cols:
                    try:
                        conn.execute(sql)
                        print(f"  [MIGRATION] Colonne ajoutée: lead_lists.{col_name}")
                    except Exception:
                        pass


def migrate_emails_envoyes_critical_fields():
    """Ajoute les colonnes critiques pour le tracking d'envoi si manquantes."""
    with get_conn() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(emails_envoyes)").fetchall()]
        migrations = [
            ("statut_envoi", "TEXT DEFAULT 'en_attente'"),
            ("message_erreur", "TEXT"),
            ("nb_tentatives_envoi", "INTEGER DEFAULT 0"),
            ("date_dernier_essai", "TEXT")
        ]
        for col_name, col_def in migrations:
            if col_name not in cols:
                try:
                    conn.execute(f"ALTER TABLE emails_envoyes ADD COLUMN {col_name} {col_def}")
                    print(f"  [MIGRATION] Colonne ajoutée: emails_envoyes.{col_name}")
                except Exception:
                    pass


def migrate_emails_envoyes_tracking_fields():
    """Ajoute les colonnes de tracking d'email et lead scoring si manquantes."""
    with get_conn() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(emails_envoyes)").fetchall()]
        migrations = [
            ("date_premiere_ouverture", "TEXT"),
            ("date_derniere_ouverture", "TEXT"),
            ("nb_clics", "INTEGER DEFAULT 0"),
            ("date_dernier_clic", "TEXT"),
            ("ip_ouverture", "TEXT"),
            ("user_agent_ouverture", "TEXT"),
            ("date_relance_prevue", "TEXT"),
            ("relance_type", "TEXT"),
            ("lead_temperature", "TEXT"),
            ("derniere_interaction", "TEXT"),
            ("score_lead", "INTEGER DEFAULT 0"),
        ]
        for col_name, col_def in migrations:
            if col_name not in cols:
                try:
                    conn.execute(f"ALTER TABLE emails_envoyes ADD COLUMN {col_name} {col_def}")
                    print(f"  [MIGRATION] Colonne ajoutée: emails_envoyes.{col_name}")
                except Exception:
                    pass


def migrate_email_events_table():
    """Crée la table email_events si elle n'existe pas."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS email_events (
                id INTEGER PRIMARY KEY,
                email_record_id INTEGER NOT NULL,
                lead_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,  -- 'sent', 'opened', 'clicked', 'bounced', 'unsubscribed'
                event_data TEXT,  -- JSON avec métadonnées (ip, user_agent, etc.)
                timestamp TEXT NOT NULL,
                FOREIGN KEY (email_record_id) REFERENCES emails_envoyes(id),
                FOREIGN KEY (lead_id) REFERENCES leads_bruts(id)
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_email_events_email_record ON email_events(email_record_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_email_events_lead ON email_events(lead_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_email_events_type ON email_events(event_type);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_email_events_timestamp ON email_events(timestamp);")


def migrate_lead_lists():
    """Crée les tables lead_lists et lead_list_items si elles n'existent pas."""
    with get_conn() as conn:
        conn.executescript("""
            -- ─── LISTES DE LEADS (gestion manuelle) ────────────────────────────
            CREATE TABLE IF NOT EXISTS lead_lists (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nom         TEXT    NOT NULL,
                description TEXT,
                couleur     TEXT    DEFAULT '#6366f1',
                icone       TEXT    DEFAULT '📋',
                created_at  TEXT    DEFAULT (datetime('now')),
                updated_at  TEXT    DEFAULT (datetime('now'))
            );

            -- ─── LIAISON LEADS ↔ LISTES (many-to-many) ──────────────────────────
            CREATE TABLE IF NOT EXISTS lead_list_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                list_id     INTEGER NOT NULL REFERENCES lead_lists(id) ON DELETE CASCADE,
                lead_id     INTEGER NOT NULL REFERENCES leads_bruts(id) ON DELETE CASCADE,
                added_at    TEXT    DEFAULT (datetime('now')),
                UNIQUE(list_id, lead_id)
            );

            CREATE INDEX IF NOT EXISTS idx_list_items_list ON lead_list_items(list_id);
            CREATE INDEX IF NOT EXISTS idx_list_items_lead ON lead_list_items(lead_id);
        """)


def init_db():
    """Crée les tables et index si ils n'existent pas encore."""
    Path(DB_PATH.parent).mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
        -- ─── SÉQUENCES EMAILS (relances automatiques) ─────────────────────────
        CREATE TABLE IF NOT EXISTS email_sequences (
            id INTEGER PRIMARY KEY,
            lead_id INTEGER NOT NULL,
            email_record_id INTEGER,
            email_type TEXT NOT NULL,  -- 'relance_1', 'relance_2', 'relance_special'
            statut TEXT DEFAULT 'planned',  -- 'planned', 'pending_approval', 'sent', 'cancelled', 'bounced'
            date_planifiee TEXT NOT NULL,
            date_envoi TEXT,
            condition_envoi TEXT,  -- JSON
            email_objet TEXT,      -- généré, en attente d'approval
            email_corps TEXT,      -- généré, en attente d'approval
            telegram_msg_id TEXT,  -- message_id Telegram pour suivi
            created_at TEXT NOT NULL,
            FOREIGN KEY (lead_id) REFERENCES leads_audites(id),
            FOREIGN KEY (email_record_id) REFERENCES emails_envoyes(id)
        );

        CREATE INDEX IF NOT EXISTS idx_sequences_lead ON email_sequences(lead_id);
        CREATE INDEX IF NOT EXISTS idx_sequences_statut ON email_sequences(statut);
        CREATE INDEX IF NOT EXISTS idx_sequences_date_planifiee ON email_sequences(date_planifiee);

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
            rating          REAL,
            nb_avis         INTEGER DEFAULT 0,
            category        TEXT,
            mot_cle         TEXT,
            ville           TEXT,
            lien_maps       TEXT,
            secteur         TEXT,
            date_scraping   TEXT    DEFAULT (datetime('now')),
            statut          TEXT    DEFAULT 'en_attente',
            sheets_synced   INTEGER DEFAULT 0
        );

        -- ─── LEADS AUDITÉS (auditeur + copywriter) ───────────────────────
        CREATE TABLE IF NOT EXISTS leads_audites (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id                     INTEGER REFERENCES leads_bruts(id) ON DELETE CASCADE,
            mobile_score                INTEGER DEFAULT 0,
            desktop_score               INTEGER DEFAULT 0,
            tablet_score                INTEGER DEFAULT 0,
            lcp_ms                      REAL    DEFAULT 0,
            fcp_ms                      REAL    DEFAULT 0,
            cls                         REAL    DEFAULT 0,
            render_blocking_scripts     INTEGER DEFAULT 0,
            uses_cache                  INTEGER DEFAULT 0,
            page_size_kb                REAL    DEFAULT 0,
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
            score_performance           INTEGER DEFAULT 0,
            score_seo                   INTEGER DEFAULT 0,
            score_gmb                   INTEGER DEFAULT 0,
            score_urgence               REAL    DEFAULT 0,
            top3_problems               TEXT,   -- JSON array
            service_suggere             TEXT,
            probleme_principal          TEXT,
            arguments                   TEXT,   -- JSON array
            rapport_resume              TEXT,
            email_objet                 TEXT,
            email_corps                 TEXT,
            approuve                    INTEGER DEFAULT 0,
            lien_rapport                TEXT,
            lien_pdf                    TEXT,
            template_used               TEXT,
            template_variant            TEXT    DEFAULT 'v1',
            date_audit                  TEXT    DEFAULT (datetime('now')),
            statut                      TEXT    DEFAULT 'audite',
            audit_partial               INTEGER DEFAULT 0,
            audit_error                 TEXT,
            notified_at                 TEXT,
            sheets_synced               INTEGER DEFAULT 0
        );

        -- ─── EMAILS ENVOYÉS (brevo_sender.py) ────────────────────────────
        CREATE TABLE IF NOT EXISTS emails_envoyes (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id             INTEGER REFERENCES leads_bruts(id) ON DELETE SET NULL,
            message_id_brevo    TEXT,
            message_id_resend   TEXT,
            date_envoi          TEXT    DEFAULT (datetime('now')),
            email_destinataire  TEXT,
            email_objet         TEXT,
            email_corps         TEXT,
            lien_rapport        TEXT,
            template_variant    TEXT    DEFAULT 'v1',
            statut_envoi        TEXT    DEFAULT 'envoye',
            ouvert              INTEGER DEFAULT 0,
            date_ouverture      TEXT,
            nb_ouvertures       INTEGER DEFAULT 0,
            clique              INTEGER DEFAULT 0,
            date_clic           TEXT,
            bounce              INTEGER DEFAULT 0,
            spam                INTEGER DEFAULT 0,
            repondu             INTEGER DEFAULT 0,
            date_reponse        TEXT,
            type_reponse        TEXT,
            rdv_confirme        INTEGER DEFAULT 0,
            date_rdv            TEXT,
            notes               TEXT,
            date_premiere_ouverture TEXT,
            date_derniere_ouverture TEXT,
            nb_clics            INTEGER DEFAULT 0,
            date_dernier_clic   TEXT,
            ip_ouverture        TEXT,
            user_agent_ouverture TEXT,
            date_relance_prevue TEXT,
            relance_type        TEXT,
            lead_temperature    TEXT,
            derniere_interaction TEXT,
            score_lead          INTEGER DEFAULT 0,
            sheets_synced       INTEGER DEFAULT 0
        );

        -- ─── LOG DE SYNCHRONISATION ───────────────────────────────────────
        CREATE TABLE IF NOT EXISTS sync_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name  TEXT,
            direction   TEXT,
            rows_synced INTEGER DEFAULT 0,
            date_sync   TEXT    DEFAULT (datetime('now')),
            statut      TEXT,
            erreur      TEXT
        );

        -- ─── SYSTEM LOGS (Centre Global de Notifications) ────────────────
        CREATE TABLE IF NOT EXISTS system_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT    NOT NULL CHECK(type IN ('info', 'warning', 'error', 'fatal')),
            message     TEXT    NOT NULL,
            source      TEXT    DEFAULT 'system',
            created_at  TEXT    DEFAULT (datetime('now')),
            is_read     INTEGER DEFAULT 0
        );

        -- ─── PLANIFICATEUR ───────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS planned_campaigns (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            secteur         TEXT    NOT NULL,
            keyword         TEXT    NOT NULL,
            city            TEXT    NOT NULL,
            limit_leads     INTEGER DEFAULT 50,
            date_planifiee  DATE    NOT NULL,
            heure           TEXT    DEFAULT '09:00',
            statut          TEXT    DEFAULT 'planned',
            source          TEXT    DEFAULT 'maps',
            campaign_id     INTEGER REFERENCES campagnes(id) ON DELETE SET NULL,
            created_at      TIMESTAMP DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS planning_settings (
            key     TEXT PRIMARY KEY,
            value   TEXT
        );

        INSERT OR IGNORE INTO planning_settings (key, value)
            VALUES ('daily_quota', '30'),
                   ('quota_start_date', date('now')),
                   ('auto_send', '0'),
                   ('send_hour_start', '9'),
                   ('send_hour_end', '18'),
                   ('auto_plan_enabled', '1'),
                   ('auto_plan_per_day', '3'),
                   ('sniper_daily_quota', '20'),
                   ('sniper_auto_generate', '1'),
                   ('sniper_auto_send', '0'),
                   ('sniper_ads_auto_scrape', '0');

        -- ─── PRIORITÉS DE SCRAPING ───────────────────
        CREATE TABLE IF NOT EXISTS scraping_priorities (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            secteur             TEXT    NOT NULL,
            keyword             TEXT    NOT NULL,
            ville               TEXT    NOT NULL,
            limit_leads         INTEGER DEFAULT 50,
            priorite            INTEGER DEFAULT 5,
            actif               INTEGER DEFAULT 1,
            frequence_jours     INTEGER DEFAULT 30,
            source              TEXT    DEFAULT 'maps',
            derniere_execution  DATE    DEFAULT NULL,
            created_at          TIMESTAMP DEFAULT (datetime('now'))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_scraping_prio_uniq
            ON scraping_priorities(keyword, ville, source);

        -- ─── BATCHES PROGRAMMÉS SUR RESEND ────────────────────────────────
        CREATE TABLE IF NOT EXISTS scheduled_batches (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_key    TEXT    UNIQUE NOT NULL,
            scheduled_at TEXT    NOT NULL,
            status       TEXT    DEFAULT 'pending',
            nb_emails    INTEGER DEFAULT 0,
            lead_ids     TEXT,
            message_ids  TEXT,
            created_at   TEXT    DEFAULT (datetime('now', 'localtime'))
        );

        -- ─── INDEX ────────────────────────────────────────────────────────
        CREATE INDEX IF NOT EXISTS idx_leads_statut ON leads_bruts(statut);
        CREATE INDEX IF NOT EXISTS idx_leads_date ON leads_bruts(date_scraping DESC);
        CREATE INDEX IF NOT EXISTS idx_leads_ville ON leads_bruts(ville);
        CREATE INDEX IF NOT EXISTS idx_audits_score ON leads_audites(score_urgence DESC);
        CREATE INDEX IF NOT EXISTS idx_audits_lead ON leads_audites(lead_id);
        CREATE INDEX IF NOT EXISTS idx_emails_date ON emails_envoyes(date_envoi DESC);
        CREATE INDEX IF NOT EXISTS idx_emails_repondu ON emails_envoyes(repondu);
        """)

def register_schema(table_name: str, schema_sql: str):
    """Permet aux nouveaux modules d'ajouter des tables/colonnes au démarrage."""
    with get_conn() as conn:
        try:
            conn.executescript(schema_sql)
            logger.info(f"  [SCHEMA] Schema enregistré/migré pour {table_name}")
        except Exception as e:
            logger.error(f"  [SCHEMA] Erreur register_schema {table_name}: {e}")

if __name__ == '__main__':
    init_db()
