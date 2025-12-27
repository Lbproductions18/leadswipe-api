#!/usr/bin/env python3
"""
scheduler.py - Planificateur pour le scraping automatique

Ce script tourne en continu et lance le scraping aux heures configurées.
Peut aussi être utilisé pour un run manuel.

Usage:
    python scheduler.py          # Lance le scheduler (tourne en continu)
    python scheduler.py --now    # Lance un scraping immédiatement
    python scheduler.py --test   # Mode test (vérifie la config sans scraper)
"""

import sys
import time
import schedule
from datetime import datetime
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent))

from auto_scrape import main as run_scrape


def job():
    """Job de scraping planifié"""
    print(f"\n{'='*60}")
    print(f"⏰ Scraping planifié déclenché: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    try:
        run_scrape()
    except Exception as e:
        print(f"❌ Erreur lors du scraping: {e}")


def run_scheduler():
    """Lance le scheduler qui tourne en continu"""
    print("\n🕐 Scheduler démarré!")
    print("   Scraping planifié à: 12:00 et 19:00")
    print("   Ctrl+C pour arrêter\n")
    
    # Planifier les jobs
    schedule.every().day.at("12:00").do(job)
    schedule.every().day.at("19:00").do(job)
    
    # Afficher le prochain run
    print(f"   Prochain scraping: {schedule.next_run()}")
    
    # Boucle principale
    while True:
        schedule.run_pending()
        time.sleep(60)  # Vérifier chaque minute


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == '--now':
            print("🚀 Lancement immédiat du scraping...")
            run_scrape()
        elif sys.argv[1] == '--test':
            print("🧪 Mode test - Vérification de la configuration...")
            import json
            config_path = Path(__file__).parent.parent / 'config' / 'groups.json'
            
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                
                print(f"\n✅ Configuration trouvée:")
                print(f"   Groupes: {len(config.get('groups', []))}")
                for g in config.get('groups', []):
                    print(f"   • {g['name']}")
                
                print(f"\n   Posts/groupe: {config.get('settings', {}).get('posts_per_group', 50)}")
                
                # Vérifier les variables d'environnement
                import os
                from dotenv import load_dotenv
                load_dotenv()
                
                apify = "✅" if os.getenv('APIFY_TOKEN') else "❌"
                openai = "✅" if os.getenv('OPENAI_API_KEY') else "❌"
                
                print(f"\n   APIFY_TOKEN: {apify}")
                print(f"   OPENAI_API_KEY: {openai}")
            else:
                print(f"❌ Config non trouvée: {config_path}")
        else:
            print(__doc__)
    else:
        run_scheduler()


if __name__ == '__main__':
    main()







