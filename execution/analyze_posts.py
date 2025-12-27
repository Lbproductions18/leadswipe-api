#!/usr/bin/env python3
"""
analyze_posts.py - Analyse les posts Facebook extraits pour trouver des opportunités

Lit les fichiers JSON extraits par l'extension Chrome et filtre les posts
contenant des mots-clés pertinents pour identifier des freelances/créateurs.
"""

import json
import sys
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

# Mots-clés à rechercher
KEYWORDS = [
    # Français - Médias
    "photographe",
    "vidéaste",
    "vidéo",
    "montage",
    "réseaux sociaux",
    "créatif",
    "contenu",
    "freelance",
    "indépendant",
    # English - Media
    "photographer",
    "videographer",
    "video editor",
    "editing",
    "social media",
    "creative",
    "content creator",
    "content creation",
    # Tech/AI (attention: "ai" seul matche "j'ai" en français!)
    "intelligence artificielle",
    "artificial intelligence",
    " IA ",          # IA avec espaces pour éviter "j'ai", "avait", etc.
    "chatgpt",
    "automatisation",
    "automation",
    # Domaines
    "marketing",
    "branding",
    "design",
    "graphiste",
    "motion",
    "animation",
    "community manager",
    "gestionnaire de communauté",
    "stratégie digitale",
    "digital strategy",
]

# Couleurs ANSI pour le terminal
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def find_latest_json(tmp_dir: Path) -> Optional[Path]:
    """Trouve le fichier JSON le plus récent dans .tmp/"""
    json_files = list(tmp_dir.glob("facebook_posts_*.json"))
    
    if not json_files:
        return None
    
    # Trier par date de modification (plus récent en premier)
    json_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return json_files[0]


def load_posts(file_path: Path) -> dict:
    """Charge les posts depuis un fichier JSON"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def find_keywords_in_text(text: str, keywords: list) -> list:
    """Trouve tous les mots-clés présents dans le texte"""
    if not text:
        return []
    
    # Ajouter des espaces au début et fin pour matcher " IA "
    text_with_spaces = f" {text} "
    text_lower = text_with_spaces.lower()
    found = []
    
    for keyword in keywords:
        keyword_lower = keyword.lower()
        
        # Cas spécial: " IA " - chercher exactement avec espaces (case insensitive mais mot isolé)
        if keyword.strip() == "IA":
            # Chercher IA comme mot isolé, pas dans "j'ai", "avait", etc.
            if re.search(r'[^a-zéèêë]ia[^a-zéèêë]', text_lower):
                # Vérifier que ce n'est pas "j'ai" ou similaire
                if not re.search(r"[jntl]'ia", text_lower):
                    found.append("IA")
            continue
        
        # Cas normal: utilise une regex pour matcher le mot entier
        pattern = r'\b' + re.escape(keyword_lower) + r'\b'
        if re.search(pattern, text_lower):
            found.append(keyword)
    
    return found


def analyze_posts(data: dict, keywords: list = KEYWORDS) -> list:
    """Analyse les posts et retourne ceux qui matchent les mots-clés"""
    matching_posts = []
    
    for post in data.get('posts', []):
        text = post.get('text', '')
        found_keywords = find_keywords_in_text(text, keywords)
        
        if found_keywords:
            matching_posts.append({
                **post,
                'matched_keywords': found_keywords
            })
    
    return matching_posts


def highlight_keywords(text: str, keywords: list) -> str:
    """Met en surbrillance les mots-clés dans le texte"""
    if not text:
        return ""
    
    for keyword in keywords:
        pattern = re.compile(r'(\b' + re.escape(keyword) + r'\b)', re.IGNORECASE)
        text = pattern.sub(f'{Colors.YELLOW}{Colors.BOLD}\\1{Colors.END}', text)
    
    return text


def truncate_text(text: str, max_length: int = 300) -> str:
    """Tronque le texte à une longueur maximale"""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def print_results(matching_posts: list, data: dict):
    """Affiche les résultats de manière formatée"""
    total_posts = len(data.get('posts', []))
    
    print(f"\n{Colors.HEADER}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}📊 ANALYSE DES POSTS FACEBOOK{Colors.END}")
    print(f"{Colors.HEADER}{'='*60}{Colors.END}")
    
    print(f"\n{Colors.CYAN}Groupe:{Colors.END} {data.get('groupName', 'N/A')}")
    print(f"{Colors.CYAN}Extrait le:{Colors.END} {data.get('extractedAt', 'N/A')}")
    print(f"{Colors.CYAN}Total posts:{Colors.END} {total_posts}")
    print(f"{Colors.CYAN}Posts avec mots-clés:{Colors.END} {Colors.GREEN}{len(matching_posts)}{Colors.END}")
    
    if not matching_posts:
        print(f"\n{Colors.YELLOW}⚠️  Aucun post ne correspond aux mots-clés recherchés.{Colors.END}")
        return
    
    # Compter les mots-clés les plus fréquents
    keyword_counts = {}
    for post in matching_posts:
        for kw in post.get('matched_keywords', []):
            keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
    
    print(f"\n{Colors.BOLD}🏷️  Mots-clés trouvés:{Colors.END}")
    for kw, count in sorted(keyword_counts.items(), key=lambda x: -x[1]):
        print(f"   • {kw}: {count} occurrences")
    
    print(f"\n{Colors.HEADER}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}📝 POSTS CORRESPONDANTS{Colors.END}")
    print(f"{Colors.HEADER}{'='*60}{Colors.END}")
    
    for i, post in enumerate(matching_posts, 1):
        print(f"\n{Colors.BLUE}━━━ Post #{i} ━━━{Colors.END}")
        print(f"{Colors.BOLD}👤 Auteur:{Colors.END} {post.get('author', 'Inconnu')}")
        
        if post.get('date') or post.get('dateRelative'):
            date_str = post.get('date') or post.get('dateRelative')
            print(f"{Colors.BOLD}📅 Date:{Colors.END} {date_str}")
        
        print(f"{Colors.BOLD}🏷️  Mots-clés:{Colors.END} {', '.join(post.get('matched_keywords', []))}")
        
        # Afficher le texte avec mots-clés en surbrillance
        text = post.get('text', '')
        highlighted = highlight_keywords(truncate_text(text, 400), post.get('matched_keywords', []))
        print(f"{Colors.BOLD}💬 Contenu:{Colors.END}\n   {highlighted}")
        
        if post.get('postUrl'):
            print(f"{Colors.BOLD}🔗 Lien:{Colors.END} {post.get('postUrl')}")
        
        if post.get('authorProfileUrl'):
            print(f"{Colors.BOLD}👤 Profil:{Colors.END} {post.get('authorProfileUrl')}")


def save_results(matching_posts: list, data: dict, output_path: Path):
    """Sauvegarde les résultats dans un fichier JSON"""
    results = {
        'analyzedAt': datetime.now().isoformat(),
        'sourceFile': str(output_path),
        'groupName': data.get('groupName'),
        'groupUrl': data.get('groupUrl'),
        'totalPosts': len(data.get('posts', [])),
        'matchingPosts': len(matching_posts),
        'keywordsUsed': KEYWORDS,
        'posts': matching_posts
    }
    
    output_file = output_path.parent / f"analyzed_{output_path.name}"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n{Colors.GREEN}✅ Résultats sauvegardés: {output_file}{Colors.END}")
    return output_file


def main():
    # Déterminer le dossier .tmp
    script_dir = Path(__file__).parent.parent
    tmp_dir = script_dir / '.tmp'
    
    # Vérifier si un fichier spécifique est passé en argument
    if len(sys.argv) > 1:
        input_file = Path(sys.argv[1])
        if not input_file.exists():
            print(f"{Colors.RED}❌ Fichier non trouvé: {input_file}{Colors.END}")
            sys.exit(1)
    else:
        # Trouver le fichier JSON le plus récent
        if not tmp_dir.exists():
            print(f"{Colors.RED}❌ Le dossier .tmp n'existe pas.{Colors.END}")
            print(f"   Créez-le et placez-y les fichiers JSON extraits.")
            sys.exit(1)
        
        input_file = find_latest_json(tmp_dir)
        if not input_file:
            print(f"{Colors.RED}❌ Aucun fichier facebook_posts_*.json trouvé dans .tmp/{Colors.END}")
            print(f"   Utilisez l'extension Chrome pour extraire des posts.")
            sys.exit(1)
    
    print(f"{Colors.CYAN}📂 Analyse du fichier: {input_file}{Colors.END}")
    
    # Charger et analyser
    data = load_posts(input_file)
    matching_posts = analyze_posts(data)
    
    # Afficher les résultats
    print_results(matching_posts, data)
    
    # Sauvegarder les résultats
    if matching_posts:
        save_results(matching_posts, data, input_file)


if __name__ == '__main__':
    main()

