# -*- coding: utf-8 -*-
import subprocess
import sys
import argparse
import time

# Forcer l'encodage UTF-8 pour la sortie standard (Windows support)
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

def run_command(command):
    """Exécute une commande système et affiche la sortie en temps réel."""
    print(f"\nExécution : {' '.join(command)}")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    
    if process.stdout:
        for line in process.stdout:
            print(line, end="")
    
    process.wait()
    return process.returncode

def main():
    parser = argparse.ArgumentParser(description="Orchestrateur Automatique Prospection Machine")
    parser.add_argument("--keyword", required=True, help="Métier à rechercher")
    parser.add_argument("--city", required=True, help="Ville de recherche")
    parser.add_argument("--limit", type=int, default=10, help="Nombre de leads à collecter")
    parser.add_argument("--dry-run", action="store_true", help="Mode test sans écriture Sheets")
    
    args = parser.parse_args()
    
    print("="*60)
    print("🚀 DÉMARRAGE DE LA MACHINE DE PROSPECTION")
    print(f"📍 Cible : {args.keyword} à {args.city}")
    print(f"📊 Limite : {args.limit} leads")
    print("="*60)
    
    start_time = time.time()
    
    # 1. SCRAPING
    scraper_cmd = [
        sys.executable, "scraper/main.py",
        "--keyword", args.keyword,
        "--city", args.city,
        "--limit", str(args.limit)
    ]
    if args.dry_run:
        scraper_cmd.append("--dry-run")
        
    res_scraper = run_command(scraper_cmd)
    if res_scraper != 0:
        print("\n❌ Le scrapper a rencontré une erreur.")
        sys.exit(1)
        
    print("\n✅ Scraping terminé. Passage à l'audit technique...")
    time.sleep(1)
    
    # 2. AUDIT TECHNIQUE
    auditor_cmd = [
        sys.executable, "auditeur/main.py",
        "--limit", str(args.limit)
    ]
    res_audit = run_command(auditor_cmd)
    if res_audit != 0:
        print("\n❌ L'auditeur technique a rencontré une erreur.")
        sys.exit(1)
        
    print("\n✅ Audit technique terminé. Passage au copywriter (Jean-Marc)...")
    time.sleep(1)

    # 3. COPYWRITER (Jean-Marc)
    copywriter_cmd = [
        sys.executable, "copywriter/main.py",
        "--limit", str(args.limit)
    ]
    res_copy = run_command(copywriter_cmd)
    if res_copy != 0:
        print("\n❌ Le copywriter a rencontré une erreur.")
        sys.exit(1)

    print("\n✅ Copywriting terminé. Passage à la génération des rapports PDF...")
    time.sleep(1)

    # 4. REPORTER (PDF)
    reporter_cmd = [
        sys.executable, "reporter/main.py",
        "--limit", str(args.limit)
    ]
    res_report = run_command(reporter_cmd)
    if res_report != 0:
        print("\n❌ Le reporter a rencontré une erreur.")
        # On ne s'arrête pas forcément ici car c'est facultatif
        
    end_time = time.time()
    duration = end_time - start_time
    
    print("\n" + "="*60)
    print(f"🎉 MISSION TERMINÉE EN {duration:.1f} SECONDES")
    print("Consultez vos Google Sheets : 'leads_bruts' et 'leads_audites'")
    print("="*60)

if __name__ == "__main__":
    main()
