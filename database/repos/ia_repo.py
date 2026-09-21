# -*- coding: utf-8 -*-
"""
database/repos/ia_repo.py — Repository des opérations IA ⇄ Dashboard

Couverture :
  - ia_executions  : journal de chaque demande IA (qualify/maquette/redact/export/scan)
  - écriture des retours IA : qualification (ia_*), email (email_objet/email_corps),
    depuis le scan fichier (ia_echanges) ou le moteur intégré.

Règle de sécurité : JAMAIS d'envoi. Les emails IA sont toujours écrits approuve=0 ;
l'envoi est déclenché manuellement par l'utilisateur, une fois tout vérifié.
"""
from __future__ import annotations
import json
from datetime import datetime

from database.connection import get_conn, logger

_OPERATIONS = ("qualify", "maquette", "redact", "export", "scan")


class IaRepo:

    # ─── LECTURE / journal ────────────────────────────────────────────────

    def list_executions(self, limit: int = 50, operation: str | None = None) -> list[dict]:
        where, params = "", []
        if operation in _OPERATIONS:
            where, params = " WHERE operation = ?", [operation]
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    f"SELECT * FROM ia_executions {where} ORDER BY id DESC LIMIT ?",
                    params + [limit]
                ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["cible"] = json.loads(d.get("cible_json") or "[]")
                d["meta"] = json.loads(d.get("meta_json") or "{}")
                out.append(d)
            return out
        except Exception as e:
            logger.error(f"IaRepo.list_executions → {e}")
            return []

    def list_executions_for_list(self, liste_id: int | None, limit: int = 30) -> list[dict]:
        if not liste_id:
            return []
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM ia_executions WHERE liste_id = ? ORDER BY id DESC LIMIT ?",
                    (liste_id, limit)
                ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["cible"] = json.loads(d.get("cible_json") or "[]")
                d["meta"] = json.loads(d.get("meta_json") or "{}")
                out.append(d)
            return out
        except Exception as e:
            logger.error(f"IaRepo.list_executions_for_list → {e}")
            return []

    # ─── Écriture du journal ──────────────────────────────────────────────

    def create_execution(self, liste_id: int | None, liste_nom: str | None,
                         operation: str, cible: list[int] | None = None,
                         moteur: str = "file") -> int:
        if operation not in _OPERATIONS:
            raise ValueError(f"opération IA inconnue: {operation}")
        try:
            now = datetime.now().isoformat(timespec="seconds")
            with get_conn() as conn:
                cur = conn.execute(
                    """INSERT INTO ia_executions
                       (liste_id, liste_nom, operation, moteur, cible_json, statut, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, 'created', ?, ?)""",
                    (liste_id, liste_nom, operation, moteur,
                     json.dumps(cible or [], ensure_ascii=False), now, now)
                )
                conn.commit()
                return cur.lastrowid
        except Exception as e:
            logger.error(f"IaRepo.create_execution → {e}")
            return 0

    def set_execution_statut(self, exec_id: int, statut: str, meta: dict | None = None,
                             ecart_count: int | None = None) -> bool:
        try:
            sets, params = ["statut = ?"], [statut]
            if meta is not None:
                sets.append("meta_json = ?"); params.append(json.dumps(meta, ensure_ascii=False))
            if ecart_count is not None:
                sets.append("ecart_count = ?"); params.append(int(ecart_count))
            sets.append("updated_at = ?"); params.append(datetime.now().isoformat(timespec="seconds"))
            params.append(exec_id)
            with get_conn() as conn:
                conn.execute(f"UPDATE ia_executions SET {', '.join(sets)} WHERE id = ?", params)
                conn.commit()
                # Notify via Telegram when an execution completes
                try:
                    if statut == 'done':
                        import threading
                        def _notify():
                            try:
                                from core.telegram_adapter import notify
                                # fetch execution for summary
                                with get_conn() as c2:
                                    row = c2.execute("SELECT liste_id, liste_nom, operation FROM ia_executions WHERE id = ?", (exec_id,)).fetchone()
                                    if row:
                                        liste = row['liste_nom'] or f"liste #{row['liste_id']}"
                                        op = row['operation']
                                        msg = f"IA {op} terminée pour {liste} — {meta or {}} — écarts: {ecart_count or 0}"
                                    else:
                                        msg = f"IA exécution #{exec_id} terminée — écarts: {ecart_count or 0}"
                                notify("IA — Exécution terminée", msg)
                            except Exception:
                                pass
                        threading.Thread(target=_notify, daemon=True).start()
                except Exception:
                    pass
                return True
        except Exception as e:
            logger.error(f"IaRepo.set_execution_statut → {e}")
            return False

    # ─── Retours IA ───────────────────────────────────────────────────────

    def set_ia_email(self, lead_id: int, email_objet: str | None, email_corps: str | None) -> bool:
        """Écrit l'email fourni par l'IA dans leads_audites (approuve=0, JAMAIS d'envoi)."""
        if not email_objet and not email_corps:
            return False
        try:
            with get_conn() as conn:
                row = conn.execute("SELECT id FROM leads_audites WHERE lead_id = ?", (lead_id,)).fetchone()
                if row:
                    conn.execute(
                        "UPDATE leads_audites SET email_objet = ?, email_corps = ?, approuve = 0 WHERE lead_id = ?",
                        (email_objet, email_corps, lead_id)
                    )
                else:
                    conn.execute(
                        "INSERT INTO leads_audites (lead_id, email_objet, email_corps, approuve) VALUES (?, ?, ?, 0)",
                        (lead_id, email_objet, email_corps)
                    )
                conn.execute(
                    "UPDATE leads_bruts SET statut = ? WHERE id = ? AND statut NOT IN ('envoye','repondu')",
                    ("email_genere", lead_id)
                )
                conn.commit()
                # Notify Telegram about the new IA email (preview)
                try:
                    import threading
                    def _notify_email():
                        try:
                            from core.telegram_adapter import notify
                            with get_conn() as c2:
                                row = c2.execute("SELECT nom FROM leads_bruts WHERE id = ?", (lead_id,)).fetchone()
                                name = row['nom'] if row else f"lead #{lead_id}"
                            preview = (email_objet or '')[:80]
                            msg = f"Nouveau mail IA pour {name}\n\nObjet: {preview}\n\nVérifie et approuve depuis le dashboard."
                            notify(f"IA — Email généré", msg)
                        except Exception:
                            pass
                    threading.Thread(target=_notify_email, daemon=True).start()
                except Exception:
                    pass
                return True
        except Exception as e:
            logger.error(f"IaRepo.set_ia_email({lead_id}) → {e}")
            return False

    def newest_email_for_list(self, liste_id: int | None) -> str | None:
        """Le nouvel email le plus récent (objet) pour prévisualisation — rien d'autre."""
        if not liste_id:
            return None
        try:
            with get_conn() as conn:
                row = conn.execute(
                    """SELECT la.email_objet FROM leads_audites la
                       JOIN lead_list_items lli ON lli.lead_id = la.lead_id
                       WHERE lli.list_id = ? AND la.email_corps IS NOT NULL AND la.email_corps != ''
                       ORDER BY la.id DESC LIMIT 1""",
                    (liste_id,)
                ).fetchone()
                return row[0] if row else None
        except Exception:
            return None


# Singleton partagé
ia_repo = IaRepo()