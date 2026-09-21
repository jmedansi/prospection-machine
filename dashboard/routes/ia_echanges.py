# -*- coding: utf-8 -*-
"""
dashboard/routes/ia_echanges.py — Passerelle IA ⇄ Dashboard

Échange par le dossier partagé `ia_echanges/` + journal ia_executions.
Contrat (PROMPT-SYSTÈME) :
  ia_echanges/<liste>/leads.csv
  ia_echanges/<liste>/PROMPT/<IdLead>/{index.html,capture.png}
  ia_echanges/ecarts.log

Les opérations IA (qualify / maquette / redact / export / scan) sont servies
par services/ia_runner.py (moteur 'file' ou 'integrated', même résultat).
Cibles = prospects v2 (Id = prospects.id). Rappel sécurité : aucun mail n'est
envoyé ici — l'envoi reste exclusivement manuel.
"""
import os
from datetime import datetime

from flask import Blueprint, jsonify, request, send_from_directory, abort

from core.config import ROOT as PROJECT_ROOT
from database.connection import logger
from database.repos import ia_repo
from services import ia_runner

ia_bp = Blueprint("ia_exchange", __name__, url_prefix="/api/ia")


def _echanges_root() -> str:
    root = os.path.join(PROJECT_ROOT, "ia_echanges")
    os.makedirs(root, exist_ok=True)
    return root


def _safe_list_name(name: str) -> str:
    name = (name or "leads").strip()
    name = name.replace("/", "_").replace("\\", "_").replace("..", "_")
    return name[:80]


def _body():
    return request.get_json(silent=True) or {}


# ─── Lecture / listing ──────────────────────────────────────────────────────

@ia_bp.get("/status")
def api_ia_status():
    """Liste les dossiers d'échange existants + leur état."""
    root = _echanges_root()
    lists = []
    try:
        entries = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    except FileNotFoundError:
        entries = []
    for d in entries:
        csv_path = os.path.join(root, d, "leads.csv")
        maquettes_dir = os.path.join(root, d, "PROMPT")
        maquettes = 0
        if os.path.isdir(maquettes_dir):
            maquettes = len([x for x in os.listdir(maquettes_dir)
                             if os.path.isdir(os.path.join(maquettes_dir, x))])
        lists.append({
            "liste": d,
            "csv_existe": os.path.isfile(csv_path),
            "maquettes": maquettes,
            "ecarts": _read_ecarts(d),
        })
    return jsonify({"liste": lists})


def _read_ecarts(liste: str):
    path = os.path.join(_echanges_root(), "ecarts.log")
    out = []
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if f"[{liste}]" in line:
                        out.append(line.strip())
        except Exception:
            pass
    return out[-20:]


# ─── Opérations IA (gateway) ────────────────────────────────────────────────

def _common(operation: str):
    """Lit le body commun {liste_id, liste_nom, lead_ids, objectif, moteur},
    enregistre une exécution et exécute via ia_runner."""
    b = _body()
    liste_id = b.get("liste_id")
    liste_nom = b.get("liste_nom") or b.get("liste")
    lead_ids = b.get("lead_ids") or None
    objectif = b.get("objectif") or "tous"
    moteur = b.get("moteur") or "file"

    exec_id = ia_repo.create_execution(
        liste_id=liste_id,
        liste_nom=liste_nom,
        operation=operation,
        cible=lead_ids,
        moteur=moteur,
    )

    if moteur == "integrated":
        result = ia_runner.integrated_run(operation, liste_id=liste_id,
                                          liste_nom=liste_nom, lead_ids=lead_ids, objectif=objectif)
    else:
        result = ia_runner.run_operation(operation, liste_id=liste_id,
                                         liste_nom=liste_nom, lead_ids=lead_ids, objectif=objectif, moteur="file")

    statut = "pret" if result.get("ok") else "erreur"
    ia_repo.set_execution_statut(exec_id, statut,
                                 meta={"message": result.get("message", ""), "liste": result.get("liste", "")},
                                 ecart_count=result.get("ecarts"))
    return result


@ia_bp.post("/qualify")
def api_ia_qualify():
    """Prépare une liste pour la qualification IA (écrit leads.csv)."""
    return jsonify(_common("qualify"))


@ia_bp.post("/maquette")
def api_ia_maquette():
    """Créée les dossiers PROMPT/<IdLead>/ pour les leads 'web' (index.html + capture.png)."""
    return jsonify(_common("maquette"))


@ia_bp.post("/redact")
def api_ia_redact():
    """Prépare la rédaction d'emails IA (colonnes EmailObjet/EmailCorps du CSV)."""
    return jsonify(_common("redact"))


@ia_bp.post("/export")
def api_ia_export():
    """Export (alias) — exporte des leads vers ia_echanges/<liste>/leads.csv."""
    return jsonify(_common("export"))


@ia_bp.post("/scan")
def api_ia_scan():
    """Relit le CSV (qualification v2 + brouillons) et réintègre. JAMAIS d'envoi."""
    b = _body()
    liste_nom = b.get("liste") or b.get("liste_nom")
    result = ia_runner.scan(liste_nom=liste_nom, liste_id=b.get("liste_id"))
    code = 200 if result.get("ok") else 404
    return jsonify(result), code


@ia_bp.get("/executions")
def api_ia_executions():
    """Journal des exécutions IA (filtre optionnel ?operation= / ?liste_id=)."""
    op = request.args.get("operation")
    lid = request.args.get("liste_id", type=int)
    if lid:
        rows = ia_repo.list_executions_for_list(lid)
    else:
        rows = ia_repo.list_executions(operation=op)
    return jsonify({"executions": rows})


@ia_bp.get("/cible")
def api_ia_cible():
    """Helper : leads (ids+infos) pour une cible liste ou sélection → pour l'UI."""
    b = request.args
    liste_id = b.get("liste_id", type=int)
    lead_ids = [int(x) for x in b.get("lead_ids", "").split(",") if x]
    objectif = b.get("objectif")
    leads = ia_runner.resolve_target_leads(liste_id, lead_ids or None, objectif)
    return jsonify({
        "leads": [{
            "id": d.get("id"), "nom": d.get("nom"), "son_objectif": d.get("objectif") or "general",
            "domain": d.get("site_web"),
        } for d in leads],
        "count": len(leads),
    })


# ─── Maquettes (lecture IA) ─────────────────────────────────────────────────

@ia_bp.get("/maquettes/<liste>")
def api_ia_maquettes(liste):
    """Liste les dossiers PROMPT/<IdLead>+ leurs fichiers pour une liste."""
    liste = _safe_list_name(liste)
    base = os.path.join(_echanges_root(), liste, "PROMPT")
    items = []
    if os.path.isdir(base):
        for d in sorted(os.listdir(base)):
            dpath = os.path.join(base, d)
            if not os.path.isdir(dpath):
                continue
            files = sorted(f for f in os.listdir(dpath))
            items.append({
                "IdLead": d,
                "files": files,
                "a_index": "index.html" in files,
                "a_capture": "capture.png" in files,
            })
    return jsonify({"liste": liste, "maquettes": items})


@ia_bp.get("/maquettes/<liste>/<path:filepath>")
def api_ia_file(liste, filepath):
    """Sert un fichier maquette (index.html / capture.png �?�)."""
    liste = _safe_list_name(liste)
    base = os.path.join(_echanges_root(), liste, "PROMPT")
    try:
        return send_from_directory(base, filepath)
    except (FileNotFoundError, OSError):
        abort(404)


@ia_bp.get("/lead/<int:lead_id>/maquette")
def api_ia_lead_maquette(lead_id):
    """
    Localise la maquette IA d'un lead, quelle que soit la liste (dossier PROMPT/<IdLead>).
    Recherche dans tous les dossiers ia_echanges/<liste>/PROMPT/<IdLead>/.
    Retourne la liste (slug), les fichiers présents et une URL de capture si elle existe.
    Lecture seule — aucun écriture ni envoi.
    """
    import re
    root = _echanges_root()
    capt_pat = None
    liste_ok = None
    files_ok = []
    try:
        entries = [d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]
    except FileNotFoundError:
        entries = []
    for d in entries:
        dpath = os.path.join(root, d, "PROMPT", str(lead_id))
        if os.path.isdir(dpath):
            files_ok = sorted(f for f in os.listdir(dpath) if os.path.isfile(os.path.join(dpath, f)))
            liste_ok = d
            if "capture.png" in files_ok:
                capt_pat = _safe_list_name(d) + "/" + str(lead_id) + "/capture.png"
            break
    return jsonify({
        "lead_id": lead_id,
        "liste": liste_ok,
        "files": files_ok,
        "a_index": "index.html" in files_ok,
        "a_capture": "capture.png" in files_ok,
        "capture_url": capt_pat,
    })