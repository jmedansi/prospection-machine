# analyze.py  —  usage: python3 analyze.py <asset-pack-dir>
import sys, json, re, io
from pathlib import Path
from collections import Counter
import numpy as np, requests
from PIL import Image, ImageFilter
from bs4 import BeautifulSoup

outdir=Path(sys.argv[1]); raw=outdir/"raw"
for d in ("images","images-rejected"): (outdir/d).mkdir(parents=True, exist_ok=True)
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
    if UI.search(src or ""):
        it.update(status="rejected",reject_reason="ui_chrome"); items.append(it); rej+=1; continue
    try:
        data=requests.get(src,headers=UA,timeout=20).content[:20_000_000]
        im=Image.open(io.BytesIO(data)); im.load()
    except Exception as ex:
        it.update(status="rejected",reject_reason=f"download_fail:{ex.__class__.__name__}"); items.append(it); rej+=1; continue
    w,h=im.size; fmt=im.format or ""; nb=len(data); ratio=round(w/h,2) if h else 0
    has_exif=bool(getattr(im,"getexif",lambda:{})())
    checks={"w":w,"h":h,"bytes":nb,"format":fmt,"ratio":ratio}
    reject=None
    if max(w,h)<800 or w*h<350000: reject="low_resolution"
    elif nb<12000 and fmt!="SVG": reject="too_small_bytes"
    elif ratio>4 or ratio<0.25: reject="aspect_ratio"
    if not reject:
        lv=lap_var(im); checks["blur_laplacian_var"]=round(lv,1)
        if lv<100: reject="blurry"
    ai,sig=ai_score(im,src or "",fmt,has_exif); checks.update(ai_suspicion_score=ai,ai_signals=sig)
    if not reject and ai>=0.6: reject="ai_suspected"
    it["checks"]=checks
    ext={"JPEG":"jpg","PNG":"png","WEBP":"webp","GIF":"gif"}.get(fmt,"jpg")
    if reject:
        it.update(status="rejected",reject_reason=reject)
        try: im.convert("RGB").save(outdir/"images-rejected"/f'{it["id"]}.{ext}')
        except: pass
        rej+=1
    else:
        role="hero" if (kept==0 and max(w,h)>=1200) else "gallery"
        it.update(status="kept",role_guess=role,ai_uncertain=ai>=0.3,saved_as=f'images/{it["id"]}.{ext}')
        try: im.save(outdir/"images"/f'{it["id"]}.{ext}')
        except: im.convert("RGB").save(outdir/"images"/f'{it["id"]}.jpg'); it["saved_as"]=f'images/{it["id"]}.jpg'
        kept+=1
    items.append(it)
manifest={"scanned":len(items),"kept":kept,"rejected":rej,"items":items}
(outdir/"images-manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8")

# ---- CONTENU ----
html=(raw/"rendered.html").read_text(encoding="utf-8",errors="ignore") if (raw/"rendered.html").exists() else ""
soup=BeautifulSoup(html,"lxml") if html else None
c={"headline":None,"subheadline":None,"services":[],"about":None,
   "contact":{"phone":None,"email":None,"address":None},"hours":None,
   "testimonials":[],"cta_found":[],"missing_fields":[]}
md=[]
if soup:
    title=soup.title.string.strip() if soup.title and soup.title.string else None
    h1=soup.find("h1"); c["headline"]=h1.get_text(" ",strip=True) if h1 else title
    desc=soup.find("meta",attrs={"name":"description"})
    c["subheadline"]=desc["content"].strip() if desc and desc.get("content") else None
    for s in soup.find_all("script",attrs={"type":"application/ld+json"}):
        try: data=json.loads(s.string or "{}")
        except: continue
        for nd in (data if isinstance(data,list) else [data]):
            if isinstance(nd,dict) and "LocalBusiness" in str(nd.get("@type","")):
                c["contact"]["phone"]=c["contact"]["phone"] or nd.get("telephone")
                a=nd.get("address")
                if isinstance(a,dict):
                    c["contact"]["address"]=", ".join(filter(None,[a.get("streetAddress"),a.get("postalCode"),a.get("addressLocality")]))
    body=soup.get_text(" ",strip=True)
    if not c["contact"]["phone"]:
        m=re.search(r'(?:\+33|0)\s?[1-9](?:[\s.\-]?\d{2}){4}',body); c["contact"]["phone"]=m.group(0) if m else None
    em=re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+',body); c["contact"]["email"]=em.group(0) if em else None
    for hx in soup.find_all(["h2","h3"]):
        t=hx.get_text(" ",strip=True)
        if t and 3<len(t)<80: c["services"].append({"title":t,"source":hx.name})
    c["services"]=c["services"][:8]
    for a in soup.find_all(["a","button"]):
        t=a.get_text(" ",strip=True)
        if any(k in t.lower() for k in ["devis","contact","appel","rendez-vous","réserv","demande"]): c["cta_found"].append(t)
    c["cta_found"]=list(dict.fromkeys([x for x in c["cta_found"] if x]))[:6]
    md.append(f"# {c['headline'] or 'ABSENT'}")
    if c["subheadline"]: md.append(f"> {c['subheadline']}")
    md.append("## Services / sections\n"+("\n".join(f"- {s['title']}" for s in c["services"]) or "ABSENT"))
    md.append(f"## Contact\n- Téléphone: {c['contact']['phone'] or 'ABSENT'}\n- Email: {c['contact']['email'] or 'ABSENT'}\n- Adresse: {c['contact']['address'] or 'ABSENT'}")
for f,v in [("headline",c["headline"]),("subheadline",c["subheadline"]),("about",c["about"]),("hours",c["hours"])]:
    if not v: c["missing_fields"].append(f)
if not c["services"]: c["missing_fields"].append("services")
if not c["testimonials"]: c["missing_fields"].append("testimonials")
if not c["contact"]["phone"]: c["missing_fields"].append("contact.phone")
if not c["contact"]["email"]: c["missing_fields"].append("contact.email")
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
      "business":{"name":c["headline"],"phone":c["contact"]["phone"],"email":c["contact"]["email"],"address":c["contact"]["address"]},
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
