# analyze.py  —  usage: python3 analyze.py <asset-pack-dir>
import sys, json, re, io
from pathlib import Path
from collections import Counter
import numpy as np, requests
from PIL import Image, ImageFilter
from bs4 import BeautifulSoup

outdir=Path(sys.argv[1]); raw=outdir/"raw"
for d in ("images","images-rejected","images/brand"): (outdir/d).mkdir(parents=True, exist_ok=True)
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
hexify=lambda rgb:"#%02X%02X%02X"%tuple(int(x) for x in rgb)

# ---- COULEURS ----
def parse_color(s):
    if not s: return None
    m=re.match(r'rgba?\(([^)]+)\)', s.strip())
    if not m: return None
    parts=[p.strip() for p in m.group(1).split(',')]
    try:
        r,g,b=int(float(parts[0])),int(float(parts[1])),int(float(parts[2]))
        if len(parts)>3 and float(parts[3])<0.1: return None
        return (r,g,b)
    except: return None
sat=lambda rgb:0 if max(rgb)==0 else (max(rgb)-min(rgb))/max(rgb)
neutral=lambda rgb:sat(rgb)<0.12

styles=json.loads((raw/"computed-styles.json").read_text()) if (raw/"computed-styles.json").exists() else {}
declared=Counter()
def add(c,w):
    rgb=parse_color(c)
    if rgb: declared[rgb]+=w
for key,w in [("button",4),("h1",2),("header",2),("nav",2),("link",2),("h2",1),("body",1)]:
    nd=styles.get(key)
    if nd: add(nd.get("background"),w); add(nd.get("color"),1)
for b in styles.get("buttons",[]) or []: add(b.get("background"),4)

def quantize(path,n=8):
    try: im=Image.open(path).convert("RGB")
    except: return []
    im.thumbnail((240,240))
    q=im.quantize(colors=n, method=Image.MEDIANCUT).convert("RGB")
    arr=np.array(q).reshape(-1,3); cnt=Counter(map(tuple,arr)); tot=sum(cnt.values())
    return [(tuple(int(x) for x in rgb), c/tot) for rgb,c in cnt.most_common(n)]
perceived=quantize(outdir/"screenshots"/"full-page.png")

sat_decl=[rgb for rgb,_ in declared.most_common() if not neutral(rgb)]
primary = sat_decl[0] if sat_decl else next((rgb for rgb,_ in perceived if not neutral(rgb)),(37,99,235))
secondary = sat_decl[1] if len(sat_decl)>1 else None
neutrals=[rgb for rgb,_ in perceived if neutral(rgb)]
light=max(neutrals,key=sum) if neutrals else (244,244,244)
dark=min(neutrals,key=sum) if neutrals else (26,26,26)
confidence="high" if (sat_decl and perceived) else ("medium" if (sat_decl or perceived) else "low")
dominant=[{"hex":hexify(rgb),"rgb":list(rgb),"source":"css_declared","saturation":round(sat(rgb),2)} for rgb,_ in declared.most_common(6)]
dominant+=[{"hex":hexify(rgb),"rgb":list(rgb),"source":"screenshot_quant","share":round(s,3)} for rgb,s in perceived[:6]]
colors={"palette_for_design":{"primary":hexify(primary),"secondary":hexify(secondary) if secondary else None,
        "neutral_light":hexify(light),"neutral_dark":hexify(dark)},
        "dominant":dominant,"confidence":confidence,
        "note":"palette_for_design est imposee a /refonte-design ; garder ces hex comme ancrage."}
(outdir/"colors.json").write_text(json.dumps(colors,indent=2,ensure_ascii=False),encoding="utf-8")

# ---- IMAGES ----
AI=re.compile(r'(ai[-_]?gen|generated|midjourney|dall[-_]?e|stable[-_]?diffusion|sdxl|firefly|leonardo|gen[-_]?\d)',re.I)
UI=re.compile(r'(logo|icon|sprite|favicon|spacer|pixel|placeholder|loader|avatar|badge)',re.I)
PRACT=re.compile(r'(Dr[-_. ]|drossard|julienne|garreau|praticien|chirurg|docteur|medecin|cabinet)',re.I)
def lap_var(im):
    try:
        import cv2
        return float(cv2.Laplacian(cv2.cvtColor(np.array(im.convert("RGB")),cv2.COLOR_RGB2GRAY),cv2.CV_64F).var())
    except Exception:
        return float(np.array(im.convert("L").filter(ImageFilter.FIND_EDGES)).var())
def ai_score(im,url,fmt,has_exif):
    s=0.0; sig=[]
    if AI.search(url): s+=0.4; sig.append("filename_ai")
    w,h=im.size
    if w==h and w in (512,768,1024,1536): s+=0.2; sig.append(f"square_{w}")
    if fmt=="PNG" and w*h>400000: s+=0.15; sig.append("png_photo")
    if not has_exif: s+=0.15; sig.append("no_exif")
    try:
        g=np.array(im.convert("L").resize((128,128))).astype(int)
        hf=np.abs(np.diff(g,axis=0)).mean()+np.abs(np.diff(g,axis=1)).mean()
        if hf<6: s+=0.2; sig.append("oversmooth")
    except: pass
    return round(min(s,1.0),2),sig

dom=json.loads((raw/"dom-images.json").read_text()) if (raw/"dom-images.json").exists() else []
items=[]; kept=rej=0
for i,e in enumerate(dom,1):
    src=e.get("src"); it={"id":f"img-{i:03d}","src":src,"kind":e.get("kind")}
    try:
        data=requests.get(src,headers=UA,timeout=20).content[:20_000_000]
        if (src or "").lower().endswith(".svg") or data.lstrip().startswith((b"<svg",b"<?xml")):
            (outdir/"images/brand"/f'{it["id"]}.svg').write_bytes(data)
            it.update(status="kept",role_guess="brand",saved_as=f'images/brand/{it["id"]}.svg')
            items.append(it); kept+=1
            continue
        im=Image.open(io.BytesIO(data)); im.load()
    except Exception as ex:
        it.update(status="rejected",reject_reason=f"download_fail:{ex.__class__.__name__}"); items.append(it); rej+=1; continue
    w,h=im.size; fmt=im.format or ""; nb=len(data); ratio=round(w/h,2) if h else 0
    has_exif=bool(getattr(im,"getexif",lambda:{})())
    checks={"w":w,"h":h,"bytes":nb,"format":fmt,"ratio":ratio}
    reject=None
    if max(w,h)<300 or w*h<40000: reject="low_resolution"
    elif nb<3000 and fmt!="SVG": reject="too_small_bytes"
    elif ratio>4 or ratio<0.25: reject="aspect_ratio"
    is_pract=PRACT.search(src or "")
    is_ui=UI.search(src or "")
    if not reject:
        lv=lap_var(im); checks["blur_laplacian_var"]=round(lv,1)
        if lv<15 and not is_pract: reject="blurry"
    ai,sig=ai_score(im,src or "",fmt,has_exif); checks.update(ai_suspicion_score=ai,ai_signals=sig)
    if not reject and not is_pract and not is_ui and ai>=0.7: reject="ai_suspected"
    it["checks"]=checks
    ext={"JPEG":"jpg","PNG":"png","WEBP":"webp","GIF":"gif"}.get(fmt,"jpg")
    if reject:
        it.update(status="rejected",reject_reason=reject)
        try: im.convert("RGB").save(outdir/"images-rejected"/f'{it["id"]}.{ext}')
        except: pass
        rej+=1
    elif is_ui:
        it.update(status="kept",role_guess="brand",ai_uncertain=False,saved_as=f'images/brand/{it["id"]}.{ext}')
        try: im.save(outdir/"images/brand"/f'{it["id"]}.{ext}')
        except: im.convert("RGB").save(outdir/"images/brand"/f'{it["id"]}.jpg')
        kept+=1
    else:
        role="hero" if (kept==0 and max(w,h)>=1200) else "gallery"
        if is_pract: role="practitioner"
        it.update(status="kept",role_guess=role,ai_uncertain=ai>=0.3,saved_as=f'images/{it["id"]}.{ext}')
        try: im.save(outdir/"images"/f'{it["id"]}.{ext}')
        except: im.convert("RGB").save(outdir/"images"/f'{it["id"]}.jpg'); it["saved_as"]=f'images/{it["id"]}.jpg'
        kept+=1
    items.append(it)
manifest={"scanned":len(items),"kept":kept,"rejected":rej,"items":items}
(outdir/"images-manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8")

# ---- CONTENU ----
import html as _html
def el_text(el, limit=800):
    if el is None: return ""
    txt=re.sub(r'<[^>]+>',' ',str(el))
    return _html.unescape(re.sub(r'\s+',' ',txt)).strip()[:limit]
html=(raw/"rendered.html").read_text(encoding="utf-8",errors="ignore") if (raw/"rendered.html").exists() else ""
soup=BeautifulSoup(html,"lxml") if html else None
c={"name":None,"headline":None,"subheadline":None,"services":[],"about":None,"story":None,"credo":None,"french_touch":None,
   "rating":None,"practitioners":[],"poles":[],"testimonials":[],"services_detail":{},
   "contact":{"phone":None,"email":None,"address":None},"hours":None,
   "cta_found":[],"missing_fields":[]}
md=[]
if soup:
    title=soup.title.string.strip() if soup.title and soup.title.string else None
    h1=soup.find("h1"); c["headline"]=h1.get_text(" ",strip=True) if h1 else title
    desc=soup.find("meta",attrs={"name":"description"})
    c["subheadline"]=desc["content"].strip() if desc and desc.get("content") else None
    # ld+json
    for s in soup.find_all("script",attrs={"type":"application/ld+json"}):
        try: data=json.loads(s.string or "{}")
        except: continue
        for nd in (data if isinstance(data,list) else [data]):
            if isinstance(nd,dict) and "LocalBusiness" in str(nd.get("@type","")):
                c["contact"]["phone"]=c["contact"]["phone"] or nd.get("telephone")
                c["name"]=nd.get("name") or c["name"]
                a=nd.get("address")
                if isinstance(a,dict):
                    c["contact"]["address"]=", ".join(filter(None,[a.get("streetAddress"),a.get("postalCode"),a.get("addressLocality")]))
    # body text nettoyé
    for tag in soup.find_all(["script","style","noscript"]): tag.decompose()
    body_text=soup.get_text(" ",strip=True) if soup else ""
    if not c["contact"]["phone"]:
        m=re.search(r'(?:\+33|0)\s?[1-9](?:[\s.\-]?\d{2}){4}',body_text); c["contact"]["phone"]=m.group(0) if m else None
    em=re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+',body_text); c["contact"]["email"]=em.group(0) if em else None
    if not c["name"]:
        nm2=re.search(r'(CLINIQUE(?:\s+[A-ZÉÈÀ][A-ZÉÈÀ\'\-]*)+)(?![a-zà-ÿ])',body_text)
        if nm2: c["name"]=nm2.group(1).strip().title()
    else:
        c["name"]=str(c["name"]).strip()
    if not c["contact"]["address"]:
        ad=re.search(r'(\d{1,4}\s+(?:[Bb]d\.?|boulevard|avenue|av\.|rue|place|chemin|cours|allee|allée|impasse|quai)\s+[\w\'\-À-ÿ]+[^,]{0,40}(?:,\s*\d{5}\s+[A-Za-zÀ-ÿ\- ]+)?)',body_text)
        if ad: c["contact"]["address"]=ad.group(1).strip()
    # horaires (anticipe l'éventuel bloc suivant « Centre »)
    chunk=body_text.split(" Centre ",1)[0] if " Centre " in body_text else body_text
    hr=re.search(r'((?:Lundi|Mardi|Mercredi|Jeudi|Vendredi|Samedi|Dimanche)[^.]{0,220}(?:\d{1,2}\s*h\s?\d{0,2})(?:\s*(?:à|au)\s*\d{1,2}\s*h\s?\d{0,2})?)',chunk,re.I)
    if hr: c["hours"]=hr.group(1).strip()
    # story / embleme / credo / french touch
    sv=re.search(r"(Le saviez-vous\s*\?\s*[^\.]+(?:\.[^\.]+){1,4}\. Cette allégorie[^\.]+\.)",body_text,re.I)
    if not sv: sv=re.search(r"(Le saviez-vous\s*\?\s*[^\.]+(?:\.[^\.]+){1,6}\.)",body_text,re.I)
    if sv: c["story"]=sv.group(1).strip()
    cr=re.search(r'(?:Notre credo|Credo)\s*([A-Z][^\.]{10,220}\.)',body_text,re.I)
    if not cr: cr=re.search(r"(Utiliser des methodes[^\.]{10,200}\.)",body_text,re.I)
    if cr: c["credo"]=cr.group(1).strip()
    ft=re.search(r'(Nous sommes toujours[^\.]{10,220}\.)',body_text,re.I)
    if ft: c["french_touch"]=ft.group(1).strip()
    # about : 1er paragraphe long parlant de la boîte
    if not c["about"]:
        for _p in soup.find_all("p"):
            pt=el_text(_p,400)
            if len(pt)>80 and re.search(r'\b(clinique|cabinet|centre|établissement|docteur|chirurg)\b',pt,re.I):
                c["about"]=pt; break
    # poles
    for m in re.finditer(r'(\d\s*[Pp][oô]les?\s+d[\'\u2019]interventions\s+en\s+esth[ée]tique)',body_text,re.I):
        c["poles"].append(m.group(1).strip())
    c["poles_intro"]=None
    pin=re.search(r'(La chirurgie esthétique plastique[^.]*(?:\.[^.]*){1,4}\.)',body_text,re.I)
    if pin: c["poles_intro"]=pin.group(1).strip()
    # rating Google (Trustindex — texte dans <template>, lire le HTML brut)
    rating_el=soup.select_one(".ti-rating-large")
    ra=re.search(r'Bas[ée]e?[^0-9<>]{0,6}sur(?:<[^>]*>|[^0-9]){0,80}?(\d+)\s+avis',html,re.I)
    if rating_el and el_text(rating_el,20):
        c["rating"]={"label":el_text(rating_el,20),
                     "count":int(ra.group(1)) if ra else None,
                     "source":"Google"}
    # praticiens (role .btSuperTitle, Dr dans h4, bio .btSubTitle)
    for st in soup.select(".btSuperTitle"):
        role=el_text(st,60)
        p=st.parent
        h4=p.select_one("h4") if p else None
        name=el_text(h4,80)
        if not re.search(r'Dr\.?\s',name): continue
        sub=p.select_one(".btSubTitle")
        bio=el_text(sub,320)
        c["practitioners"].append({"name":name,"role":role,"bio":bio})
    if not c["practitioners"]:
        for tag in soup.find_all(["h4","h3","h2"]):
            t=tag.get_text(" ",strip=True).strip()
            if re.match(r'Dr\.?\s+[A-ZÀÈÉ][a-zà-ÿ]+(?:\s+[A-ZÀÈÉ]{2,})',t):
                c["practitioners"].append({"name":t,"role":"","bio":""})
    c["practitioners"]=c["practitioners"][:6]
    # testimonials (Trustindex .ti-review-item → .ti-name + .ti-review-content, texte dans <template>)
    for item in soup.select(".ti-review-item"):
        author=el_text(item.select_one(".ti-name"),80)
        text=el_text(item.select_one(".ti-review-content"),520)
        if author and text and author not in [t["author"] for t in c["testimonials"]]:
            c["testimonials"].append({"author":author,"text":text})
    c["testimonials"]=c["testimonials"][:14]
    # h2/h3 services + menu items détaillés
    for hx in soup.find_all(["h2","h3"]):
        t=hx.get_text(" ",strip=True)
        if t and 3<len(t)<80: c["services"].append({"title":t,"source":hx.name})
    c["services"]=c["services"][:12]
    # services détaillés (menu Elementor : catégorie + .sub-menu)
    for cat_li in soup.select("li.menu-item-has-children"):
        cat_el=cat_li.find("a",recursive=False)
        cat=(cat_el.get_text(" ",strip=True) if cat_el else "").strip()
        sub=cat_li.select_one(".sub-menu")
        items=[a.get_text(" ",strip=True).strip() for a in (sub.select("a") if sub else [])]
        items=[i for i in items if i and i.upper()!=cat.upper()]
        if cat and items and cat not in c["services_detail"]:
            c["services_detail"][cat]=items[:20]
    # CTA
    for a in soup.find_all(["a","button"]):
        t=a.get_text(" ",strip=True)
        if any(k in t.lower() for k in ["devis","contact","appel","rendez-vous","réserv","demande","rdv"]): c["cta_found"].append(t)
    c["cta_found"]=list(dict.fromkeys([x for x in c["cta_found"] if x]))[:6]
    # content.md complet
    md.append(f"# {c['name'] or c['headline'] or 'ABSENT'}")
    md.append(f"## Titre\n{c['headline'] or 'ABSENT'}")
    if c["subheadline"]: md.append(f"## Sous-titre\n{c['subheadline']}")
    if c["rating"] and c["rating"].get("label"):
        md.append(f"## Note Google\n{c['rating']['label']} — {c['rating'].get('count')} avis ({c['rating'].get('source')})")
    if c["about"]: md.append(f"## À propos\n{c['about']}")
    if c["story"]: md.append(f"## Histoire / embleme\n{c['story']}")
    if c["credo"]: md.append(f"## Credo\n{c['credo']}")
    if c["french_touch"]: md.append(f"## French touch\n{c['french_touch']}")
    if c["contact"]["phone"] or c["contact"]["email"] or c["contact"]["address"]:
        md.append(f"## Contact\n- Telephone: {c['contact']['phone'] or 'ABSENT'}\n- Email: {c['contact']['email'] or 'ABSENT'}\n- Adresse: {c['contact']['address'] or 'ABSENT'}")
    if c["hours"]: md.append(f"## Horaires\n{c['hours']}")
    if c["practitioners"]:
        md.append("## Praticiens")
        for p in c["practitioners"]:
            md.append(f"- **{p['name']}** — {p['role']}\n  {p['bio']}")
    if c["poles"]:
        md.append("## Pôles\n"+"\n".join(f"- {p}" for p in c["poles"]))
        if c.get("poles_intro"): md.append(f"Intro du pôle 1 : {c['poles_intro']}")
    if c["services"]:
        md.append("## Services / sections\n"+"\n".join(f"- {s['title']}" for s in c["services"]))
    if c["services_detail"]:
        md.append("## Details services")
        for cat,items in c["services_detail"].items():
            md.append(f"### {cat}\n"+"\n".join(f"- {i}" for i in items))
    if c["testimonials"]:
        md.append("## Temoignages Google")
        for t in c["testimonials"]:
            md.append(f"- **{t['author']}**: {t['text']}")
    if c["cta_found"]: md.append(f"## CTA\n"+"\n".join(f"- {x}" for x in c["cta_found"]))
for f,v in [("headline",c["headline"]),("subheadline",c["subheadline"]),("about",c["about"]),("hours",c["hours"]),("story",c.get("story")),("contact.email",c["contact"]["email"])]:
    if not v: c["missing_fields"].append(f)
if not c["services"]: c["missing_fields"].append("services")
if not c["testimonials"]: c["missing_fields"].append("testimonials")
if not c["contact"]["phone"]: c["missing_fields"].append("contact.phone")
(outdir/"content.json").write_text(json.dumps(c,indent=2,ensure_ascii=False),encoding="utf-8")
(outdir/"content.md").write_text("\n\n".join(md) if md else "ABSENT — aucun contenu extrait.",encoding="utf-8")

# ---- META + RAPPORT ----
rm=json.loads((raw/"_render-meta.json").read_text()) if (raw/"_render-meta.json").exists() else {}
status="ok"
if rm.get("http_status") and rm["http_status"]>=400: status=f"broken_{rm['http_status']}"
if not (raw/"rendered.html").exists(): status="unreachable"
elif soup and len(soup.get_text(strip=True))<200: status="empty_shell"
meta={"schema_version":"1.0","source_url":rm.get("source_url"),"final_url":rm.get("final_url"),
      "render_method":rm.get("render_method"),"http_status":rm.get("http_status"),"site_status":status,
      "business":{"name":(c["name"] or c["headline"]),"phone":c["contact"]["phone"],"email":c["contact"]["email"],"address":c["contact"]["address"]},
      "images":{"scanned":manifest["scanned"],"kept":kept,"rejected":rej},"colors_confidence":confidence}
(outdir/"meta.json").write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding="utf-8")
P=colors["palette_for_design"]
(outdir/"EXTRACTION-REPORT.md").write_text(
f"""# Rapport d'extraction

- URL : {meta['source_url']} -> {meta['final_url']}
- Statut site : {status} (HTTP {meta['http_status']})
- Rendu : {meta['render_method']}
- Couleurs (confiance {confidence}) : primary {P['primary']}, secondary {P['secondary']}, neutres {P['neutral_light']} -> {P['neutral_dark']}
- Images : {kept} gardées / {rej} écartées sur {manifest['scanned']}
- Champs manquants (-> [À COMPLÉTER] au build) : {', '.join(c['missing_fields']) or 'aucun'}

## Si le site est mort / cassé / vide
Fallback : (1) demander les assets au client (logo, photos de chantiers, textes) ;
(2) chercher l'Instagram / la fiche Google Business du client et relancer l'extraction sur ces profils ;
(3) maquette structure + placeholders, cohérente avec l'accroche « juste pour montrer ».
""", encoding="utf-8")
print("ANALYZE kept",kept,"rejected",rej,"status",status,"confidence",confidence)
