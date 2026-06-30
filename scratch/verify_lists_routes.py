"""Vérifie que l'app Flask se crée sans erreur d'import."""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

try:
    from dashboard.app import create_app
    app = create_app()
    print("OK  create_app() réussi")

    # Lister les routes relatives aux listes
    lists_routes = [r for r in app.url_map.iter_rules() if 'list' in r.rule]
    print(f"\nRoutes /api/lists enregistrées ({len(lists_routes)}):")
    for r in sorted(lists_routes, key=lambda x: x.rule):
        print(f"  {sorted(r.methods - {'HEAD','OPTIONS'})} {r.rule}")

    print("\nDashboard import: OK")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
