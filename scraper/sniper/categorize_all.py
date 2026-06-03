"""Catégorise tous les leads sans secteur — crée de nouveaux secteurs"""
import sys, os, re, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from database.connection import get_conn

logging.basicConfig(level=logging.INFO, format="%(message)s")

# Keyword -> sector mapping (all lowercase)
KEYWORD_SECTORS = [
    # Existing sectors (recatch any missed)
    (r'chirurgie|esthétique|botox|laser épilation|médecin esthétique|clinique esthétique|esthéticienne', 'cliniques_esthetiques'),
    (r'concessionnaire|voiture occasion|voiture neuve|achat voiture|révision voiture|contrôle technique auto|carrosserie|garagiste', 'concessionnaires_auto'),
    (r'courtier|crédit immobilier|prêt immobilier|simulation crédit', 'courtage'),
    (r'formation|reconversion|comptabilité|bilan de compétences|certifiante|haccp|excel|cours particuliers', 'ecoles_formation'),
    (r'agence immobili|vendre appartement|estimation immobili|achat maison|acheter appartement|agent immobilier|promoteur immobilier|gestion locative|home staging', 'immobilier'),

    # NEW sectors
    (r'plombier|chauffagiste|pompe à chaleur|débouchage|fuite eau|assainissement', 'plomberie_chauffage'),
    (r'dentiste|kinésithérapeute|kiné|ostéopathe|opticien|orthodontiste|audioprothésiste|pédicure|podologue|sage-femme|infirmier|radiologue|masseur|kinési', 'sante'),
    (r'peintre|électricien|couvreur|menuisier|serrurier|maçon|carreleur|plaquiste|plâtrier|charpentier|toiturier|façadier|ravale|étanchéité|isolation|climatisation|chape|enduit', 'batiment'),
    (r'expert-comptable|expertise comptable|comptable', 'expertise_comptable'),
    (r'avocat', 'avocat'),
    (r'salon de coiffure|coiffeur|barbier|institut beauté|salon beauté|manucure|ongle|onglerie', 'esthetique_bienetre'),
    (r'salle de sport|fitness|pilates|yoga|crossfit|musculation|danse|coach sportif|gym', 'sport_fitness'),
    (r'bijouterie|fleuriste|librairie|chaussures|matelas|vêtement|prêt-à-porter|mode|accessoire|maroquinerie|sacs|souliers', 'commerce_detail'),
    (r'hôtel|hôtellerie|hébergement|gîte|chambre d\'hôte|auberge|bnb', 'hotellerie_restauration'),
    (r'infogérance|agence web|informatique|développement web|création site|référencement|seo|marketing digital|e-commerce|logiciel|éditeur|développeur|maintenance informatique|réseau|cybersécurité|hébergement web', 'informatique_web'),
    (r'fournitures bureau|bureau|papeterie|imprimerie', 'fournitures_services'),
    (r'déménagement|garde meuble|stockage', 'demenagement_stockage'),
    (r'assurance|mutuelle|prévoyance|assureur', 'assurance'),
    (r'location limousine|taxi|vtc|transport|chauffeur', 'transport_mobilite'),
    (r'bijouterie|joaillier|horloger', 'bijouterie_horlogerie'),
    (r'pharmacie|pharmacien|parapharmacie', 'pharmacie'),
    (r'notaire|notariat', 'notaire'),
    (r'architecte', 'architecte'),
    (r'restaurant|traiteur|food|cuisine|gastronomie|pizzeria|boulangerie|pâtisserie|boucherie|charcuterie|primeur|épicerie|supermarché|alimentation', 'hotellerie_restauration'),
    (r'nettoyage|entretien|ménage|propreté|hygiène', 'nettoyage_entretien'),
    (r'jardinier|paysagiste|élagage|entretien espaces verts|jardinage', 'jardin_paysage'),
    (r'photographe|vidéaste', 'photographie'),
    (r'imprimerie|carton|emballage|étiquette', 'imprimerie_emballage'),
    (r'maison|immobilier neuf|programme neuf|promotion immobilière', 'immobilier'),
    (r'cosmétiques|cosmétique|cosmétiques naturels|parfumerie', 'commerce_detail'),
    (r'store banne|store|fenêtre|volet|fermeture', 'batiment'),
    (r'graphiste|graphisme|design graphique|designer|illustrateur', 'communication'),
    (r'nutritionniste|diététicien|naturopathe', 'sante'),
    (r'ramonage|cheminée|poêle|insert', 'plomberie_chauffage'),
    (r'cadeaux personnalisés|gift|goodies|objet pub', 'communication'),
    (r'agence web|création site|référencement|seo|marketing digital', 'informatique_web'),
    (r'cadeaux|décoration|déco|linge de maison|arts de la table', 'commerce_detail'),
]

# BODACC NAF code -> sector mapping
NAF_SECTORS = {
    '7022Z': 'conseil_gestion',        # Conseil pour les affaires
    '7021Z': 'communication',          # Conseil en relations publiques
    '7311Z': 'publicite',              # Publicité
    '7312Z': 'publicite',              # Régie publicitaire
    '7320Z': 'communication',          # Études de marché
    '7490B': 'divers_services',        # Autres activités spécialisées (fallback)
    '6201Z': 'informatique_web',       # Programmation informatique
    '6202A': 'informatique_web',       # Conseil en systèmes informatiques
    '6202B': 'informatique_web',       # Activités de conseil en informatique
    '6203Z': 'informatique_web',       # Gestion d'installations informatiques
    '6209Z': 'informatique_web',       # Autres activités informatiques
    '5829C': 'informatique_web',       # Édition de logiciels
    '5821Z': 'informatique_web',       # Édition de livres (souvent logiciels/numérique)
    '6312Z': 'informatique_web',       # Portails Internet
    '6311Z': 'informatique_web',       # Traitement de données
    '4651Z': 'informatique_web',       # Commerce gros ordinateurs
    '4652Z': 'informatique_web',       # Commerce gros composants électroniques
    '6110Z': 'informatique_web',       # Télécommunications filaires
    '6190Z': 'informatique_web',       # Autres télécommunications
}

with get_conn() as conn:
    cur = conn.execute(
        "SELECT id, mot_cle, secteur FROM leads_bruts "
        "WHERE secteur IS NULL OR secteur = ''"
    )
    leads = cur.fetchall()

print(f'{len(leads)} leads à catégoriser...')

updates = []
for lid, mot_cle, secteur in leads:
    if not mot_cle:
        continue
    mkc = mot_cle.lower()

    # Try BODACC NAF code mapping (use original case, NAF codes are uppercase)
    bodacc_match = re.search(r'(\d{4}[A-Z])', mot_cle) if mot_cle else None
    if not bodacc_match:
        bodacc_match = re.search(r'(\d{4}[A-Z])', mkc)
    if bodacc_match:
        naf = bodacc_match.group(1)
        if naf in NAF_SECTORS:
            updates.append((NAF_SECTORS[naf], lid))
            continue

    # Try keyword mapping
    found = False
    for pattern, sector in KEYWORD_SECTORS:
        if re.search(pattern, mkc):
            updates.append((sector, lid))
            found = True
            break

    if not found:
        # BODACC without recognized NAF code or unknown keyword
        if 'bodacc' in mkc:
            updates.append(('divers_services', lid))
        else:
            updates.append(('autres', lid))

print(f'{len(updates)} leads mappés')

# Apply updates
conn.executemany("UPDATE leads_bruts SET secteur=? WHERE id=?", updates)
conn.commit()

# Show results
cur2 = conn.execute("SELECT secteur, COUNT(*) as cnt FROM leads_bruts WHERE secteur IS NOT NULL AND secteur != '' GROUP BY secteur ORDER BY cnt DESC")
rows = cur2.fetchall()
total = sum(r[1] for r in rows)
print('\n=== Nouvelle répartition ===')
for r in rows:
    print(f'  {r[0]:30s}: {r[1]:4d}')
print(f'\nTotal leads catégorisés: {total}')

# Check remaining uncategorized
remaining = conn.execute("SELECT COUNT(*) FROM leads_bruts WHERE secteur IS NULL OR secteur = ''").fetchone()[0]
print(f'Restants sans secteur: {remaining}')
conn.close()
