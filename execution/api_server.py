#!/usr/bin/env python3
"""
api_server.py - API pour déclencher le scraping à distance

Endpoints:
- GET /groups - Liste des groupes configurés
- POST /scrape - Déclencher un scrape
- GET /status - Status du scrape en cours

Usage:
    python api_server.py
    # Server runs on http://localhost:5001
"""

import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)
CORS(app)  # Permet les requêtes cross-origin depuis React

# État du scraping
scrape_status = {
    "is_running": False,
    "current_session_id": None,
    "started_at": None,
    "groups_scraping": [],
    "progress": None,
    "last_result": None,
    "logs": []  # Buffer de logs pour affichage temps réel
}

def add_log(message: str):
    """Ajoute un message au buffer de logs avec timestamp"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_entry = f"[{timestamp}] {message}"
    scrape_status["logs"].append(log_entry)
    # Garder seulement les 50 derniers logs
    if len(scrape_status["logs"]) > 50:
        scrape_status["logs"] = scrape_status["logs"][-50:]
    print(log_entry)  # Aussi afficher dans la console


def load_groups():
    """Charge la liste des groupes depuis config/groups.json"""
    config_path = Path(__file__).parent.parent / 'config' / 'groups.json'
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    groups = []
    for i, g in enumerate(config.get('groups', [])):
        groups.append({
            "id": f"group_{i+1}",
            "name": g['name'],
            "url": g['url']
        })
    return groups


def run_scrape_async(group_ids, session_id):
    """Lance le scraping en arrière-plan"""
    global scrape_status
    
    try:
        # Importer le module de scraping
        sys.path.insert(0, str(Path(__file__).parent))
        from auto_scrape import load_config, run_apify_scrape, transform_apify_data, run_ai_analysis, send_to_supabase
        
        add_log("📋 Chargement de la configuration...")
        config = load_config()
        all_groups = config.get('groups', [])
        add_log(f"✓ {len(all_groups)} groupes trouvés")
        
        # Filtrer les groupes si spécifié
        if group_ids != "all":
            all_groups_with_ids = list(enumerate(all_groups))
            selected_groups = [g for i, g in all_groups_with_ids if f"group_{i+1}" in group_ids]
            add_log(f"🔍 Filtrage: {len(selected_groups)} groupe(s) sélectionné(s)")
        else:
            selected_groups = all_groups
            add_log(f"🔍 Mode: Tous les groupes ({len(selected_groups)})")
        
        scrape_status["groups_scraping"] = [g['name'] for g in selected_groups]
        scrape_status["progress"] = "Scraping en cours via Apify..."
        add_log(f"🚀 Démarrage scraping de {len(selected_groups)} groupe(s)")
        for g in selected_groups:
            add_log(f"   • {g['name']}")
        
        # Lancer le scraping
        posts_per_group = config.get('settings', {}).get('posts_per_group', 50)
        add_log(f"⚙️ Configuration: {posts_per_group} posts/groupe")
        add_log("📡 Connexion à Apify...")
        add_log("⏳ Scraping Facebook en cours...")
        
        items = run_apify_scrape(selected_groups, posts_per_group)
        
        if not items:
            add_log("⚠️ Aucun post récupéré")
            scrape_status["progress"] = "Aucun post récupéré"
            scrape_status["is_running"] = False
            return
        
        add_log(f"✅ {len(items)} posts récupérés depuis Facebook")
        scrape_status["progress"] = f"Transformation de {len(items)} posts..."
        
        # Transformer les données
        add_log("🔄 Transformation des données...")
        data = transform_apify_data(items, selected_groups)
        add_log(f"✓ {data['postsCount']} posts avec texte")
        
        # Sauvegarder
        add_log("💾 Sauvegarde des données...")
        timestamp = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
        output_dir = Path(__file__).parent.parent / '.tmp'
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f'api_scrape_{timestamp}.json'
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        add_log(f"📁 Fichier créé: api_scrape_{timestamp}.json")
        scrape_status["progress"] = "Analyse IA en cours..."
        add_log("🤖 Lancement de l'analyse IA...")
        add_log("⏳ GPT-4o-mini analyse les posts...")
        
        # Lancer l'analyse IA
        success = run_ai_analysis(output_file)
        
        if success:
            add_log("✓ Analyse IA terminée")
            analyzed_file = output_dir / f'ai_analyzed_api_scrape_{timestamp}.json'
            if analyzed_file.exists():
                add_log("📊 Chargement des résultats...")
                with open(analyzed_file, 'r', encoding='utf-8') as f:
                    results = json.load(f)
                
                opportunities = results.get('opportunities', [])
                group_names = [g['name'] for g in selected_groups]
                
                add_log(f"🎯 {len(opportunities)} opportunités détectées")
                
                if opportunities:
                    # Afficher un aperçu des opportunités trouvées
                    for i, opp in enumerate(opportunities[:3]):
                        category = opp.get('ai_analysis', {}).get('category', '?')
                        add_log(f"   #{i+1} [{category}] {opp.get('author', 'Inconnu')[:20]}")
                    if len(opportunities) > 3:
                        add_log(f"   ... et {len(opportunities) - 3} autres")
                
                scrape_status["progress"] = f"Envoi de {len(opportunities)} opportunités à Supabase..."
                add_log("📤 Connexion à Supabase...")
                add_log("⏳ Envoi des données...")
                
                # Envoyer à Supabase
                send_to_supabase(
                    opportunities,
                    groups_scraped=group_names,
                    started_at=scrape_status["started_at"]
                )
                
                add_log("✓ Données envoyées à Supabase")
                
                scrape_status["last_result"] = {
                    "session_id": session_id,
                    "total_posts": data['postsCount'],
                    "opportunities_found": len(opportunities),
                    "groups_scraped": group_names,
                    "completed_at": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                }
        
        add_log("🏁 Scraping terminé avec succès!")
        add_log(f"📈 Résumé: {data['postsCount']} posts → {len(opportunities) if success else 0} opportunités")
        scrape_status["progress"] = "Terminé!"
        
    except Exception as e:
        add_log(f"❌ Erreur: {str(e)}")
        scrape_status["progress"] = f"Erreur: {str(e)}"
    
    finally:
        scrape_status["is_running"] = False


@app.route('/groups', methods=['GET'])
def get_groups():
    """Retourne la liste des groupes configurés"""
    try:
        groups = load_groups()
        return jsonify({
            "success": True,
            "groups": groups,
            "total": len(groups)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/scrape', methods=['POST'])
def start_scrape():
    """Déclenche un nouveau scrape"""
    global scrape_status
    
    if scrape_status["is_running"]:
        return jsonify({
            "success": False,
            "error": "Un scrape est déjà en cours",
            "current_session_id": scrape_status["current_session_id"]
        }), 409
    
    data = request.get_json() or {}
    group_ids = data.get('group_ids', 'all')
    
    # Valider les group_ids
    if group_ids != "all":
        available_groups = load_groups()
        available_ids = [g['id'] for g in available_groups]
        invalid_ids = [gid for gid in group_ids if gid not in available_ids]
        if invalid_ids:
            return jsonify({
                "success": False,
                "error": f"Group IDs invalides: {invalid_ids}"
            }), 400
    
    # Créer une nouvelle session (reset les logs)
    session_id = str(uuid.uuid4())
    scrape_status = {
        "is_running": True,
        "current_session_id": session_id,
        "started_at": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        "groups_scraping": [],
        "progress": "Initialisation...",
        "last_result": None,
        "logs": []  # Reset les logs
    }
    
    # Lancer le scrape en arrière-plan
    thread = threading.Thread(target=run_scrape_async, args=(group_ids, session_id))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "message": "Scrape démarré",
        "session_id": session_id,
        "status_url": "/status"
    })


@app.route('/status', methods=['GET'])
def get_status():
    """Retourne le status du scrape en cours"""
    return jsonify({
        "success": True,
        **scrape_status
    })


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')})


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 API Server pour Facebook Scraping")
    print("="*60)
    print("\nEndpoints disponibles:")
    print("  GET  /groups  - Liste des groupes configurés")
    print("  POST /scrape  - Déclencher un scrape")
    print("  GET  /status  - Status du scrape en cours")
    print("  GET  /health  - Health check")
    print("\nExemples:")
    print('  curl http://localhost:5001/groups')
    print('  curl -X POST http://localhost:5001/scrape -H "Content-Type: application/json" -d \'{"group_ids": "all"}\'')
    print('  curl http://localhost:5001/status')
    print("\n" + "="*60 + "\n")
    
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
