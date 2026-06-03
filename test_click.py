import asyncio
async def test():
    from core.browser import cdp_tab_async, close_async_browsers
    await close_async_browsers()
    
    async with cdp_tab_async(viewport={'width': 1920, 'height': 1080}) as page:
        await page.goto('https://www.google.com/maps/search/agence+immobili%C3%A8re+Paris', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)

        # Scroll feed
        for _ in range(5):
            js = '() => { const f = document.querySelector("div[role=\\"feed\\"]"); if(f) f.scrollBy(0, 2000); }'
            await page.evaluate(js)
            await page.wait_for_timeout(800)

        # Get first result link
        href = await page.evaluate('() => { const a = document.querySelector("div[role=\\"article\\"] a.hfpxzc"); return a ? a.href : null; }')
        print(f'First result: {href}')
        
        if not href:
            # Try alternative selector
            href = await page.evaluate('() => { const a = document.querySelector("a.hfpxzc"); return a ? a.href : null; }')
            print(f'Alt first: {href}')

        if href:
            # Click the result
            print('Clicking...')
            await page.click(f'a[href="{href}"]')
            await page.wait_for_timeout(3000)
            
            # Dump ALL links outside the feed
            js = '''
            () => {
                const feed = document.querySelector('div[role="feed"]');
                const links = document.querySelectorAll('a[href]');
                const results = [];
                for (const a of links) {
                    if (feed && feed.contains(a)) continue;
                    if (!a.href || a.href.startsWith('javascript:') || a.href.startsWith('#')) continue;
                    results.push({
                        text: (a.innerText || a.getAttribute('aria-label') || '').slice(0, 80),
                        href: a.href.slice(0, 120),
                        cls: (a.className || '').slice(0, 40),
                        data_id: a.getAttribute('data-item-id') || '',
                    });
                }
                return results.slice(0, 15);
            }
            '''
            links = await page.evaluate(js)
            print(f'\nLinks outside feed ({len(links)}):')
            for l in links:
                print(f'  {l}')
            
            # Also check what role=main looks like
            main = await page.evaluate('() => { const m = document.querySelector("[role=\\"main\\"]"); return m ? m.innerHTML.slice(0, 500) : "NO MAIN"; }')
            print(f'\nMain panel (first 500 chars):')
            print(main[:500])

asyncio.run(test())
