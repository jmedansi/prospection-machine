# -*- coding: utf-8 -*-
"""
SCAN LECTURE-SEULE : état exact des ponts V1 restants (NE MODIFIE RIEN).
Rapport -> D:\\prospection-machine\\_RAPPORT_SCAN_PONTS.txt (lu via read, canal fiable)
Tokens scannés : generate_email_for_lead | build_premium_email | email_generator |
                 email_generation | email_builder | template_profil
"""
import io, os, re

ROOT = r"D:\prospection-machine"
RAPPORT = []
def w(t=""):
    RAPPORT.append(str(t))

w("#" * 70)
w("# SCAN PONTS V1 — état exact (session " + "purge-v1" + ")")
w("#" * 70)

EXCL_DIRNAME = re.compile(r"^(Archives|Archives|backups?|node_modules|\\.venv|__pycache__)$", re.I)
TOKENS = ["generate_email_for_lead", "build_premium_email",
          "from services.email_generator", "from envoi.email_builder",
          "email_generation", "email_builder", "template_profil"]

total_hits = 0
file_hit_map = {}

for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if not EXCL_DIRNAME.search(d) and d not in ("Archives")]
    if re.search(r"\\\\Archives|backups?\\\\", dirpath):
        continue
    for fn in filenames:
        if not fn.endswith(".py"):
            continue
        p = os.path.join(dirpath, fn)
        try:
            with io.open(p, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().split("\n")
        except Exception as e:
            continue
        hits_here = []
        for i, ln in enumerate(lines):
            for tok in TOKENS:
                if tok in ln:
                    hits_here.append((i + 1, tok, ln.strip()[:100]))
                    break
        if hits_here:
            rel = os.path.relpath(p, ROOT)
            file_hit_map[rel] = hits_here
            total_hits += len(hits_here)

w("")
w(f"Fichiers concernés  : {len(file_hit_map)}")
w(f"Total lignes à pont  : {total_hits}")
w("")
for rel in sorted(file_hit_map):
    w("### " + rel)
    seen = set()
    for (ln, tok, txt) in file_hit_map[rel]:
        if (ln, tok) in seen:
            continue
        seen.add((ln, tok))
        w(f"   L{ln} : [{tok}] {txt[:90]}")
    w("")

with io.open(os.path.join(ROOT, "_RAPPORT_SCAN_PONTS.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(RAPPORT))
print("OK — rapport " + str(len(RAPPORT)) + " lignes écrit")
