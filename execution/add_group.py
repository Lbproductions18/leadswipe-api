#!/usr/bin/env python3
"""
add_group.py - Ajouter un groupe Facebook à scraper

Usage:
    python add_group.py "Nom du Groupe" "https://www.facebook.com/groups/..."
    python add_group.py --list  (pour voir les groupes configurés)
"""

import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / 'config' / 'groups.json'


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"groups": [], "settings": {"posts_per_group": 50}}


def save_config(config):
    CONFIG_PATH.parent.mkdir(exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def add_group(name: str, url: str):
    config = load_config()
    
    # Vérifier si le groupe existe déjà
    for g in config['groups']:
        if g['url'] == url:
            print(f"⚠️  Ce groupe existe déjà: {g['name']}")
            return
    
    config['groups'].append({
        "name": name,
        "url": url
    })
    
    save_config(config)
    print(f"✅ Groupe ajouté: {name}")
    print(f"   URL: {url}")
    print(f"   Total groupes: {len(config['groups'])}")


def list_groups():
    config = load_config()
    groups = config.get('groups', [])
    
    if not groups:
        print("📭 Aucun groupe configuré")
        return
    
    print(f"\n📋 Groupes configurés ({len(groups)}):\n")
    for i, g in enumerate(groups, 1):
        print(f"   {i}. {g['name']}")
        print(f"      {g['url']}\n")


def remove_group(index: int):
    config = load_config()
    
    if index < 1 or index > len(config['groups']):
        print(f"❌ Index invalide. Utilisez --list pour voir les groupes.")
        return
    
    removed = config['groups'].pop(index - 1)
    save_config(config)
    print(f"🗑️  Groupe supprimé: {removed['name']}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    if sys.argv[1] == '--list':
        list_groups()
    elif sys.argv[1] == '--remove' and len(sys.argv) >= 3:
        remove_group(int(sys.argv[2]))
    elif len(sys.argv) >= 3:
        name = sys.argv[1]
        url = sys.argv[2]
        add_group(name, url)
    else:
        print(__doc__)


if __name__ == '__main__':
    main()










