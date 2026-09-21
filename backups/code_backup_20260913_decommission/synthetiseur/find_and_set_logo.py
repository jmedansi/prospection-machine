import sqlite3
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

DB = Path(__file__).parent.parent / 'data' / 'prospection.db'

try:
    import requests
    from bs4 import BeautifulSoup
except Exception as e:
    print('MISSING_LIBS', e)
    print('Please install: pip install requests beautifulsoup4')
    sys.exit(2)


def get_conn():
    return sqlite3.connect(DB)


def find_lead_with_logo():
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, nom, site_web, logo_url FROM leads_bruts WHERE logo_url IS NOT NULL AND logo_url != '' LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def find_lead_with_site():
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, nom, site_web, logo_url FROM leads_bruts WHERE site_web IS NOT NULL AND site_web != '' LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def scrape_logo_from_site(site_url: str):
    try:
        if not site_url.startswith('http'):
            site_url = 'http://' + site_url
        r = requests.get(site_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
        html = r.text
        soup = BeautifulSoup(html, 'html.parser')
        # og:image
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            return urljoin(r.url, og.get('content'))
        # apple-touch-icon or icon
        for rel in ['apple-touch-icon', 'icon', 'shortcut icon']:
            tag = soup.find('link', rel=lambda v: v and rel in v)
            if tag and tag.get('href'):
                return urljoin(r.url, tag.get('href'))
        # link rel=image_src
        tag = soup.find('link', rel='image_src')
        if tag and tag.get('href'):
            return urljoin(r.url, tag.get('href'))
        # meta itemprop
        m = soup.find('meta', itemprop='image')
        if m and m.get('content'):
            return urljoin(r.url, m.get('content'))
    except Exception as e:
        print('SCRAPE_ERROR', e)
    return None


def update_logo(lead_id: int, logo_url: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE leads_bruts SET logo_url = ? WHERE id = ?", (logo_url, lead_id))
    conn.commit()
    conn.close()


def main():
    lead = find_lead_with_logo()
    if lead:
        print('FOUND_EXISTING', lead['id'], lead['nom'], lead['logo_url'])
        return 0

    lead = find_lead_with_site()
    if not lead:
        print('NO_LEAD_WITH_SITE')
        return 1

    print('CHOSEN_LEAD', lead['id'], lead['nom'], lead.get('site_web'))
    logo = scrape_logo_from_site(lead.get('site_web') or '')
    if logo:
        print('SCRAPED_LOGO', logo)
        update_logo(lead['id'], logo)
        print('UPDATED_DB', lead['id'])
        return 0
    else:
        # fallback: try to derive from root /favicon.ico
        try:
            parsed = urlparse(lead.get('site_web'))
            base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else ('http://' + parsed.netloc)
            fav = urljoin(base, '/favicon.ico')
            # quick HEAD
            r = requests.head(fav, timeout=6)
            if r.status_code == 200:
                update_logo(lead['id'], fav)
                print('FALLBACK_FAV', fav)
                return 0
        except Exception:
            pass

    print('NO_LOGO_FOUND')
    return 2

if __name__ == '__main__':
    sys.exit(main())
