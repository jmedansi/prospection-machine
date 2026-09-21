# -*- coding: utf-8 -*-
from pathlib import Path
from playwright.sync_api import sync_playwright

page_dir = Path(r"D:\prospection-machine\ia_echanges\Restaurant Paris (auto)\PROMPT\5")
url = (page_dir / "index.html").as_uri()

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.goto(url, wait_until="load", timeout=60000)
    try:
        pg.wait_for_load_state("networkidle", timeout=25000)
    except Exception:
        pass
    pg.wait_for_timeout(3500)
    pg.screenshot(path=str(page_dir / "capture.png"))
    pg.screenshot(path=str(page_dir / "capture-full.png"), full_page=True)
    print("capture complet (page complete Chouchou)")
    b.close()