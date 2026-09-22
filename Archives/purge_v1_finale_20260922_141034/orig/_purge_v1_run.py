# -*- coding: utf-8 -*-
"""
PURGE DEFINITIVE V1 -- passe unique fiable.
Methode : les appels restants sont neutralises PAR BLOQUE (try/except entier),
puis les modules V1 + .bak sont deplaces dans une archive horodatee, puis les
ponts sont verifies et le rapport ecrit sur disque.

Ne touche PAS aux modules V2 : templating (envoi/template_registry.py),
envoi/email_shell.py, sequence_engine, sniper.email_generator (propre au v2 sniper).
"""
import io, os, re, shutil, datetime, subprocess, sys

ROOT = r"D:\prospection-machine"
TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
STAMP = "purge_v1_finale_" + TS
ARC = os.path.join(ROOT, "Archives", STAMP)
os.makedirs(ARC, exist_ok=True)

RAPPORT = os.path.join(ROOT, "_rapport_purge_v1.txt")
REPORT = []
def w(*a):
    REPORT.append(" ".join(str(x) for x in a))

w("=" * 64)
w("PURGE DEFINITIVE V1 -- " + STAMP)
w("=" * 64)

# ----------------------------------------------------------------------
# U. DETACHER LES PONTS : pour chaque fichier actif, retirer les blocs qui
#    appellent generate_email_for_lead (remplacement par commentaire manuel).
# ----------------------------------------------------------------------
def load(p):
    with io.open(p, "r", encoding="utf-8") as f:
        return f.read().split("\n")

def save(p, lines):
    with io.open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def remove_blocks_with(name):
    """Retire les blocs try/except contenant `name`. Retourne (fichier, nb_blocs)."""
    return

CALL = re.compile(r"generate_email_for_lead")

def neutralize_file(rel, token):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        w(f"[ABSENT ] {rel}")
        return 0
    lines = load(p)
    # sauvegarde de secours dans l'archive
    safe = os.path.join(ARC, rel.replace("\\", "__") + ".before")
    shutil.copy2(p, safe)

    newlines = []
    i = 0
    nblk = 0
    while i < len(lines):
        ln = lines[i]
        if token in ln:
            # trouver le try: en amont (meme indentation), puis l'except qui ferme
            indent = len(ln) - len(ln.lstrip(" "))
            tidx = None
            j = i
            while j >= 0:
                prev = lines[j]
                pind = len(prev) - len(prev.lstrip(" "))
                if prev.strip().startswith("try:") and pind <= indent:
                    tidx = j
                    break
                j -= 1
            if tidx is not None:
                # trouver l'except au niveau du try
                base_indent = len(lines[tidx]) - len(lines[tidx].lstrip(" "))
                k = tidx + 1
                end = None
                depth = 1
                while k < len(lines):
                    lk = lines[k]
                    kind = len(lk) - len(lk.lstrip(" "))
                    st = lk.strip()
                    if re.match(r"try:", st) and kind > base_indent:
                        pass
                    if st.startswith("try:"):
                        depth += 1
                    if st.startswith("except") and depth == 1 and kind == base_indent:
                        # inclure la 1ere ligne du corps except
                        end = k
                        if k + 1 < len(lines) and (len(lines[k+1]) - len(lines[k+1].lstrip(" "))) > base_indent:
                            end = k + 1
                        break
                    if st.startswith("except"):
                        depth = max(1, depth - 1)
                    k += 1
                if end is not None:
                    newlines.append("# PURGE V1 definiTIVE : generation automatique d'email RETIREE -")
                    newlines.append("# email redige MANUELLEMENT (objet/corps saisis a la main par l'editeur).")
                    if tidx - 1 >= 0 and not lines[tidx - 1].strip():
                        pass
                    i = end + 1
                    nblk += 1
                    continue
            # pas de try/except : on retire juste la ligne d'import et l'appel
            st = ln.strip()
            if st.startswith("from services.email_generator import") or st.startswith("import services.email_generator"):
                i += 1
                continue
            newlines.append("# PURGE V1 : generation auto retiree (redaction manuelle).")
        else:
            newlines.append(ln)
        i += 1

    save(p, newlines)
    w(f"[DETACHE] {rel} : {nblk} bloc(s) neutralise(s)")
    return nblk

# fichiers actifs contenant des ponts (determines par le scan Select-String fiable)
PONTS = [
    ("agents\\redacteur\\agent.py",      "generate_email_for_lead"),
    ("auditeur\\main.py",                "generate_email_for_lead"),
    ("dashboard\\pipeline\\report_publishing.py", "generate_email_for_lead"),
    ("dashboard\\routes\\leads.py",      "generate_email_for_lead"),
    ("dashboard\\routes\\templates.py",  "build_premium_email"),
    ("envoi\\test_premium_send.py",      "build_premium_email"),
    ("tests\\test_email_builder_mapping.py", "build_premium_email"),
]

w("")
w("## 1. DETACHEMENT DES PONTS (fichiers actifs)")
for rel, tok in PONTS:
    neutralize_file(rel, tok)

# ----------------------------------------------------------------------
# 2. SUPPRIMER LES MODULES V1 (deplacer dans l'archive = backup + purge)
# ----------------------------------------------------------------------
V1_MODULES = [
    "services\\email_generator.py",
    "envoi\\email_builder.py",
    "dashboard\\pipeline\\email_generation.py",
]
w("")
w("## 2. SUPPRESSION MODULES GENERATEUR V1 (=> archive)")
for rel in V1_MODULES:
    p = os.path.join(ROOT, rel)
    if os.path.exists(p):
        dest = os.path.join(ARC, "V1_modules", rel.replace("\\", "__"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(p, dest)
        w(f"[SUPPRIME en archive] {rel}")
    else:
        w(f"[ABSENT ] {rel} (rien a faire)")

# ----------------------------------------------------------------------
# 3. SUPPRIMER LES .bak (~40 fichiers)
# ----------------------------------------------------------------------
w("")
w("## 3. FICHIERS .bak (backups generes par la purge precedente) => archive")
nb_bak = 0
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in ("Archives", "backups", "node_modules", ".venv", "__pycache__")]
    if "Archives" in dirpath or "backups" in dirpath:
        continue
    for fn in filenames:
        if fn.endswith(".bak"):
            src = os.path.join(dirpath, fn)
            dest = os.path.join(ARC, "bak", dirpath[len(ROOT)+1:].replace("\\", "__") + "__" + fn)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(src, dest)
            nb_bak += 1
w(f"   {nb_bak} fichier(s) .bak deplaces dans l'archive.")

# ----------------------------------------------------------------------
# 4. COMPILER les fichiers modifies (anti-cassure V2)
# ----------------------------------------------------------------------
w("")
w("## 4. py_compile des fichiers touches")
MODIFIES = [os.path.join(ROOT, r) for r, _ in PONTS]
allok = True
for p in MODIFIES:
    if not os.path.exists(p):
        w(f"   [SKIP - absent] {os.path.basename(p)}")
        continue
    r = subprocess.run([sys.executable, "-m", "py_compile", p],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode == 0:
        w(f"   [OK] {os.path.relpath(p, ROOT)}")
    else:
        allok = False
        w(f"   [ERREUR] {os.path.relpath(p, ROOT)} : {r.stderr.strip()[:300]}")

# ----------------------------------------------------------------------
# 5. VERIFICATION FINALE : plus aucun import des modules V1 / plus de pont
# ----------------------------------------------------------------------
w("")
w("## 5. Verification finale (grep global hors Archives/backups)")
BAD1 = re.compile(r"from services\.email_generator import|from envoi\.email_builder import|generate_email_for_lead|build_premium_email")
leftover = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in ("Archives", "backups", "node_modules", ".venv", "__pycache__")]
    if "Archives" in dirpath or "backups" in dirpath:
        continue
    for fn in filenames:
        if not fn.endswith(".py"):
            continue
        p = os.path.join(dirpath, fn)
        try:
            txt = io.open(p, "r", encoding="utf-8").read()
        except Exception:
            continue
        for ln in txt.split("\n"):
            if BAD1.search(ln):
                leftover.append((os.path.relpath(p, ROOT), ln.strip()[:110]))
if leftover:
    w(f"   !! {len(leftover)} reference(s) V1 encore presente(s) :")
    for rp, l in leftover:
        w(f"      {rp} | {l}")
else:
    w("   [PROPRE] Aucune reference V1 restante (hors archives/backups).")

w("")
w("ARCHIVE : " + ARC)
w("RAPPORT FIN ICI")

with io.open(RAPPORT, "w", encoding="utf-8") as f:
    f.write("\n".join(REPORT))
print("RAPPORT: " + RAPPORT)
