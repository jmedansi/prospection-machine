import sys
sys.path.append('d:/prospection-machine')

# Patch stdout to show everything including print()
import io
import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')

from auditeur.main import run_tech_audit_sqlite

# Use actual ids from DB
print("=== Lancement audit 5 leads ===")
run_tech_audit_sqlite(lead_ids=[1373, 1488, 1634, 1921, 2078])
print("=== Audit terminé ===")
