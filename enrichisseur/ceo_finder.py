import requests
import re
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config_manager import get_config


def get_ollama_model():
    """Vérifie si Ollama tourne et récupère le meilleur modèle disponible."""
    try:
        r = requests.get('http://localhost:11434/api/tags', timeout=2)
        models = r.json().get('models', [])
        if not models:
            return None
        names = [m['name'] for m in models]
        # Prioriser les modèles connus pour être bons en extraction
        for pref in ['llama3.2', 'llama3', 'mistral', 'qwen', 'phi']:
            for n in names:
                if pref in n.lower():
                    return n
        return names[0]
    except:
        return None

def find_ceo_ollama(url, domain):
    """Utilise Ollama localement pour déduire le CEO à partir du site web."""
    model = get_ollama_model()
    if not model:
        print(f"[CEO Finder] Ollama injoignable ou aucun modèle installé.")
        return None, None
        
    print(f"[CEO Finder] Recherche du CEO sur {domain} via Ollama ({model})...")
    
    try:
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin
        
        # 1. Récupérer la page d'accueil
        headers = {'User-Agent': 'Mozilla/5.0'}
        if not url.startswith('http'): url = 'https://' + url
        try:
            r = requests.get(url, headers=headers, timeout=10)
            html = r.text
        except:
            return None, None
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # 2. Chercher des liens vers Mentions légales, A propos, Equipe
        target_links = []
        for a in soup.find_all('a', href=True):
            text = a.text.lower()
            href = a['href'].lower()
            if any(k in text or k in href for k in ['mention', 'legal', 'propos', 'equipe', 'team']):
                full_url = urljoin(url, a['href'])
                if full_url not in target_links:
                    target_links.append(full_url)
        
        # Limiter à 2 pages max pour ne pas exploser le contexte
        target_links = target_links[:2]
        
        # 3. Récupérer le contenu textuel
        full_text = soup.get_text(separator=' ', strip=True)
        for link in target_links:
            try:
                r_link = requests.get(link, headers=headers, timeout=10)
                link_soup = BeautifulSoup(r_link.text, 'html.parser')
                full_text += "\n" + link_soup.get_text(separator=' ', strip=True)
            except:
                pass
                
        # Nettoyer et limiter la taille du texte (ex: max 15000 chars pour Ollama)
        clean_text = ' '.join(full_text.split())[:15000]
        
        # 4. Prompt structuré pour l'extraction
        prompt = f"""Tu es un assistant spécialisé en extraction d'informations B2B.
Analyse le texte suivant extrait du site web de l'entreprise '{domain}'.
Trouve le prénom et le nom du gérant, directeur, fondateur, président ou administrateur.

RÈGLE ABSOLUE : Réponds UNIQUEMENT par un objet JSON au format exact suivant, RIEN D'AUTRE :
{{"prenom": "Jean", "nom": "Dupont"}}

Si tu ne trouves pas d'informations concrètes et certaines, réponds :
{{"prenom": "", "nom": ""}}

TEXTE DU SITE :
{clean_text}
"""
        
        import json
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }
        
        response = requests.post('http://localhost:11434/api/generate', json=payload, timeout=45)
        response.raise_for_status()
        
        result = response.json().get('response', '{}')
        
        try:
            data = json.loads(result)
            prenom = data.get("prenom", "")
            nom = data.get("nom", "")
            
            if prenom and nom and len(prenom) > 1 and len(nom) > 1:
                print(f"[CEO Finder] Trouvé pour {domain} : {prenom} {nom}")
                return prenom.strip().capitalize(), nom.strip().upper()
        except:
            pass
            
    except Exception as e:
        print(f"[CEO Finder] Erreur via Ollama pour {domain}: {e}")
        
    return None, None


def find_ceo_legal_mentions(html_content):
    """Fallback : Regex sur les mentions légales pour trouver 'Gérant : M. XXX'."""
    match = re.search(r"(?:Gérant|Directeur|Responsable)\s*:\s*(?:M\.|Mme)?\s*([A-Z][a-z]+)\s+([A-Z][a-z]+)", html_content)
    if match:
        return match.group(1), match.group(2)
    return None, None


def find_ceo_from_url(url):
    """Trouve le CEO à partir d'une URL en scrappant le site et en utilisant Ollama localement."""
    domain = url
    if url.startswith('http'):
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
    
    first_name, last_name = find_ceo_ollama(url, domain)
    return first_name, last_name
