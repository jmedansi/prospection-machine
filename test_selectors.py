import asyncio
async def test():
    from core.browser import cdp_tab_async
    async with cdp_tab_async(viewport={'width': 1920, 'height': 1080}) as page:
        await page.goto('https://www.google.com/maps/search/agence+immobili%C3%A8re+Paris', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(4000)

        # Scroll feed
        for _ in range(8):
            js = '() => { const f = document.querySelector("div[role=\\"feed\\"]"); if(f) f.scrollBy(0, 3000); }'
            await page.evaluate(js)
            await page.wait_for_timeout(1000)

        # Click first result
        items = await page.evaluate('() => { const r=[]; const items=document.querySelectorAll("div[role=\\"article\\"]"); items.forEach((el,i)=>{ const a=el.querySelector("a.hfpxzc"); if(a && i<3) r.push(a.href); }); return r; }')
        print(f'Found {len(items)} items')

        for href in items:
            print(f'\n--- Clicking: {href}')
            link_sel = f'a[href="{href}"]'
            try:
                await page.click(link_sel)
            except:
                await page.goto(href, wait_until='domcontentloaded', timeout=20000)
            await page.wait_for_timeout(2000)

            # Test site web
            site_js = '() => { const el = document.querySelector("a[data-item-id=\\"authority\\"]"); return el ? el.href : "NO SITE"; }'
            site = await page.evaluate(site_js)
            print(f'Site: {site}')

            # All links on page
            links_js = '() => { return Array.from(document.querySelectorAll("a")).filter(a => a.href).slice(0,10).map(a => ({text: a.innerText.slice(0,40), href: a.href.slice(0,80)})); }'
            links = await page.evaluate(links_js)
            for l in links:
                print(f'  LINK: {l}')

asyncio.run(test())
