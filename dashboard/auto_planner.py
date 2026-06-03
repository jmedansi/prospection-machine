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

    # ── Santé retirée (Interdiction de faire de la publicité en France) ────────
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


import random

# ──────────────────────────────────────────────────────────────────────────────
# DICTIONNAIRE DE VARIATIONS DE MOTS-CLÉS
# ──────────────────────────────────────────────────────────────────────────────
KEYWORD_VARIATIONS = {
    "plombier": ["plombier", "dépannage plomberie", "urgence plombier", "artisan plombier", "entreprise de plomberie", "plombier chauffagiste", "fuite d'eau"],
    "électricien": ["électricien", "artisan électricien", "dépannage électrique", "urgence électricité", "installation électrique", "entreprise électricité"],
    "menuisier": ["menuisier", "artisan menuisier", "menuiserie sur mesure", "menuiserie bois", "menuiserie pvc alu"],
    "peintre en bâtiment": ["peintre en bâtiment", "artisan peintre", "entreprise de peinture", "peintre décorateur", "rénovation peinture"],
    "chauffagiste": ["chauffagiste", "plombier chauffagiste", "dépannage chaudière", "entretien chaudière", "installation pompe à chaleur"],
    "serrurier": ["serrurier", "dépannage serrurier", "urgence serrurier", "ouverture de porte", "artisan serrurier"],
    # Santé retirée de la liste des variations
    
    "avocat": ["avocat", "cabinet d'avocats", "avocat droit du travail", "avocat affaires", "avocat famille", "cabinet juridique"],
    "expert-comptable": ["expert-comptable", "cabinet d'expertise comptable", "cabinet comptable", "expert comptable en ligne"],
    "notaire": ["notaire", "étude notariale", "office notarial", "notaire succession"],
    
    "agence immobilière": ["agence immobilière", "conseiller immobilier", "estimation immobilière", "transaction immobilière", "mandataire immobilier", "réseau immobilier"],
    
    "salon de coiffure": ["salon de coiffure", "coiffeur", "coiffeur visagiste", "coiffure femme", "coiffure homme", "institut capillaire"],
    "esthéticienne": ["esthéticienne", "institut de beauté", "soins esthétiques", "salon d'esthétique", "esthéticienne à domicile"],
    "barbier": ["barbier", "barbershop", "salon de coiffure homme", "coiffeur barbier"],
    "spa": ["spa", "centre de bien-être", "spa hammam", "massage bien-être", "institut spa"],
    
    "garagiste": ["garagiste", "garage auto", "réparation automobile", "entretien auto", "mécanicien auto", "centre auto"],
    "carrossier": ["carrossier", "carrosserie auto", "réparation carrosserie", "peinture auto", "tôlerie auto"],
    "auto-école": ["auto-école", "école de conduite", "permis de conduire", "auto école moto"],
    
    "salle de sport": ["salle de sport", "fitness", "club de sport", "centre de remise en forme", "gymnase"],
    "coach sportif": ["coach sportif", "coaching sportif", "coach personnel", "personal trainer"],
    "yoga": ["yoga", "studio de yoga", "cours de yoga", "centre de yoga", "professeur de yoga"],
    "pilates": ["pilates", "studio pilates", "cours de pilates"],
    
    "agence web": ["agence web", "agence digitale", "création site web", "agence communication digitale", "agence seo", "développement web"],
    "photographe": ["photographe", "studio photo", "photographe professionnel", "photographe mariage", "photographe portrait"],
    "graphiste": ["graphiste", "studio graphique", "graphiste freelance", "directeur artistique", "designer graphique"],
    
    "fleuriste": ["fleuriste", "artisan fleuriste", "boutique de fleurs", "création florale", "livraison fleurs"],
    "opticien": ["opticien", "magasin d'optique", "opticien lunetier", "centre optique"],
    "librairie": ["librairie", "librairie indépendante", "maison de la presse", "bouquinerie"],
    
    "hôtel": ["hôtel", "établissement hôtelier", "hôtel restaurant", "hébergement", "boutique hôtel"],
    "chambre d'hôtes": ["chambre d'hôtes", "gîte", "maison d'hôtes", "bed and breakfast"],
    
    "bijouterie": ["bijouterie", "joaillerie", "artisan bijoutier", "créateur de bijoux", "bijouterie fantaisie"],
    "horlogerie": ["horlogerie", "artisan horloger", "réparation montres", "montres de luxe"],
    
    # ── E-commerce & FB Ads ──
    "vêtements": ["vêtements homme", "vêtements femme", "prêt-à-porter", "boutique mode", "marque de vêtements", "streetwear", "boutique vêtements en ligne"],
    "bijoux": ["bijoux", "bijouterie en ligne", "bijoux créateur", "bijoux fantaisie", "bijoux argent", "créateur bijoux"],
    "cosmétiques": ["cosmétiques", "produits de beauté", "soins visage", "maquillage", "soins naturels", "cosmétiques bio", "boutique cosmétiques en ligne"],
    "décoration": ["décoration intérieur", "meubles", "décoration maison", "objets déco", "concept store déco", "boutique décoration en ligne"],
    "cbd": ["cbd", "fleurs cbd", "huile cbd", "cbd shop", "boutique cbd en ligne"],
    "restaurant": ["restaurant", "livraison repas", "pizzeria", "burger", "restaurant gastronomique", "restaurant traditionnel"],
    "chaussures": ["chaussures femme", "chaussures homme", "sneakers", "boutique chaussures en ligne"],
    "maroquinerie": ["maroquinerie", "sacs à main", "sac en cuir", "boutique maroquinerie"],
}

def get_used_keywords(city: str) -> set:
    """Récupère les variations déjà planifiées ou exécutées pour une ville donnée."""
    from database.db_manager import get_conn
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT keyword FROM planned_campaigns WHERE city = ?",
                (city,)
            ).fetchall()
        # Normaliser pour la comparaison (minuscules, strip)
        return {r['keyword'].lower().strip() for r in rows if r['keyword']}
    except Exception as e:
        logger.error(f"[AUTO-PLANNER] get_used_keywords: {e}")
        return set()

def get_keyword_variation(base_keyword: str, city: str, sector: str = "") -> str:
    """
    Retourne une variation de longue traîne générée par l'IA ou le dictionnaire.
    Consulte la base de données pour ne pas répéter la même variation dans la même ville.
    """
    used = get_used_keywords(city)
    
    # 1. Tentative avec l'IA
    try:
        from scraper.sniper.keyword_generator import generate_long_tail
        ai_variations = generate_long_tail(sector, base_keyword, city, limit=10)
        if ai_variations:
            for var in ai_variations:
                # Retirer la ville si elle y est pour la vérification exacte (car 'keyword' dans DB ne contient pas forcément la ville)
                # Mais en fait, variation = ce qu'on sauvegarde dans planned_campaigns.keyword
                if var not in used:
                    logger.info(f"[AUTO-PLANNER] Nouvelle intention IA trouvée : '{var}'")
                    return var
            logger.info(f"[AUTO-PLANNER] Toutes les variations IA pour '{base_keyword}' à '{city}' sont déjà utilisées.")
    except Exception as e:
        logger.error(f"[AUTO-PLANNER] Erreur appel keyword_generator : {e}")

    # 2. Fallback dictionnaire
    k_low = base_keyword.lower().strip()
    dict_variations = []
    if k_low in KEYWORD_VARIATIONS:
        dict_variations = KEYWORD_VARIATIONS[k_low]
    else:
        prefixes = ["", "entreprise de ", "pro ", "cabinet ", "agence "]
        dict_variations = [f"{p}{base_keyword}".strip() for p in prefixes]

    # Mélanger pour ne pas toujours prendre la première
    random.shuffle(dict_variations)
    
    for var in dict_variations:
        if var.lower() not in used:
            return var

    # 3. Si tout est utilisé, ajouter un modificateur aléatoire pour forcer une nouvelle recherche
    import string
    random_suffix = ''.join(random.choices(string.ascii_lowercase, k=3))
    new_var = f"{base_keyword} {random_suffix}"
    logger.warning(f"[AUTO-PLANNER] Mémoire pleine pour '{base_keyword}' à '{city}'. Utilisation de '{new_var}'.")
    return new_var


def seed_default_priorities():
    """Insère les priorités par défaut si elles n'existent pas déjà."""
    try:
        with get_conn() as conn:
            # S'assurer que les colonnes existent
            try: conn.execute("ALTER TABLE scraping_priorities ADD COLUMN min_emails INTEGER DEFAULT 20")
            except Exception: pass
            
            try: conn.execute("ALTER TABLE scraping_priorities ADD COLUMN source TEXT DEFAULT 'maps'")
            except Exception: pass

            conn.execute("UPDATE scraping_priorities SET min_emails = limit_leads WHERE min_emails IS NULL")
            conn.execute("UPDATE scraping_priorities SET source = 'maps' WHERE source IS NULL")

            # 1. Maps priorities (legacy defaults)
            conn.executemany("""
                INSERT OR IGNORE INTO scraping_priorities
                    (secteur, keyword, ville, limit_leads, priorite, frequence_jours)
                VALUES (?, ?, ?, ?, ?, ?)
            """, DEFAULT_PRIORITIES)
            
            # 2. Multi-source priorities
            new_sources = [
                ("vêtements", "vêtements", "Paris", 20, 2, 30, "sniper_ecom"),
                ("bijoux", "bijoux", "Lyon", 20, 3, 30, "sniper_ecom"),
                ("cosmétiques", "cosmétiques", "Marseille", 20, 3, 30, "sniper_ecom"),
                ("décoration", "décoration", "Bordeaux", 20, 3, 30, "sniper_ecom"),
                ("chaussures", "chaussures", "Toulouse", 20, 4, 30, "sniper_ecom"),
            
                ("immobilier", "agence immobilière", "Paris", 20, 3, 30, "sniper_fb"),
                ("sport", "coach sportif", "Lyon", 20, 4, 30, "sniper_fb"),
                ("beaute", "esthéticienne", "Marseille", 20, 4, 30, "sniper_fb"),
            
                ("juridique", "avocat", "Paris", 20, 2, 30, "sniper_ads"),
                ("artisan", "plombier", "Lyon", 20, 1, 30, "sniper_ads"),
            ]
            conn.executemany("""
                INSERT OR IGNORE INTO scraping_priorities
                    (secteur, keyword, ville, min_emails, priorite, frequence_jours, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, new_sources)
            
            conn.commit()
            logger.info("[AUTO-PLANNER] Priorités multi-sources vérifiées/injectées.")
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
            'maps_auto_scrape': False,  # DÉSACTIVÉ — scraping Google Maps automatique désactivé définitivement
            'maps_daily_quota': int(cfg.get('maps_daily_quota', '50')),
            'maps_topup_enabled': False,  # DÉSACTIVÉ — top-up Google Maps automatique désactivé définitivement
            # max_backlog_days : nb de jours d'envoi en stock avant de pauser le scraping
        }
    except Exception as e:
        logger.error(f"[AUTO-PLANNER] get_settings: {e}")
        return {
            'enabled': True,
            'per_day': 3,
            'daily_quota': 60,
            'max_backlog_days': 3,
            'maps_auto_scrape': False,
            'maps_daily_quota': 50,
            'maps_topup_enabled': False
        }


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


def get_next_priorities(n: int, target_date: str, exclude_source: str = None) -> list:
    """
    Retourne les N prochaines configs à scraper :
    - actif = 1
    - derniere_execution NULL ou + vieille que frequence_jours
    - pas déjà planifié pour target_date avec ce (keyword+ville)
    - exclude_source: optionnel, exclure une source (ex: 'maps')
    - ordre : priorite ASC, derniere_execution ASC (oldest first)
    """
    try:
        with get_conn() as conn:
            query = """
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
            """
            params = [target_date]
            if exclude_source:
                query += " AND sp.source != ?"
                params.append(exclude_source)
                
            query += " ORDER BY sp.priorite ASC, sp.derniere_execution ASC NULLS FIRST LIMIT ?"
            params.append(n)
            
            rows = conn.execute(query, params).fetchall()
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

    exclude = 'maps'  # DÉSACTIVÉ — Google Maps exclu de l'auto-planification
    candidates = get_next_priorities(needed, d, exclude_source=exclude)
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
                variation = get_keyword_variation(c['keyword'], c['ville'], c.get('secteur', ''))
                conn.execute("""
                    INSERT INTO planned_campaigns
                        (secteur, keyword, city, limit_leads, min_emails, date_planifiee, heure, statut, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'planned', ?)
                """, (c['secteur'], variation, c['ville'], min_e * 4, min_e, d, hour, c.get('source', 'maps')))
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
    exclude = 'maps'  # DÉSACTIVÉ — Google Maps exclu du top-up automatique
    candidates = get_next_priorities(1, today, exclude_source=exclude)
    if not candidates:
        logger.warning("[TOP-UP] Aucune priorité disponible pour top-up.")
        return deficit

    c = candidates[0]
    variation = get_keyword_variation(c['keyword'], c['ville'], c.get('secteur', ''))

    if trigger_immediate:
        # Lancer directement via l'API Flask
        try:
            import requests as req
            source = c.get('source', 'maps')
            
            if source == 'sniper_ecom':
                api_url = 'http://127.0.0.1:5001/api/sniper/tech-scan'
                payload = {
                    'keywords':      [variation],
                    'city':          c['ville'],
                    'campaign_name': f"top-up {variation} {c['ville']} {today}",
                    'max_leads':     deficit * 4,
                    'max_companies': deficit * 8
                }
            elif source == 'sniper_fb':
                api_url = 'http://127.0.0.1:5001/api/sniper/fb-ads-scan'
                payload = {
                    'search_terms':  [f"{variation} {c['ville']}"],
                    'country':       'FR',
                    'max_pages':     5,
                    'campaign_name': f"top-up {variation} {c['ville']} {today}"
                }
            elif source == 'sniper_ads':
                api_url = 'http://127.0.0.1:5001/api/sniper/launch'
                payload = {
                    'keywords':      [f"{variation} {c['ville']}"],
                    'country':       'fr',
                    'max_per_kw':    deficit * 4,
                    'campaign_name': f"top-up {variation} {c['ville']} {today}"
                }
            else:
                api_url = 'http://127.0.0.1:5001/api/scraper/launch'
                payload = {
                    'keyword':       variation,
                    'city':          c['ville'],
                    'sector':        c['secteur'],
                    'campaign_name': f"top-up {variation} {c['ville']} {today}",
                    'min_emails':    deficit,
                    'limit':         deficit * 4,
                    'multi_zone':    False,
                }
                
            resp = req.post(api_url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info(f"[TOP-UP] Scraping {source} lancé : {variation} {c['ville']} — objectif {deficit} emails")
                # Mettre à jour la date d'exécution et marquer comme running
                with get_conn() as conn:
                    # Enregistrer dans planned_campaigns pour que ça compte comme actif
                    import datetime
                    now = datetime.datetime.now()
                    conn.execute("""
                        INSERT INTO planned_campaigns
                            (secteur, keyword, city, limit_leads, min_emails, date_planifiee, heure, statut, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)
                    """, (c.get('secteur', ''), variation, c['ville'], deficit * 4, deficit, today, now.strftime('%H:%M'), source))
                    
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
                        (secteur, keyword, city, limit_leads, min_emails, date_planifiee, heure, statut, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'planned', ?)
                """, (c['secteur'], variation, c['ville'], deficit * 4, deficit, today, hour, c.get('source', 'maps')))
                conn.execute(
                    "UPDATE scraping_priorities SET derniere_execution=? WHERE id=?",
                    (today, c['id'])
                )
                conn.commit()
            logger.info(f"[TOP-UP] Campagne planifiée : {variation} {c['ville']} — objectif {deficit} emails à {hour}")
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
