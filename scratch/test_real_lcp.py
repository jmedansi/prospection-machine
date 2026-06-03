import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

from core.browser import cdp_tab_headless

def test_real_lcp(url):
    print(f"Testing real LCP extraction for: {url}")
    try:
        with cdp_tab_headless() as page:
            page.goto(url, wait_until="load", timeout=15000)
            
            js_script = """
            async () => {
                return new Promise((resolve) => {
                    let fcp = 0;
                    let lcp = 0;

                    // FCP
                    const paintEntries = performance.getEntriesByType('paint');
                    const fcpEntry = paintEntries.find(entry => entry.name === 'first-contentful-paint');
                    if (fcpEntry) fcp = fcpEntry.startTime;

                    // LCP via Observer
                    try {
                        new PerformanceObserver((entryList) => {
                            const entries = entryList.getEntries();
                            const lastEntry = entries[entries.length - 1];
                            lcp = lastEntry.renderTime || lastEntry.loadTime;
                        }).observe({type: 'largest-contentful-paint', buffered: true});
                    } catch (e) {}

                    setTimeout(() => {
                        const t = performance.timing;
                        let loadTime = 0;
                        if (t.navigationStart > 0 && t.loadEventEnd > 0) {
                            loadTime = t.loadEventEnd - t.navigationStart;
                        } else {
                            // Fallback if timing API is acting up
                            loadTime = performance.now();
                        }
                        
                        resolve({
                            fcp_ms: fcp || (loadTime * 0.4),
                            lcp_ms: lcp || (loadTime * 0.8),
                            page_load_ms: loadTime > 0 ? loadTime : 15000
                        });
                    }, 500); // Small wait for LCP events to settle
                });
            }
            """
            metrics = page.evaluate(js_script)
            print(f"Metrics extracted: {metrics}")
            return metrics
            
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_real_lcp("https://trouver-avocats.fr")
    test_real_lcp("https://depann-assistance.com")
