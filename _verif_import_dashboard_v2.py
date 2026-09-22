# -*- coding: utf-8 -*-
"""_verif_import_dashboard_v2.py — AUTONOME.
Verifie que le dashboard V2 se charge reellement (aucun ImportError V1).
Test reels :
  1. import dashboard.pipeline
  2. import dashboard (routes actives)
  3. import envoi.resend_sender  (tunnel d'envoi V2)
Rapport UTF-8 sur disque -> lu ensuite via read.
"""
import io, os, subprocess, sys, datetime

ROOT = r"D:\prospection-machine"
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
out = []

def check(mod, cwd=None):
    code = "import sys; sys.path.insert(0, r'" + ROOT + "'); import " + mod + "; print('OK: ' + '" + mod + "')"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    if r.returncode == 0:
        return "IMPORT OK : " + r.stdout.strip()
    else:
        err = (r.stderr or "").strip().splitlines()
        return "IMPORT ERREUR : " + (err[-1][:180] if err else "?")

for mod in ["dashboard.pipeline", "dashboard", "envoi.resend_sender"]:
    out.append(check(mod))

rp = os.path.join(ROOT, "_RAPPORT_IMPORT_DASHBOARD_V2.txt")
with io.open(rp, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
with io.open(rp, "r", encoding="utf-8") as f:
    print(f.read())
