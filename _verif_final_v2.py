# -*- coding: utf-8 -*-
"""_verif_final_v2.py — GATE unique « le dashboard demarre ? » (canal fiable)"""
import io, os, sys, subprocess, py_compile, datetime

ROOT = r"D:\prospection-machine"
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
log = []

def L(m=""):
    log.append(m)
    print(m)

L("=" * 60)
L("VERIF FINALE V2 — py_compile arbre actif + import dashboard.pipeline")
L("ts=" + ts)
L("=" * 60)

# 1. py_compile arbre actif (hors Archives/backups/tests V1/tools)
total = ok = 0
bad = []
for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in ("__pycache__", "Archives", "backups")]
    skip = any(s in root for s in ("Archives", "backups"))
    if skip:
        continue
    for fn in files:
        if fn.endswith(".py"):
            total += 1
            p = os.path.join(root, fn)
            try:
                py_compile.compile(p, doraise=True)
                ok += 1
            except Exception as e:
                bad.append((p.replace(ROOT + "\\", ""), str(e)[:160]))

L("")
L("py_compile : " + str(ok) + "/" + str(total) + " OK | " + str(len(bad)) + " en erreur")
for b in bad:
    L("   ERREUR : " + b[0] + "  ->  " + b[1])

# 2. import réel du package core + dashboard.pipeline (gates ImportsError)
L("")
L("--- import package (témoin ImportError éventuel) ---")
for mod in ["dashboard.pipeline", "dashboard", "core.orchestration"]:
    try:
        subprocess.run([sys.executable, "-c", "import " + mod], capture_output=True, text=True)
        # la vraie validation : exécuter l'import dans le process
        r = subprocess.run(
            [sys.executable, "-c", "import " + mod + "; print('OK ' + '" + "'" + mod + "'" + ")"],
            capture_output=True, text=True, cwd=ROOT
        )
        if r.returncode == 0:
            L("   import " + mod + "  ->  " + r.stdout.strip())
        else:
            L("   import " + mod + "  ->  ERREUR : " + (r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "?"))
    except Exception as e:
        L("   import " + mod + "  ->  EXC: " + str(e)[:120])

rp = os.path.join(ROOT, "_VERIF_FINALE_V2.txt")
with io.open(rp, "w", encoding="utf-8") as f:
    f.write("\n".join(log))
L("")
L("Rapport : " + rp)
