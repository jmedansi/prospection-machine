import os
import glob
from bs4 import BeautifulSoup

base_path = r"d:\prospection-machine\synthetiseur\templates_sites"

copywriting = {
    "immobilier-1": {
        "eyebrow": "BIENVENUE CHEZ {{NOM_ENTREPRISE}}",
        "h1": "Vendez votre bien au meilleur prix, sans stress.",
        "desc": "Confiez votre projet à nos experts locaux. De l'estimation à la signature, nous valorisons votre patrimoine avec un accompagnement sur-mesure.",
        "cta1": "Estimer mon bien",
        "cta2": "{{TELEPHONE}}"
    },
    "immobilier-2": {
        "eyebrow": "BIENVENUE CHEZ {{NOM_ENTREPRISE}}",
        "h1": "Trouvez enfin l'espace qui vous ressemble.",
        "desc": "Accédez à des biens exclusifs et laissez-vous guider par une équipe qui comprend vos exigences et votre style de vie.",
        "cta1": "Découvrir nos biens",
        "cta2": "{{TELEPHONE}}"
    },
    "juridique-1": {
        "eyebrow": "BIENVENUE CHEZ {{NOM_ENTREPRISE}}",
        "h1": "Votre sécurité juridique, notre priorité absolue.",
        "desc": "Protégez vos intérêts stratégiques avec un cabinet engagé. Un conseil clair et une défense pugnace pour vous et votre entreprise.",
        "cta1": "Consulter un avocat",
        "cta2": "{{TELEPHONE}}"
    },
    "juridique-2": {
        "eyebrow": "BIENVENUE CHEZ {{NOM_ENTREPRISE}}",
        "h1": "Sécurisez les moments clés de votre vie.",
        "desc": "Famille, immobilier ou patrimoine : bénéficiez de conseils impartiaux et d'actes authentiques rédigés avec une rigueur absolue.",
        "cta1": "Prendre rendez-vous",
        "cta2": "{{TELEPHONE}}"
    },
    "comptable-1": {
        "eyebrow": "BIENVENUE CHEZ {{NOM_ENTREPRISE}}",
        "h1": "Libérez-vous enfin des contraintes comptables.",
        "desc": "Concentrez-vous sur votre cœur de métier. Nous automatisons votre gestion financière et vous donnons les chiffres clés pour décider sereinement.",
        "cta1": "Obtenir un devis",
        "cta2": "{{TELEPHONE}}"
    },
    "comptable-2": {
        "eyebrow": "BIENVENUE CHEZ {{NOM_ENTREPRISE}}",
        "h1": "Plus qu'un bilan, un véritable levier de croissance.",
        "desc": "Pilotez votre rentabilité avec précision. Nos experts vous accompagnent au quotidien pour optimiser votre fiscalité et développer votre activité.",
        "cta1": "Parler à un expert",
        "cta2": "{{TELEPHONE}}"
    },
    "hotellerie-1": {
        "eyebrow": "BIENVENUE CHEZ {{NOM_ENTREPRISE}}",
        "h1": "Une parenthèse d'exception vous attend.",
        "desc": "Plongez dans un univers d'élégance et de sérénité. Profitez d'un séjour inoubliable où chaque détail est pensé pour votre bien-être.",
        "cta1": "Réserver mon séjour",
        "cta2": "{{TELEPHONE}}"
    },
    "hotellerie-2": {
        "eyebrow": "BIENVENUE CHEZ {{NOM_ENTREPRISE}}",
        "h1": "Le confort idéal pour vos déplacements.",
        "desc": "Emplacement idéal, wifi très haut débit et espaces repensés. Reposez-vous efficacement et restez productif lors de vos voyages.",
        "cta1": "Voir les disponibilités",
        "cta2": "{{TELEPHONE}}"
    },
    "ong-1": {
        "eyebrow": "BIENVENUE CHEZ {{NOM_ENTREPRISE}}",
        "h1": "Ensemble, transformons des vies dès aujourd'hui.",
        "desc": "Face à l'urgence, votre soutien est vital. Rejoignez notre mouvement pour apporter une aide concrète et de l'espoir aux communautés.",
        "cta1": "Faire un don",
        "cta2": "{{TELEPHONE}}"
    },
    "ong-2": {
        "eyebrow": "BIENVENUE CHEZ {{NOM_ENTREPRISE}}",
        "h1": "Devenez acteur du changement.",
        "desc": "Agissez concrètement pour notre cause. Chaque geste compte pour bâtir un avenir durable pour les générations futures.",
        "cta1": "Rejoindre le mouvement",
        "cta2": "{{TELEPHONE}}"
    }
}

mapping = {
    "immobilier-hero-1-premium.html": copywriting["immobilier-1"],
    "immobilier-hero-2-moderne.html": copywriting["immobilier-2"],
    "juridique-hero-1-institutionnel.html": copywriting["juridique-1"],
    "juridique-hero-2-moderne.html": copywriting["juridique-2"],
    "comptable-hero-1-institutionnel.html": copywriting["comptable-1"],
    "comptable-hero-2-moderne.html": copywriting["comptable-2"],
    "hotellerie-hero-1-luxe.html": copywriting["hotellerie-1"],
    "hotellerie-hero-2-urbain.html": copywriting["hotellerie-2"],
    "ong-hero-1-mission.html": copywriting["ong-1"],
    "ong-hero-2-impact.html": copywriting["ong-2"]
}

def update_file(filepath, copy_data):
    with open(filepath, 'r', encoding='utf-8') as f:
        html = f.read()

    soup = BeautifulSoup(html, 'html.parser')
    
    # 1. Update Eyebrow
    eyebrow = soup.find(class_=lambda x: x and 'eyebrow' in x)
    if eyebrow:
        eyebrow.string = copy_data['eyebrow']
    else:
        h1 = soup.find(class_='hero-title')
        if h1:
            new_eyebrow = soup.new_tag("div")
            new_eyebrow['class'] = "hero-eyebrow"
            new_eyebrow.string = copy_data['eyebrow']
            h1.insert_before(new_eyebrow)

    # 2. Update H1
    h1 = soup.find(class_='hero-title')
    if h1:
        h1.string = copy_data['h1']

    # 3. Update Description
    desc = soup.find(class_='hero-desc')
    if desc:
        desc.string = copy_data['desc']

    # 4. Update CTAs
    actions = soup.find(class_='hero-actions')
    if actions:
        links = actions.find_all('a')
        if len(links) > 0 and 'cta1' in copy_data:
            a = links[0]
            svg = a.find('svg')
            span = a.find('span')
            if span:
                span.string = copy_data['cta1']
            else:
                a.clear()
                a.append(copy_data['cta1'])
                if svg:
                    a.append(soup.new_string(" "))
                    a.append(svg)
                
        if len(links) > 1 and 'cta2' in copy_data:
            a2 = links[1]
            svg = a2.find('svg')
            span = a2.find(class_=lambda x: x and 'underline' in x) # try to find specific span
            if not span:
                span = a2.find('span')
            if span:
                span.string = copy_data['cta2']
            else:
                a2.clear()
                if svg:
                    a2.append(svg)
                    a2.append(soup.new_string(" "))
                # Add span for btn-ghost-underline if it might be missing
                new_span = soup.new_tag("span")
                new_span['class'] = "btn-ghost-underline"
                new_span.string = copy_data['cta2']
                a2.append(new_span)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(str(soup))
    print(f"Updated {os.path.basename(filepath)}")

for sector in ['immobilier', 'juridique', 'comptable', 'hotellerie', 'ong']:
    dir_path = os.path.join(base_path, sector)
    if os.path.isdir(dir_path):
        for filename in os.listdir(dir_path):
            if filename in mapping:
                update_file(os.path.join(dir_path, filename), mapping[filename])
