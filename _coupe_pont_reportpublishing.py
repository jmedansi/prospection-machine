# -*- coding: utf-8 -*-
"""
_Coupe_email_report_publishing.py — CIBLE : dashboard/pipeline/report_publishing.py
Methode EXPRESSION-AWARE et sur pour cette purge V1 :
   1. Backup du fichier dans Archives.
   2. Supprimer toutes les lignes : `from services.email_generator import generate_email_for_lead`
      (l'import disparait) 
   3. Remplacer chaque appel `generate_email_for_lead(X)` par `False` :
        - `if generate_email_for_lead(lid):`  ->  `if False:`   (CONTRAT V2: jamais en auto)
        - `ok = generate_email_for_lead(lid)` ->  `ok = False`
      La structure try/except reste intacte -> aucun NameError, aucun crash.
   4. py_compile.
   5. Rapport UTF-8 ecrit sur disque (lu via read : canal fiable).
"""
import io, os, re, shutil, subprocess, sys, datetime

ROOT = r"D:\prospection-machine"
p = os.path.join(ROOT, "dashboard", "pipeline", "report_publishing.py")

# --- backup ---
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bakdir = os.path.join(ROOT, "Archives", "purge_pont_report_publishing_" + ts)
os.makedirs(bakdir, exist_ok=True)
shutil.copy2(p, os.path.join(bakdir, "orig_report_publishing.py.bak"))

with io.open(p, "r", encoding="utf-8") as f:
    src = f.read()

removed_import = 0
neutralized = []

def repl_call(m):
    # m = "generate_email_for_lead(...)" monte dans un if/else ou assignation
    neutralized.append(m.group(0))
    return "False"

# 1. imports
src2, removed_import = re.subn(r"(?m)^[ \t]*from services\.email_generator import generate_email_for_lead[ \t]*\r?$",
                               "# CONTRAT V2 (purge V1) : import générateur auto retiré", src)

# 2. appels -> False
src3, n_calls = re.subn(r"\bgenerate_email_for_lead\s*\([^)]*\)", repl_call, src2)

with io.open(p, "w", encoding="utf-8") as f:
    f.write(src3)

# --- compile ---
r = subprocess.run([sys.executable, "-m", "py_compile", p], capture_output=True, text=True)
res = r.returncode

# --- rapport ---
fmt = []
fmt.append("=" * 60)
fmt.append("RAPPORT COUPE PONT report_publishing.py  (ts=" + ts + ")")
fmt.append("=" * 60)
fmt.append("   imports V1 retires        : " + str(removed_import))
fmt.append("   appels generate_...():False : " + str(n_calls))
fmt.append("   occurrences restantes 'generate_email_for_lead' : " + str(src3.count("generate_email_for_lead")))
fmt.append("   py_compile exit           : " + str(res))
if res != 0:
    fmt.append("   ERREUR : " + (r.stderr or "")[:300])
fmt.append("   backup                   : " + os.path.join(bakdir, "orig_report_publishing.py.bak"))

rp = os.path.join(ROOT, "_RAPPORT_CUIS_PONT_REPORTPUB.txt")
with io.open(rp, "w", encoding="utf-8") as f:
    f.write("\n".join(fmt))
print("OK " + rp)
