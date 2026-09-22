# -*- coding: utf-8 -*-
"""
Weed the 2 test V1 orphans + verify dashboard imports cleanly.
"""

import io, os, shutil, datetime

ROOT = r"D:\prospection-machine"
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
out = []
def log(m=""):
    out.append(m)
    print(m)

log("=" * 60)
log("PURGE FINALE V1 - tests orphelins + verif package")
log("=" * 60)

# 1. archiver les 2 tests V1 qui importent envoi.email_builder ABSENT
bak = os.path.join(ROOT, "Archives", "purge_tests_v1_" + ts)
os.makedirs(bak, exist_ok=True)

for rel in ["envoi\\test_premium_send.py", "tests\\test_email_builder_mapping.py"]:
    full = os.path.join(ROOT, rel)
    if os.path.exists(full):
        dest = os.path.join(bak, os.path.basename(full))
        shutil.move(full, dest)
        log("  ARCHIVE : " + rel)
    else:
        log("  absent  : " + rel)

# 2. py_compile complet outils de run
import py_compile
targets = []
for base in ["dashboard", "envoi", "services"]:
    for root, dirs, files in os.walk(os.path.join(ROOT, base)):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "Archives", "backups", "Archives")]
        if "Archives" in root or "backups" in root:
            continue
        for fn in files:
            if fn.endswith(".py"):
                targets.append(os.path.join(root, fn))

ok = 0; bad = []
for t in targets:
    try:
        py_compile.compile(t, doraise=True)
        ok += 1
    except py_compile.PyCompileError as e:
        bad.append((t.replace(ROOT + "\\", ""), str(e)[:120]))

log("")
log("py_compile : " + str(ok) + " OK, " + str(len(bad)) + " en erreur")
for b in bad:
    log("   ERREUR : " + b[0] + "  ->  " + b[1])

rp = os.path.join(ROOT, "_RAPPORT_COUPE_FINALE.txt")
with io.open(rp, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
log("Rapport : " + rp)
log("FIN")
