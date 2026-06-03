# -*- coding: utf-8 -*-
"""
services/audit_runner.py
Gère le lancement et le suivi des audits.
"""
import os
import sys
import subprocess
import threading
import re
from database import get_lead_by_id, logger
from .job_tracker import _audit_job, reset_audit_job

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def launch_audit_batch(lead_ids=None, lead_names=None, limit=None):
    """
    Lance l'auditeur sur les leads spécifiés dans un thread séparé.
    """
    if _audit_job['running']:
        return False, "Un audit est déjà en cours"

    cmd = [sys.executable, '-u', os.path.join(ROOT, 'auditeur', 'main.py')]
    
    total = 0
    if lead_names:
        total = len(lead_names)
        cmd.extend(['--leads'] + lead_names)
    elif lead_ids:
        total = len(lead_ids)
        cmd.extend(['--ids'] + [str(x) for x in lead_ids])
    elif limit:
        total = limit
        cmd.extend(['--limit', str(limit)])

    reset_audit_job(total=total)

    def _run():
        try:
            proc = subprocess.Popen(
                cmd, cwd=ROOT,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace'
            )
            for line in proc.stdout:
                line_s = line.rstrip()
                _audit_job['logs'].append(line_s)
                
                # Parsing du total
                if 'leads' in line_s and ('auditer' in line_s or 'à auditer' in line_s):
                    m = re.search(r'(\d+) leads', line_s)
                    if m:
                        n = int(m.group(1))
                        if n > _audit_job['total']:
                            _audit_job['total'] = n
                
                # Parsing de la progression
                _line_lower = line_s.lower()
                if ('[sqlite] audit' in _line_lower and 'enregistr' in _line_lower) \
                   or ('audit enregistr' in _line_lower) \
                   or ('[ok] audit enregistr' in _line_lower):
                    _audit_job['current'] += 1
                elif 'echoue' in _line_lower or 'audit_echoue' in _line_lower \
                     or 'ÉCHOUÉ'.lower() in _line_lower or '[erreur] complet' in _line_lower:
                    _audit_job['failed'] += 1
                    _audit_job['current'] += 1
                elif ('termin' in _line_lower and 'audit' in _line_lower) or ('Terminé' in line_s and 'Audit' in line_s):
                    m = re.search(r'(\d+) lead', line_s)
                    if m:
                        _audit_job['current'] = max(_audit_job['current'], int(m.group(1)))
            
            proc.wait()
            _audit_job['returncode'] = proc.returncode
        except Exception as e:
            _audit_job['logs'].append(f'ERREUR: {e}')
            _audit_job['returncode'] = -1
        finally:
            _audit_job['running'] = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return True, "Audit lancé"
