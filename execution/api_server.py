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

# Firebase Cloud Messaging (optionnel)
firebase_enabled = False
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    
    cred = None
    
    # Option 1: JSON string dans variable d'environnement (pour Render/cloud)
    firebase_cred_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    if firebase_cred_json:
        try:
            cred_dict = json.loads(firebase_cred_json)
            cred = credentials.Certificate(cred_dict)
            print("✅ Firebase credentials chargées depuis FIREBASE_CREDENTIALS_JSON")
        except json.JSONDecodeError as e:
            print(f"⚠️ FIREBASE_CREDENTIALS_JSON invalide: {e}")
    
    # Option 2: Chemin vers fichier
    if not cred:
        firebase_cred_path = os.environ.get('FIREBASE_CREDENTIALS_PATH')
        if not firebase_cred_path:
            # Chercher dans les emplacements par défaut
            possible_paths = [
                Path(__file__).parent / 'firebase-credentials.json',
                Path(__file__).parent.parent / 'firebase-credentials.json',
                Path(__file__).parent / 'serviceAccountKey.json',
            ]
            for p in possible_paths:
                if p.exists():
                    firebase_cred_path = str(p)
                    break
        
        if firebase_cred_path and Path(firebase_cred_path).exists():
            cred = credentials.Certificate(firebase_cred_path)
            print(f"✅ Firebase credentials chargées depuis {firebase_cred_path}")
    
    if cred:
        firebase_admin.initialize_app(cred)
        firebase_enabled = True
        print("✅ Firebase Cloud Messaging activé")
    else:
        print("⚠️ Firebase credentials non trouvées - notifications désactivées")
except ImportError:
    print("⚠️ firebase-admin non installé - notifications désactivées")
except Exception as e:
    print(f"⚠️ Erreur initialisation Firebase: {e}")

# Stockage des tokens FCM (en mémoire - en prod utiliser une DB)
fcm_tokens = set()

app = Flask(__name__)
CORS(app)  # Permet les requêtes cross-origin depuis React

# État du scraping
scrape_status = {
    "is_running": False,
    "current_session_id": None,
    "started_at": None,
    "groups_scraping": [],
    "progress": None,
    "progress_percent": 0,  # 0-100 pour la barre de progression
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


def send_push_notification(title: str, body: str, data: dict = None):
    """Envoie une notification push à tous les devices enregistrés"""
    if not firebase_enabled:
        print(f"📱 [FCM désactivé] {title}: {body}")
        return False
    
    if not fcm_tokens:
        print("📱 Aucun device enregistré pour les notifications")
        return False
    
    success_count = 0
    failed_tokens = []
    
    for token in list(fcm_tokens):
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                token=token,
            )
            response = messaging.send(message)
            print(f"📱 Notification envoyée: {response}")
            success_count += 1
        except Exception as e:
            error_str = str(e)
            print(f"❌ Erreur envoi notification: {error_str}")
            # Supprimer les tokens invalides
            if "not found" in error_str.lower() or "invalid" in error_str.lower():
                failed_tokens.append(token)
    
    # Nettoyer les tokens invalides
    for token in failed_tokens:
        fcm_tokens.discard(token)
        print(f"🗑️ Token invalide supprimé")
    
    print(f"📱 Notifications: {success_count}/{len(fcm_tokens) + len(failed_tokens)} envoyées")
    return success_count > 0


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
        
        # === ÉTAPE 1: Chargement config (0-5%) ===
        scrape_status["progress_percent"] = 2
        add_log("📋 Chargement de la configuration...")
        config = load_config()
        all_groups = config.get('groups', [])
        add_log(f"✓ {len(all_groups)} groupes trouvés")
        scrape_status["progress_percent"] = 5
        
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
        
        # === ÉTAPE 2: Connexion Apify (5-10%) ===
        posts_per_group = config.get('settings', {}).get('posts_per_group', 50)
        add_log(f"⚙️ Configuration: {posts_per_group} posts/groupe")
        scrape_status["progress_percent"] = 8
        add_log("📡 Connexion à Apify...")
        scrape_status["progress_percent"] = 10
        add_log("⏳ Scraping Facebook en cours...")
        
        # === ÉTAPE 3: Scraping (10-60%) ===
        # Note: Apify ne donne pas de progression par groupe, donc on met 35% pendant le scraping
        scrape_status["progress_percent"] = 35
        items = run_apify_scrape(selected_groups, posts_per_group)
        scrape_status["progress_percent"] = 60
        
        if not items:
            add_log("⚠️ Aucun post récupéré")
            scrape_status["progress"] = "Aucun post récupéré"
            scrape_status["progress_percent"] = 100
            scrape_status["is_running"] = False
            return
        
        add_log(f"✅ {len(items)} posts récupérés depuis Facebook")
        scrape_status["progress"] = f"Transformation de {len(items)} posts..."
        scrape_status["progress_percent"] = 62
        
        # Transformer les données
        add_log("🔄 Transformation des données...")
        data = transform_apify_data(items, selected_groups)
        add_log(f"✓ {data['postsCount']} posts avec texte")
        scrape_status["progress_percent"] = 65
        
        # Sauvegarder
        add_log("💾 Sauvegarde des données...")
        timestamp = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
        output_dir = Path(__file__).parent.parent / '.tmp'
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f'api_scrape_{timestamp}.json'
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        add_log(f"📁 Fichier créé: api_scrape_{timestamp}.json")
        scrape_status["progress_percent"] = 68
        
        # === ÉTAPE 4: Analyse IA (68-85%) ===
        scrape_status["progress"] = "Analyse IA en cours..."
        add_log("🤖 Lancement de l'analyse IA...")
        scrape_status["progress_percent"] = 70
        add_log("⏳ GPT-4o-mini analyse les posts...")
        scrape_status["progress_percent"] = 75
        
        # Lancer l'analyse IA
        success = run_ai_analysis(output_file)
        scrape_status["progress_percent"] = 85
        
        if success:
            add_log("✓ Analyse IA terminée")
            analyzed_file = output_dir / f'ai_analyzed_api_scrape_{timestamp}.json'
            if analyzed_file.exists():
                add_log("📊 Chargement des résultats...")
                scrape_status["progress_percent"] = 87
                with open(analyzed_file, 'r', encoding='utf-8') as f:
                    results = json.load(f)
                
                opportunities = results.get('opportunities', [])
                group_names = [g['name'] for g in selected_groups]
                
                add_log(f"🎯 {len(opportunities)} opportunités détectées")
                scrape_status["progress_percent"] = 88
                
                if opportunities:
                    # Afficher un aperçu des opportunités trouvées
                    for i, opp in enumerate(opportunities[:3]):
                        category = opp.get('ai_analysis', {}).get('category', '?')
                        add_log(f"   #{i+1} [{category}] {opp.get('author', 'Inconnu')[:20]}")
                    if len(opportunities) > 3:
                        add_log(f"   ... et {len(opportunities) - 3} autres")
                
                # === ÉTAPE 5: Envoi Supabase (88-100%) ===
                scrape_status["progress"] = f"Envoi de {len(opportunities)} opportunités à Supabase..."
                scrape_status["progress_percent"] = 90
                add_log("📤 Connexion à Supabase...")
                add_log("⏳ Envoi des données...")
                scrape_status["progress_percent"] = 92
                
                # Calculer le coût Apify
                # Pricing: $4.00 / 1000 posts + $1.00 / 1000 (date filter) + $0.005 (actor start)
                total_posts_scraped = len(items)  # Nombre TOTAL de posts avant filtrage IA
                cost_posts = (total_posts_scraped / 1000) * 4.00
                cost_date_filter = (total_posts_scraped / 1000) * 1.00
                cost_actor_start = 0.005
                apify_cost = round(cost_posts + cost_date_filter + cost_actor_start, 4)
                add_log(f"💰 Coût Apify estimé: ${apify_cost:.4f}")
                
                # Envoyer à Supabase avec le coût
                send_to_supabase(
                    opportunities,
                    groups_scraped=group_names,
                    started_at=scrape_status["started_at"],
                    cost=apify_cost  # ← NOUVEAU: envoi du coût
                )
                scrape_status["progress_percent"] = 98
                
                add_log("✓ Données envoyées à Supabase")
                
                scrape_status["last_result"] = {
                    "session_id": session_id,
                    "total_posts": data['postsCount'],
                    "opportunities_found": len(opportunities),
                    "groups_scraped": group_names,
                    "completed_at": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
                    "cost": apify_cost  # ← Coût Apify
                }
        
        # === TERMINÉ (100%) ===
        scrape_status["progress_percent"] = 100
        add_log("🏁 Scraping terminé avec succès!")
        add_log(f"📈 Résumé: {data['postsCount']} posts → {len(opportunities) if success else 0} opportunités")
        scrape_status["progress"] = "Terminé!"
        
        # Envoyer une notification push
        opp_count = len(opportunities) if success else 0
        if opp_count > 0:
            send_push_notification(
                title="🎉 Scraping terminé!",
                body=f"{opp_count} nouvelle{'s' if opp_count > 1 else ''} opportunité{'s' if opp_count > 1 else ''} trouvée{'s' if opp_count > 1 else ''}",
                data={
                    "type": "scrape_complete",
                    "opportunities_count": str(opp_count),
                    "session_id": session_id
                }
            )
        else:
            send_push_notification(
                title="✅ Scraping terminé",
                body="Aucune nouvelle opportunité cette fois",
                data={"type": "scrape_complete", "opportunities_count": "0"}
            )
        
    except Exception as e:
        add_log(f"❌ Erreur: {str(e)}")
        scrape_status["progress"] = f"Erreur: {str(e)}"
        scrape_status["progress_percent"] = 100  # Marquer comme terminé même en cas d'erreur
    
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
        "progress_percent": 0,  # Reset à 0
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


@app.route('/', methods=['GET', 'HEAD'])
def root():
    """Root endpoint - utilisé par Render pour le health check"""
    return jsonify({
        "service": "LeadSwipe API",
        "status": "healthy",
        "version": "1.1.0",
        "firebase_enabled": firebase_enabled,
        "endpoints": ["/groups", "/scrape", "/status", "/health", "/register-device", "/test-notification"]
    })


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')})


@app.route('/register-device', methods=['POST'])
def register_device():
    """Enregistre un device pour les notifications push"""
    data = request.get_json() or {}
    fcm_token = data.get('fcm_token')
    
    if not fcm_token:
        return jsonify({
            "success": False,
            "error": "fcm_token requis"
        }), 400
    
    fcm_tokens.add(fcm_token)
    print(f"📱 Device enregistré (total: {len(fcm_tokens)})")
    
    return jsonify({
        "success": True,
        "message": "Device enregistré pour les notifications",
        "firebase_enabled": firebase_enabled,
        "total_devices": len(fcm_tokens)
    })


@app.route('/unregister-device', methods=['POST'])
def unregister_device():
    """Désenregistre un device des notifications push"""
    data = request.get_json() or {}
    fcm_token = data.get('fcm_token')
    
    if fcm_token and fcm_token in fcm_tokens:
        fcm_tokens.discard(fcm_token)
        print(f"📱 Device désenregistré (total: {len(fcm_tokens)})")
    
    return jsonify({
        "success": True,
        "message": "Device désenregistré",
        "total_devices": len(fcm_tokens)
    })


@app.route('/test-notification', methods=['POST'])
def test_notification():
    """Endpoint de test pour les notifications (développement uniquement)"""
    data = request.get_json() or {}
    title = data.get('title', '🔔 Test LeadSwipe')
    body = data.get('body', 'Ceci est une notification de test!')
    
    success = send_push_notification(
        title=title,
        body=body,
        data={"type": "test"}
    )
    
    return jsonify({
        "success": success,
        "firebase_enabled": firebase_enabled,
        "registered_devices": len(fcm_tokens),
        "message": "Notification envoyée" if success else "Échec ou aucun device"
    })


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 API Server pour Facebook Scraping")
    print("="*60)
    print(f"\n📱 Firebase: {'✅ Activé' if firebase_enabled else '❌ Désactivé'}")
    print("\nEndpoints disponibles:")
    print("  GET  /groups           - Liste des groupes configurés")
    print("  POST /scrape           - Déclencher un scrape")
    print("  GET  /status           - Status du scrape en cours")
    print("  GET  /health           - Health check")
    print("  POST /register-device  - Enregistrer device pour push")
    print("  POST /test-notification - Tester les notifications")
    print("\nExemples:")
    print('  curl http://localhost:5001/groups')
    print('  curl -X POST http://localhost:5001/scrape -H "Content-Type: application/json" -d \'{"group_ids": "all"}\'')
    print('  curl http://localhost:5001/status')
    print("\n" + "="*60 + "\n")
    
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
