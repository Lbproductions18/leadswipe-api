# Directive: Scraper les posts d'un groupe Facebook

## Objectif
Extraire les posts d'un groupe Facebook et identifier les freelances/créateurs potentiels via des mots-clés.

## Flow actuel

### Étape 1 : Scanner le groupe (Chrome)
1. Ouvrir Chrome sur un groupe Facebook (ex: `facebook.com/groups/EntrepreneursQc`)
2. **Scroller la page** pour charger plus de posts (10-20 posts minimum)
3. Cliquer sur l'icône de l'extension 🔍
4. Cliquer **"Scanner le groupe"**
5. Le fichier JSON se télécharge automatiquement

### Étape 2 : Analyser (via Cursor)
1. Ouvrir Cursor dans le projet `Facebook Scraping`
2. Glisser le fichier JSON dans la conversation
3. L'assistant lance l'analyse Python et affiche les résultats

### Étape 3 : Agir sur les résultats
- Voir les posts qui matchent les mots-clés
- Cliquer les liens pour voir le post / contacter l'auteur

---

## Extension Chrome (v1.6.0)

**Localisation :** `chrome_extension/`

**Installation :**
1. `chrome://extensions` → Mode développeur ON
2. "Charger l'extension non empaquetée" → sélectionner `chrome_extension/`

**Fonctionnement :**
- Trouve les liens `/posts/{ID}/` (sans `comment_id`) = posts principaux
- Ignore les `[role="article"]` = commentaires
- Extrait : auteur, texte, URL du post, médias

---

## Script d'analyse Python

**Localisation :** `execution/analyze_posts.py`

**Commande :**
```bash
source venv/bin/activate
python execution/analyze_posts.py .tmp/facebook_posts_XXXX.json
```

**Mots-clés recherchés :**
| Catégorie | Mots-clés |
|-----------|-----------|
| Médias | photographe, vidéaste, vidéo, montage |
| Social | réseaux sociaux, social media, content creator, community manager |
| Tech | intelligence artificielle, IA, ChatGPT, automatisation |
| Créatif | design, graphiste, motion, animation |
| Business | freelance, indépendant, marketing, branding |

---

## Learnings & Edge Cases

### Facebook bloque les scrapers
- Classes CSS dynamiques (changent chaque semaine)
- `[role="article"]` = commentaires, PAS les posts
- Les posts sont des `div` génériques avec lien `/posts/{ID}/`

### Faux positifs
- "ai" en français = "j'ai" → filtré pour chercher "IA" isolé seulement

### Peu de posts extraits ?
- Scroller plus avant de scanner
- Les posts se chargent dynamiquement (lazy loading)

---

## Prochaine étape : Interface Lovable
Créer une app no-code pour :
- Upload du JSON
- Affichage des résultats filtrés
- Actions : Contacter / Ignorer / À suivre
