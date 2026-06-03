# -*- coding: utf-8 -*-
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'd:\prospection-machine')
os.chdir(r'd:\prospection-machine')

try:
    from config_manager import get_sheet
    
    print("=== VERIFICATION GOOGLE SHEETS ===\n")
    
    for sheet_name in ["leads_bruts", "Leads", "leads_audites"]:
        try:
            sheet = get_sheet(sheet_name)
            if sheet is None:
                print(f"[ABSENT] Feuille '{sheet_name}': get_sheet retourne None")
                continue
            all_rows = sheet.get_all_records()
            print(f"[OK] Feuille '{sheet_name}': {len(all_rows)} lignes")
            if all_rows:
                print(f"   Colonnes: {list(all_rows[0].keys())[:8]}")
                for i, r in enumerate(all_rows[:3]):
                    nom = r.get('nom', r.get('Nom', r.get('name', '?')))
                    ville = r.get('ville', r.get('Ville', '?'))
                    date = r.get('date_scraping', r.get('Date', '?'))
                    print(f"   [{i+1}] {nom} | {ville} | {date}")
        except Exception as e:
            print(f"[ERREUR] Feuille '{sheet_name}': {e}")
    
except Exception as e:
    print(f"[ERREUR CRITIQUE] {e}")
    import traceback
    traceback.print_exc()
