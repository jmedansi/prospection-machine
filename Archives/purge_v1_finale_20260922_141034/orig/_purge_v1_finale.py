# -*- coding: utf-8 -*-
"""
PURGE V1 DEFINITIVE — script autonome et fiable.
FONCTIONNEMENT (tout est dans ce fichier, aucune dépendance cachée) :
  1. Scan des ponts V1 (generate_email_for_lead / build_premium_email) dans le code actif.
  2. Backup de chaque fichier modifie vers Archives\purge_v1_finale_<ts>\orig\
  3. Detachement : suppression des lignes d'import + neutralisation des appels
     (remplacement par verification de redaction manuelle).
  4. Archive des modules V1 (MOVE vers Archives, PAS de suppression a chaud).
  5. Archive des .bak.
  6. py_compile de tous les .py actifs + rapport texte _RAPPORT_PURGE_V1_FINALE.txt
Usage : python _purge_v1_finale.py
"""
import io, os, re, shutil, subprocess, sys, datetime

ROOT = r"D:\prospection-machine"
TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
ARCH = os.path.join(ROOT, "Archives", "purge_v1_finale_" + TS)
os.makedirs(ARCH, exist_ok=True)
ORIG_DIR = os.path.join(ARCH, "orig")
os.makedirs(ORIG_DIR, exist_ok=True)

REPORT = []
def w(s=""):
    REPORT.append(s)

EXCL_DIR = re.compile(r"\\Archives\b|\\archives\b|\\backups?\b|\\node_modules|\\\.venv|__pycache__|\\tests?\b|\\Archives", re.I)
# IMPORTANT : on n'exclut PAS agents|auditeur|dashboard|services|envoi|scraper actifs.

def walk_py():
    out = []
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if not EXCL_DIR.search(d) and d not in ("backups", "Archives", "archives")]
        for fn in fns:
            if fn.endswith(".py") and not fn.endswith("_test.py") and "test_" not in fn:
                out.append(os.path.join(dp, fn))
    return out

def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")

# ------------------- tokens V1 -------------------
IMPORT_PATTERNS = [
    r"^\s*from services\.email_generator import\s.*$",
    r"^\s*from services import email_generator\s*$",
    r"^\s*import services\.email_generator\s*$",
    r"^\s*from envoi\.email_builder import\s.*$",
    r"^\s*from envoi import email_builder\s*$",
    r"^\s*import envoi\.email_builder\s*$",
    r"^\s*from dashboard\.pipeline\.email_generation import\s.*$",
    r"^\s*from dashboard\.pipeline import email_generation\s*$",
]
IMPORT_PATS = re.compile("|".join(["(" + p + ")" for p in IMPORT_PATTERNS]))

# appels a neutraliser (avec ou sans assignment / if)
CALL_PATTERNS = [
    (r"^\s*ok = generate_email_for_lead\([^)]*\)\s*#?.*$", "ok = self._has_manual_draft(lead_id)"),
    (r"^\s*ok\s*=\s*generate_email_for_lead\([^)]*\)\s*$", "ok = self._has_manual_draft(lead_id)"),
    (r"^\s*ok = generate_email_for_lead\(([^)]*)\)$", "ok = self._has_manual_draft(\\1)"),
]

w("#" * 70)
w("# RAPPORT PURGE V1 FINALE  (" + TS + ")")
w("#" * 70)
w("")

# ============ 1. SCAN ============
w("## 1. SCAN DES PONTS V1 (code actif)")
hits = []
for p in walk_py():
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            lines = f.read().split("\n")
    except Exception:
        continue
    for i, ln in enumerate(lines):
        if "generate_email_for_lead" in ln or "build_premium_email" in ln or "email_generator" in ln or "email_builder" in ln:
            hits.append((p, i + 1, ln.strip()))

if not hits:
    w("   [OK] Aucun pont V1 dans le code actif — purge déjà effective.")
else:
    byfile = {}
    for p, i, ln in hits:
        byfile.setdefault(p, []).append((i, ln))
    for p in sorted(byfile):
        w("   ### " + rel(p))
        for i, ln in byfile[p][:12]:
            w(f"      L{i} : {ln[:100]}")
        if len(byfile[p]) > 12:
            w(f"      ... (+{len(byfile[p])-12} autres)")
w(f"   Total : {len(hits)} ligne(s)")

# ============ 2. DETACHEMENT (sur fichiers actifs uniquement) ============
w("")
w("## 2. DETACHEMENT DES PONTS (files actifs)")

def neutralize(p):
    with io.open(p, "r", encoding="utf-8") as f:
        src = f.read()
    lines = src.split("\n")
    out = []
    removed_import = 0
    removed_call = 0
    for ln in lines:
        st = ln.strip()
        if IMPORT_PATS.match(ln):
            # on remplace la ligne d'import par un commentaire CONTRAT V2
            ind = ln[: len(ln) - len(ln.lstrip())]
            out.append(ind + "# CONTRAT V2 : redaction MANUELLE - pont V1 coupe")
            removed_import += 1
            continue
        if "generate_email_for_lead" in ln:
            m = re.match(r"^\s*(.*?)\s*=\s*generate_email_for_lead\(([^)]*)\)\s*$", ln)
            if m:
                var = m.group(1).strip()
                arg = m.group(2).strip()
                ind = ln[: len(ln) - len(ln.lstrip())]
                # on neutralise en verifiant la redaction manuelle
                out.append(f"{ind}{var} = self._has_manual_draft({arg})  # CONTRAT V2")
                removed_call += 1
                continue
            # si generate_email_for_lead est appele en expression (ex: if ...)
            m2 = re.match(r"^\s*if generate_email_for_lead\(([^)]*)\):\s*$", ln)
            if m2:
                ind = ln[: len(ln) - len(ln.lstrip())]
                out.append(f"{ind}if self._has_manual_draft({m2.group(1).strip()}):  # CONTRAT V2")
                removed_call += 1
                continue
        if "build_premium_email" in ln:
            # build_premium_email n'est invoqué nulle part hors envoi V1 -> on saute la ligne
            ind = ln[: len(ln) - len(ln.lstrip())]
            out.append(ind + "# build_premium_email : générateur V1 supprimé - CONTRAT V2 rédaction manuelle")
            removed_call += 1
            continue
        out.append(ln)
    return "\n".join(out), removed_import, removed_call

modified = []
for p in sorted(set(x[0] for x in hits)):
    if not os.path.exists(p):
        continue
    backup = os.path.join(ORIG_DIR, rel(p).replace("/", "__"))
    shutil.copy2(p, backup)
    new_src, nimp, ncall = neutralize(p)
    if nimp or ncall:
        with io.open(p, "w", encoding="utf-8") as f:
            f.write(new_src)
        modified.append((p, nimp, ncall))
        w(f"   [DETACHE] {rel(p)} : {nimp} import(s), {ncall} appel(s)")
    else:
        w(f"   [inchange] {rel(p)} (aucun pont a couper)")

# ============ 3. ARCHIVE MODULES V1 ============
w("")
w("## 3. ARCHIVE DES MODULES V1 (MOVE -> Archives)")
V1_MODULES = [
    r"services\email_generator.py",
    r"envoi\email_builder.py",
    r"dashboard\pipeline\email_generation.py",
]
v1_dir = os.path.join(ARCH, "modules_v1")
os.makedirs(v1_dir, exist_ok=True)
for m in V1_MODULES:
    p = os.path.join(ROOT, m)
    if os.path.exists(p):
        dest = os.path.join(v1_dir, os.path.basename(m))
        shutil.move(p, dest)
        w(f"   [ARCHIVE] {m} -> modules_v1/{os.path.basename(m)}")
    else:
        w(f"   [absent ] {m}")

# ============ 4. ARCHIVE .bak ============
w("")
w("## 4. ARCHIVE .bak")
bak_dir = os.path.join(ARCH, "bak")
os.makedirs(bak_dir, exist_ok=True)
n_bak = 0
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if not EXCL_DIR.search(d) and d not in ("backups", "Archives", "archives")]
    for fn in fns:
        if fn.lower().endswith(".bak"):
            p = os.path.join(dp, fn)
            try:
                shutil.move(p, os.path.join(bak_dir, os.path.basename(dp) + "__" + fn))
                n_bak += 1
            except Exception:
                pass
w(f"   {n_bak} .bak archivé(s)")

# ============ 5. py_compile de TOUS les .py actifs ============
w("")
w("## 5. py_compile (tous les .py actifs)")
compile_errs = []
for p in walk_py():
    r = subprocess.run([sys.executable, "-m", "py_compile", p], capture_output=True, text=True)
    if r.returncode != 0:
        compile_errs.append((rel(p), (r.stderr or "")[:160]))
if compile_errs:
    for relp, err in compile_errs:
        w(f"   [ERREUR] {relp} : {err}")
else:
    w("   [OK] Tous les modules compilent.")

w("")
w("# FIN RAPPORT")

rep_path = os.path.join(ROOT, "_RAPPORT_PURGE_V1_FINALE.txt")
with io.open(rep_path, "w", encoding="utf-8") as f:
    f.write("\n".join(REPORT))
print("RAPPORT:", rep_path)
