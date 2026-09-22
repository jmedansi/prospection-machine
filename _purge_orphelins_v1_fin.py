# -*- coding: utf-8 -*-
"""
_purge_orphelins_v1_fin.py — AUTONOME, canal fiable (script court, aucun dep externe).
Archive : envoi\test_premium_send.py + tests\test_email_builder_mapping.py
(2 tests V1 qui importent envoi.email_builder ABSENT -> ImportError si jetes en CI,
 mais NE bloquent PAS le runtime dashboard).
Puis : py_compile arbre actif (hors Archives) + verif aucun import email_builder/email_generator.
Rapport UTF-8 sur disque.
"""
import io, os, re, shutil, datetime, py_compile

ROOT = r"D:\prospection-machine"
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
out = []

def log(m=""):
    out.append(m)
    print(m)

ROOT_NORM = ROOT.replace("\\", "_")
log("=" * 60)
log("ARCHIVAGE DERNIERS ORPHELINS V1    (ts=" + ts + ")")
log("=" * 60)

bak = os.path.join(ROOT, "Archives", "purge_orphelins_v1_" + ts)
os.makedirs(bak, exist_ok=True)

# 1. archiver les 2 tests V1
log("")
log("--- 1. Tests V1 orphelins (importent envoi.email_builder ABSENT) ---")
for rel in ["envoi\\test_premium_send.py", "tests\\test_email_builder_mapping.py"]:
    full = os.path.join(ROOT, rel)
    if os.path.exists(full):
        dest = os.path.join(bak, os.path.basename(full))
        shutil.move(full, dest)
        log("   ARCHIVE  : " + rel)
    else:
        log("   absent   : " + rel)

# 2. py_compile arbre actif
log("")
log("--- 2. py_compile arbre actif (hors Archives/backups/__pycache__) ---")
ok = 0
bad = []
for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", "Archives", "Archives", "backups")]
    if "Archives" in root or "backups" in root:
        continue
    if "\\Archives" in root or "\\backups" in root:
        continue
    for fn in files:
        if fn.endswith(".py"):
            full = os.path.join(root, fn)
            try:
                py_compile.compile(full, doraise=True)
                ok += 1
            except py_compile.PyCompileError as e:
                bad.append((full.replace(ROOT + "\\", ""), str(e)[:130]))
log("   compile OK : " + str(ok) + "  |  en erreur : " + str(len(bad)))
for b in bad:
    log("      ERREUR : " + b[0] + "  ->  " + b[1])

# 3. verification finale : aucun import V1 dans l'arbre actif
log("")
log("--- 3. Imports V1 residuels (source finale de verite) ---")
importers = []
token = re.compile(r"from envoi.email_builder|from services.email_generator|from services.email_generation|from dashboard.pipeline.email_generation|from envoi.email_generation")
for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", "Archives", "Archives", "backups")]
    if "Archives" in root or "backups" in root or "\\Archives" in root or "\\backups" in root:
        continue
    for fn in files:
        if fn.endswith(".py"):
            full = os.path.join(root, fn)
            with io.open(full, "r", encoding="utf-8") as f:
                content = f.read()
            if token.search(content):
                for i, line in enumerate(content.splitlines(), 1):
                    if token.search(line) and not line.strip().startswith("#"):
                        importers.append((full.replace(ROOT + "\\", "") + " L" + str(i), line.strip()[:100]))
if importers:
    for imp in importers:
        log("   PONT   : " + imp[0] + " : " + imp[1])
    log("")
    log("   => " + str(len(importers)) + " import(s) V1 residuel(s)  [a nettoyer]")
else:
    log("   AUCUN — arbre 100% V2 (CONTRAT redaction manuelle)  OK")

# 4. test import dashboard.pipeline (temoins ImportError)
log("")
log("--- 4. import dashboard.pipeline (temoins ImportError eventuel) ---")
import subprocess, sys
r = subprocess.run(
    [sys.executable, "-c", "import dashboard.pipeline; print('OK dashboard.pipeline')"],
    capture_output=True, text=True, cwd=ROOT, encoding="utf-8")
if r.returncode == 0:
    log("   " + r.stdout.strip())
else:
    log("   ERREUR : " + (r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "?")[:200])

# rapport
rp = os.path.join(ROOT, "_RAPPORT_PURGE_ORPHELINS_FIN.txt")
with io.open(rp, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
log("")
log("Rapport : " + rp)
