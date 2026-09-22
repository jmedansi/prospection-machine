# -*- coding: utf-8 -*-
"""_archive_tests_v1_orphelins.py — AUTONOME, canal fiable.
Archive les 2 tests V1 qui importent un module ABSENT (envoi.email_builder) :
  - envoi\\test_premium_send.py
  - tests\\test_email_builder_mapping.py
+ grep de controle final (sortie sur disque, lue via read) pour certifier
  qu'il ne reste AUCUN import/services.email_generator, envoi.email_builder,
  dashboard.pipeline.email_generation dans l'arbre ACTIF (hors Archives/backups).
"""
import io, os, re, shutil, subprocess, sys, datetime

ROOT = r"D:\prospection-machine"
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
lines = []
def L(m=""):
    lines.append(m)
    print(m)

L("=" * 60)
L("ARCHIVE TESTS V1 ORPHELINS + CONTROLE PONTS FINAL   ts=" + ts)
L("=" * 60)

bakdir = os.path.join(ROOT, "Archives", "purge_tests_v1_" + ts)
os.makedirs(bakdir, exist_ok=True)

L("")
L("--- 1. Archive des tests V1 orphelins ---")
for rel in [r"envoi\test_premium_send.py", r"tests\test_email_builder_mapping.py"]:
    full = os.path.join(ROOT, rel)
    if os.path.exists(full):
        dest = os.path.join(bakdir, os.path.basename(full))
        shutil.move(full, dest)
        L("   ARCHIVE : " + rel)
    else:
        L("   absent  : " + rel)

L("")
L("--- 2. CONTROLE FINAL — imports V1 dans l'arbre actif ---")
SKIP = ("__pycache__", "Archives", "backups", "Archives")
PAT = re.compile(
    r"(?:services\.email_generator|envoi\.email_builder|envoi\.email_generator"
    r"|envoi\.email_generation|dashboard\.pipeline\.email_generation"
    r"|import email_generator|generate_email_for_lead|build_premium_email"
    r"|build_premium_email)"
)
found = []
total_py = 0
for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", "Archives", "backups", "Archives")]
    if any(sk in root for sk in ("Archives", "backups")):
        continue
    for fn in files:
        if fn.endswith(".py"):
            total_py += 1
            full = os.path.join(root, fn)
            try:
                with io.open(full, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                continue
            if PAT.search(content):
                for i, ln in enumerate(content.splitlines(), 1):
                    if PAT.search(ln):
                        found.append((full.replace(ROOT + "\\", ""), i, ln.strip()))

L("   fichiers .py actifs analyses  : " + str(total_py))
if not found:
    L("   RESULTAT : AUCUN import/appel V1 residuel -> CONTRAT V2 100% actif")
else:
    L("   RESULTAT : " + str(len(found)) + " occurrence(s) detectable(s) (dont commentaires) :")
    for p, n, txt in found:
        L("      " + p + " L" + str(n) + " : " + txt[:110])

L("")
L("--- 3. verif imports runtime du package dashboard.pipeline ---")
r = subprocess.run([sys.executable, "-c",
    "import sys; sys.path.insert(0, r'{}'); import dashboard.pipeline; print('DASHBOARD.PIPELINE IMPORT OK')".format(ROOT)],
    capture_output=True, text=True, cwd=ROOT)
L("   " + (r.stdout.strip() if r.returncode == 0 else "ERREUR: " + (r.stderr.strip()[-300:] or "?")))

rp = os.path.join(ROOT, "_CONTROLE_PONTS_FINAL.txt")
with io.open(rp, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
L("")
L("Rapport : " + rp)
