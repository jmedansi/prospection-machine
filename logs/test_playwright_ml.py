"""Test: trouver Mentions Legales via Playwright et cliquer"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from playwright.async_api import async_playwright
import json, re

ML_KEYWORDS = ["mentions l", "mentions l\u00e9gales", "mentions legales", "legal", "notice l", "notice leg"]

async def find_ml(url: str) -> dict:
    result = {"url_ml": None, "text": None, "error": None}
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
            print(f"  Navigation vers {url}...")
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(3000)

            # Fermer les bannieres cookies si presentes
            try:
                cookie_btns = await page.query_selector_all('button:has-text("Accepter"), button:has-text("Tout accepter"), button:has-text("OK"), button:has-text("Continuer"), [id*="accept"], [class*="accept"]')
                for btn in cookie_btns:
                    if await btn.is_visible():
                        await btn.click(force=True, timeout=3000)
                        await page.wait_for_timeout(1000)
                        break
            except:
                pass

            # Chercher tous les liens (texte et href normalises)
            links = await page.evaluate("""
                () => {
                    const items = [];
                    const seen = new Set();
                    document.querySelectorAll('a, [onclick*=\"mention\"], [onclick*=\"legal\"]').forEach(a => {
                        const txt = (a.textContent || '').trim().toLowerCase().replace(/\\s+/g, ' ');
                        const href = (a.getAttribute('href') || '').toLowerCase();
                        const key = txt.slice(0, 30) + '|' + href.slice(0, 50);
                        if (!seen.has(key)) {
                            seen.add(key);
                            items.push({text: txt.slice(0, 80), href: href.slice(0, 120)});
                        }
                    });
                    return items;
                }
            """)
            print(f"  {len(links)} liens trouves")

            # Filtrer ceux qui contiennent les mots-cles (version large)
            ml_links = []
            for link in links:
                txt = link["text"]
                href = link["href"]
                if any(k in txt or k in href for k in ML_KEYWORDS):
                    ml_links.append(link)
                    print(f"  CIBLE: text='{txt[:60]}' href='{href}'")

            if ml_links:
                link = ml_links[0]
                target_text = link["text"]
                target_href = link["href"]
                print(f"  Clic sur '{target_text[:50]}'...")

                # Essayer navigation directe si c'est une URL absolue, sinon clic
                if target_href.startswith('http'):
                    await page.goto(target_href, wait_until="domcontentloaded", timeout=15000)
                else:
                    try:
                        async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                            await page.click(f'a:has-text("{target_text}")', force=True)
                    except:
                        # Fallback: naviguer directement
                        from urllib.parse import urljoin
                        full = urljoin(url, target_href)
                        await page.goto(full, wait_until="domcontentloaded", timeout=15000)

                await page.wait_for_timeout(2000)
                result["url_ml"] = page.url

                # Extraire le texte visible
                text = await page.evaluate("""
                    () => {
                        const els = document.querySelectorAll('p, h1, h2, h3, h4, li, span, div');
                        let t = '';
                        const seen = new Set();
                        els.forEach(el => {
                            const txt = (el.textContent || '').trim().replace(/\\s+/g, ' ');
                            if (txt.length > 20 && !seen.has(txt.slice(0, 50))) {
                                seen.add(txt.slice(0, 50));
                                t += txt + '\\n';
                            }
                        });
                        return t.slice(0, 5000);
                    }
                """)
                result["text"] = text[:2000]
            else:
                result["error"] = "aucun lien ML trouve"
        except Exception as e:
            result["error"] = str(e)[:200]

        await browser.close()
    return result

async def main():
    tests = [
        "https://jeep.fr",
        "https://promoneuve.fr",
        "https://suzuki-bagneux.fr",
        "https://vauban-groupe.fr",
    ]
    for url in tests:
        print(f"\n{'='*60}")
        print(f"TEST: {url}")
        print(f"{'='*60}")
        r = await find_ml(url)
        if r["url_ml"]:
            print(f"  OK -> {r['url_ml']}")
            if r["text"]:
                print(f"  TEXTE (debut): {r['text'][:200]}")
        else:
            print(f"  ECHEC: {r['error']}")

if __name__ == "__main__":
    asyncio.run(main())
