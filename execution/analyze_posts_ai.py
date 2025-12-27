#!/usr/bin/env python3
"""
analyze_posts_ai.py - Analyse les posts Facebook avec OpenAI

Utilise GPT-4o-mini pour comprendre le CONTEXTE des posts et identifier
les opportunités (quelqu'un qui cherche un freelance/prestataire).
"""

import json
import sys
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv
from openai import OpenAI

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


# Services offerts par l'utilisateur (pour filtrer les opportunités pertinentes)
MES_SERVICES = [
    "vidéo",
    "montage",
    "réseaux sociaux",
    "contenu",
    "automatisation",
    "no-code",
    "marketing digital",
]

# Prompt système pour l'analyse
SYSTEM_PROMPT = """Tu es un assistant qui analyse des posts de groupes Facebook d'entrepreneurs québécois.

🎯 TON OBJECTIF : Identifier les posts où quelqu'un A BESOIN D'AIDE dans ces domaines SPÉCIFIQUES :
- Vidéo / Montage vidéo
- Réseaux sociaux / Community management / Contenu
- Automatisation / No-code / Intégrations
- Marketing digital / Branding / Personal branding

⛔ IGNORER les demandes de SERVICE dans ces domaines :
- Graphisme / Design graphique / Infographie (cherche graphiste)
- Comptabilité / Finance / Fiscalité (cherche comptable)
- Assurance / Cautionnement (cherche assureur)
- Immobilier / Location (cherche local)
- Distribution physique / Logistique (cherche distributeur)
- Juridique / Incorporation (cherche avocat)
- Construction / Rénovation (cherche entrepreneur)

⚠️ MAIS ATTENTION : Si quelqu'un dans ces domaines décrit un PROBLÈME qui pourrait être AUTOMATISÉ, c'est une opportunité!
Exemple: "Mon comptable a livré en retard et j'ai payé des intérêts" → Opportunité d'automatisation (rappels, alertes)

⚠️ RÈGLE CRITIQUE - AUTOPROMOTION vs BESOIN RÉEL :

❌ AUTOPROMOTION (PAS une opportunité) :
La personne OFFRE ses services ou fait sa promo. Indices :
- "Je suis [métier] et je peux vous aider..."
- "Mon entreprise/équipe offre..."
- "Nous avons ajouté X à notre offre..."
- "Je t'aide à..." / "On t'aide à..."
- "Contactez-moi/Écris-moi pour..."
- "Voici ce qu'on offre..."
- "Ma spécialité c'est..."
- Liens vers son site/portfolio/services
- Langage marketing vantant leurs services
- Témoignages ou résultats de leurs clients
- Hashtags promotionnels

✅ BESOIN RÉEL (opportunité) :
La personne CHERCHE de l'aide. Indices :
- "Je cherche..." / "On cherche..." / "Recherche..."
- "Avez-vous des recommandations pour..."
- "Connaissez-vous quelqu'un qui..."
- "J'ai besoin de..."
- "À la recherche de..."
- Formulation d'un PROBLÈME sans solution proposée
- Question demandant de l'aide concrète

---

## TYPES D'OPPORTUNITÉS (si c'est un besoin réel ET dans le scope) :

### TYPE 1 : CHERCHE QUELQU'UN (hiring)
L'auteur cherche activement un freelance/prestataire pour :
- Vidéaste / Monteur vidéo / Photographe
- Gestionnaire réseaux sociaux / Community manager
- Créateur de contenu
- Marketing digital / Branding / Personal branding
- Google Ads / SEO / Publicité en ligne

### TYPE 2 : PROBLÈME AUTOMATISABLE (automation) ⚠️ IMPORTANT!
L'auteur décrit un PROBLÈME ou une FRUSTRATION qui pourrait être résolu par automatisation/no-code.
La personne NE SAIT PEUT-ÊTRE PAS que c'est automatisable - c'est une opportunité cachée!

🔍 INDICES À DÉTECTER :
- "Je passe des heures à..." / "Je perds du temps à..."
- "C'est long de..." / "C'est répétitif..."
- "Je dois toujours..." / "À chaque fois je dois..."
- "Comment vous gérez...?" / "Comment faites-vous pour...?"
- "Je cherche une solution pour..."
- Problèmes de suivi (clients, leads, factures, inventaire)
- Problèmes de communication (répondre aux mêmes questions)
- Problèmes d'organisation (rappels, rendez-vous, tâches)
- Problèmes d'intégration (données éparpillées, copier-coller entre outils)
- Frustrations avec des processus manuels
- Questions sur des logiciels (Quickbooks, Excel, CRM, etc.)

🎯 EXEMPLES DE PROBLÈMES AUTOMATISABLES :
- "Je réponds toujours aux mêmes questions" → Chatbot/FAQ automatique
- "Je copie mes leads de Facebook vers Excel" → Zapier/Make
- "Je dois rappeler mes clients pour leurs RDV" → Rappels automatiques
- "Mes factures traînent" → Facturation automatique
- "Je perds du temps à chercher l'info" → Dashboard centralisé
- "Comment gérez-vous vos suivis clients?" → CRM + séquences auto

---

Réponds UNIQUEMENT avec un JSON valide :
{
  "is_opportunity": true/false,
  "opportunity_type": "hiring" | "automation" | null,
  "confidence": 0.0-1.0,
  "category": "vidéo" | "réseaux sociaux" | "contenu" | "marketing" | "automatisation" | null,
  "short_title": "Titre court (max 40 caractères, style direct: 'Vidéaste Montréal', 'Social Media Manager', 'Expert Zapier')",
  "summary": "Résumé en 1 phrase",
  "automation_potential": "Si applicable, comment l'automatisation aiderait",
  "reason": "Justification courte"
}

⚠️ Si la demande est HORS SCOPE (comptabilité, assurance, distribution physique, etc.), retourne is_opportunity: false

---

## EXEMPLES CRITIQUES :

### ❌ AUTOPROMO (is_opportunity: FALSE) :
- "Je suis vidéaste et je cherche des partenariats" → FALSE (OFFRE ses services)
- "Notre équipe aide les PME à trouver des leads de qualité. Contactez-nous!" → FALSE (PROMO)
- "J'aide les entrepreneurs à créer un système..." → FALSE (OFFRE coaching)

### ❌ HORS SCOPE - DEMANDES DE SERVICE (is_opportunity: FALSE) :
- "Je cherche un graphiste" → FALSE (graphisme, pas vidéo/automation)
- "Je cherche un comptable" → FALSE (cherche comptable, pas vidéo/automation)
- "Recherche assureur pour cautionnement" → FALSE (assurance)
- "Cherche quelqu'un pour distribution en pharmacie" → FALSE (logistique physique)
- "Besoin d'un avocat" → FALSE (juridique)

### ✅ DANS LE SCOPE - HIRING (is_opportunity: TRUE, type: hiring) :
- "Je cherche un vidéaste pour filmer mon quotidien" → TRUE, hiring, vidéo
- "Recherche gestionnaire réseaux sociaux autonome" → TRUE, hiring, réseaux sociaux
- "Besoin d'un monteur vidéo pour mes capsules" → TRUE, hiring, vidéo
- "Je cherche quelqu'un pour mon personal branding" → TRUE, hiring, marketing

### ✅ DANS LE SCOPE - AUTOMATION (is_opportunity: TRUE, type: automation) :
MÊME SI LE SUJET EST "HORS SCOPE" (compta, admin, etc.), si c'est un PROBLÈME AUTOMATISABLE, c'est une opportunité!

- "Je perds du temps à copier mes leads dans Excel" → TRUE, automation
- "Mon comptable a pas livré à temps, j'ai eu des frais" → TRUE, automation (rappels automatiques)
- "Comment vous gérez le suivi de vos clients?" → TRUE, automation
- "Je passe des heures sur ma facturation" → TRUE, automation
- "Quelqu'un utilise Sage 50? C'est compliqué" → TRUE, automation (intégration possible)
- "Je réponds toujours aux mêmes questions" → TRUE, automation (chatbot)
- "C'est long de faire mes posts sur tous les réseaux" → TRUE, automation (scheduling)
- "Je dois relancer mes clients manuellement" → TRUE, automation
"""


def load_posts(file_path: Path) -> dict:
    """Charge les posts depuis un fichier JSON"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# Mapping des mois français
MOIS_FR = {
    'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6,
    'juillet': 7, 'août': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12,
    'jan': 1, 'fév': 2, 'mar': 3, 'avr': 4, 'jun': 6,
    'juil': 7, 'aoû': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'déc': 12
}


def parse_french_date(date_str: str) -> Optional[datetime]:
    """Parse une date française et retourne un datetime"""
    if not date_str:
        return None
    
    date_str = date_str.lower().strip()
    now = datetime.now()
    
    # "5 h", "3 j", "2 sem", etc.
    relative_match = re.match(r'^(\d+)\s*(h|m|d|w|j|s|min|sec|sem|mo)\.?$', date_str)
    if relative_match:
        num = int(relative_match.group(1))
        unit = relative_match.group(2)
        
        if unit in ['h', 'hr']:
            return now - timedelta(hours=num)
        elif unit in ['m', 'min']:
            return now - timedelta(minutes=num)
        elif unit in ['d', 'j']:
            return now - timedelta(days=num)
        elif unit in ['w', 'sem']:
            return now - timedelta(weeks=num)
        elif unit == 'mo':
            return now - timedelta(days=num * 30)
    
    # "hier"
    if 'hier' in date_str:
        return now - timedelta(days=1)
    
    # "il y a X jours/semaines/mois"
    il_y_a_match = re.match(r'il y a\s+(\d+)\s*(jour|semaine|mois|heure)', date_str)
    if il_y_a_match:
        num = int(il_y_a_match.group(1))
        unit = il_y_a_match.group(2)
        if 'jour' in unit:
            return now - timedelta(days=num)
        elif 'semaine' in unit:
            return now - timedelta(weeks=num)
        elif 'mois' in unit:
            return now - timedelta(days=num * 30)
        elif 'heure' in unit:
            return now - timedelta(hours=num)
    
    # "20 octobre" ou "octobre 20"
    for mois, num_mois in MOIS_FR.items():
        if mois in date_str:
            # Chercher le jour
            day_match = re.search(r'(\d{1,2})', date_str)
            if day_match:
                day = int(day_match.group(1))
                # Chercher l'année
                year_match = re.search(r'(\d{4})', date_str)
                year = int(year_match.group(1)) if year_match else now.year
                
                try:
                    post_date = datetime(year, num_mois, day)
                    # Si la date est dans le futur, c'est probablement l'année précédente
                    if post_date > now:
                        post_date = datetime(year - 1, num_mois, day)
                    return post_date
                except ValueError:
                    pass
    
    return None


def get_post_age_days(post: dict) -> Optional[int]:
    """Retourne l'âge du post en jours"""
    date_str = post.get('dateRelative') or post.get('date')
    parsed = parse_french_date(date_str)
    if parsed:
        delta = datetime.now() - parsed
        return delta.days
    return None


def format_age(days: Optional[int]) -> str:
    """Formate l'âge en texte lisible"""
    if days is None:
        return "?"
    if days == 0:
        return "Aujourd'hui"
    if days == 1:
        return "Hier"
    if days < 7:
        return f"{days} jours"
    if days < 30:
        weeks = days // 7
        return f"{weeks} sem."
    if days < 365:
        months = days // 30
        return f"{months} mois"
    return f"{days // 365} an(s)"


def analyze_post_with_ai(client: OpenAI, post: dict) -> dict:
    """Analyse un post avec GPT-4o-mini"""
    
    text = post.get('text', '')
    author = post.get('author', 'Inconnu')
    
    if not text or len(text) < 20:
        return {
            "is_opportunity": False,
            "confidence": 0,
            "category": None,
            "summary": "Post trop court",
            "reason": "Pas assez de contenu pour analyser"
        }
    
    user_message = f"""Analyse ce post Facebook :

Auteur: {author}
Contenu: {text[:1500]}"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            max_tokens=300
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Parser le JSON
        # Nettoyer si nécessaire (enlever ```json``` si présent)
        if result_text.startswith('```'):
            result_text = result_text.split('\n', 1)[1]
            result_text = result_text.rsplit('```', 1)[0]
        
        result = json.loads(result_text)
        return result
        
    except json.JSONDecodeError as e:
        print(f"  ⚠️ Erreur parsing JSON: {e}")
        return {
            "is_opportunity": False,
            "confidence": 0,
            "category": None,
            "summary": "Erreur d'analyse",
            "reason": f"JSON invalide: {result_text[:100]}"
        }
    except Exception as e:
        print(f"  ⚠️ Erreur API: {e}")
        return {
            "is_opportunity": False,
            "confidence": 0,
            "category": None,
            "summary": "Erreur",
            "reason": str(e)
        }


def main():
    # Vérifier la clé API
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print(f"{Colors.RED}❌ OPENAI_API_KEY non trouvée dans .env{Colors.END}")
        sys.exit(1)
    
    client = OpenAI(api_key=api_key)
    
    # Trouver le fichier à analyser
    script_dir = Path(__file__).parent.parent
    tmp_dir = script_dir / '.tmp'
    
    if len(sys.argv) > 1:
        input_file = Path(sys.argv[1])
    else:
        json_files = list(tmp_dir.glob("facebook_posts_*.json"))
        if not json_files:
            print(f"{Colors.RED}❌ Aucun fichier facebook_posts_*.json dans .tmp/{Colors.END}")
            sys.exit(1)
        json_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        input_file = json_files[0]
    
    if not input_file.exists():
        print(f"{Colors.RED}❌ Fichier non trouvé: {input_file}{Colors.END}")
        sys.exit(1)
    
    print(f"{Colors.CYAN}📂 Analyse IA du fichier: {input_file}{Colors.END}")
    
    # Charger les posts
    data = load_posts(input_file)
    posts = data.get('posts', [])
    
    print(f"\n{Colors.HEADER}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}🤖 ANALYSE IA DES POSTS FACEBOOK{Colors.END}")
    print(f"{Colors.HEADER}{'='*60}{Colors.END}")
    print(f"\n{Colors.CYAN}Groupe:{Colors.END} {data.get('groupName', 'N/A')}")
    print(f"{Colors.CYAN}Total posts:{Colors.END} {len(posts)}")
    print(f"\n{Colors.YELLOW}⏳ Analyse en cours avec GPT-4o-mini...{Colors.END}\n")
    
    # Analyser chaque post
    opportunities = []
    
    for i, post in enumerate(posts):
        author = post.get('author', 'Inconnu')
        text_preview = (post.get('text', '')[:50] + '...') if post.get('text') else 'N/A'
        age_days = get_post_age_days(post)
        age_str = format_age(age_days)
        
        # Avertissement si post ancien (> 14 jours)
        age_warning = ""
        if age_days is not None and age_days > 14:
            age_warning = f" {Colors.YELLOW}⚠️ ANCIEN ({age_str}){Colors.END}"
        
        print(f"  [{i+1}/{len(posts)}] {author} ({age_str}): {text_preview}{age_warning}")
        
        result = analyze_post_with_ai(client, post)
        post['ai_analysis'] = result
        
        if result.get('is_opportunity'):
            opportunities.append(post)
            conf = result.get('confidence', 0) * 100
            opp_type = result.get('opportunity_type', '?')
            type_emoji = "👥" if opp_type == "hiring" else "🤖" if opp_type == "automation" else "❓"
            print(f"       {Colors.GREEN}✅ OPPORTUNITÉ {type_emoji} ({conf:.0f}%) - {result.get('category')}{Colors.END}")
        else:
            print(f"       {Colors.BLUE}⏭️ Pas une opportunité{Colors.END}")
    
    # Afficher les résultats
    print(f"\n{Colors.HEADER}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}📊 RÉSULTATS{Colors.END}")
    print(f"{Colors.HEADER}{'='*60}{Colors.END}")
    
    print(f"\n{Colors.CYAN}Posts analysés:{Colors.END} {len(posts)}")
    print(f"{Colors.GREEN}Opportunités trouvées:{Colors.END} {len(opportunities)}")
    
    if opportunities:
        print(f"\n{Colors.HEADER}{'='*60}{Colors.END}")
        print(f"{Colors.BOLD}🎯 OPPORTUNITÉS DÉTECTÉES{Colors.END}")
        print(f"{Colors.HEADER}{'='*60}{Colors.END}")
        
        for i, post in enumerate(opportunities, 1):
            analysis = post.get('ai_analysis', {})
            print(f"\n{Colors.BLUE}━━━ Opportunité #{i} ━━━{Colors.END}")
            age_days = get_post_age_days(post)
            age_str = format_age(age_days)
            age_color = Colors.GREEN if (age_days is not None and age_days <= 7) else Colors.YELLOW if (age_days is not None and age_days <= 30) else Colors.RED
            
            opp_type = analysis.get('opportunity_type', '?')
            type_label = "👥 Cherche quelqu'un" if opp_type == "hiring" else "🤖 Automatisable" if opp_type == "automation" else "❓ Autre"
            
            print(f"{Colors.BOLD}👤 Auteur:{Colors.END} {post.get('author', 'Inconnu')}")
            print(f"{Colors.BOLD}📅 Âge:{Colors.END} {age_color}{age_str}{Colors.END}")
            print(f"{Colors.BOLD}🏷️  Type:{Colors.END} {type_label}")
            print(f"{Colors.BOLD}📁 Catégorie:{Colors.END} {analysis.get('category', 'N/A')}")
            print(f"{Colors.BOLD}📊 Confiance:{Colors.END} {analysis.get('confidence', 0)*100:.0f}%")
            print(f"{Colors.BOLD}📝 Résumé:{Colors.END} {analysis.get('summary', 'N/A')}")
            
            # Afficher le potentiel d'automatisation si présent
            if analysis.get('automation_potential'):
                print(f"{Colors.BOLD}🤖 Automatisation possible:{Colors.END} {Colors.CYAN}{analysis.get('automation_potential')}{Colors.END}")
            print(f"{Colors.BOLD}💬 Contenu:{Colors.END}")
            print(f"   {post.get('text', 'N/A')[:300]}...")
            print(f"{Colors.BOLD}🔗 Lien:{Colors.END} {post.get('postUrl', 'N/A')}")
            print(f"{Colors.BOLD}👤 Profil:{Colors.END} {post.get('authorProfileUrl', 'N/A')}")
    else:
        print(f"\n{Colors.YELLOW}⚠️ Aucune opportunité détectée dans ces posts.{Colors.END}")
    
    # Sauvegarder les résultats
    output_file = input_file.parent / f"ai_analyzed_{input_file.name}"
    results = {
        'analyzedAt': datetime.now().isoformat(),
        'sourceFile': str(input_file),
        'groupName': data.get('groupName'),
        'totalPosts': len(posts),
        'opportunitiesCount': len(opportunities),
        'opportunities': opportunities,
        'allPosts': posts
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n{Colors.GREEN}✅ Résultats sauvegardés: {output_file}{Colors.END}")


if __name__ == '__main__':
    main()

