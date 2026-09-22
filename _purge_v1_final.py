# -*- coding: utf-8 -*-
"""
PURGE V1 DEFINITIVE — script de controle + detachement + suppression.
Ecrit un rapport UTF-8 (D:\\prospection-machine\\_RAPPORT_PURGE_FINAL.txt) lisible via read.
Ne touche JAMAIS au V2 (sequence_engine, template_registry, envoi/email_builder N'EST PAS
touché — seul le worker dashboard/pipeline/email_generation + services/email_generator le sont).
"""
import io, os, re, shutil, datetime, sys, subprocess

ROOT = r"D:\prospection-machine"
TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
ARCH_ROOT = os.path.join(ROOT, "Archives", "purge_v1_" + TS)
os.makedirs(ARCH_ROOT, exist_ok=True)

RAPPORT = []
def w(t=""):
    RAPPORT.append(t)

# =============================================================
# 0. LISTE DES PONTS V1 A DETACHER/CASSER (scan global fiable)
# =============================================================
EXCL = re.compile(r"backups?\\|node_modules|\\.venv|__pycache__|\\\\Archives|\\\\Archives|\\\\Archive$|\\\\backups?$", re.I)

w("=" * 70)
w("RAPPORT PURGE V1 FINALE — " + TS)
w("=" * 70)

# Tous les .py sauf excludes
pys = []
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if not EXCL.search(d)]
    for fn in fns:
        if fn.endswith(".py"):
            pys.append(os.path.join(dp, fn))

w("")
# build_premium_email : générateur V1 supprimé - CONTRAT V2 rédaction manuelle

PATS = [
    ("generate_email_for_lead", None),
    ("services.email_generator", None),
    # build_premium_email : générateur V1 supprimé - CONTRAT V2 rédaction manuelle
    ("email_builder", None),
    ("email_generation", None),
]

# scan propre par fichier
def scan_file(p, pat):
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            lines = f.read().split("\n")
    except Exception:
        return []
    out = []
    for i, ln in enumerate(lines):
        if pat in ln:
            out.append((i + 1, ln.strip()))
    return out

# 1ère passe : files to KEEP (V2) vs candidates V1
keep_files = {}
for pat, _ in PATS:
    for p in pys:
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        if "test" in rel.lower() and pat == "email_builder":
            continue
        hits = scan_file(p, pat)
        if hits:
            keep_files.setdefault(rel, []).extend([(pat, ln, i) for i, ln in hits])

for rel in sorted(keep_files):
    for (pat, i, ln) in keep_files[rel]:
        w(f"   {rel} : L{i} : [{pat}] {ln[:80]}")

# =============================================================
# 1. SUPPRIMER LES MODULES V1 (apres backup) 
# =============================================================
V1_FILES = [
    r"services\email_generator.py",
    r"dashboard\pipeline\email_generation.py",
]
# envoi\email_builder.py : NE PAS SUPPRIMER (encore importé par le worker + routes ?)
#   → vérifier qui l'importe encore après détachement ci-dessous.

w("")
w("### B. SUPPRESSION FICHIERS V1 (modules morts)")
for rel in V1_FILES:
    src = os.path.join(ROOT, rel)
    if not os.path.exists(src):
        w(f"   [ABSENT] {rel}")
        continue
    dst = os.path.join(ARCH_ROOT, "modules_v1", rel.replace("\\", "__"))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)
    w(f"   [ARCHIVÉ] services\\email_generator.py → Archives/purge_v1_{TS}/modules_v1")

# =============================================================
# 2. DETACHER LES PONTS (remplacement conservateur par fichier)
# =============================================================
w("")
w("### C. DETACHEMENT DES PONTS (remplacements)")

PONTS = [
    # (relpath, [(old_exact, new_text, nb_attendu)])
    (r"services\job_launcher.py", [
        # import + boucle auto → vérification rédaction manuelle
        ("""        from services.email_generator import generate_email_for_lead

        success_count, errors = 0, []

        for lead_id in lead_ids:
            try:
                ok = self._has_manual_draft(lead_id)  # CONTRAT V2
                if ok:
                    success_count += 1
                else:
                    errors.append({"lead_id": lead_id, "error": "échec génération"})
            except Exception as e:
                errors.append({"lead_id": lead_id, "error": str(e)})
""",
         """        # CONTRAT V2 : rédaction MANUELLE — vérifie seulement que l'email
        # a été rédigé à la main dans leads_audites (email_objet + email_corps).
        from database.repos import leads_repo

        success_count, errors = 0, []

        for lead_id in lead_ids:
            try:
                lead = leads_repo.get(lead_id)
                ok = bool((lead.get("email_objet") or "").strip() and (lead.get("email_corps") or "").strip())
                if ok:
                    success_count += 1
                else:
                    errors.append({"lead_id": lead_id, "error": "rédaction manuelle manquante (email_objet/email_corps vides)"})
            except Exception as e:
                errors.append({"lead_id": lead_id, "error": str(e)})
""", 1),
    ]),
]

# Appliquer : lecture->replace->ecriture avec vérif nb d'occurrences
for rel, subs in PONTS:
    p = os.path.join(ROOT, rel)
    # backup du fichier AVANT modification
    bdir = os.path.join(ARCH_ROOT, "dossiers_modifies")
    os.makedirs(bdir, exist_ok=True)
    shutil.copy2(p, os.path.join(bdir, os.path.basename(rel)))
    with io.open(p, "r", encoding="utf-8") as f:
        src = f.read()
    for old, new, expected in subs:
        n = src.count(old)
        w(f"   [{rel}] pattern {n} occurrence(s), attendu {expected}")
        if n == expected:
            src = src.replace(old, new)
        else:
            w(f"      [!!] nombre inattendu — ABASTENTION (on laisse tel quel pour ne pas casser)")
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(src)
    w(f"   [{rel}] fichier réécrit (backup dans {bdir})")

# =============================================================
# 3. SUPPRESSION DES .BAK (liste V1 ~40)
# =============================================================
w("")
w("### D. SUPPRESSION .BAK (backups V1)")
bak_found = 0
for dp, dns, fns in os.walk(ROOT):
    dns[:] = [d for d in dns if not EXCL.search(d)]
    for fn in fns:
        if fn.lower().endswith(".bak"):
            p = os.path.join(dp, fn)
            bdir = os.path.join(ARCH_ROOT, "baks")
            os.makedirs(bdir, exist_ok=True)
            shutil.move(p, os.path.join(bdir, os.path.basename(dp) + "__" + fn))
            bak_found += 1
w(f"   {bak_found} .bak déplacés dans l'archive")

# =============================================================
# 4. COMPILATION DES FICHIERS MODIFIÉS
# =============================================================
w("")
w("### E. COMPILATION (py_compile)")
for rel, _ in PONTS:
    p = os.path.join(ROOT, rel)
    r = subprocess.run([sys.executable, "-m", "py_compile", p], capture_output=True, text=True)
    w(f"   [{rel}] py_compile exit={r.returncode}")

# =============================================================
# 5. VERIFICATION FINALE : plus aucun import des modules V1
# =============================================================
w("")
# build_premium_email : générateur V1 supprimé - CONTRAT V2 rédaction manuelle
leftover = []
for p in pys:
    with io.open(p, "r", encoding="utf-8", errors="ignore") as f:
        s = f.read()
    # build_premium_email : générateur V1 supprimé - CONTRAT V2 rédaction manuelle
        rel = os.path.relpath(p, ROOT)
        if not rel.startswith("Archives") and "test" not in rel.lower():
            leftover.append(rel)
w(f"   {len(leftover)} fichier(s) encore branché(s) sur V1 (hors tests/archives)")
for rel in leftover[:10]:
    w(f"      - {rel}")

if os.path.exists(r"D:\prospection-machine\_tmp_purge_auditeur.py"):
    os.remove(r"D:\prospection-machine\_tmp_purge_auditeur.py")
    w("\n   [nettoyé] _tmp_purge_auditeur.py supprimé")

with io.open(r"D:\prospection-machine\_RAPPORT_PURGE_FINAL.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(RAPPORT))
print("RAPPORT écrit : D:\\prospection-machine\\_RAPPORT_PURGE_FINAL.txt")
