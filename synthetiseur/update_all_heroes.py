import os
import re
from bs4 import BeautifulSoup

base_path = r"d:\prospection-machine\synthetiseur\templates_sites"

copywriting = {
    "artisan-1": {
        "h1": "L'artisanat de qualité, sans mauvaise surprise.",
        "desc": "{{NOM_ENTREPRISE}} garantit des interventions rapides et des travaux durables. Confiez vos projets à des experts reconnus pour leur savoir-faire.",
        "cta1": "Obtenir un devis gratuit"
    },
    "artisan-2": {
        "h1": "Donnez vie à vos projets en toute confiance.",
        "desc": "{{NOM_ENTREPRISE}} vous accompagne de la conception à la réalisation avec rigueur. Obtenez des résultats à la hauteur de vos attentes.",
        "cta1": "Parler de mon projet"
    },
    "auto-1": {
        "h1": "Roulez l'esprit tranquille, on s'occupe de tout.",
        "desc": "{{NOM_ENTREPRISE}} s'occupe de l'entretien, réparation ou diagnostic de votre véhicule en privilégiant avant tout votre sécurité.",
        "cta1": "Prendre rendez-vous"
    },
    "auto-2": {
        "h1": "Trouvez le véhicule idéal, garanti et révisé.",
        "desc": "{{NOM_ENTREPRISE}} vous propose un large choix de modèles fiables, avec des conseillers qui comprennent réellement vos besoins.",
        "cta1": "Voir nos véhicules"
    },
    "beaute-1": {
        "h1": "Révélez votre beauté dans un cadre exclusif.",
        "desc": "{{NOM_ENTREPRISE}} vous offre un moment de pure détente. Nos experts subliment votre style avec des soins sur-mesure de haute qualité.",
        "cta1": "Réserver mon soin"
    },
    "beaute-2": {
        "h1": "Prenez enfin du temps pour vous.",
        "desc": "{{NOM_ENTREPRISE}} regroupe des passionnés dédiés à votre satisfaction. Coiffure, esthétique ou bien-être, profitez de notre expertise.",
        "cta1": "Prendre rendez-vous"
    },
    "bijouterie-1": {
        "h1": "L'élégance intemporelle pour marquer vos instants.",
        "desc": "{{NOM_ENTREPRISE}} crée des pièces uniques et raffinées. Un savoir-faire d'exception pour des bijoux qui traversent le temps.",
        "cta1": "Découvrir la collection"
    },
    "bijouterie-2": {
        "h1": "Des créations qui reflètent votre singularité.",
        "desc": "{{NOM_ENTREPRISE}} réalise du sur-mesure et des pièces tendances. Trouvez le bijou parfait pour sublimer votre quotidien.",
        "cta1": "Voir nos créations"
    },
    "commerce-1": {
        "h1": "Des produits d'exception sélectionnés pour vous.",
        "desc": "{{NOM_ENTREPRISE}} met la qualité, le conseil personnalisé et la passion au cœur de sa démarche. Découvrez notre sélection exclusive.",
        "cta1": "Voir nos produits"
    },
    "commerce-2": {
        "h1": "Le savoir-faire authentique près de chez vous.",
        "desc": "{{NOM_ENTREPRISE}} soutient activement le commerce local. Profitez de conseils d'experts passionnés pour trouver exactement ce qu'il vous faut.",
        "cta1": "Visiter la boutique"
    },
    "comptable-1": {
        "h1": "Libérez-vous enfin des contraintes comptables.",
        "desc": "{{NOM_ENTREPRISE}} automatise votre gestion financière. Concentrez-vous sur votre cœur de métier et prenez vos décisions sereinement.",
        "cta1": "Obtenir un devis"
    },
    "comptable-2": {
        "h1": "Plus qu'un bilan, un véritable levier de croissance.",
        "desc": "{{NOM_ENTREPRISE}} vous accompagne au quotidien pour optimiser votre fiscalité. Pilotez votre rentabilité avec la plus grande précision.",
        "cta1": "Parler à un expert"
    },
    "default-1": {
        "h1": "L'expertise au service de vos exigences.",
        "desc": "{{NOM_ENTREPRISE}} apporte un savoir-faire reconnu et des solutions sur-mesure pour répondre efficacement à tous vos besoins.",
        "cta1": "En savoir plus"
    },
    "default-2": {
        "h1": "Un partenaire de confiance pour vos projets.",
        "desc": "{{NOM_ENTREPRISE}} est à l'écoute de vos attentes. Notre équipe dédiée vous garantit un service de qualité et sans aucun compromis.",
        "cta1": "Nous contacter"
    },
    "education-1": {
        "h1": "Construisez votre avenir avec l'excellence.",
        "desc": "{{NOM_ENTREPRISE}} propose des formations reconnues et un accompagnement pédagogique de très haut niveau pour atteindre vos objectifs.",
        "cta1": "Découvrir nos formations"
    },
    "education-2": {
        "h1": "Révélez votre potentiel, à votre rythme.",
        "desc": "{{NOM_ENTREPRISE}} utilise des méthodes d'apprentissage innovantes. Bénéficiez d'un suivi totalement personnalisé pour garantir votre réussite.",
        "cta1": "S'inscrire maintenant"
    },
    "evenementiel-1": {
        "h1": "Créez des moments inoubliables et mémorables.",
        "desc": "{{NOM_ENTREPRISE}} orchestre chaque détail avec soin pour faire de votre mariage, gala ou séminaire une réussite absolue.",
        "cta1": "Demander un devis"
    },
    "evenementiel-2": {
        "h1": "L'inspiration au service de vos événements.",
        "desc": "{{NOM_ENTREPRISE}} déploie des concepts originaux et une organisation sans faille pour surprendre vos invités et marquer les esprits.",
        "cta1": "Parler de mon projet"
    },
    "hotellerie-1": {
        "h1": "Une parenthèse d'exception vous attend.",
        "desc": "{{NOM_ENTREPRISE}} vous plonge dans un univers d'élégance et de sérénité. Profitez d'un séjour inoubliable pensé pour votre confort.",
        "cta1": "Réserver mon séjour"
    },
    "hotellerie-2": {
        "h1": "Le confort idéal pour vos déplacements.",
        "desc": "{{NOM_ENTREPRISE}} propose le parfait emplacement, un wifi très haut débit et des espaces repensés pour vos déplacements professionnels.",
        "cta1": "Voir les disponibilités"
    },
    "immobilier-1": {
        "h1": "Vendez votre bien au meilleur prix, sans stress.",
        "desc": "{{NOM_ENTREPRISE}} confie votre projet à des experts locaux. De l'estimation à la signature, nous valorisons pleinement votre patrimoine.",
        "cta1": "Estimer mon bien"
    },
    "immobilier-2": {
        "h1": "Trouvez enfin l'espace qui vous ressemble.",
        "desc": "{{NOM_ENTREPRISE}} vous donne accès à des biens exclusifs. Laissez-vous guider par une équipe qui comprend réellement votre style de vie.",
        "cta1": "Découvrir nos biens"
    },
    "juridique-1": {
        "h1": "Votre sécurité juridique, notre priorité absolue.",
        "desc": "{{NOM_ENTREPRISE}} protège vos intérêts stratégiques avec un engagement total. Bénéficiez d'un conseil clair et d'une défense pugnace.",
        "cta1": "Consulter un avocat"
    },
    "juridique-2": {
        "h1": "Sécurisez les moments clés de votre vie.",
        "desc": "{{NOM_ENTREPRISE}} vous fait bénéficier de conseils impartiaux et d'actes authentiques, rédigés avec une rigueur juridique absolue.",
        "cta1": "Prendre rendez-vous"
    },
    "microfinance-1": {
        "h1": "Des solutions financières pour réaliser vos projets.",
        "desc": "{{NOM_ENTREPRISE}} garantit un accompagnement transparent et accessible. Nous vous aidons à concrétiser vos ambitions professionnelles.",
        "cta1": "Simuler mon prêt"
    },
    "microfinance-2": {
        "h1": "Gérez vos finances en toute simplicité.",
        "desc": "{{NOM_ENTREPRISE}} offre des services financiers rapides, sécurisés et innovants, pensés exclusivement pour faciliter votre quotidien.",
        "cta1": "Ouvrir un compte"
    },
    "ong-1": {
        "h1": "Ensemble, transformons des vies dès aujourd'hui.",
        "desc": "{{NOM_ENTREPRISE}} considère que votre soutien est vital face à l'urgence. Rejoignez notre mouvement pour apporter une aide concrète.",
        "cta1": "Faire un don"
    },
    "ong-2": {
        "h1": "Devenez acteur du changement.",
        "desc": "{{NOM_ENTREPRISE}} vous invite à agir concrètement pour notre cause. Chaque geste compte pour bâtir un avenir plus durable.",
        "cta1": "Rejoindre le mouvement"
    },
    "restaurant-1": {
        "h1": "Une expérience culinaire qui éveille vos sens.",
        "desc": "{{NOM_ENTREPRISE}} sélectionne des produits frais et de saison pour une cuisine créative. Réservez votre table pour un moment inoubliable.",
        "cta1": "Réserver une table"
    },
    "restaurant-2": {
        "h1": "Le goût de l'authentique, comme à la maison.",
        "desc": "{{NOM_ENTREPRISE}} vous fait retrouver les saveurs d'antan dans une ambiance conviviale. Une cuisine généreuse et faite avec passion.",
        "cta1": "Voir le menu"
    },
    "sante-1": {
        "h1": "Votre santé entre les mains de spécialistes.",
        "desc": "{{NOM_ENTREPRISE}} assure une prise en charge globale, humaine et rigoureuse. Notre équipe médicale vous accompagne avec bienveillance.",
        "cta1": "Prendre rendez-vous"
    },
    "sante-2": {
        "h1": "Retrouvez votre vitalité et votre sérénité.",
        "desc": "{{NOM_ENTREPRISE}} propose des soins adaptés à vos besoins dans un environnement apaisant, avec des professionnels toujours à votre écoute.",
        "cta1": "Consulter un spécialiste"
    },
    "sport-1": {
        "h1": "Dépassez vos limites, atteignez vos objectifs.",
        "desc": "{{NOM_ENTREPRISE}} met à disposition des équipements premium et une ambiance motivante. Rejoignez une communauté sportive dynamique.",
        "cta1": "Découvrir la salle"
    },
    "sport-2": {
        "h1": "Un accompagnement sur-mesure pour votre corps.",
        "desc": "{{NOM_ENTREPRISE}} vous fait bénéficier d'un suivi totalement personnalisé par des coachs diplômés et passionnés pour votre remise en forme.",
        "cta1": "Réserver une séance"
    }
}

mapping = {
    "artisan-hero-1-robuste.html": "artisan-1",
    "artisan-hero-2-expertise.html": "artisan-2",
    "auto-hero-1-technique.html": "auto-1",
    "auto-hero-2-moderne.html": "auto-2",
    "beaute-hero-1-elegant.html": "beaute-1",
    "beaute-hero-2-moderne.html": "beaute-2",
    "bijouterie-hero-1-luxe.html": "bijouterie-1",
    "bijouterie-hero-2-tendance.html": "bijouterie-2",
    "commerce-hero-1-boutique.html": "commerce-1",
    "commerce-hero-2-artisan.html": "commerce-2",
    "comptable-hero-1-institutionnel.html": "comptable-1",
    "comptable-hero-2-moderne.html": "comptable-2",
    "default-hero-1-professionnel.html": "default-1",
    "default-hero-2-chaleureux.html": "default-2",
    "education-hero-1-savoir.html": "education-1",
    "education-hero-2-avenir.html": "education-2",
    "evenementiel-hero-1-prestige.html": "evenementiel-1",
    "evenementiel-hero-2-creatif.html": "evenementiel-2",
    "hotellerie-hero-1-luxe.html": "hotellerie-1",
    "hotellerie-hero-2-urbain.html": "hotellerie-2",
    "immobilier-hero-1-premium.html": "immobilier-1",
    "immobilier-hero-2-moderne.html": "immobilier-2",
    "juridique-hero-1-institutionnel.html": "juridique-1",
    "juridique-hero-2-moderne.html": "juridique-2",
    "microfinance-hero-1-confiance.html": "microfinance-1",
    "microfinance-hero-2-moderne.html": "microfinance-2",
    "ong-hero-1-mission.html": "ong-1",
    "ong-hero-2-impact.html": "ong-2",
    "restaurant-hero-1-moderne.html": "restaurant-1",
    "restaurant-hero-2-chaleureux.html": "restaurant-2",
    "sante-hero-1-confiance.html": "sante-1",
    "sante-hero-2-lumineux.html": "sante-2",
    "sport-hero-1-energie.html": "sport-1",
    "sport-hero-2-coach.html": "sport-2"
}

def update_file(filepath, copy_key):
    copy_data = copywriting[copy_key]
    with open(filepath, 'r', encoding='utf-8') as f:
        html = f.read()

    soup = BeautifulSoup(html, 'html.parser')
    
    # We DO NOT touch the eyebrow anymore. It stays exactly as it was in the original template.

    # 1. Update H1
    h1 = soup.find(class_='hero-title')
    if h1:
        h1.string = copy_data['h1']

    # 2. Update Description
    desc = soup.find(class_='hero-desc')
    if desc:
        desc.string = copy_data['desc']

    # 3. Update CTAs
    actions = soup.find(class_='hero-actions')
    if not actions and h1:
         actions = h1.find_parent().find(class_=lambda x: x and 'cta' in x.lower())
         
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
                
        if len(links) > 1:
            a2 = links[1]
            svg = a2.find('svg')
            span = a2.find(class_=lambda x: x and 'underline' in x) 
            if not span:
                span = a2.find('span')
            if span:
                span.string = "{{TELEPHONE}}"
            else:
                a2.clear()
                if svg:
                    a2.append(svg)
                    a2.append(soup.new_string(" "))
                new_span = soup.new_tag("span")
                new_span['class'] = "btn-ghost-underline"
                new_span.string = "{{TELEPHONE}}"
                a2.append(new_span)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(str(soup))
    print(f"Updated {os.path.basename(filepath)}")

sectors = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
for sector in sectors:
    dir_path = os.path.join(base_path, sector)
    for filename in os.listdir(dir_path):
        if filename in mapping:
            update_file(os.path.join(dir_path, filename), mapping[filename])
print("Done!")
