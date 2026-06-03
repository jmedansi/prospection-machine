
import sqlite3

db_path = r'd:\prospection-machine\data\prospection.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

print("=== 1. Leads avec audit_error non NULL ===")
rows = conn.execute("SELECT lead_id, audit_error, mobile_score, score_performance, audit_partial FROM leads_audites WHERE audit_error IS NOT NULL AND audit_error != ''").fetchall()
print(f"Count: {len(rows)}")
for r in rows[:5]:
    print(f"  lead_id={r['lead_id']}, audit_error='{r['audit_error']}', mobile_score={r['mobile_score']}, score_perf={r['score_performance']}, partial={r['audit_partial']}")

print("\n=== 2. Leads avec statut 'audit_echoue' dans leads_bruts ===")
rows = conn.execute("SELECT id, nom, statut FROM leads_bruts WHERE statut = 'audit_echoue'").fetchall()
print(f"Count: {len(rows)}")
for r in rows[:5]:
    print(f"  id={r['id']}, nom='{r['nom']}', statut={r['statut']}")

print("\n=== 3. Leads avec statut 'failed' dans leads_bruts ===")
rows = conn.execute("SELECT id, nom, statut FROM leads_bruts WHERE statut = 'failed'").fetchall()
print(f"Count: {len(rows)}")
for r in rows[:5]:
    print(f"  id={r['id']}, nom='{r['nom']}', statut={r['statut']}")

print("\n=== 4. Cross-check: leads echoue mais re-audités avec succes ===")
rows = conn.execute("""
    SELECT lb.id, lb.nom, lb.statut, la.mobile_score, la.score_performance, la.audit_error, la.audit_partial
    FROM leads_bruts lb
    JOIN leads_audites la ON la.lead_id = lb.id
    WHERE lb.statut = 'audit_echoue' AND la.score_performance > 0
""").fetchall()
print(f"Count: {len(rows)}")
for r in rows[:5]:
    print(f"  id={r['id']}, nom='{r['nom']}', statut_brut={r['statut']}, score_perf={r['score_performance']}, audit_error={r['audit_error']}")

print("\n=== 5. Leads audités avec score_performance = 0 ===")
rows = conn.execute("""
    SELECT lb.id, lb.nom, lb.statut, la.mobile_score, la.score_performance, la.template_used
    FROM leads_bruts lb
    JOIN leads_audites la ON la.lead_id = lb.id
    WHERE la.score_performance = 0
    LIMIT 10
""").fetchall()
print(f"Count (showing max 10): {len(rows)}")
for r in rows:
    print(f"  id={r['id']}, nom='{r['nom']}', statut={r['statut']}, mobile={r['mobile_score']}, perf={r['score_performance']}, tmpl={r['template_used']}")

conn.close()
