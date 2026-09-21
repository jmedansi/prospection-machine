# render.py  —  usage: python3 render.py <url> <asset-pack-dir>
import sys, json
from pathlib import Path
from playwright.sync_api import sync_playwright

url, outdir = sys.argv[1], Path(sys.argv[2])
(outdir/"raw").mkdir(parents=True, exist_ok=True)
(outdir/"screenshots").mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

JS_IMAGES = r"""
() => {
  const out=[]; const seen=new Set();
  const push=(src,w,h,kind)=>{ if(!src||src.startsWith('data:'))return; if(seen.has(src))return; seen.add(src); out.push({src,w:w||0,h:h||0,kind}); };
  document.querySelectorAll('img').forEach(i=>push(i.currentSrc||i.src,i.naturalWidth,i.naturalHeight,'img'));
  document.querySelectorAll('*').forEach(el=>{ const bg=getComputedStyle(el).backgroundImage;
    if(bg&&bg.includes('url(')){ const m=bg.match(/url\(["']?(.*?)["']?\)/); if(m){ try{push(new URL(m[1],location.href).href,el.clientWidth,el.clientHeight,'bg');}catch(e){} } } });
  return out;
}"""
JS_STYLES = r"""
() => { const grab=s=>{const el=document.querySelector(s); if(!el)return null; const c=getComputedStyle(el);
    return {color:c.color,background:c.backgroundColor,font:c.fontFamily,size:c.fontSize,weight:c.fontWeight};};
  const btns=[...document.querySelectorAll('button,.btn,a.button,[class*=cta],[class*=btn]')].slice(0,6)
    .map(el=>{const c=getComputedStyle(el);return{color:c.color,background:c.backgroundColor};});
  return {body:grab('body'),header:grab('header'),nav:grab('nav'),h1:grab('h1'),h2:grab('h2'),
    link:grab('a'),button:grab('button,.btn,a.button'),buttons:btns}; }"""

meta={"source_url":url,"render_method":None,"final_url":None,"http_status":None}
images=[]
with sync_playwright() as p:
    browser=None
    for launch in (lambda:p.chromium.launch(headless=True),
                   lambda:p.chromium.launch(headless=True, channel="chrome")):
        try: browser=launch(); break
        except Exception as e: print("launch fail:",e)
    if not browser: raise SystemExit("PLAYWRIGHT_UNAVAILABLE")
    page=browser.new_page(viewport={"width":1440,"height":900}, user_agent=UA)
    try:
        resp=page.goto(url, wait_until="domcontentloaded", timeout=60000)
        meta["final_url"]=page.url; meta["http_status"]=resp.status if resp else None
        # best-effort: laisser le réseau se calmer sans bloquer si le site poll en continu
        try: page.wait_for_load_state("networkidle", timeout=12000)
        except Exception: pass
        page.evaluate("async()=>{await new Promise(r=>{let y=0;const t=setInterval(()=>{window.scrollBy(0,700);y+=700;if(y>=document.body.scrollHeight){clearInterval(t);r();}},120);});}")
        page.wait_for_timeout(1500)
        (outdir/"raw"/"rendered.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(outdir/"screenshots"/"above-fold.png"))
        page.screenshot(path=str(outdir/"screenshots"/"full-page.png"), full_page=True)
        (outdir/"raw"/"computed-styles.json").write_text(json.dumps(page.evaluate(JS_STYLES),indent=2), encoding="utf-8")
        images=page.evaluate(JS_IMAGES)
        (outdir/"raw"/"dom-images.json").write_text(json.dumps(images,indent=2), encoding="utf-8")
        meta["render_method"]="playwright-chromium"
    except Exception as e:
        meta["render_method"]="failed"; meta["error"]=str(e)
    browser.close()
(outdir/"raw"/"_render-meta.json").write_text(json.dumps(meta,indent=2), encoding="utf-8")
print("RENDER", meta["render_method"], meta.get("http_status"), "images:", len(images))
