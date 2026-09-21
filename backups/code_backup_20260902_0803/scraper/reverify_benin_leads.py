# -*- coding: utf-8 -*-
"""
scraper/reverify_benin_leads.py — Revérification des fiches Google Maps pour les leads Bénin sans site

Re-visite chaque fiche Google Maps des leads Bénin sans site web,
met à jour les données (rating, avis, téléphone, adresse, site web).
Si un site web est trouvé, le lead est marqué comme "avec site".

Usage:
    python scraper/reverify_benin_leads.py
    python scraper/reverify_benin_leads.py --limit 10   # tester sur 10 leads
    python scraper/reverify_benin_leads.py --dry-run    # afficher sans modifier
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.connection import get_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

# ─── JS extraction (réutilise le pattern du scraper principal) ────────────────

_JS_EXTRACT_DETAILS = r'''() => {
    const d = { site_web: "", telephone: "", adresse: "", rating: 0, nb_avis: 0, category: "" };

    // ===== WEBSITE (3 stratégies) =====
    const anchors = document.querySelectorAll('a[href]');
    for (const a of anchors) {
        const did = a.getAttribute('data-item-id') || '';
        if (did.startsWith('website:') && a.href && !a.href.includes('google.') && !a.href.includes('maps.')) {
            d.site_web = a.href; break;
        }
    }
    if (!d.site_web) {
        for (const a of anchors) {
            const txt = (a.innerText || a.getAttribute('aria-label') || '').toLowerCase().trim();
            if ((txt.includes('site web') || txt.includes('site internet') || txt === 'website')
                && a.href && !a.href.includes('google.') && !a.href.includes('maps.')) {
                d.site_web = a.href; break;
            }
        }
    }
    if (!d.site_web) {
        for (const a of anchors) {
            const aria = (a.getAttribute('aria-label') || '').toLowerCase();
            if (aria.includes('website') && a.href && !a.href.includes('google.') && !a.href.includes('maps.')) {
                d.site_web = a.href; break;
            }
        }
    }

    // ===== PHONE =====
    const telBtn = document.querySelector('button[data-item-id^="phone:tel:"]');
    if (telBtn) d.telephone = telBtn.getAttribute('data-item-id').replace('phone:tel:', '');
    else {
        const telLink = document.querySelector('a[href^="tel:"]');
        if (telLink) d.telephone = telLink.getAttribute('href').replace('tel:', '');
    }

    // ===== ADDRESS =====
    const addrEl = document.querySelector('button[data-item-id="address"]');
    if (addrEl) d.adresse = (addrEl.innerText || '').trim();

    // ===== RATING =====
    let ratingEl = document.querySelector('div.F7nice span span[aria-hidden="true"]');
    if (ratingEl) d.rating = parseFloat(ratingEl.innerText.replace(',', '.'));
    if (!d.rating) {
        const starAria = Array.from(document.querySelectorAll('[aria-label*="étoile"], [aria-label*="star"]'))
            .find(el => /[\d.,]+\s*(étoile|star)/.test(el.getAttribute('aria-label') || ''));
        if (starAria) {
            const m = starAria.getAttribute('aria-label').match(/([\d.,]+)/);
            if (m) d.rating = parseFloat(m[1].replace(',', '.'));
        }
    }

    // ===== REVIEW COUNT =====
    const bodyText = document.body.innerText;
    const ratingArea = document.querySelector('[aria-label*="étoile"], [aria-label*="star"], div.F7nice');
    if (ratingArea) {
        const areaText = ratingArea.innerText || ratingArea.getAttribute('aria-label') || '';
        const m = areaText.match(/(\d[\d\s]*)\s*avis/i);
        if (m) d.nb_avis = parseInt(m[1].replace(/\s/g, ''));
    }
    if (!d.nb_avis) {
        const avisMatch = bodyText.match(/(\d[\d\s]*)\s*avis/i);
        if (avisMatch) d.nb_avis = parseInt(avisMatch[1].replace(/\s/g, ''));
    }
    if (!d.nb_avis) {
        const parenMatch = bodyText.match(/\((\d[\d\s]*)\s*avis\)/i);
        if (parenMatch) d.nb_avis = parseInt(parenMatch[1].replace(/\s/g, ''));
    }

    // ===== CATEGORY =====
    const catEl = document.querySelector('button[jsaction="pane.rating.category"]');
    if (catEl) d.category = (catEl.innerText || '').trim();

    return d;
}'''

_JS_IS_CAPTCHA = "() => document.querySelector('#captcha-form') !== null || document.body.innerText.includes('unusual traffic')"


def _random_ua():
    """Retourne un User-Agent aléatoire."""
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    ]
    return random.choice(uas)


async def _reverify_lead(page, lead_id, lien_maps, nom):
    """
    Visite la fiche Google Maps et retourne les données mises à jour.
    Retourne un dict avec les champs à mettre à jour, ou None en cas d'erreur.
    """
    try:
        await page.goto(lien_maps, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(3000)

        # Vérifier CAPTCHA
        if await page.evaluate(_JS_IS_CAPTCHA):
            logger.warning(f"  ! CAPTCHA detecte pour #{lead_id} {nom} -- pause 60s")
            await asyncio.sleep(60)
            # Reessayer une fois
            await page.goto(lien_maps, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(3000)
            if await page.evaluate(_JS_IS_CAPTCHA):
                logger.error(f"  X CAPTCHA persistant pour #{lead_id} -- skip")
                return None

        details = await page.evaluate(_JS_EXTRACT_DETAILS)
        return details

    except Exception as e:
        logger.warning(f"  ! Erreur pour #{lead_id} {nom}: {type(e).__name__}: {e}")
        return None


async def main(limit=None, dry_run=False):
    """Point d'entrée principal."""
    from playwright.async_api import async_playwright

    # 1. Charger les leads Bénin sans site
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, nom, ville, secteur, lien_maps, telephone, site_web,
                   rating, nb_avis, adresse, category
            FROM leads_bruts
            WHERE pays = 'bj'
              AND (site_web IS NULL OR site_web = '')
              AND statut NOT IN ('archive', 'bounced', 'desabonne')
              AND lien_maps IS NOT NULL AND lien_maps != ''
            ORDER BY secteur, nom
        """).fetchall()

    leads = [dict(r) for r in rows]
    if limit:
        leads = leads[:limit]

    total = len(leads)
    if total == 0:
        logger.info("Aucun lead Bénin sans site avec lien_maps trouvé.")
        return

    logger.info(f"\n{'='*60}")
    logger.info(f"Revérification de {total} leads Bénin sans site")
    logger.info(f"{'='*60}\n")

    # Compteurs
    stats = {
        "total": total,
        "ok": 0,
        "site_trouve": 0,
        "ferme": 0,
        "erreur": 0,
        "captcha": 0,
        "maj_telephone": 0,
        "maj_rating": 0,
    }

    updates_log = []

    # 2. Lancer Playwright
    pw = await async_playwright().__aenter__()
    browser = await pw.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu', '--no-zygote',
              '--disable-blink-features=AutomationControlled']
    )

    try:
        ctx = await browser.new_context(
            locale="fr-BJ",
            viewport={"width": 1920, "height": 1080},
            user_agent=_random_ua(),
        )
        page = await ctx.new_page()

        for i, lead in enumerate(leads, 1):
            lid = lead["id"]
            nom = lead["nom"] or "(sans nom)"
            secteur = lead.get("secteur") or "unknown"
            lien = lead["lien_maps"]

            print(f"  [{i}/{total}] #{lid} [{secteur}] {nom[:45]:45s}", end="", flush=True)

            if not lien:
                print(" — pas de lien_maps, skip")
                continue

            details = await _reverify_lead(page, lid, lien, nom)

            if details is None:
                print(" — erreur")
                stats["erreur"] += 1
                continue

            # Construire les updates
            updates = {}
            changes = []

            # Site web
            new_site = details.get("site_web", "").strip()
            if new_site and new_site != lead.get("site_web", ""):
                updates["site_web"] = new_site
                changes.append(f"site={new_site[:40]}")

            # Téléphone
            new_tel = details.get("telephone", "").strip()
            if new_tel and new_tel != lead.get("telephone", ""):
                updates["telephone"] = new_tel
                changes.append(f"tel={new_tel}")
                stats["maj_telephone"] += 1

            # Rating
            new_rating = details.get("rating", 0)
            if new_rating and new_rating != lead.get("rating", 0):
                updates["rating"] = new_rating
                changes.append(f"note={new_rating}")
                stats["maj_rating"] += 1

            # Nombre d'avis
            new_avis = details.get("nb_avis", 0)
            if new_avis and new_avis != lead.get("nb_avis", 0):
                updates["nb_avis"] = new_avis
                changes.append(f"avis={new_avis}")

            # Adresse
            new_addr = details.get("adresse", "").strip()
            if new_addr and new_addr != lead.get("adresse", ""):
                updates["adresse"] = new_addr

            # Category
            new_cat = details.get("category", "").strip()
            if new_cat and new_cat != lead.get("category", ""):
                updates["category"] = new_cat

            # Date de revérification
            updates["date_scraping"] = time.strftime("%Y-%m-%d %H:%M:%S")

            # Appliquer les updates
            if updates and not dry_run:
                set_clause = ", ".join(f"{k}=?" for k in updates)
                with get_conn() as conn:
                    conn.execute(
                        f"UPDATE leads_bruts SET {set_clause} WHERE id=?",
                        list(updates.values()) + [lid]
                    )
                    conn.commit()

            if new_site:
                print(f" -> SITE TROUVE: {new_site[:50]}")
                stats["site_trouve"] += 1
            elif changes:
                print(f" -> mis a jour ({', '.join(changes[:3])})")
                stats["ok"] += 1
            else:
                print(f" -> inchange")
                stats["ok"] += 1

            updates_log.append({
                "id": lid, "nom": nom, "secteur": secteur,
                "updates": updates, "site_trouve": bool(new_site),
            })

            # Pause entre chaque lead
            delay = random.uniform(2.0, 4.0)
            await asyncio.sleep(delay)

            # Pause plus longue tous les 20 leads
            if i % 20 == 0:
                logger.info(f"  ⏸ Pause de 10s après {i} leads...")
                await asyncio.sleep(10)

    finally:
        await browser.close()
        pw.stop()

    # 3. Rapport
    logger.info(f"\n{'='*60}")
    logger.info(f"RAPPORT DE REVÉRIFICATION")
    logger.info(f"{'='*60}")
    logger.info(f"  Leads vérifiés :        {stats['total']}")
    logger.info(f"  Site web trouvé :        {stats['site_trouve']} (exclus de Profil A)")
    logger.info(f"  Données mises à jour :   {stats['ok']}")
    logger.info(f"  Téléphones mis à jour :  {stats['maj_telephone']}")
    logger.info(f"  Ratings mis à jour :     {stats['maj_rating']}")
    logger.info(f"  Erreurs :                {stats['erreur']}")
    logger.info(f"{'='*60}")

    # 4. Sauvegarder le rapport en JSON
    report_path = os.path.join(ROOT, "data", "reverify_benin_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "stats": stats,
            "updates": updates_log,
        }, f, ensure_ascii=False, indent=2)
    logger.info(f"\nRapport sauvegardé : {report_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Revérifier les leads Bénin sans site sur Google Maps")
    parser.add_argument("--limit", type=int, default=None, help="Nombre max de leads à traiter")
    parser.add_argument("--dry-run", action="store_true", help="Afficher sans modifier la DB")
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit, dry_run=args.dry_run))
