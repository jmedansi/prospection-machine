# -*- coding: utf-8 -*-
"""
_Coupe_pont_pipeline_init.py — CIBLE : dashboard\pipeline\__init__.py
PURGE V1 DEFINITIVE : le module dashboard\pipeline\email_generation.py (worker auto
generation email) est SUPPRIME -> le package __init__ ne doit plus l'importer ni le
reexporter, sinon ImportError fatal au chargement du package.

Actions :
  1. Backup __init__.py dans Archives.
  2. Supprimer la ligne :  `from .email_generation import generate_email_for_lead`
  3. Retirer 'generate_email_for_lead' de __all__.
  4. py_compile.
  5. Archiver (supprimer) les 2 tests V1 qui pointent vers des modules absents :
       - envoi\test_premium_send.py
       - tests\test_email_builder_mapping.py
     (emails maintenant rediges MANUELLEMENT - CONTRAT V2 : ces tests V1 sont
      obsoletes et deja en ImportError puisque envoi\email_builder.py est absent)
  6. rapport UTF-8 sur disque.
"""
import io, os, re, shutil, subprocess, sys, datetime

ROOT = r"D:\prospection-machine"
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
fmt = []

def log(m):
    fmt.append(m)
    print(m)

log("=" * 62)
log("COUPE PONT dashboard\\pipeline\\__init__.py   (ts=" + ts + ")")
log("=" * 62)

# ---------- 1. __init__.py ----------
p = os.path.join(ROOT, "dashboard", "pipeline", "__init__.py")
bakdir = os.path.join(ROOT, "Archives", "purge_pont_pipeline_init_" + ts)
os.makedirs(bakdir, exist_ok=True)
shutil.copy2(p, os.path.join(bakdir, "orig_pipeline___init__.py.bak"))

with io.open(p, "r", encoding="utf-8") as f:
    src = f.read()

# retirer l'import de .email_generation
src2, n_import = re.subn(
    r"(?m)^[ \t]*from \.email_generation import generate_email_for_lead[ \t]*\r?\n?",
    "", src)

# retirer 'generate_email_for_lead' de __all__
src3, n_all = re.subn(
    r"(?m)^[ \t]*'generate_email_for_lead'[ \t]*\r?\n?",
    "", src2)
# si __all__ devient vide ou ne contient que des espaces entre crochets, laisser propre
src3 = re.sub(r"(?s)\]?\s*\]\s*$", "", src3)
src3 = src3.rstrip() + "\n"

with io.open(p, "w", encoding="utf-8") as f:
    f.write(src3)

log("   __init__.py")
log("      - import .email_generation retire      : " + str(1 if n_import or (".email_generation" not in src3) else 0))
log("      - 'generate_email_for_lead' retire __all__ : " + ("oui (absent du fichier)" if "generate_email_for_lead" not in src3 else "RESTE : " + str(src3.count("generate_email_for_lead"))))

r = subprocess.run([sys.executable, "-m", "py_compile", p], capture_output=True, text=True)
log("      - py_compile                         : " + ("OK" if r.returncode == 0 else ("ERREUR " + (r.stderr or "")[:200])))

# ---------- 2. archiver les 2 tests V1 orphelins ----------
tests_v1 = [
    os.path.join(ROOT, "envoi", "test_premium_send.py"),
    os.path.join(ROOT, "tests", "test_email_builder_mapping.py"),
]
log("")
log("   Tests V1 orphelins (modules V1 absents -> CONTRAT V2) :")
for t in tests_v1:
    if os.path.exists(t):
        shutil.move(t, os.path.join(bakdir, os.path.basename(t)))
        log("      - ARCHIVE   : " + t.replace(ROOT + "\\", ""))
    else:
        log("      - absent    : " + t.replace(ROOT + "\\", ""))

# ---------- 3. rapport ---------------------------------------------------------------------------
rp = os.path.join(ROOT, "_RAPPORT_COUPE_PIPELINE_INIT.txt")
with io.open(rp, "w", encoding="utf-8") as f:
    f.write("\n".join(fmt))
log("")
log("Rapport ecrit : " + rp)
