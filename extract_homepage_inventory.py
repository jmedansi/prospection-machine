import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.request import Request, urlopen

SITES = {
    "clinique-esthetique-com": "https://www.cliniqueesthetique.com",
    "medecine-esthetique-lyon-com": "https://medecine-esthetique-lyon.com",
    "cabinetjeanpierregobin-fr": "https://cabinetjeanpierregobin.fr",
    "dr-malglaive-com": "https://dr-malglaive.com",
    "drpaoli-fr": "https://drpaoli.fr",
}


def clean_text(s):
    s = re.sub(r"\s+", " ", s or "")
    return s.strip()


class HomepageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta_desc = ""
        self.text_blocks = []
        self.links = []
        self.images = []
        self.button_text = []
        self.in_title = False
        self.in_meta = False
        self.current_link = None
        self.current_button = None
        self.current_tag = None
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        self.current_tag = tag

        if tag == 'title':
            self.in_title = True

        if tag == 'meta':
            name = (attrs.get('name') or attrs.get('property') or '').lower()
            content = attrs.get('content', '')
            if name in {'description', 'og:description'} and content:
                self.meta_desc = clean_text(content)

        if tag == 'a':
            href = attrs.get('href')
            self.current_link = {'text': '', 'href': href or ''}

        if tag == 'button':
            self.current_button = {'text': '', 'href': attrs.get('formaction') or attrs.get('onclick') or ''}

        if tag == 'img':
            src = attrs.get('src') or attrs.get('data-src') or attrs.get('data-lazy-src')
            if src:
                self.images.append(src)

        if tag == 'source':
            src = attrs.get('srcset') or attrs.get('src')
            if src:
                self.images.append(src.split()[0] if src else src)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == 'title':
            self.in_title = False
        if tag == 'a' and self.current_link is not None:
            text = clean_text(self.current_link['text'])
            href = self.current_link['href']
            if text or href:
                self.links.append({'text': text, 'href': href})
            self.current_link = None
        if tag == 'button' and self.current_button is not None:
            text = clean_text(self.current_button['text'])
            if text:
                self.button_text.append(text)
            self.current_button = None
        self.current_tag = None

    def handle_data(self, data):
        text = clean_text(data)
        if not text:
            return
        if self.in_title:
            self.title = (self.title + ' ' + text).strip()
            return

        if self.current_link is not None:
            self.current_link['text'] += ' ' + text
            return
        if self.current_button is not None:
            self.current_button['text'] += ' ' + text
            return

        if self.current_tag in {'h1','h2','h3','h4','p','li','span','a','button','strong','b','em','div'}:
            self.text_blocks.append(text)


def fetch(url):
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=25) as resp:
        body = resp.read().decode('utf-8', errors='replace')
    return body


def main():
    for slug, url in SITES.items():
        html = fetch(url)
        parser = HomepageParser()
        parser.feed(html)

        texts = []
        seen = set()
        for t in parser.text_blocks:
            if t not in seen:
                seen.add(t)
                texts.append(t)

        images = []
        seen_img = set()
        for img in parser.images:
            candidate = img.strip()
            if not candidate:
                continue
            candidate = candidate.split(' ')[0]
            if candidate.startswith('//'):
                candidate = 'https:' + candidate
            elif candidate.startswith('/'):
                candidate = urljoin(url, candidate)
            if candidate not in seen_img:
                seen_img.add(candidate)
                images.append(candidate)

        payload = {
            'lead_slug': slug,
            'source_url': url,
            'title': clean_text(parser.title),
            'meta_description': parser.meta_desc,
            'headline': texts[0] if texts else '',
            'all_visible_text': ' '.join(texts),
            'text_blocks': texts,
            'links': [
                {'text': clean_text(x['text']), 'href': x['href']} for x in parser.links if x.get('href') or x.get('text')
            ],
            'buttons': [clean_text(x) for x in parser.button_text if clean_text(x)],
            'images': images,
            'image_count': len(images),
        }

        out_path = f"D:/prospection-machine/output/clients/{slug}/asset-pack/content.json"
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"WROTE {out_path}")


if __name__ == '__main__':
    main()
