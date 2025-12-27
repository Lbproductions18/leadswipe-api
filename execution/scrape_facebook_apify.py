#!/usr/bin/env python3
"""
Facebook Group Scraper via Apify API
Scrape les posts d'un groupe Facebook et les analyse avec OpenAI

Usage:
    python scrape_facebook_apify.py
    python scrape_facebook_apify.py --group "https://www.facebook.com/groups/EntrepreneursQc"
    python scrape_facebook_apify.py --limit 100 --analyze
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from pathlib import Path

# Ajouter le dossier parent au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from apify_client import ApifyClient
except ImportError:
    print("❌ Module 'apify-client' non installé.")
    print("   Exécute: pip install apify-client")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️ python-dotenv non installé, utilise les variables d'environnement système")

# Configuration
APIFY_TOKEN = os.getenv('APIFY_TOKEN')
DEFAULT_GROUP_URL = "https://www.facebook.com/groups/EntrepreneursQc"
DEFAULT_LIMIT = 50
OUTPUT_DIR = Path(__file__).parent.parent / ".tmp"


def scrape_facebook_group(group_url: str, limit: int = 50, sort: str = "recent") -> list:
    """
    Scrape un groupe Facebook via Apify
    
    Args:
        group_url: URL du groupe Facebook
        limit: Nombre max de posts à récupérer
        sort: 'recent', 'relevant', ou 'activity'
    
    Returns:
        Liste des posts
    """
    if not APIFY_TOKEN:
        print("❌ APIFY_TOKEN non configuré!")
        print("   1. Crée un compte sur https://apify.com")
        print("   2. Va dans Settings > Integrations > API tokens")
        print("   3. Ajoute dans .env: APIFY_TOKEN=ton_token")
        sys.exit(1)
    
    print(f"🔍 Scraping du groupe: {group_url}")
    print(f"   Limite: {limit} posts")
    print(f"   Tri: {sort}")
    print()
    
    # Initialiser le client Apify
    client = ApifyClient(APIFY_TOKEN)
    
    # Configuration du scraper
    run_input = {
        "startUrls": [{"url": group_url}],
        "resultsLimit": limit,
        "sort": sort,
        "searchQuery": "",
        "maxComments": 5,  # Top 5 commentaires par post
    }
    
    print("⏳ Lancement du scraper Apify...")
    print("   (Cela peut prendre 1-5 minutes selon le nombre de posts)")
    print()
    
    # Lancer le scraper
    run = client.actor("apify/facebook-groups-scraper").call(run_input=run_input)
    
    # Récupérer les résultats
    print("📥 Récupération des résultats...")
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    
    print(f"✅ {len(items)} posts récupérés!")
    print()
    
    return items


def convert_to_standard_format(apify_posts: list, group_url: str) -> dict:
    """
    Convertit les posts Apify au format standard de notre extension
    """
    posts = []
    
    for item in apify_posts:
        post = {
            "id": f"apify_{item.get('postId', '')}",
            "postId": item.get('postId', ''),
            "author": item.get('profileName', item.get('authorName', 'Inconnu')),
            "authorProfileUrl": item.get('profileUrl', ''),
            "timestamp": item.get('timestamp', ''),
            "text": item.get('postText', item.get('text', '')),
            "postUrl": item.get('postUrl', item.get('url', '')),
            "hasMedia": bool(item.get('media') or item.get('imageUrls') or item.get('videoUrl')),
            "mediaType": "video" if item.get('videoUrl') else ("image" if item.get('imageUrls') else None),
            "source": "apify",
            "capturedAt": datetime.now().isoformat(),
            # Données supplémentaires d'Apify
            "likesCount": item.get('likesCount', 0),
            "commentsCount": item.get('commentsCount', 0),
            "sharesCount": item.get('sharesCount', 0),
            "topComments": item.get('topComments', [])
        }
        
        # Ne garder que les posts avec du texte
        if post["text"] and len(post["text"]) > 10:
            posts.append(post)
    
    # Extraire le nom du groupe depuis l'URL
    group_name = "Unknown Group"
    if "/groups/" in group_url:
        group_name = group_url.split("/groups/")[-1].rstrip("/").replace("-", " ").title()
    
    return {
        "extractedAt": datetime.now().isoformat(),
        "groupUrl": group_url,
        "groupName": group_name,
        "postsCount": len(posts),
        "source": "apify",
        "posts": posts
    }


def save_results(data: dict, output_dir: Path) -> Path:
    """Sauvegarde les résultats en JSON"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    filename = f"facebook_posts_apify_{timestamp}.json"
    filepath = output_dir / filename
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"💾 Résultats sauvegardés: {filepath}")
    return filepath


def run_analysis(filepath: Path):
    """Lance l'analyse AI sur les posts"""
    print()
    print("🤖 Lancement de l'analyse AI...")
    print("=" * 50)
    
    # Importer et lancer analyze_posts_ai
    try:
        from analyze_posts_ai import analyze_posts_with_ai, load_posts
        
        data = load_posts(str(filepath))
        if data:
            analyze_posts_with_ai(data)
    except ImportError as e:
        print(f"⚠️ Impossible d'importer analyze_posts_ai: {e}")
        print("   Lance manuellement: python analyze_posts_ai.py " + str(filepath))
    except Exception as e:
        print(f"❌ Erreur lors de l'analyse: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Scrape un groupe Facebook via Apify et analyse les posts"
    )
    parser.add_argument(
        "--group", "-g",
        default=DEFAULT_GROUP_URL,
        help=f"URL du groupe Facebook (défaut: {DEFAULT_GROUP_URL})"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Nombre max de posts à récupérer (défaut: {DEFAULT_LIMIT})"
    )
    parser.add_argument(
        "--sort", "-s",
        choices=["recent", "relevant", "activity"],
        default="recent",
        help="Tri des posts (défaut: recent)"
    )
    parser.add_argument(
        "--analyze", "-a",
        action="store_true",
        help="Lancer l'analyse AI après le scraping"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Dossier de sortie (défaut: {OUTPUT_DIR})"
    )
    
    args = parser.parse_args()
    
    print("=" * 50)
    print("🔍 Facebook Group Scraper (via Apify)")
    print("=" * 50)
    print()
    
    # Scraper le groupe
    apify_posts = scrape_facebook_group(
        group_url=args.group,
        limit=args.limit,
        sort=args.sort
    )
    
    if not apify_posts:
        print("❌ Aucun post récupéré")
        sys.exit(1)
    
    # Convertir au format standard
    data = convert_to_standard_format(apify_posts, args.group)
    
    # Afficher un aperçu
    print("📊 Aperçu des posts:")
    print("-" * 50)
    for i, post in enumerate(data["posts"][:5]):
        author = post.get("author", "?")
        text = post.get("text", "")[:80] + "..." if len(post.get("text", "")) > 80 else post.get("text", "")
        likes = post.get("likesCount", 0)
        comments = post.get("commentsCount", 0)
        print(f"  {i+1}. [{author}] {text}")
        print(f"     👍 {likes} | 💬 {comments}")
    
    if len(data["posts"]) > 5:
        print(f"  ... et {len(data['posts']) - 5} autres posts")
    print()
    
    # Sauvegarder
    filepath = save_results(data, args.output)
    
    # Analyser si demandé
    if args.analyze:
        run_analysis(filepath)
    else:
        print()
        print("💡 Pour analyser les posts avec l'IA:")
        print(f"   python analyze_posts_ai.py {filepath}")


if __name__ == "__main__":
    main()










