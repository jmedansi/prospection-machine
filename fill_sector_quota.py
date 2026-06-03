import argparse
import sqlite3
import subprocess
import sys
import os
import time

def get_db_path():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, 'data', 'prospection.db')
    if not os.path.exists(db_path):
        db_path = 'prospection.db'
    return db_path

def get_current_count(db_path, secteur, source):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Filtrer la requête de comptage en fonction de la source demandée
        if source == 'maps':
            query = """
                SELECT COUNT(*) as c 
                FROM leads_bruts 
                WHERE (secteur = ? OR mot_cle LIKE ?) 
                AND (source = 'maps' OR source IS NULL)
            """
        elif source == 'ads':
            query = """
                SELECT COUNT(*) as c 
                FROM leads_bruts 
                WHERE (secteur = ? OR mot_cle LIKE ?) 
                AND source = 'ads'
            """
        else:
            return 0
            
        row = conn.execute(query, (secteur, f"%{secteur}%")).fetchone()
        return row['c'] if row else 0
    finally:
        conn.close()

def run_scraper(source, keyword, city, secteur, missing_leads, min_reviews, max_retries=3):
    if source == 'maps':
        cmd = [
            sys.executable,
            os.path.join("scraper", "main.py"),
            "--keyword", keyword,
            "--city", city,
            "--secteur", secteur,
            "--limit", str(missing_leads),
            "--min-reviews", str(min_reviews),
            "--multi-zone"
        ]
    elif source == 'ads':
        # Le SniperPipeline gère la source ads
        python_code = f"""
from scraper.sniper.pipeline import SniperPipeline
p = SniperPipeline()
result = p.run(
    keywords=['{keyword}'], 
    city='{city}', 
    secteur='{secteur}', 
    min_leads={missing_leads}
)
if result.get('error'):
    import sys
    sys.exit(1)
"""
        cmd = [sys.executable, "-c", python_code]
    else:
        print(f"[ERREUR] Source '{source}' inconnue.")
        return False
        
    print(f"\n[MONITOR] Lancement du scraper pour la source '{source.upper()}'")
    if source == 'maps':
        print(f"[MONITOR] Commande : {' '.join(cmd)}")
    
    for attempt in range(1, max_retries + 1):
        print(f"\n[MONITOR] Tentative {attempt}/{max_retries}...")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())
                
        rc = process.poll()
        if rc == 0:
            print(f"[MONITOR] Scraper '{source}' terminé avec succès.")
            return True
        else:
            print(f"[MONITOR] [ERREUR] Le scraper s'est terminé avec le code d'erreur {rc}.")
            if attempt < max_retries:
                print(f"[MONITOR] Nouvelle tentative dans 5 secondes...")
                time.sleep(5)
            else:
                print("[MONITOR] Nombre maximum de tentatives atteint. Échec du scraper.")
                return False

def main():
    parser = argparse.ArgumentParser(description="Renflouer les leads pour un secteur spécifique selon une source (Google Maps ou Google Ads).")
    parser.add_argument("--keyword", required=True, help="Mot-clé de recherche (ex: 'agence immobilière')")
    parser.add_argument("--city", required=True, help="Ville de recherche (ex: 'Paris')")
    parser.add_argument("--secteur", required=True, help="Le secteur d'activité (ex: 'immobilier')")
    parser.add_argument("--quota", type=int, required=True, help="Le nombre total de leads souhaité en base de données pour cette source")
    
    # Nouveaux paramètres ajoutés :
    parser.add_argument("--source", choices=['maps', 'ads'], default='maps', help="Source de leads ciblée : Google Maps ('maps') ou Google Ads ('ads')")
    parser.add_argument("--min-reviews", type=int, default=0, help="Nombre d'avis minimum requis (applicable uniquement à la source 'maps')")
    
    args = parser.parse_args()

    print(f"=== VERIFICATION DU QUOTA POUR LE SECTEUR '{args.secteur}' | SOURCE : {args.source.upper()} ===")
    
    db_path = get_db_path()
    if not os.path.exists(db_path):
        print(f"[ERREUR] Base de données introuvable à : {db_path}")
        sys.exit(1)

    current_count = get_current_count(db_path, args.secteur, args.source)
    print(f"Leads actuels pour '{args.secteur}' ({args.source}) : {current_count}")
    print(f"Objectif de quota : {args.quota}")

    if current_count >= args.quota:
        print("[OK] Quota déjà atteint pour cette source. Aucun scraping nécessaire.")
        sys.exit(0)

    missing = args.quota - current_count
    print(f"[INFO] Manque détecté : {missing} leads. Lancement du scraper...")

    success = run_scraper(
        source=args.source,
        keyword=args.keyword,
        city=args.city,
        secteur=args.secteur,
        missing_leads=missing,
        min_reviews=args.min_reviews
    )
    
    # Vérification finale
    if success:
        new_count = get_current_count(db_path, args.secteur, args.source)
        print(f"\n=== BILAN ===")
        print(f"Leads actuels pour '{args.secteur}' ({args.source}) : {new_count} / {args.quota}")
        if new_count >= args.quota:
            print("[SUCCÈS] Quota atteint !")
        else:
            print(f"[AVERTISSEMENT] Quota non atteint, il manque encore {args.quota - new_count} leads.")
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()

