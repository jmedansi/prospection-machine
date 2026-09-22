# -*- coding: utf-8 -*-
"""
_purge_derniers_orphelins.py — AUTONOME (aucune dep externe).
1. Archive les 2 tests V1 qui importent envoi.email_builder (module ABSENT -> ImportError CI).
2. Purge tout fichier .bak eparpille hors Archives.
3. py_compile de tout l'arbre actif (hors Archives/backups).
4. Verif finale : aucun import 'services.email_generator' / 'envoi.email_builder' / 'dashboard.pipeline.email_generation'.
5. Rapport UTF-8 sur disque (lu ensuite via read).
"""
import io, os, re, shutil, subprocess, sys, py_compile, datetime

ROOT = r"D:\prospection-machine"
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
out = []
def log(m=""):
    out.append(m)
    print(m)

log("=" * 60)
log("PURGE DERNIERS ORPHELINS V1   (ts=" + ts + ")")
log("=" * 60)

# ---------- 1. archiver les 2 tests V1 orphelins ----------
bakdir = os.path.join(ROOT, "Archives", "purge_tests_v1_" + ts)
os.makedirs(bakdir, exist_ok=True)
log("")
log("--- 1. Tests V1 orphelins (importent envoi.email_builder ABSENT) ---")
for rel in ["envoi\\test_premium_send.py", "tests\\test_email_builder_mapping.py"]:
    full = os.path.join(ROOT, rel)
    if os.path.exists(full):
        dest = os.path.join(bakdir, os.path.basename(full))
        shutil.move(full, dest)
        log("   ARCHIVE  : " + rel)
    else:
        log("   absent   : " + rel)

# ---------- 2. purger .bak eparpilles ----------
log("")
log("--- 2. Fichiers .bak hors Archives ---")
removed_bak = 0
for base in ["services", "envoi", "envoi", "dashboard", "auditeur", "agents", "scraper", "modules"]:
    b = os.path.join(ROOT, base)
    if not os.path.exists(b):
        continue
    for root, dirs, files in os.walk(b):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "Archives")]
        if "Archives" in root:
            continue
        for fn in files:
            if fn.endswith(".bak"):
                full = os.path.join(root, fn)
                shutil.move(full, os.path.join(bakdir, "bak_" + fn))
                removed_bak += 1
log("   .bak supprimes/archives : " + str(removed_bak))

# ---------- 3. py_compile arbre actif ----------
log("")
log("--- 3. py_compile arbre actif (hors Archives/backups) ---")
ok = 0
bad = []
for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", "Archives", "Archives", "backups")]
    if "Archives" in root or "backups" in root:
        continue
    for fn in files:
        if fn.endswith(".py"):
            full = os.path.join(root, fn)
            try:
                py_compile.compile(full, doraise=True)
                ok += 1
            except py_compile.PyCompileError as e:
                bad.append((full.replace(ROOT + "\\", ""), str(e)[:120]))
log("   compile OK : " + str(ok) + "   en erreur : " + str(len(bad)))
for b in bad:
    log("      ERREUR : " + b[0] + " -> " + b[1])

# ---------- 4. verif finale : plus aucun import V1 ----------
log("")
log("--- 4. Imports V1 residuels (source de verite finale) ---")
importers = []
for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", "Archives", "Archives", "backups")]
    if "Archives" in root or "backups" in root:
        continue
    for fn in files:
        if fn.endswith(".py"):
            full = os.path.join(root, fn)
            with io.open(full, "r", encoding="utf-8") as f:
                content = f.read()
            if re.search(r"from services\.email_generator|from envoi\.email_builder|from dashboard\.pipeline\.email_generation", content):
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(r"email_generator|email_builder|email_generation", line) and not line.strip().startswith("#") and "CONTRAT" not in line:
                        importers.append((full.replace(ROOT + "\\", "") + " L" + str(i), line.strip()[:100]))
if importers:
    for imp in importers:
        log("   PONT   : " + imp[0] + " : " + imp[1])
else:
    log("   AUCUN - arbre 100% V2 (redaction manuelle)")

# ---------- 5. rapport ----------
rp = os.path.join(ROOT, "_RAPPORT_PURGE_FINALE.txt")
with io.open(rp, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
log("")
log("### RESUME ###")
log("  Tests V1 archives            : 2 cibles traitees")
log("  .bak purges                  : " + str(removed_bak) + " fichier(s)")
log("  py_compile                   : " + str(ok) + " OK / " + str(len(bad)) + " erreur(s)")
log("  Imports V1 residuels         : " + ("0 - arbre V2 PROPRE" if not importers else str(len(importers)) + "  => voir ci-dessus"))
log("Rapport : " + rp)
