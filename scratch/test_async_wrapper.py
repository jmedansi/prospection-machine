import asyncio
import os
import sys
from typing import Dict, Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

def get_real_lcp_async_wrapper(url: str) -> Dict[str, float]:
    from core.browser import cdp_tab_headless_async
    
    async def _extract():
        metrics = {"lcp_ms": 15000, "fcp_ms": 15000}
        try:
            async with cdp_tab_headless_async() as page:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=3000)
                except:
                    pass
                
                js_script = """
                async () => {
                    return new Promise((resolve) => {
                        let fcp = 0;
                        let lcp = 0;
                        const paintEntries = performance.getEntriesByType('paint');
                        const fcpEntry = paintEntries.find(e => e.name === 'first-contentful-paint');
                        if (fcpEntry) fcp = fcpEntry.startTime;
                        try {
                            new PerformanceObserver((l) => {
                                const e = l.getEntries();
                                lcp = e[e.length - 1].renderTime || e[e.length - 1].loadTime;
                            }).observe({type: 'largest-contentful-paint', buffered: true});
                        } catch(e) {}
                        setTimeout(() => {
                            const t = performance.timing;
                            let load = t.domContentLoadedEventEnd - t.navigationStart;
                            if (load <= 0) load = performance.now();
                            resolve({
                                fcp_ms: fcp || load * 0.5,
                                lcp_ms: lcp || load * 1.5
                            });
                        }, 500);
                    });
                }
                """
                metrics = await page.evaluate(js_script)
        except Exception as e:
            print(f"Extraction error: {e}")
        return metrics

    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, _extract()).result()
    except RuntimeError:
        return asyncio.run(_extract())

if __name__ == "__main__":
    print(get_real_lcp_async_wrapper("https://trouver-avocats.fr"))
    print(get_real_lcp_async_wrapper("https://depann-assistance.com"))
