# -*- coding: utf-8 -*-
"""
core/scoring.py — Seuils et labels PageSpeed / LCP unifiés

Source unique pour l'interprétation des métriques de performance web.
Remplace les seuils divergents entre copywriter/main.py et sniper/rapport_generator.py.

Deux usages :
  - Détection (is_*) : décision binaire pour déclencher un email ou une situation
  - Affichage (label, color) : texte et couleur dans les rapports HTML

Seuils de référence Google PageSpeed Insights (avril 2025) :
  Score mobile  ≥ 90 → Bon | 50–89 → Moyen | < 50 → Faible
  LCP           ≤ 2500ms → Bon | 2500–4000ms → À améliorer | > 4000ms → Mauvais
"""

# ── Seuils de détection ────────────────────────────────────────────────────────

SCORE_MOBILE_BON      = 70   # ≥ 70 → acceptable pour la prospection
SCORE_MOBILE_MOYEN    = 50   # 50–69 → insuffisant (trigger email)
# < 50 → critique

LCP_BON_MS            = 2500  # ≤ 2500ms → bon
LCP_MOYEN_MS          = 4000  # 2500–4000ms → à améliorer
# > 4000ms → mauvais (trigger email critique)

LCP_LENT_MS           = 3000  # Seuil "lent" pour le copywriter (S1, S8)


# ── Couleurs (hex) ────────────────────────────────────────────────────────────

COLOR_BON      = "#10b981"   # vert
COLOR_MOYEN    = "#f59e0b"   # orange
COLOR_MAUVAIS  = "#ef4444"   # rouge


# ── Score mobile ──────────────────────────────────────────────────────────────

def score_label(score: int) -> str:
    if score >= SCORE_MOBILE_BON:   return "Acceptable"
    if score >= SCORE_MOBILE_MOYEN: return "Insuffisant"
    return "Critique"

def score_color(score: int) -> str:
    if score >= SCORE_MOBILE_BON:   return COLOR_BON
    if score >= SCORE_MOBILE_MOYEN: return COLOR_MOYEN
    return COLOR_MAUVAIS

def is_score_critique(score: int) -> bool:
    return score < SCORE_MOBILE_MOYEN

def is_score_lent(score: int) -> bool:
    """Seuil copywriter — déclenche situation S1."""
    return score < SCORE_MOBILE_BON


# ── LCP ───────────────────────────────────────────────────────────────────────

def lcp_label(ms: float) -> str:
    if ms <= LCP_BON_MS:   return "Bon"
    if ms <= LCP_MOYEN_MS: return "À améliorer"
    return "Mauvais"

def lcp_color(ms: float) -> str:
    if ms <= LCP_BON_MS:   return COLOR_BON
    if ms <= LCP_MOYEN_MS: return COLOR_MOYEN
    return COLOR_MAUVAIS

def is_lcp_critique(ms: float) -> bool:
    return ms > LCP_MOYEN_MS

def is_lcp_lent(ms: float) -> bool:
    """Seuil copywriter — déclenche situation S1/S8."""
    return ms > LCP_LENT_MS
