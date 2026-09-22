# -*- coding: utf-8 -*-
"""Scan lecture-seule : ponts V1 restants dans l'arbre ACTIF (hors archives/backups).
Rapport -> D:\prospection-machine\_SCAN_MAINTENANT.txt
NB : si agents\redacteur\agent.py apparaît encore avec import+appel, c'est l'état FAUX
(l'edit a déjà coupé) — le change réel sera confirmé par une 2e passe après purge.
"""
import io, os, re

ROOT = r"D:\prospection-machine"
OUT = r"D:\prospection-machine\_SCAN_MAINTENANT.txt"
EXCL_DIR = re.compile(r"backups?\\|node_modules|\.venv|__pycache__|\\Archives|\\archives", re.I)
TOKENS = ["generate_email_for_lead", "build_premium_email",
          "from services.email_generator", "from envoi.email_builder",
          "email_generation", "email_generator", "email_builder"]

R = []
def w(t=""): R.append(t)

w("=" * 60)
w("SCAN MAINTENANT — ponts V1 dans l'arbre actif")
w("=" * 60)

hits = []
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if not EXCL_DIR.search(d + "\\")]
    if EXCL_DIR.search(dp + "\\"): continue
    for fn in fns:
        if not fn.endswith(".py") or fn.startswith("_"): continue
        p = os.path.join(dp, fn)
        try:
            with io.open(p, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().split("\n")
        except Exception:
            continue
        for i, ln in enumerate(lines):
            for tok in TOKENS:
                if tok in ln:
                    rel = os.path.relpath(p, ROOT).replace("\\", "/")
                    hits.append((rel, i+1, tok, ln.strip()[:95]))
                    break

for h in hits:
    w(f"   {h[0]} : L{h[1]} : [{h[2]}] {h[3]}")
w("")
w(f"TOTAL : {len(hits)} occurrence(s) dont modules V1 eux-mêmes")
w("")
w("Fichiers uniques : " + str(len(set(h[0] for h in hits))))

with io.open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(R))
print("scan écrit: " + OUT)
