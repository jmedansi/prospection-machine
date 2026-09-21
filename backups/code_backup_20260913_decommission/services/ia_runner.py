# -*- coding: utf-8 -*-
"""
services/ia_runner.py — Moteur d'opérations IA ⇄ Dashboard

Deux moteurs interchangeables, MÊME résultat :
  - moteur 'file'       : via dossier partagé ia_echanges/ (on premise, opencode)
  - moteur 'integrated' : via un runner LLM branché au dashboard (crédits payants, plus tard)

Chaque opération cible une liste (liste_id) ou un sous-ensemble de leads (lead_ids).
Règle de sécurité incarnée ici : JAMAIS d'envoi de mail. Le dashboard écrit approuve=0
et seul l'utilisateur déclenche l'envoi manuellement après vérification.
"""
from __future__ import annotations
import json
import os
from datetime import datetime

from database.connection import get_conn, logger
from database.repos import leads_repo, ia_repo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─── Résolution de la cible ────────────────────────────────────────────────

def resolve_target_leads(liste_id: int | None = None, lead_ids: list[int] | None = None,
                         objectif: str | None = None) -> list[dict]:
    """
    Retourne la liste de leads normalisés à traiter (Lead Station / Liste / sélection).
    filtre optionsnels : objectif ('web'/'general'/'tous'/'none').
    """
    ids = []
    if lead_ids:
        ids = [int(x) for x in lead_ids]
    elif liste_id:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT lead_id FROM lead_list_items WHERE list_id = ?", (liste_id,)
            ).fetchall()
        ids = [r[0] for r in rows]

    out = []
    for lid in ids:
        d = leads_repo.get_by_id(lead_id=lid)
        if not d:
            continue
        if objectif is not None and objectif != "tous":
            if (d.get("objectif") or "general") != objectif:
                continue
        out.append(d)
    return out


def normalize_liste_id(liste_id, liste_nom=None):
    """Nettoye le nom de liste pour le slug du dossier ia_echanges."""
    name = (liste_nom or f"liste_{liste_id or 'adhoc'}").strip()
    name = name.replace("/", "_").replace("\\", "_").replace("..", "_")
    return (name or "leads")[:80]


# ─── Opérations ────────────────────────────────────────────────────────────

def run_operation(operation: str, liste_id: int | None = None, liste_nom: str | None = None,
                  lead_ids: list[int] | None = None, objectif: str = "tous",
                  moteur: str = "file") -> dict:
    """Point d'entrée unique. Retourne un payload JSON destiné à la route /api/ia/*."""
    if operation not in ("qualify", "maquette", "redact", "export", "scan"):
        return {"ok": False, "error": f"opération IA inconnue: {operation}"}

    if operation == "export":
        return export(liste_id=liste_id, liste_nom=liste_nom, lead_ids=lead_ids, objectif=objectif, moteur=moteur)

    if operation == "qualify":
        return qualify(liste_id=liste_id, liste_nom=liste_nom, lead_ids=lead_ids, objectif=objectif, moteur=moteur)

    if operation == "maquette":
        return maquette(liste_id=liste_id, liste_nom=liste_nom, lead_ids=lead_ids, moteur=moteur)

    if operation == "redact":
        return redact(liste_id=liste_id, liste_nom=liste_nom, lead_ids=lead_ids, moteur=moteur)

    if operation == "scan":
        return scan(liste_nom=liste_nom)


# ─── Préparation fichier (moteur 'file') ───────────────────────────────────

def _echanges_root() -> str:
    root = os.path.join(ROOT, "ia_echanges")
    os.makedirs(root, exist_ok=True)
    return root


def _export_csv(liste_slug: str, leads: list[dict]) -> str:
    import csv
    folder = os.path.join(_echanges_root(), liste_slug)
    os.makedirs(folder, exist_ok=True)
    cols = ["Id", "Nom", "Adresse", "Ville", "Secteur", "Site", "Tel", "Email",
            "ScoreActuel", "Categorie", "Objectif", "Opportunite", "Score", "Signaux",
            "EmailObjet", "EmailCorps"]
    path = os.path.join(folder, "leads.csv")
    # Use UTF-8 with BOM (utf-8-sig) to improve Excel compatibility on Windows
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for d in leads:
            w.writerow({
                "Id": d.get("id"), "Nom": d.get("nom"), "Adresse": d.get("adresse"),
                "Ville": d.get("ville"), "Secteur": d.get("secteur"), "Site": d.get("site_web"),
                "Tel": d.get("telephone"), "Email": d.get("email"),
                "ScoreActuel": d.get("score_perf"), "Categorie": d.get("categorie"),
                "Objectif": d.get("objectif") or "general",
                "Opportunite": "", "Score": "", "Signaux": "",
                "EmailObjet": "", "EmailCorps": "",
            })
    return path


def _prep_prompt_folders(liste_slug: str, leads: list[dict]) -> int:
    base = os.path.join(_echanges_root(), liste_slug, "PROMPT")
    count = 0
    for d in leads:
        if (d.get("objectif") or "general") == "web":
            os.makedirs(os.path.join(base, str(d.get("id"))), exist_ok=True)
            count += 1
    return count


def export(liste_id=None, liste_nom=None, lead_ids=None, objectif="tous", moteur="file"):
    leads = resolve_target_leads(liste_id, lead_ids, objectif)
    slug = normalize_liste_id(liste_id, liste_nom)
    path = _export_csv(slug, leads)
    nw = _prep_prompt_folders(slug, leads)
    # Créer une exécution IA enregistrée pour tracer l'export
    try:
        cible_ids = [int(d.get('id')) for d in leads if d.get('id')]
        exec_id = ia_repo.create_execution(liste_id, slug, 'export', cible=cible_ids, moteur=moteur)
        # Enregistrer l'exec_id dans le dossier pour que le scan puisse le retrouver
        try:
            with open(os.path.join(_echanges_root(), slug, 'exec_id.txt'), 'w', encoding='utf-8') as ef:
                ef.write(str(exec_id))
        except Exception:
            pass
    except Exception:
        exec_id = None

    return {"ok": True, "liste": slug, "exportes": len(leads), "maquettes_prep": nw,
            "csv": path, "moteur": moteur, "exec_id": exec_id}


def qualify(liste_id=None, liste_nom=None, lead_ids=None, objectif="web", moteur="file"):
    leads = resolve_target_leads(liste_id, lead_ids, objectif)
    slug = normalize_liste_id(liste_id, liste_nom)
    _export_csv(slug, leads)
    return {"ok": True, "liste": slug, "leads": len(leads),
            "message": f"{len(leads)} lead(s) prêts à qualifier. Complète Opportunite/Score/Signaux puis lance le scan."}


def maquette(liste_id=None, liste_nom=None, lead_ids=None, moteur="file"):
    leads = resolve_target_leads(liste_id, lead_ids, objectif="web")
    slug = normalize_liste_id(liste_id, liste_nom)
    n = _prep_prompt_folders(slug, leads)
    return {"ok": True, "liste": slug, "leads_web": len(leads),
            "message": f"{n} dossier(s) PROMPT/<IdLead>/ créés pour les maquettes (index.html + capture.png)."}


def redact(liste_id=None, liste_nom=None, lead_ids=None, moteur="file"):
    leads = resolve_target_leads(liste_id, lead_ids, objectif="tous")
    slug = normalize_liste_id(liste_id, liste_nom)
    _export_csv(slug, leads)
    return {"ok": True, "liste": slug, "leads": len(leads),
            "message": "Leads prêts à rédiger. Remplis les colonnes EmailObjet/EmailCorps puis lance le scan."}


# ─── Scan / réintégration (fichier et moteur intégré) ──────────────────────

def _to_int(lid: int, col: str, raw: str, ecarts: list) -> int | None:
    """Conversion défensive d'une colonne numérique (Opportunite/Score).
    En cas de valeur invalide, enregistre un écart et renvoie None au lieu de crasher."""
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        ecarts.append(f"Id {lid}: «{col}» non numérique («{raw[:40]}»)")
        return None


def scan(liste_nom=None, liste_id=None, mark_fait: bool = True) -> dict:
    """Relit le CSV complété et réintègre qualité + emails. Ne fait JAMAIS d'envoi."""
    import csv
    slug = normalize_liste_id(liste_id, liste_nom)
    path = os.path.join(_echanges_root(), slug, "leads.csv")
    if not os.path.isfile(path):
        return {"ok": False, "error": f"Aucun leads.csv à scanner pour «{slug}»", "liste": slug}

    updated_q, updated_m, ecarts, ids = 0, 0, [], []
    # Try UTF-8 first, fallback to latin-1 for legacy CSVs
    reader = None
    enc_used = None
    try:
        f = open(path, newline="", encoding="utf-8")
        reader = csv.DictReader(f)
        enc_used = 'utf-8'
    except UnicodeDecodeError:
        try:
            f = open(path, newline="", encoding="latin-1")
            reader = csv.DictReader(f)
            enc_used = 'latin-1'
            ecarts.append(f"Fichier lu en latin-1 (fallback)")
        except Exception as e:
            ecarts.append(f"Impossible d'ouvrir le CSV: {e}")
            return {"ok": False, "error": "Impossible d'ouvrir le CSV", "liste": slug}
    except Exception as e:
        logger.error(f"IA scan open {path} → {e}")
        return {"ok": False, "error": str(e), "liste": slug}

    try:
        for row in reader:
            lid = row.get("Id")
            if lid is None:
                continue
            try:
                lid = int(lid)
            except (TypeError, ValueError):
                ecarts.append(f"Id «{lid}» invalide")
                continue

            opp = (row.get("Opportunite") or "").strip()
            score = (row.get("Score") or "").strip()
            signaux = (row.get("Signaux") or "").strip()
            eobj = (row.get("EmailObjet") or "").strip()
            ecorps = (row.get("EmailCorps") or "").strip()

            if not (opp or score or signaux or eobj or ecorps):
                ecarts.append(f"Id {lid}: aucune donnée IA")
                continue

            if not leads_repo.get_by_id(lead_id=lid):
                ecarts.append(f"Id {lid}: introuvable en base")
                continue

            opp_i = _to_int(lid, "Opportunite", opp, ecarts)
            score_i = _to_int(lid, "Score", score, ecarts)
            if opp and opp_i is None:
                continue
            if score and score_i is None:
                continue

            n = leads_repo.set_ia_qualification(
                lid,
                opportunite=opp_i,
                score=score_i,
                signaux=signaux or None,
            )
            if n:
                updated_q += 1

            # If CSV contained an Email column, prefer to update leads_bruts.email when empty
            csv_email = (row.get('Email') or '').strip()
            if csv_email:
                try:
                    leads_repo.update_fields(lid, {'email': csv_email})
                except Exception:
                    pass

            if eobj or ecorps:
                if ia_repo.set_ia_email(lid, eobj or None, ecorps or None):
                    updated_m += 1
            ids.append(lid)
    except Exception as e:
        logger.error(f"IA scan {slug} → {e}")
        try:
            f.close()
        except Exception:
            pass
        return {"ok": False, "error": str(e), "liste": slug}

    try:
        f.close()
    except Exception:
        pass

    for e in ecarts:
        _append_ecart(slug, e)
    _append_ecart(slug, f"Scan: {updated_q} qualifié(s), {updated_m} email(s) rédigés, {len(ecarts)} écart(s).")

    ec = len(ecarts)
    # Enregistre si un exec_id actif existe pour cette liste (appel via route, sinon no-op)
    if mark_fait and ids:
        _mark_latest_noop()

    maquettes = _scan_maquettes(slug, ids)

    # Si un exec_id a été généré lors de l'export, marquer l'exécution IA comme terminée
    try:
        exec_file = os.path.join(_echanges_root(), slug, 'exec_id.txt')
        if os.path.isfile(exec_file):
            with open(exec_file, 'r', encoding='utf-8') as ef:
                raw = ef.read().strip()
            try:
                exec_id = int(raw)
                ia_repo.set_execution_statut(exec_id, 'done', meta={'qualifies': updated_q, 'emails': updated_m}, ecart_count=ec)
            except Exception:
                pass
    except Exception:
        pass

    return {"ok": True, "liste": slug, "qualifies": updated_q, "emails": updated_m,
            "ecarts": ec, "leads_cibles": len(ids), "maquettes": maquettes, "encoding": enc_used}


def _scan_maquettes(liste_slug: str, lead_ids: list[int]) -> list[dict]:
    """Retourne l'état des maquettes déposées par l'agent dans PROMPT/<IdLead>/."""
    import os
    base = os.path.join(_echanges_root(), liste_slug, "PROMPT")
    if not os.path.isdir(base):
        return []
    id_set = set(map(str, lead_ids))
    out = []
    for d in sorted(os.listdir(base), key=lambda x: (len(x), x)):
        dpath = os.path.join(base, d)
        if not os.path.isdir(dpath):
            continue
        if id_set and d not in id_set:
            continue
        files = set(f for f in os.listdir(dpath))
        out.append({
            "IdLead": d,
            "a_index": "index.html" in files,
            "a_capture": "capture.png" in files,
        })
    return out


def _append_ecart(slug: str, message: str) -> None:
    try:
        with open(os.path.join(_echanges_root(), "ecarts.log"), "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] [{slug}] {message}\n")
    except Exception:
        pass


def _mark_latest_noop():
    """Raccourci : la route marquera précisément l'exécution créée. Ici no-op."""
    return None


# ─── Moteur intégré (placeholder payant) ───────────────────────────────────

def integrated_run(operation: str, liste_id=None, liste_nom=None, lead_ids=None, **kw):
    """
    Point de branchement futur d'une IA payante via le dashboard.
    Aujourd'hui : on prépare les données et on le signale comme à brancher.
    """
    leads = resolve_target_leads(liste_id, lead_ids, kw.get("objectif", "tous"))
    return {
        "ok": True,
        "moteur": "integrated",
        "operation": operation,
        "etat": "placeholder",
        "message": "Moteur IA intégré pas encore branché (crédits). Les actions passent par le mode fichier.",
        "leads": len(leads),
    }