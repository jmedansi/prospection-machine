# -*- coding: utf-8 -*-
from pathlib import Path
from . import connection
get_conn = connection.get_conn
logger = connection.logger


def migrate_db():
    """Ajoute les colonnes manquantes aux tables existantes."""
    migrate_v2_schema()
    _migrate_leads_bruts_fk()
    migrate_emails_threading()
    _migrate_emails_envoyes_fk()
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
                        print(f"  [MIGRATION] Colonne ajoutÃ©e: emails_envoyes.{col_name}")
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
                    conn.execute("ALTER TABLE leads_bruts ADD COLUMN campaign_id INTEGER REFERENCES campagnes_legacy(id) ON DELETE SET NULL")
                except Exception:
                    pass
            if 'logo_url' not in cols:
                try:
                    conn.execute("ALTER TABLE leads_bruts ADD COLUMN logo_url TEXT DEFAULT ''")
                    print("  [MIGRATION] Colonne ajoutÃ©e: leads_bruts.logo_url")
                except Exception:
                    pass
            if 'email_2' not in cols:
                try:
                    conn.execute("ALTER TABLE leads_bruts ADD COLUMN email_2 TEXT DEFAULT ''")
                    print("  [MIGRATION] Colonne ajoutÃ©e: leads_bruts.email_2")
                except Exception:
                    pass

        if 'leads_audites' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(leads_audites)").fetchall()]
            if 'template_variant' not in cols:
                try:
                    conn.execute("ALTER TABLE leads_audites ADD COLUMN template_variant TEXT DEFAULT 'v1'")
                    print("  [MIGRATION] Colonne ajoutÃ©e: leads_audites.template_variant")
                except Exception:
                    pass
            if 'statut_prospection' not in cols:
                try:
                    conn.execute("ALTER TABLE leads_audites ADD COLUMN statut_prospection TEXT DEFAULT 'a_contacter'")
                    print("  [MIGRATION] Colonne ajoutÃ©e: leads_audites.statut_prospection")
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
                        print(f"  [MIGRATION] Colonne ajoutÃ©e: leads_audites.{col_name}")
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
                        print(f"  [MIGRATION] Colonne ajoutÃ©e: leads_audites.{col_name}")
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
                        print(f"  [MIGRATION] Colonne ajoutÃ©e: leads_audites.{col_name}")
                    except Exception:
                        pass

            # Colonnes de contact (prospection tracking)
            # NB: contact_mail/wp/li/fb/autres existent dÃ©jÃ  dans certaines DB, on ne migre que ce qui manque
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
                        print(f"  [MIGRATION] Colonne ajoutÃ©e: leads_audites.{col_name}")
                    except Exception:
                        pass

        # Remarque : la table legacy `campagnes` (pipeline 1) a cÃ©dÃ© son nom Ã  la v2
        # (migrate_v2_schema la renomme `campagnes_legacy`) â€” les migrations legacy
        # ci-dessous ciblent donc `campagnes_legacy` pour ne pas polluer la v2.
        if 'campagnes_legacy' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(campagnes_legacy)").fetchall()]
            if 'nb_demande' not in cols:
                try:
                    conn.execute("ALTER TABLE campagnes_legacy ADD COLUMN nb_demande INTEGER DEFAULT 0")
                    print("  [MIGRATION] Colonne ajoutÃ©e: campagnes_legacy.nb_demande")
                except Exception:
                    pass

            # â”€â”€â”€ Status Registry : suivi granulaire des campagnes legacy â”€â”€
            campaign_tracker_cols = [
                ("source",         "TEXT DEFAULT 'maps'"),         # maps | ads | fb_ads | tech | jobs | bodacc
                ("phase",          "TEXT DEFAULT 'pending'"),      # pending | scraping | enrichment | audit | email_gen | done | failed | stopped
                ("error_message",  "TEXT"),                        # Raison de l'arrÃªt brutal
                ("stopped_at",     "TEXT"),                        # Timestamp arrÃªt
                ("started_at",     "TEXT"),                        # Timestamp dÃ©but
                ("finished_at",    "TEXT"),                        # Timestamp fin
                ("progress_data",  "TEXT"),                        # JSON: {processed, total, emails_found, phase_detail}
            ]
            for col_name, col_def in campaign_tracker_cols:
                if col_name not in cols:
                    try:
                        conn.execute(f"ALTER TABLE campagnes_legacy ADD COLUMN {col_name} {col_def}")
                        print(f"  [MIGRATION] Colonne ajoutÃ©e: campagnes_legacy.{col_name}")
                    except Exception:
                        pass

        # â”€â”€â”€ Sniper columns (Source 1 high-ticket pipeline) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if 'leads_bruts' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(leads_bruts)").fetchall()]
            sniper_cols = [
                ("source",          "TEXT DEFAULT 'maps'"),        # 'maps' | 'ads' | 'tech' | 'jobs'
                ("tag_urgence",     "TEXT"),                        # 'perf' | 'securite' | 'automatisation'
                ("niveau_urgence",  "INTEGER DEFAULT 0"),           # 0-5
                ("donnees_audit",   "TEXT"),                        # JSON prÃ©-qualification
                ("secteur",         "TEXT"),                        # Ã©tiquette secteur pour filtrage
            ]
            for col_name, col_def in sniper_cols:
                if col_name not in cols:
                    try:
                        conn.execute(f"ALTER TABLE leads_bruts ADD COLUMN {col_name} {col_def}")
                        print(f"  [MIGRATION] Colonne ajoutÃ©e: leads_bruts.{col_name}")
                    except Exception:
                        pass

        # â”€â”€â”€ Planned Campaigns & Scraping Priorities â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if 'planned_campaigns' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(planned_campaigns)").fetchall()]
            if 'source' not in cols:
                try:
                    conn.execute("ALTER TABLE planned_campaigns ADD COLUMN source TEXT DEFAULT 'maps'")
                    print("  [MIGRATION] Colonne ajoutÃ©e: planned_campaigns.source")
                except Exception:
                    pass

        if 'scraping_priorities' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(scraping_priorities)").fetchall()]
            if 'source' not in cols:
                try:
                    conn.execute("ALTER TABLE scraping_priorities ADD COLUMN source TEXT DEFAULT 'maps'")
                    print("  [MIGRATION] Colonne ajoutÃ©e: scraping_priorities.source")
                except Exception:
                    pass
            try:
                # Re-crÃ©er l'index pour inclure 'source'
                conn.execute("DROP INDEX IF EXISTS idx_scraping_prio_uniq")
                conn.execute("CREATE UNIQUE INDEX idx_scraping_prio_uniq ON scraping_priorities(keyword, ville, source)")
            except Exception:
                pass

        migrate_email_events_table()
        migrate_lead_lists()

        # â”€â”€â”€ Migration: pays pour leads_bruts et campagnes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if 'leads_bruts' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(leads_bruts)").fetchall()]
            if 'pays' not in cols:
                try:
                    conn.execute("ALTER TABLE leads_bruts ADD COLUMN pays TEXT DEFAULT 'fr'")
                    print("  [MIGRATION] Colonne ajoutÃ©e: leads_bruts.pays")
                except Exception:
                    pass

        if 'campagnes_legacy' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(campagnes_legacy)").fetchall()]
            if 'pays' not in cols:
                try:
                    conn.execute("ALTER TABLE campagnes_legacy ADD COLUMN pays TEXT DEFAULT 'fr'")
                    print("  [MIGRATION] Colonne ajoutÃ©e: campagnes_legacy.pays")
                except Exception:
                    pass

        # â”€â”€â”€ Migration: campaign_id dans lead_lists pour auto-listes â”€â”€
        if 'lead_lists' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(lead_lists)").fetchall()]
            if 'campaign_id' not in cols:
                try:
                    conn.execute("ALTER TABLE lead_lists ADD COLUMN campaign_id INTEGER REFERENCES campagnes_legacy(id) ON DELETE SET NULL")
                    print("  [MIGRATION] Colonne ajoutÃ©e: lead_lists.campaign_id")
                except Exception:
                    pass

        # â”€â”€â”€ Migration: colonnes note/relance/archivage pour lead_lists â”€â”€
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
                'objectif': "ALTER TABLE lead_lists ADD COLUMN objectif TEXT DEFAULT 'general'",  # 'web' | 'general' (I.A. â‡„ Dashboard)
            }
            for col_name, sql in new_cols.items():
                if col_name not in cols:
                    try:
                        conn.execute(sql)
                        print(f"  [MIGRATION] Colonne ajoutÃ©e: lead_lists.{col_name}")
                    except Exception:
                        pass

        # â”€â”€â”€ Migration: objectif / catÃ©gorie / Ã©cartement / dÃ©sinscription â”€â”€
        if 'leads_bruts' in table_names:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(leads_bruts)").fetchall()]
            lead_classification_cols = [
                ("objectif",     "TEXT DEFAULT 'general'"),   # 'web' | 'general'
                ("categorie",    "TEXT"),                     # catÃ©gorisation Ã©tudiÃ©e/IA (ex: 'Pas de site', 'Site datÃ©')
                ("ecarte",       "INTEGER DEFAULT 0"),        # 1 = exclu des flux d'envoi
                ("desinscrit",   "INTEGER DEFAULT 0"),        # 1 = opposition au contact
                ("ia_opportunite", "INTEGER"),                # 0-100 (I.A. Â· passerelle IA â‡„ Dashboard)
                ("ia_score",     "INTEGER"),                  # 0-100 (cohÃ©rence site / besoin refonte Â· I.A.)
                ("ia_signaux",   "TEXT"),                     # 1 phrase de signaux observÃ©s (I.A.)
            ]
            for col_name, col_def in lead_classification_cols:
                if col_name not in cols:
                    try:
                        conn.execute(f"ALTER TABLE leads_bruts ADD COLUMN {col_name} {col_def}")
                        print(f"  [MIGRATION] Colonne ajoutÃ©e: leads_bruts.{col_name}")
                    except Exception:
                        pass

        # Table des catÃ©gories de leads (dÃ©finition + style)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lead_categories (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                nom      TEXT    NOT NULL UNIQUE,
                objectif TEXT    DEFAULT 'web',
                couleur  TEXT    DEFAULT '#64748b',
                sort     INTEGER DEFAULT 0
            );
        """)
        conn.execute("INSERT OR IGNORE INTO lead_categories (nom, objectif, sort) VALUES ('Pas de site', 'web', 1)")
        conn.execute("INSERT OR IGNORE INTO lead_categories (nom, objectif, sort) VALUES ('Site cassÃ©', 'web', 2)")
        conn.execute("INSERT OR IGNORE INTO lead_categories (nom, objectif, sort) VALUES ('Site datÃ©', 'web', 3)")
        conn.execute("INSERT OR IGNORE INTO lead_categories (nom, objectif, sort) VALUES ('Site Ã  vÃ©rifier', 'web', 4)")
        conn.execute("INSERT OR IGNORE INTO lead_categories (nom, objectif, sort) VALUES ('Site moderne', 'web', 5)")
        conn.execute("INSERT OR IGNORE INTO lead_categories (nom, objectif, sort) VALUES ('Ã‰cartÃ©', 'general', 6)")
        conn.execute("INSERT OR IGNORE INTO lead_categories (nom, objectif, sort) VALUES ('DÃ©sinscrit', 'general', 7)")

        # â”€â”€â”€ Migration: async_tasks pour le Task Engine UnifiÃ© â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        conn.execute("""
            CREATE TABLE IF NOT EXISTS async_tasks (
                id                  TEXT PRIMARY KEY,
                task_type           TEXT NOT NULL,
                label               TEXT NOT NULL,
                status              TEXT NOT NULL DEFAULT 'pending',
                progress            INTEGER DEFAULT 0,
                total_items         INTEGER DEFAULT 0,
                processed_items     INTEGER DEFAULT 0,
                current_item_label  TEXT DEFAULT '',
                params_json         TEXT DEFAULT '{}',
                result_json         TEXT DEFAULT '{}',
                error_message       TEXT DEFAULT '',
                created_at          TEXT DEFAULT (datetime('now')),
                started_at          TEXT,
                completed_at        TEXT,
                logs_json           TEXT DEFAULT '[]'
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON async_tasks(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON async_tasks(created_at);")

        # â”€â”€â”€ Migration: ia_executions (journal actions IA â‡„ Dashboard) â”€â”€
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ia_executions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                liste_id    INTEGER,
                liste_nom   TEXT,
                operation   TEXT    NOT NULL,   -- qualify | maquette | redact | export | scan
                moteur      TEXT    DEFAULT 'file',  -- file | integrated
                cible_json  TEXT    DEFAULT '[]',    -- lead_ids ciblÃ©s
                statut      TEXT    DEFAULT 'created', -- created | pret | fait | erreur
                meta_json   TEXT    DEFAULT '{}',
                ecart_count INTEGER DEFAULT 0,
                created_at  TEXT    DEFAULT (datetime('now')),
                updated_at  TEXT
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ia_exec_liste ON ia_executions(liste_id);")


def migrate_v2_schema():
    """SchÃ©ma v2 (SaaS) â€” modÃ¨le pilotÃ© par Campagne â†’ Liste â†’ Prospect.

    Une CAMPAGNE (ex Â« objectif Â» v2) est le conteneur de configuration dÃ©fini par
    l'utilisateur avant tout lead (ex. Â« Refonte site web Â»). Elle regroupe des LISTES
    (unitÃ©s opÃ©rationnelles : un scraping, un import, un secteur). Chaque PROSPECT
    appartient Ã  UNE liste. La machine Ã  Ã©tats (core/state_machine.py) suit les
    statuts de la spec `prompt-prospection-machine-saas.md` Â§1-2 et Â§8.

    Migration idempotente : Ã  partir d'une base dÃ©jÃ  au modÃ¨le Â« objectif Â», les
    donnÃ©es sont prÃ©servÃ©es (objectifs â†’ campagnes, 1 liste auto par campagne,
    prospects rattachÃ©s Ã  la liste). La table legacy `campagnes` (pipeline 1,
    dÃ©commissionnÃ©e) cÃ¨de son nom et devient `campagnes_legacy`.
    """
    with get_conn() as conn:
        _migrate_v2_grouping(conn)
        conn.executescript("""
        -- â”€â”€â”€ CAMPAGNES (ex Â« objectifs Â» : groupe de Listes, spec Â§8) â”€â”€â”€â”€â”€â”€â”€â”€
        CREATE TABLE IF NOT EXISTS campagnes (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            nom                 TEXT    NOT NULL UNIQUE,
            description         TEXT    DEFAULT '',
            statut              TEXT    DEFAULT 'actif',        -- actif | archive
            segment             TEXT    DEFAULT '',             -- 'particuliers' | 'agences' | '' (donnÃ©e de config, spec Â§8)
            sequence_id         INTEGER,                        -- FK sequence_templates (NULL = dÃ©faut)
            template_id         INTEGER,                        -- FK sequence_templates (template d'email par dÃ©faut) (NULL = dÃ©faut)
            validation_telegram INTEGER DEFAULT 0,              -- 0 = envoi auto, 1 = âœ… Telegram requis par campagne
            backend_pref        TEXT    DEFAULT 'auto',         -- smtp | resend | auto (spec Â§3 dÃ©couplÃ©)
            max_touches         INTEGER DEFAULT 3,              -- nombre max de touches (initial + relances)
            envoi_auto          INTEGER DEFAULT 1,              -- 0 = envoi manuel seul, 1 = participe Ã  l'auto-send
            qualification       TEXT    DEFAULT '',             -- JSON: rÃ¨gles de qualification (mots-clÃ©s, scoring, exclusions)
            created_at          TEXT    DEFAULT (datetime('now')),
            updated_at          TEXT    DEFAULT (datetime('now'))
        );

        -- â”€â”€â”€ LISTES (unitÃ©s opÃ©rationnelles d'une campagne) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        CREATE TABLE IF NOT EXISTS listes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            campagne_id INTEGER NOT NULL REFERENCES campagnes(id) ON DELETE CASCADE,
            nom         TEXT    NOT NULL,
            description TEXT    DEFAULT '',
            secteur     TEXT    DEFAULT '',
            source      TEXT    DEFAULT 'import',       -- scraping | csv | json | migration | manuel
            note        TEXT    DEFAULT '',             -- note libre de liste (UI)
            icone       TEXT    DEFAULT '📋',            -- emoji icône (UI sidebar)
            couleur     TEXT    DEFAULT '#6366f1',        -- couleur sidebar (UI)
            objectif    TEXT    DEFAULT 'general',        -- general | web (traitement IA)
            statut      TEXT    DEFAULT 'actif',        -- actif | archive
            created_at  TEXT    DEFAULT (datetime('now')),
            updated_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_listes_campagne ON listes(campagne_id);

        -- â”€â”€â”€ PROSPECTS v2 (machine Ã  Ã©tats unifiÃ©e, spec Â§1-2) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        CREATE TABLE IF NOT EXISTS prospects (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            liste_id            INTEGER NOT NULL REFERENCES listes(id) ON DELETE CASCADE,
            source              TEXT    DEFAULT 'import',       -- scraping | csv | json | ia | manuel
            nom                 TEXT,
            prenom              TEXT,
            email               TEXT,
            telephone           TEXT,
            entreprise          TEXT,
            site_web            TEXT,
            adresse             TEXT,
            ville               TEXT,
            secteur             TEXT,
            rating              REAL,
            nb_avis             INTEGER DEFAULT 0,
            data_extra          TEXT,                           -- JSON brut de la source (adaptateur)
            statut              TEXT    DEFAULT 'qualifie',     -- machine Ã  Ã©tats (core/state_machine.py)
            statut_meta         TEXT    DEFAULT '{}',           -- JSON: {updated_at, reason, touch}
            score               INTEGER,
            ecarte              INTEGER DEFAULT 0,              -- exclu des flux d'envoi
        ne_plus_contacter   INTEGER DEFAULT 0,              -- opposition (miroir suppression_list)
        note                TEXT    DEFAULT '',               -- note libre (restauration legacy / commentaire)
        created_at          TEXT    DEFAULT (datetime('now')),
        updated_at          TEXT    DEFAULT (datetime('now'))
    );

        CREATE INDEX IF NOT EXISTS idx_prospects_liste  ON prospects(liste_id);
        CREATE INDEX IF NOT EXISTS idx_prospects_email   ON prospects(email);
        CREATE INDEX IF NOT EXISTS idx_prospects_statut  ON prospects(statut);

        -- â”€â”€â”€ PROSPECT_EVENTS (historique du prospect, spec Â§1 Message/Ã‰vÃ©nement) â”€
        CREATE TABLE IF NOT EXISTS prospect_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id INTEGER NOT NULL REFERENCES prospects(id) ON DELETE CASCADE,
            campagne_id INTEGER NOT NULL REFERENCES campagnes(id)   ON DELETE CASCADE,
            event_type  TEXT    NOT NULL,   -- creation | import | status_change | initial | relance | reponse | auto_reply | ndr | desinscription | rdv | note
            payload     TEXT,               -- JSON
            mailbox_id  INTEGER,
            message_id  TEXT,               -- Message-ID sortant
            in_reply_to TEXT,               -- In-Reply-To entrant
            references_header TEXT,         -- References RFC 2822 (fil de conversation)
            parent_event_id INTEGER,        -- event message répond à
            thread_id       INTEGER,        -- event racine du fil
            direction       TEXT    DEFAULT 'out',   -- out (sortant) | in (réponse entrante)
            created_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_prospect_events_prospect ON prospect_events(prospect_id);
        CREATE INDEX IF NOT EXISTS idx_prospect_events_campagne ON prospect_events(campagne_id);

        -- â”€â”€â”€ SUPPRESSION_LIST (registre central, travers toutes campagnes, spec Â§8) â”€
        CREATE TABLE IF NOT EXISTS suppression_list (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            email               TEXT    NOT NULL UNIQUE,
            raison              TEXT    DEFAULT 'desinscription',  -- desinscription | bounce_dur | plainte
            source_campagne_id  INTEGER REFERENCES campagnes(id) ON DELETE SET NULL,
            created_at          TEXT    DEFAULT (datetime('now'))
        );

        -- â”€â”€â”€ MAILBOXES (domaines + rotation de boÃ®tes, spec Â§3 & Â§8) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        CREATE TABLE IF NOT EXISTS mailboxes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            label           TEXT    NOT NULL,
            domaine         TEXT    NOT NULL,
            email           TEXT    NOT NULL,
            smtp_host       TEXT,
            smtp_port       INTEGER DEFAULT 587,
            smtp_user       TEXT,
            smtp_pass       TEXT,
            imap_host       TEXT,
            imap_user       TEXT,
            imap_pass       TEXT,
            backend         TEXT    DEFAULT 'smtp',      -- smtp | resend
            quota_jour      INTEGER DEFAULT 40,           -- quota du jour de cette boÃ®te
            usage_jour      INTEGER DEFAULT 0,            -- compteur du jour
            last_send_at    TEXT,
            campagne_pool   TEXT    DEFAULT '*',          -- '*' ou JSON [campagne_ids] Ã©ligibles
            warmup_days     INTEGER DEFAULT 0,
            actif           INTEGER DEFAULT 1,
            created_at      TEXT    DEFAULT (datetime('now'))
        );

        -- â”€â”€â”€ SEQUENCE_TEMPLATES (templates + variables de fusion, spec Â§8) â”€â”€â”€â”€â”€
        CREATE TABLE IF NOT EXISTS sequence_templates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            campagne_id INTEGER,                            -- NULL = template gÃ©nÃ©rique partagÃ©
            nom         TEXT    NOT NULL,
            objet       TEXT    NOT NULL,                   -- supporte {{prenom}}, {{entreprise}}, {{secteur}}, {{offre}}...
            corps       TEXT    NOT NULL,
            canal       TEXT    DEFAULT 'email',            -- email | whatsapp | autre (dimension canal, spec Â§8)
            position    INTEGER DEFAULT 0,                  -- order de la sÃ©quence (0 = initial)
            delai_jours INTEGER DEFAULT 0,                  -- dÃ©lai aprÃ¨s l'Ã©tape prÃ©cÃ©dente
            actif       INTEGER DEFAULT 1,
            created_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_seq_tpl_campagne ON sequence_templates(campagne_id);
        """)
        try:
            conn.execute("INSERT OR IGNORE INTO sequence_templates (nom, objet, corps, position, delai_jours) VALUES ('Template par dÃ©faut', '{{prenom}}, un mot sur {{secteur}}', 'Bonjour {{prenom}},\\n\\nEn regardant le site de {{entreprise}} ({{secteur}}), j''ai remarquÃ© quelques points qui mÃ©riteraient un coup d''Å“il : j''ai prÃ©parÃ© une Ã©bauche et quelques idÃ©es de modernisation \u2014 pas d''obligation, juste un aperÃ§u si Ã§a vous intÃ©resse.\\n\\n{{site_web}}\\n\\nBien Ã  vous,\\nJean-Marc', 0, 0)")
        except Exception:
            pass
        _migrate_campagnes_cols(conn)
        _migrate_relance_validation(conn)
        _migrate_listes_cols(conn)
        _migrate_prospects_note(conn)
        _backfill_listes(conn)
        conn.execute("INSERT OR IGNORE INTO planning_settings (key, value) VALUES ('v2_auto_send', '1')")


def _table_names(conn) -> set:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _rename_col(conn, table: str, old: str, new: str):
    """Renomme idempotemment une colonne si elle existe encore."""
    if table not in _table_names(conn):
        return
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if old in cols and new not in cols:
        conn.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
        print(f"  [MIGRATION] {table}.{old} â†’ {new}")


def _migrate_v2_grouping(conn):
    """Passe idempotente du concept Â« objectif Â» au couple Â« campagne â†’ liste Â».

    Ne touche QUE les bases dÃ©jÃ  au modÃ¨le v2 Â« objectif Â» (objectifs /
    prospects.objectif_id) â€” donnÃ©es prÃ©servÃ©es (1 liste auto par campagne).
    La table legacy `campagnes` (pipeline 1) cÃ¨de son nom Ã  la v2.
    """
    tables = _table_names(conn)

    # 1) Legacy `campagnes` (pipeline 1) cÃ¨de son nom au v2 â€”
    #    dÃ©tectÃ©e par sa signature 'phase' ET indÃ©pendamment de la prÃ©sence
    #    d'`objectifs` (base fraÃ®che ou legacy pur : objectifs n'existe pas encore).
    if 'campagnes' in tables and 'campagnes_legacy' not in tables:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(campagnes)")}
        if 'phase' in cols:  # signature legacy (phase / total_leads) â†’ pas le v2
            conn.execute("ALTER TABLE campagnes RENAME TO campagnes_legacy")
            print("  [MIGRATION] campagnes (legacy pipeline 1) â†’ campagnes_legacy")
    elif 'campagnes' in tables and 'campagnes_legacy' in tables:
        # legacy dÃ©jÃ  renommÃ©e mais l'ancienne existe encore â†’ la dropper
        cols = {r[1] for r in conn.execute("PRAGMA table_info(campagnes)")}
        if 'phase' in cols:
            conn.execute("DROP TABLE IF EXISTS campagnes")

    # 2) Â« objectif Â» â†’ Â« campagne Â»
# 2) objectif -> campagne (snapshot rafraichi : le step 1 a libere le nom)
    tables = _table_names(conn)
    if 'objectifs' in tables and 'campagnes' not in tables:
        conn.execute("ALTER TABLE objectifs RENAME TO campagnes")
        print("  [MIGRATION] objectifs -> campagnes")

    # 3) Table LISTES + 1 liste auto par campagne (rattachement prospects)
    tables = _table_names(conn)
    if 'campagnes' in tables and 'listes' not in tables:
        conn.execute("""CREATE TABLE IF NOT EXISTS listes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            campagne_id INTEGER NOT NULL REFERENCES campagnes(id) ON DELETE CASCADE,
            nom         TEXT    NOT NULL,
            description TEXT    DEFAULT '',
            secteur     TEXT    DEFAULT '',
            source      TEXT    DEFAULT 'import',
            note        TEXT    DEFAULT '',
            icone       TEXT    DEFAULT '📋',
            couleur     TEXT    DEFAULT '#6366f1',
            objectif    TEXT    DEFAULT 'general',
            statut      TEXT    DEFAULT 'actif',
            created_at  TEXT    DEFAULT (datetime('now')),
            updated_at  TEXT    DEFAULT (datetime('now'))
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_listes_campagne ON listes(campagne_id)")
        has_obj = 'prospects' in tables and 'objectif_id' in {
            r[1] for r in conn.execute("PRAGMA table_info(prospects)")}
        if has_obj and 'liste_id' not in {r[1] for r in conn.execute("PRAGMA table_info(prospects)")}:
            conn.execute("ALTER TABLE prospects ADD COLUMN liste_id INTEGER REFERENCES listes(id) ON DELETE CASCADE")
        for row in conn.execute("SELECT id, nom, description FROM campagnes").fetchall():
            cur = conn.execute(
                "INSERT INTO listes (campagne_id, nom, description, source, statut) VALUES (?, ?, ?, 'migration', 'actif')",
                (row['id'], row['nom'], row['description'] or ''),
            )
            if has_obj:
                conn.execute(
                    "UPDATE prospects SET liste_id = ? WHERE objectif_id = ?",
                    (cur.lastrowid, row['id']),
                )

    # 4) prospects : objectif_id â†’ liste_id (suppression de la colonne legacy)
    if 'prospects' in tables:
        pcols = {r[1] for r in conn.execute("PRAGMA table_info(prospects)")}
        if 'objectif_id' in pcols:
            if 'liste_id' not in pcols:
                conn.execute("ALTER TABLE prospects ADD COLUMN liste_id INTEGER REFERENCES listes(id) ON DELETE CASCADE")
            conn.execute("DROP INDEX IF EXISTS idx_prospects_objectif")
            conn.execute(
                """UPDATE prospects SET liste_id = (
                       SELECT l.id FROM listes l WHERE l.campagne_id = prospects.objectif_id LIMIT 1
                   ) WHERE liste_id IS NULL"""
            )
            conn.execute("ALTER TABLE prospects DROP COLUMN objectif_id")
            pass
        if 'liste_id' in pcols or 'liste_id' in {r[1] for r in conn.execute("PRAGMA table_info(prospects)")}:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_prospects_liste ON prospects(liste_id)")
    if 'objectifs' in tables:
        conn.execute("DROP TABLE IF EXISTS objectifs")

    # 5) Renommages colonnes liÃ©s (tables v2)
    _rename_col(conn, 'prospect_events', 'objectif_id', 'campagne_id')
    _rename_col(conn, 'suppression_list', 'source_objectif_id', 'source_campagne_id')
    _rename_col(conn, 'sequence_templates', 'objectif_id', 'campagne_id')
    _rename_col(conn, 'mailboxes', 'objectif_pool', 'campagne_pool')

    # index Ã  l'ancien nom â†’ nouveau nom
    conn.execute("DROP INDEX IF EXISTS idx_prospect_events_objectif")
    conn.execute("DROP INDEX IF EXISTS idx_seq_tpl_objectif")
    if 'prospect_events' in tables:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_prospect_events_campagne ON prospect_events(campagne_id)")
    if 'sequence_templates' in tables:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_seq_tpl_campagne ON sequence_templates(campagne_id)")


_LEGACY_FK_REBUILD_INDEXES = {
    'leads_bruts': [
        "CREATE INDEX IF NOT EXISTS idx_leads_statut ON leads_bruts(statut)",
        "CREATE INDEX IF NOT EXISTS idx_leads_date ON leads_bruts(date_scraping DESC)",
        "CREATE INDEX IF NOT EXISTS idx_leads_ville ON leads_bruts(ville)",
    ],
}


def _rebuild_legacy_campaign_fk(conn, table: str):
    """Reconstruit `table` si sa FK `campaign_id` pointe encore vers `campagnes` (v2)
    au lieu de `campagnes_legacy` (bug provoqué par le renommage migrate_v2_schema).
    Rebuild inoffensif : copie à l'identique + recréation des index."""
    if table not in _table_names(conn):
        return
    fks = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    wrong = any(r['table'] == 'campagnes' and r['from'] == 'campaign_id' for r in fks)
    if not wrong:
        return
    print(f"  [MIGRATION] {table}.campaign_id: FK erronee -> campagnes_legacy")
    cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    parts = []
    for c in cols:
        name = c['name']
        if name == 'campaign_id':
            parts.append('"campaign_id" INTEGER REFERENCES campagnes_legacy(id) ON DELETE SET NULL')
        elif c['pk']:
            parts.append(f'"{name}" INTEGER PRIMARY KEY AUTOINCREMENT')
        else:
            t = c['type'] or 'TEXT'
            nn = ' NOT NULL' if c['notnull'] else ''
            dv = f" DEFAULT {c['dflt_value']}" if c['dflt_value'] is not None else ''
            if c['dflt_value'] is not None and '(' in str(c['dflt_value']):
                dv = f" DEFAULT ({c['dflt_value']})"
            parts.append(f'"{name}" {t}{nn}{dv}')
    col_names = ', '.join(f'"{c["name"]}"' for c in cols)
    conn.execute(f"CREATE TABLE {table}_new ({', '.join(parts)})")
    conn.execute(f"INSERT INTO {table}_new ({col_names}) SELECT {col_names} FROM {table}")
    conn.execute(f"DROP TABLE {table}")
    conn.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
    for ddl in _LEGACY_FK_REBUILD_INDEXES.get(table, []):
        conn.execute(ddl)
    conn.commit()
    print(f"  [MIGRATION] {table} FK corrigee")


def _migrate_leads_bruts_fk() -> None:
    """Corrige la FK campaign_id (leads_bruts + lead_lists) pointant vers
    `campagnes` (v2) au lieu de `campagnes_legacy`."""
    with get_conn() as conn:
        _rebuild_legacy_campaign_fk(conn, 'leads_bruts')
        _rebuild_legacy_campaign_fk(conn, 'lead_lists')


def _migrate_emails_envoyes_fk() -> None:
    """emails_envoyes.lead_id référence `leads_bruts(id)` (v1 legacy) ; le modèle
    v2 stocke ici des id de `prospects`. Supprime la contrainte FK (le tracking
    se fait par message_id_resend/message_id_brevo, pas par lead_id). Table
    CRIÉE via migrate_v2_schema() → on ne migre que si un doublon existe déjà."""
    with get_conn() as conn:
        if 'emails_envoyes' not in _table_names(conn):
            return
        cols = [r[1] for r in conn.execute("PRAGMA table_info(emails_envoyes)").fetchall()]
        if 'lead_id' not in cols:
            return
        # Regénère le CREATE TABLE tel que défini par migrate_v2_schema()
        # (sans la clause REFERENCES leads_bruts), puis re-injecte les lignes.
        sql = """CREATE TABLE emails_envoyes (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id             INTEGER,
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
            sheets_synced       INTEGER DEFAULT 0,
            ouverture           INTEGER DEFAULT 0,
            message_erreur      TEXT,
            nb_tentatives_envoi INTEGER DEFAULT 0,
            date_dernier_essai  TEXT
        )"""
        old = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='emails_envoyes'"
        ).fetchone()
        if not old or 'REFERENCES leads_bruts' not in (old['sql'] or ''):
            return
        rows = conn.execute("SELECT * FROM emails_envoyes").fetchall()
        _all = [r[1] for r in conn.execute("PRAGMA table_info(emails_envoyes)").fetchall()]
        conn.execute("DROP TABLE emails_envoyes")
        conn.execute(sql)
        placeholders = ','.join('?' * len(_all))
        col_list = ','.join('"%s"' % c for c in _all)
        for row in rows:
            conn.execute(f"INSERT INTO emails_envoyes ({col_list}) VALUES ({placeholders})", tuple(row))
        conn.commit()
        print("  [MIGRATION] emails_envoyes.lead_id : FK leads_bruts supprimÃ©e (modÃ¨le v2)")


def _backfill_listes(conn):
    """SÃ©curitÃ© idempotente : chaque campagne sans liste â†’ 1 liste Â« auto Â»."""
    if 'campagnes' not in _table_names(conn) or 'listes' not in _table_names(conn):
        return
    for row in conn.execute("SELECT id, nom, description FROM campagnes").fetchall():
        has = conn.execute(
            "SELECT COUNT(*) AS n FROM listes WHERE campagne_id = ?", (row['id'],)
        ).fetchone()['n']
        if has:
            continue
        conn.execute(
            "INSERT INTO listes (campagne_id, nom, description, source, statut) VALUES (?, ?, ?, 'migration', 'actif')",
            (row['id'], row['nom'], row['description'] or ''),
        )


def _migrate_campagnes_cols(conn):
    """Colonnes campagnes ajoutées après la création initiale (idempotent)."""
    if 'campagnes' not in _table_names(conn):
        return
    cols = [r[1] for r in conn.execute("PRAGMA table_info(campagnes)").fetchall()]
    if 'envoi_auto' not in cols:
        try:
            conn.execute("ALTER TABLE campagnes ADD COLUMN envoi_auto INTEGER DEFAULT 1")
            print("  [MIGRATION] Colonne ajoutée: campagnes.envoi_auto")
        except Exception:
            pass


def _migrate_relance_validation(conn):
    """Validation Telegram PAR LOT des relances (validation_relances + relance_batches).

    - campagnes.validation_relances : 0 = relances auto, 1 = confirmation Telegram
      par lot (1 message par liste) avant envoi.
    - relance_batches : état persistant des lots (pending | sent | refuse).
    Idempotent : colonne ajoutée si absente, table créée le cas échéant.
    """
    if 'campagnes' in _table_names(conn):
        cols = [r[1] for r in conn.execute("PRAGMA table_info(campagnes)").fetchall()]
        if 'validation_relances' not in cols:
            try:
                conn.execute("ALTER TABLE campagnes ADD COLUMN validation_relances INTEGER DEFAULT 0")
                print("  [MIGRATION] Colonne ajoutée: campagnes.validation_relances")
            except Exception:
                pass
    conn.execute(
        """CREATE TABLE IF NOT EXISTS relance_batches (
            callback_id TEXT PRIMARY KEY,
            campagne_id INTEGER NOT NULL,
            liste_id    INTEGER NOT NULL,
            position    INTEGER DEFAULT 1,
            count       INTEGER DEFAULT 0,
            statut      TEXT DEFAULT 'pending',        -- pending | sent | refuse
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT
        )"""
    )


def _migrate_listes_cols(conn):
    """Colonnes listes ajoutées après la création initiale (idempotent)."""
    if 'listes' not in _table_names(conn):
        return
    cols = [r[1] for r in conn.execute("PRAGMA table_info(listes)").fetchall()]
    migrations = [
        ('note',      "TEXT DEFAULT ''"),
        ('icone',     "TEXT DEFAULT '📋'"),
        ('couleur',   "TEXT DEFAULT '#6366f1'"),
        ('objectif',  "TEXT DEFAULT 'general'"),
    ]
    for col_name, col_def in migrations:
        if col_name not in cols:
            try:
                conn.execute(f"ALTER TABLE listes ADD COLUMN {col_name} {col_def}")
                print(f"  [MIGRATION] Colonne ajoutée: listes.{col_name}")
            except Exception:
                pass


def _migrate_prospects_note(conn):
    """Ajoute la colonne prospects.note si absente (idempotent)."""
    if 'prospects' not in _table_names(conn):
        return
    cols = [r[1] for r in conn.execute("PRAGMA table_info(prospects)").fetchall()]
    if 'note' not in cols:
        try:
            conn.execute("ALTER TABLE prospects ADD COLUMN note TEXT DEFAULT ''")
            print("  [MIGRATION] Colonne ajoutée: prospects.note")
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
                    print(f"  [MIGRATION] Colonne ajoutÃ©e: emails_envoyes.{col_name}")
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
                    print(f"  [MIGRATION] Colonne ajoutÃ©e: emails_envoyes.{col_name}")
                except Exception:
                    pass


def migrate_emails_threading():
    """Ajoute les colonnes de threading RFC 2822 à prospect_events si manquantes.

    V2 : le fil de conversation (sortant + entrant) vit dans `prospect_events` —
    la table est déjà écrite par le tunnel d'envoi (sequence_engine) et par le
    poller IMAP (reply_poller). Colonnes ajoutées :
      - references_header : chaîne References au moment de l'envoi
      - parent_event_id   : id de l'event message (sortant) auquel répond ce message
      - thread_id         : id de l'event racine du fil (groupe de conversation)
      - direction         : 'out' (sortant) | 'in' (réponse entrante)
    """
    with get_conn() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(prospect_events)").fetchall()]
        migrations = [
            ("references_header", "TEXT"),
            ("parent_event_id", "INTEGER"),
            ("thread_id", "INTEGER"),
            ("direction", "TEXT DEFAULT 'out'"),
        ]
        for col_name, col_def in migrations:
            if col_name not in cols:
                try:
                    conn.execute(f"ALTER TABLE prospect_events ADD COLUMN {col_name} {col_def}")
                    print(f"  [MIGRATION] Colonne ajoutée: prospect_events.{col_name}")
                except Exception:
                    pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_prospect_events_thread ON prospect_events(thread_id)")


def migrate_email_events_table():
    """CrÃ©e la table email_events si elle n'existe pas.

    `lead_id` = id du prospect v2 OU id brute v1 : pas de FK vers leads_bruts
    (le tracking se rattache à emails_envoyes.email_record_id).
    """
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS email_events (
                id INTEGER PRIMARY KEY,
                email_record_id INTEGER NOT NULL,
                lead_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,  -- 'sent', 'opened', 'clicked', 'bounced', 'unsubscribed'
                event_data TEXT,  -- JSON avec mÃ©tadonnÃ©es (ip, user_agent, etc.)
                timestamp TEXT NOT NULL,
                FOREIGN KEY (email_record_id) REFERENCES emails_envoyes(id)
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_email_events_email_record ON email_events(email_record_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_email_events_lead ON email_events(lead_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_email_events_type ON email_events(event_type);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_email_events_timestamp ON email_events(timestamp);")
        _drop_email_events_leads_bruts_fk(conn)


def _drop_email_events_leads_bruts_fk(conn):
    """Reconstruit email_events si une ancienne FK vers leads_bruts subsiste."""
    old = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='email_events'"
    ).fetchone()
    if not old or 'REFERENCES leads_bruts' not in (old['sql'] or ''):
        return
    rows = conn.execute("SELECT * FROM email_events").fetchall()
    _all = [r[1] for r in conn.execute("PRAGMA table_info(email_events)").fetchall()]
    conn.execute("DROP TABLE email_events")
    conn.execute("""
        CREATE TABLE email_events (
            id INTEGER PRIMARY KEY,
            email_record_id INTEGER NOT NULL,
            lead_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (email_record_id) REFERENCES emails_envoyes(id)
        );
    """)
    placeholders = ','.join('?' * len(_all))
    col_list = ','.join('"%s"' % c for c in _all)
    for row in rows:
        conn.execute(f"INSERT INTO email_events ({col_list}) VALUES ({placeholders})", tuple(row))
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_events_email_record ON email_events(email_record_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_events_lead ON email_events(lead_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_events_type ON email_events(event_type);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_email_events_timestamp ON email_events(timestamp);")
    conn.commit()
    print("  [MIGRATION] email_events.lead_id : FK leads_bruts supprimÃ©e (modÃ¨le v2)")


def migrate_lead_lists():
    """CrÃ©e les tables lead_lists et lead_list_items si elles n'existent pas."""
    with get_conn() as conn:
        conn.executescript("""
            -- â”€â”€â”€ LISTES DE LEADS (gestion manuelle) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            CREATE TABLE IF NOT EXISTS lead_lists (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                nom         TEXT    NOT NULL,
                description TEXT,
                couleur     TEXT    DEFAULT '#6366f1',
                icone       TEXT    DEFAULT 'ðŸ“‹',
                created_at  TEXT    DEFAULT (datetime('now')),
                updated_at  TEXT    DEFAULT (datetime('now'))
            );

            -- â”€â”€â”€ LIAISON LEADS â†” LISTES (many-to-many) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    # Ensurer que les tables/colonnes des lead_lists existent (migrations complÃ©mentaires)
    try:
        migrate_lead_lists()
    except Exception:
        pass


def init_db():
    """CrÃ©e les tables et index si ils n'existent pas encore."""
    Path(str(connection.DB_PATH)).parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript("""
        -- â”€â”€â”€ SÃ‰QUENCES EMAILS (relances automatiques) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        CREATE TABLE IF NOT EXISTS email_sequences (
            id INTEGER PRIMARY KEY,
            lead_id INTEGER NOT NULL,
            email_record_id INTEGER,
            email_type TEXT NOT NULL,  -- 'relance_1', 'relance_2', 'relance_special'
            statut TEXT DEFAULT 'planned',  -- 'planned', 'pending_approval', 'sent', 'cancelled', 'bounced'
            date_planifiee TEXT NOT NULL,
            date_envoi TEXT,
            condition_envoi TEXT,  -- JSON
            email_objet TEXT,      -- gÃ©nÃ©rÃ©, en attente d'approval
            email_corps TEXT,      -- gÃ©nÃ©rÃ©, en attente d'approval
            telegram_msg_id TEXT,  -- message_id Telegram pour suivi
            created_at TEXT NOT NULL,
            FOREIGN KEY (lead_id) REFERENCES leads_audites(id),
            FOREIGN KEY (email_record_id) REFERENCES emails_envoyes(id)
        );

        CREATE INDEX IF NOT EXISTS idx_sequences_lead ON email_sequences(lead_id);
        CREATE INDEX IF NOT EXISTS idx_sequences_statut ON email_sequences(statut);
        CREATE INDEX IF NOT EXISTS idx_sequences_date_planifiee ON email_sequences(date_planifiee);

        -- â”€â”€â”€ CAMPAGNES LEGACY (pipeline 1, dÃ©commissionnÃ©e) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        CREATE TABLE IF NOT EXISTS campagnes_legacy (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nom             TEXT    NOT NULL,
            secteur         TEXT,
            ville           TEXT,
            date_creation   TEXT    DEFAULT (datetime('now')),
            total_leads     INTEGER DEFAULT 0,
            nb_demande      INTEGER DEFAULT 0,
            statut          TEXT    DEFAULT 'actif',
            source          TEXT    DEFAULT 'maps',
            phase           TEXT    DEFAULT 'pending',
            started_at      TEXT,
            finished_at     TEXT,
            pays            TEXT    DEFAULT 'fr'
        );

        -- â”€â”€â”€ LEADS BRUTS (scraper) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        CREATE TABLE IF NOT EXISTS leads_bruts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id     INTEGER REFERENCES campagnes_legacy(id) ON DELETE SET NULL,
            nom             TEXT    NOT NULL,
            adresse         TEXT,
            site_web        TEXT,
            telephone       TEXT,
            email           TEXT,
            email_2         TEXT    DEFAULT '',
            email_valide    TEXT    DEFAULT '',
            rating          REAL,
            nb_avis         INTEGER DEFAULT 0,
            category        TEXT,
            mot_cle         TEXT,
            ville           TEXT,
            lien_maps       TEXT,
            secteur         TEXT,
            logo_url        TEXT    DEFAULT '',
            source          TEXT    DEFAULT 'maps',
            tag_urgence     TEXT,
            niveau_urgence  INTEGER DEFAULT 0,
            donnees_audit   TEXT,
            objectif        TEXT    DEFAULT 'general',
            categorie       TEXT,
            ecarte          INTEGER DEFAULT 0,
            desinscrit      INTEGER DEFAULT 0,
            ia_opportunite  INTEGER,
            ia_score        INTEGER,
            ia_signaux      TEXT,
            pays            TEXT    DEFAULT 'fr',
            date_scraping   TEXT    DEFAULT (datetime('now')),
            statut          TEXT    DEFAULT 'en_attente',
            sheets_synced   INTEGER DEFAULT 0
        );

        -- â”€â”€â”€ LEADS AUDITÃ‰S (auditeur + copywriter) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

        -- â”€â”€â”€ EMAILS ENVOYÃ‰S (brevo_sender.py) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        CREATE TABLE IF NOT EXISTS emails_envoyes (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id             INTEGER,
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

        -- â”€â”€â”€ LOG DE SYNCHRONISATION â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        CREATE TABLE IF NOT EXISTS sync_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name  TEXT,
            direction   TEXT,
            rows_synced INTEGER DEFAULT 0,
            date_sync   TEXT    DEFAULT (datetime('now')),
            statut      TEXT,
            erreur      TEXT
        );

        -- â”€â”€â”€ SYSTEM LOGS (Centre Global de Notifications) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        CREATE TABLE IF NOT EXISTS system_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT    NOT NULL CHECK(type IN ('info', 'warning', 'error', 'fatal')),
            message     TEXT    NOT NULL,
            source      TEXT    DEFAULT 'system',
            created_at  TEXT    DEFAULT (datetime('now')),
            is_read     INTEGER DEFAULT 0
        );

        -- â”€â”€â”€ PLANIFICATEUR â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
            campaign_id     INTEGER REFERENCES campagnes_legacy(id) ON DELETE SET NULL,
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
                   ('sniper_ads_auto_scrape', '0'),
                   ('envoi_backend', 'auto');

        -- â”€â”€â”€ PRIORITÃ‰S DE SCRAPING â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

        -- â”€â”€â”€ BATCHES PROGRAMMÃ‰S SUR RESEND â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

        -- â”€â”€â”€ INDEX â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        CREATE INDEX IF NOT EXISTS idx_leads_statut ON leads_bruts(statut);
        CREATE INDEX IF NOT EXISTS idx_leads_date ON leads_bruts(date_scraping DESC);
        CREATE INDEX IF NOT EXISTS idx_leads_ville ON leads_bruts(ville);
        CREATE INDEX IF NOT EXISTS idx_audits_score ON leads_audites(score_urgence DESC);
        CREATE INDEX IF NOT EXISTS idx_audits_lead ON leads_audites(lead_id);
        CREATE INDEX IF NOT EXISTS idx_emails_date ON emails_envoyes(date_envoi DESC);
        CREATE INDEX IF NOT EXISTS idx_emails_repondu ON emails_envoyes(repondu);

        -- â”€â”€â”€ LISTES DE LEADS (gestion manuelle) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        CREATE TABLE IF NOT EXISTS lead_lists (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nom         TEXT    NOT NULL,
            description TEXT,
            couleur     TEXT    DEFAULT '#6366f1',
            icone       TEXT    DEFAULT 'ðŸ“‹',
            campaign_id     INTEGER REFERENCES campagnes_legacy(id) ON DELETE SET NULL,
            objectif    TEXT    DEFAULT 'general',
            note        TEXT    DEFAULT '',
            contactee   INTEGER DEFAULT 0,
            contacted_at TEXT,
            relance_j3  INTEGER DEFAULT 0,
            relance_j7  INTEGER DEFAULT 0,
            relance_j14 INTEGER DEFAULT 0,
            archived    INTEGER DEFAULT 0,
            archived_at TEXT,
            created_at  TEXT    DEFAULT (datetime('now')),
            updated_at  TEXT    DEFAULT (datetime('now'))
        );

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

def register_schema(table_name: str, schema_sql: str):
    """Permet aux nouveaux modules d'ajouter des tables/colonnes au dÃ©marrage."""
    with get_conn() as conn:
        try:
            conn.executescript(schema_sql)
            logger.info(f"  [SCHEMA] Schema enregistrÃ©/migrÃ© pour {table_name}")
        except Exception as e:
            logger.error(f"  [SCHEMA] Erreur register_schema {table_name}: {e}")

if __name__ == '__main__':
    init_db()
