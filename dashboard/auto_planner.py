# -*- coding: utf-8 -*-
"""
dashboard/auto_planner.py
Auto-planificateur de scraping.

Logique :
  - Tourne à 07h45 (avant le lancement des scrapings à 08h00)
  - Vérifie le nombre de campagnes planifiées pour aujourd'hui
  - Si insuffisant, pioche dans scraping_priorities (par priorité, puis ancienneté)
  - Chaque campagne tourne jusqu'à trouver `min_emails` emails (pas de limite de leads)
  - Évite de re-scraper le même (keyword+ville) avant `frequence_jours` jours
  - Peut aussi planifier la semaine entière d'un coup

Priorités par défaut (injectées au 1er démarrage) :
  Artisans > Santé > Juridique > Immobilier > Beauté > Auto > Sport > Numérique > Commerce
  × 15 villes françaises = ~135 combos, rotation ~45 jours à 3/jour
  min_emails = daily_quota / nb_campagnes_par_jour (ex: 60/3 = 20 emails/campagne)
"""
import os
import sys
import logging
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from database.db_manager import get_conn

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# LISTE DE PRIORITÉS PAR DÉFAUT
# ──────────────────────────────────────────────────────────────────────────────

# (secteur, keyword, ville, min_emails, priorite, frequence_jours)
# min_emails = nombre d'emails à trouver par campagne (le scraper s'arrête quand atteint)
# Par défaut 20 emails/campagne × 3 campagnes/jour = 60 emails/jour = quota exact
DEFAULT_PRIORITIES = [
    # ── Artisans BTP (priorité 1 — taux email élevé) ──────────────────────
    ("artisan", "plombier",          "Paris",        20, 1, 30),
    ("artisan", "électricien",       "Paris",        20, 1, 30),
    ("artisan", "menuisier",         "Paris",        20, 1, 30),
    ("artisan", "peintre en bâtiment","Paris",       20, 1, 30),
    ("artisan", "plombier",          "Lyon",         20, 1, 30),
    ("artisan", "électricien",       "Lyon",         20, 1, 30),
    ("artisan", "plombier",          "Marseille",    20, 1, 30),
    ("artisan", "électricien",       "Marseille",    20, 1, 30),
    ("artisan", "plombier",          "Toulouse",     20, 1, 30),
    ("artisan", "plombier",          "Nice",         20, 1, 30),
    ("artisan", "plombier",          "Bordeaux",     20, 1, 30),
    ("artisan", "plombier",          "Nantes",       20, 1, 30),
    ("artisan", "plombier",          "Strasbourg",   20, 1, 30),
    ("artisan", "plombier",          "Montpellier",  20, 1, 30),
    ("artisan", "plombier",          "Lille",        20, 1, 30),
    ("artisan", "menuisier",         "Lyon",         20, 2, 30),
    ("artisan", "menuisier",         "Marseille",    20, 2, 30),
    ("artisan", "chauffagiste",      "Paris",        20, 2, 30),
    ("artisan", "chauffagiste",      "Lyon",         20, 2, 30),
    ("artisan", "serrurier",         "Paris",        20, 2, 30),

    # ── Santé (priorité 2 — sites pro, emails visibles) ───────────────────
    ("sante", "dentiste",            "Paris",        20, 2, 30),
    ("sante", "kinésithérapeute",    "Paris",        20, 2, 30),
    ("sante", "ostéopathe",          "Paris",        20, 2, 30),
    ("sante", "dentiste",            "Lyon",         20, 2, 30),
    ("sante", "kinésithérapeute",    "Lyon",         20, 2, 30),
    ("sante", "dentiste",            "Marseille",    20, 2, 30),
    ("sante", "ostéopathe",          "Marseille",    20, 2, 30),
    ("sante", "dentiste",            "Toulouse",     20, 2, 30),
    ("sante", "dentiste",            "Nice",         20, 2, 30),
    ("sante", "dentiste",            "Bordeaux",     20, 2, 30),
    ("sante", "naturopathe",         "Paris",        20, 3, 30),
    ("sante", "psychologue",         "Paris",        20, 3, 30),
    ("sante", "nutritionniste",      "Paris",        20, 3, 30),

    # ── Juridique / Comptable (priorité 2 — sites toujours présents) ──────
    ("juridique", "avocat",          "Paris",        20, 2, 30),
    ("juridique", "expert-comptable","Paris",        20, 2, 30),
    ("juridique", "avocat",          "Lyon",         20, 2, 30),
    ("juridique", "expert-comptable","Lyon",         20, 2, 30),
    ("juridique", "avocat",          "Marseille",    20, 2, 30),
    ("juridique", "notaire",         "Paris",        20, 3, 30),
    ("juridique", "avocat",          "Toulouse",     20, 3, 30),
    ("juridique", "avocat",          "Bordeaux",     20, 3, 30),

    # ── Immobilier (priorité 3) ────────────────────────────────────────────
    ("immobilier", "agence immobilière","Paris",     20, 3, 30),
    ("immobilier", "agence immobilière","Lyon",      20, 3, 30),
    ("immobilier", "agence immobilière","Marseille", 20, 3, 30),
    ("immobilier", "agence immobilière","Toulouse",  20, 3, 30),
    ("immobilier", "agence immobilière","Nice",      20, 3, 30),
    ("immobilier", "agence immobilière","Bordeaux",  20, 3, 30),

    # ── Beauté / Coiffure (priorité 3) ────────────────────────────────────
    ("beaute", "salon de coiffure",  "Paris",        20, 3, 30),
    ("beaute", "esthéticienne",      "Paris",        20, 3, 30),
    ("beaute", "salon de coiffure",  "Lyon",         20, 3, 30),
    ("beaute", "barbier",            "Paris",        20, 4, 30),
    ("beaute", "salon de coiffure",  "Marseille",    20, 4, 30),
    ("beaute", "spa",                "Paris",        20, 4, 30),

    # ── Auto / Garage (priorité 4) ────────────────────────────────────────
    ("auto", "garagiste",            "Paris",        20, 4, 30),
    ("auto", "carrossier",           "Paris",        20, 4, 30),
    ("auto", "garagiste",            "Lyon",         20, 4, 30),
    ("auto", "garagiste",            "Marseille",    20, 4, 30),
    ("auto", "garagiste",            "Toulouse",     20, 4, 30),
    ("auto", "auto-école",           "Paris",        20, 4, 30),

    # ── Sport / Fitness (priorité 4) ──────────────────────────────────────
    ("sport", "salle de sport",      "Paris",        20, 4, 30),
    ("sport", "coach sportif",       "Paris",        20, 4, 30),
    ("sport", "salle de sport",      "Lyon",         20, 4, 30),
    ("sport", "yoga",                "Paris",        20, 5, 30),
    ("sport", "pilates",             "Paris",        20, 5, 30),

    # ── Numérique / Créatif (priorité 4) ──────────────────────────────────
    ("numerique", "agence web",      "Paris",        20, 4, 30),
    ("numerique", "photographe",     "Paris",        20, 4, 30),
    ("numerique", "agence web",      "Lyon",         20, 4, 30),
    ("numerique", "graphiste",       "Paris",        20, 5, 30),

    # ── Commerce local (priorité 5) ───────────────────────────────────────
    ("commerce", "fleuriste",        "Paris",        20, 5, 30),
    ("commerce", "opticien",         "Paris",        20, 5, 30),
    ("commerce", "librairie",        "Paris",        20, 5, 30),
    ("commerce", "fleuriste",        "Lyon",         20, 5, 30),

    # ── Hôtellerie (priorité 5) ───────────────────────────────────────────
    ("hotellerie", "hôtel",          "Paris",        20, 5, 30),
    ("hotellerie", "hôtel",          "Nice",         20, 5, 30),
    ("hotellerie", "hôtel",          "Lyon",         20, 5, 30),
    ("hotellerie", "chambre d'hôtes","Paris",        20, 6, 30),

    # ── Bijouterie (priorité 6) ───────────────────────────────────────────
    ("bijouterie", "bijouterie",     "Paris",        20, 6, 30),
    ("bijouterie", "bijouterie",     "Lyon",         20, 6, 30),
    ("bijouterie", "horlogerie",     "Paris",        20, 6, 30),
]


def seed_default_priorities():
    """Insère les priorités par défaut si la table est vide."""
    try:
        with get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) as n FROM scraping_priorities").fetchone()['n']
            if count > 0:
                return  # déjà peuplé

            conn.executemany("""
                INSERT OR IGNORE INTO scraping_priorities
                    (secteur, keyword, ville, limit_leads, priorite, frequence_jours)
                VALUES (?, ?, ?, ?, ?, ?)
            """, DEFAULT_PRIORITIES)
            # Renommer limit_leads → min_emails dans la colonne (valeurs déjà correctes)
            try:
                conn.execute("ALTER TABLE scraping_priorities ADD COLUMN min_emails INTEGER DEFAULT 20")
            except Exception:
                pass  # colonne existe déjà
            conn.execute("UPDATE scraping_priorities SET min_emails = limit_leads WHERE min_emails IS NULL")
            conn.commit()
            logger.info(f"[AUTO-PLANNER] {len(DEFAULT_PRIORITIES)} priorités par défaut injectées.")
    except Exception as e:
        logger.error(f"[AUTO-PLANNER] seed_default_priorities: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# LOGIQUE D'AUTO-PLANIFICATION
# ──────────────────────────────────────────────────────────────────────────────

def get_auto_plan_settings() -> dict:
    """Lit les paramètres auto-plan depuis planning_settings."""
    try:
        with get_conn() as conn:
            rows = conn.execute("SELECT key, value FROM planning_settings").fetchall()
        cfg = {r['key']: r['value'] for r in rows}
        return {
            'enabled':          cfg.get('auto_plan_enabled', '1') == '1',
            'per_day':          int(cfg.get('auto_plan_per_day', '3')),
            'daily_quota':      int(cfg.get('daily_quota', '60')),
            'max_backlog_days': int(cfg.get('max_backlog_days', '3')),
            # max_backlog_days : nb de jours d'envoi en stock avant de pauser le scraping
        }
    except Exception as e:
        logger.error(f"[AUTO-PLANNER] get_settings: {e}")
        return {'enabled': True, 'per_day': 3, 'daily_quota': 60, 'max_backlog_days': 3}


def get_pipeline_backlog() -> dict:
    """
    Calcule le backlog actuel :
    - leads_with_email  : leads avec email, non encore envoyés
    - leads_approved    : leads approuvés prêts à envoyer demain
    - leads_draft       : leads avec brouillon email non encore approuvés
    - leads_no_audit    : leads avec email mais sans audit
    """
    try:
        with get_conn() as conn:
            r = conn.execute("""
                SELECT
                    COUNT(DISTINCT lb.id) FILTER (
                        WHERE lb.email IS NOT NULL AND lb.email != ''
                          AND lb.statut NOT IN ('envoye','email_sent')
                          AND lb.id NOT IN (
                              SELECT DISTINCT lead_id FROM emails_envoyes WHERE lead_id IS NOT NULL
                          )
                    ) AS leads_with_email,

                    COUNT(DISTINCT la.lead_id) FILTER (
                        WHERE la.approuve = 1
                          AND lb.statut NOT IN ('envoye','email_sent')
                    ) AS leads_approved,

                    COUNT(DISTINCT la.lead_id) FILTER (
                        WHERE la.email_corps IS NOT NULL AND la.email_corps != ''
                          AND la.approuve = 0
                    ) AS leads_draft,

                    COUNT(DISTINCT lb.id) FILTER (
                        WHERE lb.email IS NOT NULL AND lb.email != ''
                          AND lb.id NOT IN (SELECT lead_id FROM leads_audites WHERE lead_id IS NOT NULL)
                    ) AS leads_no_audit

                FROM leads_bruts lb
                LEFT JOIN leads_audites la ON la.lead_id = lb.id
            """).fetchone()
        return dict(r) if r else {}
    except Exception as e:
        logger.error(f"[AUTO-PLANNER] get_pipeline_backlog: {e}")
        return {}


def count_planned_today(target_date: str | None = None) -> int:
    """Nombre de campagnes déjà planifiées pour la date donnée (défaut: aujourd'hui)."""
    d = target_date or date.today().isoformat()
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as n FROM planned_campaigns WHERE date_planifiee = ? AND statut != 'cancelled'",
                (d,)
            ).fetchone()
        return row['n'] if row else 0
    except Exception:
        return 0


def get_next_priorities(n: int, target_date: str) -> list:
    """
    Retourne les N prochaines configs à scraper :
    - actif = 1
    - derniere_execution NULL ou + vieille que frequence_jours
    - pas déjà planifié pour target_date avec ce (keyword+ville)
    - ordre : priorite ASC, derniere_execution ASC (oldest first)
    """
    try:
        with get_conn() as conn:
            rows = conn.execute("""
                SELECT sp.*
                FROM scraping_priorities sp
                WHERE sp.actif = 1
                  AND (
                      sp.derniere_execution IS NULL
                      OR julianday('now') - julianday(sp.derniere_execution) >= sp.frequence_jours
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM planned_campaigns pc
                      WHERE pc.keyword = sp.keyword
                        AND pc.city    = sp.ville
                        AND pc.date_planifiee = ?
                        AND pc.statut != 'cancelled'
                  )
                ORDER BY sp.priorite ASC, sp.derniere_execution ASC NULLS FIRST
                LIMIT ?
            """, (target_date, n)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[AUTO-PLANNER] get_next_priorities: {e}")
        return []


def _compute_scraping_slots(settings: dict, backlog: dict) -> int:
    """
    Calcule combien de campagnes scraper aujourd'hui en fonction du backlog.

    Règle :
      - backlog_days = leads_with_email / daily_quota
      - Si backlog_days >= max_backlog_days → 0 (pause scraping)
      - Si backlog_days >= max_backlog_days - 1 → 1 campagne (ralentir)
      - Sinon → per_day campagnes (plein régime)
    """
    daily_quota      = settings['daily_quota']
    max_days         = settings['max_backlog_days']
    leads_with_email = backlog.get('leads_with_email', 0)

    if daily_quota <= 0:
        return settings['per_day']

    backlog_days = leads_with_email / daily_quota

    if backlog_days >= max_days:
        logger.info(
            f"[AUTO-PLANNER] Backlog {leads_with_email} leads "
            f"= {backlog_days:.1f}j d'envoi >= seuil {max_days}j → scraping pausé."
        )
        return 0

    if backlog_days >= max_days - 1:
        logger.info(
            f"[AUTO-PLANNER] Backlog {leads_with_email} leads "
            f"= {backlog_days:.1f}j → ralentissement (1 campagne)."
        )
        return 1

    logger.info(
        f"[AUTO-PLANNER] Backlog {leads_with_email} leads "
        f"= {backlog_days:.1f}j → plein régime ({settings['per_day']} campagnes)."
    )
    return settings['per_day']


def plan_day(target_date: str | None = None, force: bool = False) -> int:
    """
    Auto-planifie des scrapings pour target_date.
    Respecte le seuil de backlog sauf si force=True.
    Retourne le nombre de campagnes ajoutées.
    """
    settings = get_auto_plan_settings()
    if not settings['enabled'] and not force:
        return 0

    d = target_date or date.today().isoformat()

    already = count_planned_today(d)

    # Calcul du nombre de slots en fonction du backlog (seulement pour aujourd'hui)
    if d == date.today().isoformat() and not force:
        backlog = get_pipeline_backlog()
        target  = _compute_scraping_slots(settings, backlog)
    else:
        # Pour les jours futurs on planifie normalement
        target = settings['per_day']

    needed = target - already

    if needed <= 0:
        logger.info(f"[AUTO-PLANNER] {d} → {already}/{target} campagne(s), rien à ajouter.")
        return 0

    candidates = get_next_priorities(needed, d)
    if not candidates:
        logger.info("[AUTO-PLANNER] Aucune priorité disponible pour compléter la journée.")
        return 0

    added = 0
    try:
        # min_emails par campagne = daily_quota / per_day, toujours recalculé depuis les settings
        min_e_par_campagne = max(20, settings['daily_quota'] // settings['per_day'])
        
        # Heures disponibles pour étaler les campagnes dans la journée
        hours = ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00']
        
        with get_conn() as conn:
            for idx, c in enumerate(candidates):
                min_e = min_e_par_campagne
                # Assigner une heure différente pour chaque campagne (alternance)
                hour = hours[idx % len(hours)]
                conn.execute("""
                    INSERT INTO planned_campaigns
                        (secteur, keyword, city, limit_leads, min_emails, date_planifiee, heure, statut)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'planned')
                """, (c['secteur'], c['keyword'], c['ville'], min_e * 4, min_e, d, hour))
                added += 1
            conn.commit()

        with get_conn() as conn:
            for c in candidates:
                conn.execute(
                    "UPDATE scraping_priorities SET derniere_execution=? WHERE id=?",
                    (d, c['id'])
                )
            conn.commit()

        logger.info(f"[AUTO-PLANNER] {d} → {added} campagne(s) ajoutée(s).")
    except Exception as e:
        logger.error(f"[AUTO-PLANNER] plan_day: {e}")

    return added


def plan_week(from_date: str | None = None) -> dict:
    """
    Auto-planifie la semaine (7 jours à partir de from_date).
    Retourne un dict {date: nb_ajouté}.
    """
    start = date.fromisoformat(from_date) if from_date else date.today()
    results = {}
    for i in range(7):
        d = (start + timedelta(days=i)).isoformat()
        n = plan_day(d)
        results[d] = n
    total = sum(results.values())
    logger.info(f"[AUTO-PLANNER] Semaine planifiée : {total} campagne(s) sur 7 jours.")
    return results


# ──────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE SCHEDULER
# ──────────────────────────────────────────────────────────────────────────────

def get_pipeline_count() -> int:
    """
    Nombre de leads actuellement dans le pipeline (prêts à envoyer + en cours d'audit/génération).
    Utilisé pour détecter un déficit et déclencher un top-up scraping.
    """
    try:
        with get_conn() as conn:
            r = conn.execute("""
                SELECT
                    -- Approuvés prêts à envoyer
                    COUNT(DISTINCT la.lead_id) FILTER (WHERE la.approuve = 1) +
                    -- Emails générés en attente d'approbation
                    COUNT(DISTINCT la.lead_id) FILTER (
                        WHERE la.email_corps IS NOT NULL AND la.email_corps != '' AND la.approuve = 0
                    ) +
                    -- Leads avec email non encore audités
                    COUNT(DISTINCT lb.id) FILTER (
                        WHERE lb.email IS NOT NULL AND lb.email != ''
                          AND lb.id NOT IN (SELECT lead_id FROM leads_audites WHERE lead_id IS NOT NULL)
                          AND lb.statut NOT IN ('envoye', 'email_sent')
                    ) AS total
                FROM leads_bruts lb
                LEFT JOIN leads_audites la ON la.lead_id = lb.id
                  AND lb.statut NOT IN ('envoye', 'email_sent')
                  AND lb.id NOT IN (
                      SELECT DISTINCT lead_id FROM emails_envoyes WHERE lead_id IS NOT NULL
                  )
            """).fetchone()
        return r['total'] if r else 0
    except Exception as e:
        logger.error(f"[AUTO-PLANNER] get_pipeline_count: {e}")
        return 0


def fill_quota_if_needed(trigger_immediate: bool = False) -> int:
    """
    Vérifie si le pipeline est en dessous du quota journalier.
    Si déficit ET aucune campagne active/planifiée aujourd'hui, lance un scraping.

    Args:
        trigger_immediate: si True, appelle l'API Flask pour lancer le scraper tout de suite.

    Retourne le nombre d'emails manquants (0 si quota atteint).
    """
    settings = get_auto_plan_settings()
    quota = settings['daily_quota']
    pipeline = get_pipeline_count()
    deficit = max(0, quota - pipeline)

    # Si une campagne est déjà en cours ou planifiée aujourd'hui, ne pas doubler
    today = date.today().isoformat()
    try:
        with get_conn() as conn:
            active = conn.execute("""
                SELECT COUNT(*) as n FROM planned_campaigns
                WHERE date_planifiee = ? AND statut IN ('planned', 'running')
            """, (today,)).fetchone()['n']
        if active > 0:
            logger.info(f"[TOP-UP] {active} campagne(s) déjà active(s) aujourd'hui — pas de top-up.")
            return deficit
    except Exception:
        pass

    logger.info(f"[TOP-UP] Pipeline: {pipeline}/{quota} emails — déficit: {deficit}")

    if deficit <= 0:
        return 0

    # Trouver la prochaine campagne disponible
    today = date.today().isoformat()
    candidates = get_next_priorities(1, today)
    if not candidates:
        logger.warning("[TOP-UP] Aucune priorité disponible pour top-up.")
        return deficit

    c = candidates[0]

    if trigger_immediate:
        # Lancer directement via l'API Flask
        try:
            import requests as req
            payload = {
                'keyword':       c['keyword'],
                'city':          c['ville'],
                'sector':        c['secteur'],
                'campaign_name': f"top-up {c['keyword']} {c['ville']} {today}",
                'min_emails':    deficit,
                'limit':         deficit * 4,
                'multi_zone':    False,
            }
            resp = req.post('http://127.0.0.1:5001/api/scraper/launch', json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info(f"[TOP-UP] Scraping lancé : {c['keyword']} {c['ville']} — objectif {deficit} emails")
                # Mettre à jour la date d'exécution
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE scraping_priorities SET derniere_execution=? WHERE id=?",
                        (today, c['id'])
                    )
                    conn.commit()
            else:
                logger.warning(f"[TOP-UP] Erreur lancement: {resp.text}")
        except Exception as e:
            logger.error(f"[TOP-UP] fill_quota_if_needed: {e}")
    else:
        # Planifier pour demain - trouver une heure libre
        try:
            # Heures disponibles
            hours = ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00']
            
            # Trouver une heure qui n'est pas déjà utilisée ce jour
            with get_conn() as conn:
                used = set(r[0] for r in conn.execute(
                    "SELECT heure FROM planned_campaigns WHERE date_planifiee = ? AND statut != 'cancelled'",
                    (today,)
                ).fetchall())
                
                # Prendre la première heure non utilisée
                hour = '08:00'
                for h in hours:
                    if h not in used:
                        hour = h
                        break
                
                conn.execute("""
                    INSERT INTO planned_campaigns
                        (secteur, keyword, city, limit_leads, min_emails, date_planifiee, heure, statut)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'planned')
                """, (c['secteur'], c['keyword'], c['ville'], deficit * 4, deficit, today, hour))
                conn.execute(
                    "UPDATE scraping_priorities SET derniere_execution=? WHERE id=?",
                    (today, c['id'])
                )
                conn.commit()
            logger.info(f"[TOP-UP] Campagne planifiée : {c['keyword']} {c['ville']} — objectif {deficit} emails à {hour}")
        except Exception as e:
            logger.error(f"[TOP-UP] plan: {e}")

    return deficit


def run_auto_plan():
    """
    Job scheduler 07h45 : s'assure que la journée a assez de scrapings planifiés.
    Injecte les priorités par défaut si la table est vide.
    Déclenche un top-up si le pipeline est en dessous du quota.
    """
    seed_default_priorities()
    added = plan_day()
    if added:
        logger.info(f"[AUTO-PLANNER] {added} scraping(s) ajouté(s) pour aujourd'hui.")

    # Top-up immédiat si déficit (trigger direct via API Flask)
    fill_quota_if_needed(trigger_immediate=True)

    return added
