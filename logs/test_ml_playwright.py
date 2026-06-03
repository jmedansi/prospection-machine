"""Test complet: Ads extraction → injection → ML enrichment (Playwright) sur 5 centres de formation"""
import asyncio, sys, os, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.INFO, format="%(message)s")

from database.leads import insert_lead
from database.connection import get_conn
from enrichisseur.mentions_legales_enricher import _format_notes, update_db
from playwright.async_api import async_playwright

ML_KEYWORDS = ["mentions l", "mentions legales", "legal notice"]

async def trouver_ml_playwright(base_url: str) -> dict:
    """Playwright: charge homepage, trouve lien ML, clique, retourne texte."""
    result = {"url": None, "text": None, "error": None}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--ignore-certificate-errors"]
        )
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            ignore_https_errors=True
        )
        page = await ctx.new_page()

        try:
            await page.goto(base_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(3000)

            # Cookie banner
            try:
                for sel in ['button:has-text("Accepter")', 'button:has-text("Tout accepter")', '[id*="accept"]', '[class*="accept"] button']:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click(force=True, timeout=3000)
                        await page.wait_for_timeout(1000)
                        break
            except: pass

            # Chercher le lien ML
            found = None
            links = await page.evaluate("""
                () => {
                    const items = [];
                    document.querySelectorAll('a').forEach(a => {
                        const txt = (a.textContent || '').trim().toLowerCase().replace(/\\s+/g, ' ');
                        const href = (a.getAttribute('href') || '').toLowerCase();
                        items.push({text: txt.slice(0, 100), href: href.slice(0, 150)});
                    });
                    return items;
                }
            """)
            for link in links:
                txt, href = link["text"], link["href"]
                if any(k in txt or k in href for k in ML_KEYWORDS):
                    found = link
                    break

            if not found:
                result["error"] = "aucun lien ML"
            else:
                target = found["href"]
                if target.startswith("http"):
                    await page.goto(target, wait_until="domcontentloaded", timeout=15000)
                else:
                    from urllib.parse import urljoin
                    await page.goto(urljoin(base_url, target), wait_until="domcontentloaded", timeout=15000)

                await page.wait_for_timeout(2000)
                result["url"] = page.url

                text = await page.evaluate("""
                    () => {
                        const tags = ['p','h1','h2','h3','h4','h5','h6','li','span','div','section','article'];
                        let t = '';
                        const seen = new Set();
                        for (const tag of tags) {
                            document.querySelectorAll(tag).forEach(el => {
                                const txt = (el.textContent || '').trim().replace(/\\s+/g, ' ');
                                if (txt.length > 30 && !seen.has(txt.slice(0,50))) {
                                    seen.add(txt.slice(0,50));
                                    t += txt + '\\n';
                                }
                            });
                        }
                        return t;
                    }
                """)
                result["text"] = text
        except Exception as e:
            result["error"] = str(e)[:200]

        await browser.close()
    return result


def enrichir_lead_playwright(site_web: str) -> dict:
    """Version enrichir_lead qui utilise Playwright pour trouver les ML."""
    from enrichisseur.mentions_legales_enricher import _normalize_url, _clean_legal_text, _parse_legal_text

    result = {"dirigeant_prenom": None, "dirigeant_nom": None, "emails": [], "telephones": [], "url_trouvee": None}
    base_url = _normalize_url(site_web)
    if not base_url:
        return result

    print(f"    Playwright: scan de {base_url}...")
    ml = asyncio.run(trouver_ml_playwright(base_url))
    if ml["text"]:
        result["url_trouvee"] = ml["url"]
        text = _clean_legal_text(ml["text"])
        _parse_legal_text(result, text)
    else:
        print(f"    Fallback requests: {ml['error']}")
        # Fallback silenceux vers requests
        from enrichisseur.mentions_legales_enricher import enrichir_lead
        result = enrichir_lead(0, site_web, "")
    return result


def main():
    leads_ads = [
        {"nom": "ITIC Paris", "site_web": "https://iticparis.com"},
        {"nom": "Crisis BRG", "site_web": "https://crisisbrg.com"},
        {"nom": "NEOMA BS", "site_web": "https://neoma-bs.fr"},
        {"nom": "Coaching Ways", "site_web": "https://coachingways.fr"},
        {"nom": "IESEG", "site_web": "https://ieseg.fr"},
    ]

    print("=== Injection + ML Playwright sur 5 centres de formation ===\n")
    for lead in leads_ads:
        # 1. Injection
        lid = insert_lead({
            "nom": lead["nom"], "site_web": lead["site_web"],
            "telephone": "", "ville": "Paris",
            "mot_cle": "centre de formation Paris",
            "source": "ads", "secteur": "ecoles_formation", "rating": 0,
        })
        if not lid:
            print(f"  #{lid} {lead['nom']} -> duplicata, skip")
            continue

        print(f"\n  #{lid} {lead['nom']} ({lead['site_web']})")

        # 2. ML enrichment avec Playwright
        result = enrichir_lead_playwright(lead["site_web"])
        notes = _format_notes(result)

        if notes:
            update_db(lid, notes, result)
        else:
            update_db(lid, "mentions_introuvables", result)

        p = result.get('dirigeant_prenom') or '-'
        n = result.get('dirigeant_nom') or '-'
        url_t = result.get('url_trouvee') or '-'
        e = ', '.join(result.get('emails', [])[:2]) or '-'
        print(f"    url_ml={url_t}")
        print(f"    dirigeant={p} {n} | emails={e}")

    # Bilan
    print("\n=== BILAN ===")
    from database.connection import get_conn
    with get_conn() as conn:
        rows = conn.execute('''
            SELECT id, nom, notes FROM leads_bruts
            WHERE source='ads' AND secteur='ecoles_formation'
            ORDER BY id DESC LIMIT 5
        ''').fetchall()
        for r in rows:
            print(f"  #{r['id']} {r['nom'][:30]:30s} | {(r['notes'] or '(vide)')[:100]}")

if __name__ == "__main__":
    main()
