#!/usr/bin/env python3
"""
auto_scrape.py - Système automatisé de scraping Facebook

Ce script:
1. Charge la liste des groupes depuis config/groups.json
2. Lance Apify pour scraper tous les groupes
3. Attend les résultats
4. Lance l'analyse IA
5. Sauvegarde les opportunités
6. Envoie une notification (optionnel)
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Couleurs ANSI
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'


def load_config():
    """Charge la configuration des groupes"""
    config_path = Path(__file__).parent.parent / 'config' / 'groups.json'
    
    if not config_path.exists():
        print(f"{Colors.RED}❌ Fichier config/groups.json non trouvé{Colors.END}")
        sys.exit(1)
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def run_apify_scrape(groups: list, posts_per_group: int = 50):
    """Lance le scraping via Apify"""
    try:
        from apify_client import ApifyClient
    except ImportError:
        print(f"{Colors.RED}❌ apify-client non installé. Run: pip install apify-client{Colors.END}")
        sys.exit(1)
    
    token = os.getenv('APIFY_TOKEN')
    if not token:
        print(f"{Colors.RED}❌ APIFY_TOKEN non trouvé dans .env{Colors.END}")
        sys.exit(1)
    
    client = ApifyClient(token)
    
    # Préparer les URLs
    start_urls = [{"url": g["url"]} for g in groups]
    
    print(f"\n{Colors.CYAN}📡 Lancement du scraping Apify...{Colors.END}")
    print(f"   Groupes: {len(groups)}")
    print(f"   Posts/groupe: {posts_per_group}")
    
    for g in groups:
        print(f"   • {g['name']}")
    
    # Configuration de l'Actor (paramètres selon doc API Apify)
    run_input = {
        "startUrls": start_urls,
        "resultsLimit": posts_per_group,  # Limite le nombre total de posts
        "sort": "recent"
    }
    
    # Lancer l'Actor
    print(f"\n{Colors.YELLOW}⏳ Scraping en cours...{Colors.END}")
    
    try:
        # Utiliser facebook-groups-scraper (confirmé par l'utilisateur)
        run = client.actor("apify/facebook-groups-scraper").call(run_input=run_input)
    except Exception as e:
        print(f"{Colors.RED}❌ Erreur Apify: {e}{Colors.END}")
        return None
    
    # Récupérer les résultats
    print(f"{Colors.GREEN}✅ Scraping terminé!{Colors.END}")
    
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    print(f"   Posts récupérés: {len(items)}")
    
    return items


def transform_apify_data(items: list, groups: list) -> dict:
    """Transforme les données Apify en format standard"""
    posts = []
    
    # Debug: afficher ce qu'on reçoit d'Apify
    print(f"\n{Colors.YELLOW}🔍 DEBUG: Apify items reçus: {len(items)}{Colors.END}")
    for i, item in enumerate(items[:3]):  # Afficher les 3 premiers
        print(f"   Item {i+1}: {list(item.keys())[:8]}...")
        # Selon la doc Apify, le champ est "postText"
        if 'postText' in item:
            text_preview = item['postText'][:50] if item['postText'] else "(vide)"
            print(f"      postText: {text_preview}...")
        elif 'text' in item:
            text_preview = item['text'][:50] if item['text'] else "(vide)"
            print(f"      text: {text_preview}...")
        else:
            print(f"      ⚠️ Ni 'postText' ni 'text' trouvé dans les clés")
    
    for item in items:
        # Mapper selon les champs de la doc Apify:
        # postText, postUrl, profileName, profileId, likesCount, commentsCount, time, topComments
        post = {
            "id": f"apify_{item.get('facebookId', item.get('id', ''))}",
            "postId": item.get('facebookId', item.get('id', '')),
            "author": item.get('profileName', item.get('user', {}).get('name', 'Inconnu')),
            "authorProfileUrl": item.get('profileUrl', item.get('user', {}).get('url', '')),
            "timestamp": item.get('time', ''),
            "text": item.get('postText', item.get('text', item.get('message', ''))),
            "postUrl": item.get('postUrl', item.get('url', '')),
            "hasMedia": bool(item.get('media')),
            "mediaType": item.get('media', [{}])[0].get('type') if item.get('media') else None,
            "source": "apify",
            "capturedAt": datetime.now().isoformat(),
            "likesCount": item.get('likesCount', item.get('likes', 0)),
            "commentsCount": item.get('commentsCount', item.get('comments', 0)),
            "sharesCount": item.get('sharesCount', item.get('shares', 0)),
            "topComments": item.get('topComments', [])[:3] if item.get('topComments') else []
        }
        
        if post['text']:  # Ne garder que les posts avec du texte
            posts.append(post)
    
    # Extraire les noms de groupes
    group_names = [g['name'] for g in groups]
    
    return {
        "extractedAt": datetime.now().isoformat(),
        "groupUrls": [g['url'] for g in groups],
        "groupNames": group_names,
        "postsCount": len(posts),
        "source": "apify-auto",
        "posts": posts
    }


def run_ai_analysis(json_file: Path):
    """Lance l'analyse IA sur les posts"""
    print(f"\n{Colors.CYAN}🤖 Lancement de l'analyse IA...{Colors.END}")
    
    # Importer et exécuter le script d'analyse
    import subprocess
    result = subprocess.run(
        [sys.executable, str(Path(__file__).parent / 'analyze_posts_ai.py'), str(json_file)],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    
    return result.returncode == 0


def send_to_supabase(opportunities: list, groups_scraped: list = None, started_at: str = None) -> bool:
    """Envoie les opportunités à Supabase via Edge Function webhook"""
    import requests
    
    WEBHOOK_URL = "https://axkfgpsadfgadbqtfhlf.supabase.co/functions/v1/ingest-opportunity"
    
    if not opportunities:
        print(f"{Colors.YELLOW}⚠️ Aucune opportunité à envoyer à Supabase{Colors.END}")
        return True
    
    print(f"\n{Colors.CYAN}📤 Envoi de {len(opportunities)} opportunités à Supabase...{Colors.END}")
    
    # Construire le payload avec les infos de session
    today = datetime.now().strftime('%d %b')
    num_groups = len(groups_scraped) if groups_scraped else 0
    num_opps = len(opportunities)
    
    # Titre court et descriptif
    if num_groups == 1:
        session_title = f"{groups_scraped[0][:20]} - {today}"
    else:
        session_title = f"Scrape {num_groups} groupes - {today}"
    
    payload = {
        "session_title": session_title,
        "groups_scraped": groups_scraped or [],
        "started_at": started_at or datetime.now().isoformat(),
        "opportunities": opportunities
    }
    
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"{Colors.GREEN}✅ Supabase: {result.get('message', 'Success')}{Colors.END}")
            if result.get('session_id'):
                print(f"   Session ID: {result.get('session_id')}")
            return True
        else:
            print(f"{Colors.RED}❌ Erreur Supabase ({response.status_code}): {response.text}{Colors.END}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"{Colors.RED}❌ Erreur connexion Supabase: {e}{Colors.END}")
        return False


def send_notification(opportunities: list, total_posts: int, groups_scraped: list = None, started_at: str = None):
    """Envoie une notification avec les résultats (extensible)"""
    print(f"\n{Colors.HEADER}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}📬 RÉSUMÉ{Colors.END}")
    print(f"{Colors.HEADER}{'='*60}{Colors.END}")
    
    print(f"\n{Colors.CYAN}Posts scrapés:{Colors.END} {total_posts}")
    print(f"{Colors.GREEN}Opportunités:{Colors.END} {len(opportunities)}")
    
    if opportunities:
        print(f"\n{Colors.BOLD}🎯 Top opportunités:{Colors.END}")
        for i, opp in enumerate(opportunities[:5], 1):
            category = opp.get('ai_analysis', {}).get('category', '?')
            summary = opp.get('ai_analysis', {}).get('summary', '')[:60]
            print(f"   {i}. [{category}] {summary}...")
        
        # Envoyer à Supabase avec les infos de session
        send_to_supabase(opportunities, groups_scraped=groups_scraped, started_at=started_at)
    
    # TODO: Ajouter ici l'envoi par email/Slack/SMS
    # - Email: via smtplib ou SendGrid
    # - Slack: via webhook
    # - SMS: via Twilio


def main():
    print(f"\n{Colors.HEADER}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}🚀 AUTO-SCRAPE FACEBOOK GROUPS{Colors.END}")
    print(f"{Colors.HEADER}{'='*60}{Colors.END}")
    
    # Capturer le timestamp de début pour la session (en UTC avec timezone)
    from datetime import timezone
    started_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    print(f"\n{Colors.CYAN}Heure:{Colors.END} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. Charger la config
    config = load_config()
    groups = config.get('groups', [])
    posts_per_group = config.get('settings', {}).get('posts_per_group', 50)
    
    if not groups:
        print(f"{Colors.RED}❌ Aucun groupe configuré dans config/groups.json{Colors.END}")
        sys.exit(1)
    
    # Extraire les noms des groupes pour la session
    group_names = [g['name'] for g in groups]
    print(f"\n{Colors.CYAN}Groupes configurés:{Colors.END} {len(groups)}")
    
    # 2. Lancer le scraping
    items = run_apify_scrape(groups, posts_per_group)
    
    if not items:
        print(f"{Colors.YELLOW}⚠️ Aucun post récupéré{Colors.END}")
        sys.exit(1)
    
    # 3. Transformer et sauvegarder les données
    data = transform_apify_data(items, groups)
    
    timestamp = datetime.now().strftime('%Y-%m-%dT%H-%M-%S')
    output_dir = Path(__file__).parent.parent / '.tmp'
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / f'auto_scrape_{timestamp}.json'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n{Colors.GREEN}✅ Données sauvegardées: {output_file}{Colors.END}")
    
    # 4. Lancer l'analyse IA
    success = run_ai_analysis(output_file)
    
    if success:
        # Charger les résultats de l'analyse
        analyzed_file = output_dir / f'ai_analyzed_auto_scrape_{timestamp}.json'
        if analyzed_file.exists():
            with open(analyzed_file, 'r', encoding='utf-8') as f:
                results = json.load(f)
            
            opportunities = results.get('opportunities', [])
            send_notification(opportunities, data['postsCount'], groups_scraped=group_names, started_at=started_at)
    
    print(f"\n{Colors.GREEN}✅ Auto-scrape terminé!{Colors.END}\n")


if __name__ == '__main__':
    main()

