# -*- coding: utf-8 -*-
"""
services/job_launcher.py — Lanceur standardisé de tâches SaaS Ultra connectées au TaskEngine
"""
import time
from typing import Dict, Any, List, Optional
from database.connection import get_conn
from services.task_engine import TaskEngine
from core.logger import get_logger

logger = get_logger("job_launcher", "app.log")


# ─── 1. BATCH AUDIT TECHNIQUE ─────────────────────────────────────────

def run_batch_audit_worker(task_id: str, limit: int = 25) -> Dict[str, Any]:
    """Exécute l'audit technique d'un lot de leads non audités."""
    TaskEngine.log(task_id, f"Recherche de {limit} leads à auditer...")
    
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT lb.id, lb.nom, lb.site_web 
            FROM leads_bruts lb
            LEFT JOIN leads_audites la ON lb.id = la.lead_id
            WHERE (la.id IS NULL OR la.statut != 'audite')
              AND lb.site_web IS NOT NULL 
              AND lb.site_web != ''
            ORDER BY lb.id DESC
            LIMIT ?
        """, (limit,)).fetchall()

    if not rows:
        TaskEngine.log(task_id, "Aucun lead en attente d'audit technique.")
        return {"audited": 0, "message": "Aucun lead à auditer"}

    total = len(rows)
    TaskEngine.log(task_id, f"{total} leads identifiés pour l'audit.")
    TaskEngine.update_progress(task_id, processed_items=0, total_items=total, current_item_label="Initialisation")

    from auditeur.main import run_audit_for_lead

    audited_count = 0
    errors_count = 0

    for i, r in enumerate(rows, 1):
        if TaskEngine.is_cancelled(task_id):
            TaskEngine.log(task_id, "Audit interrompu par l'utilisateur", level="warning")
            break

        lead_id = r["id"]
        nom = r["nom"]
        site = r["site_web"]

        TaskEngine.update_progress(task_id, processed_items=i-1, total_items=total, current_item_label=f"{nom} ({site})")
        TaskEngine.log(task_id, f"[{i}/{total}] Audit de : {nom} -> {site}")

        try:
            ok = run_audit_for_lead(lead_id)
            if ok:
                audited_count += 1
                TaskEngine.log(task_id, f"[{i}/{total}] OK : {nom}", level="info")
            else:
                errors_count += 1
                TaskEngine.log(task_id, f"[{i}/{total}] Audit incomplet : {nom}", level="warning")
        except Exception as e:
            errors_count += 1
            TaskEngine.log(task_id, f"[{i}/{total}] Erreur sur {nom}: {e}", level="error")

        TaskEngine.update_progress(task_id, processed_items=i, total_items=total, current_item_label=f"{nom} terminé")
        time.sleep(0.5)

    return {"total": total, "audited": audited_count, "errors": errors_count}


# ─── 2. BATCH GÉNÉRATION D'EMAILS ─────────────────────────────────────

def run_batch_email_gen_worker(task_id: str, limit: int = 50) -> Dict[str, Any]:
    """Génère les emails personnalisés pour tous les leads audités en attente."""
    TaskEngine.log(task_id, f"Recherche de {limit} leads audités sans email généré...")

    with get_conn() as conn:
        rows = conn.execute("""
            SELECT la.lead_id, lb.nom 
            FROM leads_audites la
            JOIN leads_bruts lb ON la.lead_id = lb.id
            WHERE (la.email_corps IS NULL OR la.email_corps = '')
            ORDER BY la.id DESC
            LIMIT ?
        """, (limit,)).fetchall()

    if not rows:
        TaskEngine.log(task_id, "Tous les leads audités ont déjà un email généré.")
        return {"generated": 0, "message": "Aucun lead en attente"}

    total = len(rows)
    TaskEngine.log(task_id, f"{total} leads prêts pour la génération de copy.")
    TaskEngine.update_progress(task_id, processed_items=0, total_items=total, current_item_label="Démarrage")

    # CONTRAT V2 : redaction MANUELLE - pont V1 coupe

    gen_count = 0
    errors_count = 0

    for i, r in enumerate(rows, 1):
        if TaskEngine.is_cancelled(task_id):
            TaskEngine.log(task_id, "Génération interrompue par l'utilisateur", level="warning")
            break

        lead_id = r["lead_id"]
        nom = r["nom"]

        TaskEngine.update_progress(task_id, processed_items=i-1, total_items=total, current_item_label=nom)
        TaskEngine.log(task_id, f"[{i}/{total}] Génération email pour : {nom}")

        try:
            ok = self._has_manual_draft(lead_id)  # CONTRAT V2
            if ok:
                gen_count += 1
                TaskEngine.log(task_id, f"[{i}/{total}] Email généré : {nom}", level="info")
            else:
                errors_count += 1
                TaskEngine.log(task_id, f"[{i}/{total}] Échec génération : {nom}", level="warning")
        except Exception as e:
            errors_count += 1
            TaskEngine.log(task_id, f"[{i}/{total}] Erreur {nom}: {e}", level="error")

        TaskEngine.update_progress(task_id, processed_items=i, total_items=total, current_item_label=f"{nom} prêt")

    return {"total": total, "generated": gen_count, "errors": errors_count}


# ─── 3. SCAN BODACC ───────────────────────────────────────────────────

def run_bodacc_scan_worker(task_id: str, max_items: int = 30) -> Dict[str, Any]:
    """Exécute le scan quotidien des créations BODACC."""
    TaskEngine.log(task_id, f"Démarrage du scan BODACC (max {max_items} créations)...")
    try:
        from sniper.bodacc_scanner import run_daily_bodacc
        result = run_daily_bodacc(limit=max_items)
        TaskEngine.log(task_id, f"Scan BODACC terminé : {result}")
        return {"result": result}
    except Exception as e:
        TaskEngine.log(task_id, f"Erreur scan BODACC: {e}", level="error")
        raise e


# ─── API CONVENIENCE LAUNCHERS ────────────────────────────────────────

def launch_batch_audit(limit: int = 25) -> str:
    """Lance un audit par lot via le TaskEngine."""
    return TaskEngine.submit_task(
        task_type="audit_batch",
        label=f"Audit Technique ({limit} leads)",
        func=run_batch_audit_worker,
        kwargs={"limit": limit},
        total_items=limit
    )


def launch_batch_email_generation(limit: int = 50) -> str:
    """Lance une génération d'emails par lot via le TaskEngine."""
    return TaskEngine.submit_task(
        task_type="email_generation",
        label=f"Génération Copies Emails ({limit} leads)",
        func=run_batch_email_gen_worker,
        kwargs={"limit": limit},
        total_items=limit
    )


def launch_bodacc_scan(max_items: int = 30) -> str:
    """Lance le scan BODACC via le TaskEngine."""
    return TaskEngine.submit_task(
        task_type="bodacc_scan",
        label=f"Scan BODACC Créations ({max_items} max)",
        func=run_bodacc_scan_worker,
        kwargs={"max_items": max_items},
        total_items=max_items
    )
