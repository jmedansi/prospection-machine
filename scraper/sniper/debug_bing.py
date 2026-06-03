import asyncio, logging, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
        ])
        context = await browser.new_context(
            locale="fr-FR",
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        
        url = "https://www.bing.com/search?q=chirurgie+esth%C3%A9tique+Paris&mkt=fr-FR"
        logger.info(f"Navigation vers {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(5000)
        
        title = await page.title()
        logger.info(f"Title: {title}")
        
        # Check for ad elements
        has_b_ad = await page.evaluate("() => document.querySelectorAll('.b_ad').length")
        has_b_adSlug = await page.evaluate("() => document.querySelectorAll('.b_adSlug').length")
        has_li_b_ad = await page.evaluate("() => document.querySelectorAll('li.b_ad').length")
        all_links = await page.evaluate("() => document.querySelectorAll('a[href]').length")
        logger.info(f".b_ad: {has_b_ad}, .b_adSlug: {has_b_adSlug}, li.b_ad: {has_li_b_ad}, total links: {all_links}")
        
        # Check all link targets for ads
        urls = await page.evaluate("""
            () => {
                const r = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    if (a.href) r.push({text: a.textContent.trim().slice(0,40), href: a.href.slice(0,100)});
                });
                return r;
            }
        """) or []
        for u in urls[:30]:
            logger.info(f"  link: [{u['text']}] -> {u['href']}")
        
        # Check body text for ad indicators
        body_text = (await page.evaluate("() => document.body.innerText"))[:3000]
        if "annonce" in body_text.lower() or "sponsored" in body_text.lower() or "ad" in body_text.lower():
            logger.info("✓ Contient 'annonce'/'sponsored'/'ad'")
        
        await page.screenshot(path="bing_debug.png")
        logger.info("Screenshot saved to bing_debug.png")
        
        await browser.close()

asyncio.run(main())
