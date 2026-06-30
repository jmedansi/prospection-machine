# -*- coding: utf-8 -*-
import os
import re
from pathlib import Path

TEMPLATES_DIR = Path("d:/prospection-machine/synthetiseur/templates_sites")

SECTORS_DATA = {
    'restaurant': {
        'default_color': '#c8a96e',
        'subtitle': 'Une expérience culinaire unique',
        'title': 'Notre Carte & Nos Créations',
        'card_title1': 'Entrées Raffinées',
        'card_desc1': 'Des créations saisonnières légères et parfumées, préparées avec soin par notre chef.',
        'img1': 'https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=600&q=80',
        'card_title2': 'Plats Signatures',
        'card_desc2': 'Le mariage parfait des saveurs locales, des produits frais et de notre savoir-faire gastronomique.',
        'img2': 'https://images.unsplash.com/photo-1544025162-d76694265947?w=600&q=80',
        'card_title3': 'Desserts d\'Exception',
        'card_desc3': 'La note sucrée idéale pour clore en beauté votre voyage de saveurs.',
        'img3': 'https://images.unsplash.com/photo-1563805042-7684c019e1cb?w=600&q=80',
    },
    'hotellerie': {
        'default_color': '#b5924c',
        'subtitle': 'Le luxe du confort absolu',
        'title': 'Nos Chambres & Prestations',
        'card_title1': 'Suites Deluxe',
        'card_desc1': 'Des espaces pensés et décorés pour votre sérénité, offrant confort haut de gamme et calme.',
        'img1': 'https://images.unsplash.com/photo-1590490360182-c33d57733427?w=600&q=80',
        'card_title2': 'Spa & Bien-être',
        'card_desc2': 'Une véritable parenthèse de détente absolue pour le corps et l\'esprit au sein de notre établissement.',
        'img2': 'https://images.unsplash.com/photo-1540555700478-4be289fbecef?w=600&q=80',
        'card_title3': 'Table d\'Hôte',
        'card_desc3': 'Une cuisine gourmande inspirée pour éveiller délicieusement vos papilles dès le petit déjeuner.',
        'img3': 'https://images.unsplash.com/photo-1533089860892-a7c6f0a88666?w=600&q=80',
    },
    'beaute': {
        'default_color': '#c9a0a0',
        'subtitle': 'Votre instant bien-être',
        'title': 'Nos Soins & Rituels',
        'card_title1': 'Soins du Visage',
        'card_desc1': 'Rituels éclat sur-mesure pour sublimer la texture et préserver la jeunesse de votre peau.',
        'img1': 'https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=600&q=80',
        'card_title2': 'Massages Relaxants',
        'card_desc2': 'Évacuez le stress du quotidien grâce aux techniques ancestrales de nos praticiennes diplômées.',
        'img2': 'https://images.unsplash.com/photo-1519699047748-de8e457a634e?w=600&q=80',
        'card_title3': 'Beauté des Ongles',
        'card_desc3': 'Manucures professionnelles et finitions parfaites avec des vernis écologiques longue durée.',
        'img3': 'https://images.unsplash.com/photo-1604654894610-df4906b24539?w=600&q=80',
    },
    'sante': {
        'default_color': '#0077b6',
        'subtitle': 'À l\'écoute de votre santé',
        'title': 'Nos Domaines de Soins',
        'card_title1': 'Médecine Générale',
        'card_desc1': 'Un suivi médical attentionné pour toute la famille, du nourrisson au senior.',
        'img1': 'https://images.unsplash.com/photo-1584515901107-d1776cebeea4?w=600&q=80',
        'card_title2': 'Prévention & Bilan',
        'card_desc2': 'Des checkups et examens réguliers pour surveiller et préserver votre capital vital au fil des ans.',
        'img2': 'https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=600&q=80',
        'card_title3': 'Conseils Nutrition',
        'card_desc3': 'Accompagnement diététique personnalisé pour retrouver durablement votre équilibre.',
        'img3': 'https://images.unsplash.com/photo-1498837167922-ddd27525d352?w=600&q=80',
    },
    'juridique': {
        'default_color': '#1e3a5f',
        'subtitle': 'Défendre vos intérêts',
        'title': 'Nos Expertises & Conseils',
        'card_title1': 'Droit des Affaires',
        'card_desc1': 'Sécurisez juridiquement vos transactions, contrats et le développement de votre entreprise.',
        'img1': 'https://images.unsplash.com/photo-1450133064473-71024230f91b?w=600&q=80',
        'card_title2': 'Droit Social',
        'card_desc2': 'Gestion rigoureuse et conseil stratégique dans vos relations professionnelles individuelles et collectives.',
        'img2': 'https://images.unsplash.com/photo-1436450412740-6b988f486c6b?w=600&q=80',
        'card_title3': 'Contentieux Civils',
        'card_desc3': 'Représentation dévouée et défense active de vos droits devant toutes les juridictions civiles.',
        'img3': 'https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=600&q=80',
    },
    'immobilier': {
        'default_color': '#1a3c34',
        'subtitle': 'Concrétisez vos projets',
        'title': 'Nos Services Immobiliers',
        'card_title1': 'Achat & Vente',
        'card_desc1': 'Estimation précise et promotion optimale pour vendre rapidement ou trouver le bien idéal.',
        'img1': 'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=600&q=80',
        'card_title2': 'Gestion Locative',
        'card_desc2': 'Tranquillité d\'esprit totale grâce à une gestion rigoureuse de vos locataires et de vos loyers.',
        'img2': 'https://images.unsplash.com/photo-1560518883-ce09059eeffa?w=600&q=80',
        'card_title3': 'Demeures de Prestige',
        'card_desc3': 'Une sélection exclusive de propriétés d\'architecte et de maisons de caractère.',
        'img3': 'https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?w=600&q=80',
    },
    'artisan': {
        'default_color': '#e07b39',
        'subtitle': 'Le savoir-faire artisanal',
        'title': 'Nos Prestations & Travaux',
        'card_title1': 'Installation Complète',
        'card_desc1': 'Réalisation minutieuse de vos chantiers en neuf comme en rénovation, dans le respect des normes.',
        'img1': 'https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=600&q=80',
        'card_title2': 'Rénovation sur-mesure',
        'card_desc2': 'Optimisez vos espaces et valorisez votre habitat avec des matériaux robustes et isolants.',
        'img2': 'https://images.unsplash.com/photo-1581094288338-2314dddb7ecc?w=600&q=80',
        'card_title3': 'Urgences & Dépannage',
        'card_desc3': 'Intervention réactive à domicile pour résoudre rapidement tous vos problèmes techniques.',
        'img3': 'https://images.unsplash.com/photo-1534224039826-c7a0dea0e66a?w=600&q=80',
    },
    'auto': {
        'default_color': '#e63946',
        'subtitle': 'Entretien & Performance',
        'title': 'Nos Services Mécaniques',
        'card_title1': 'Diagnostic Électronique',
        'card_desc1': 'Analyse approfondie des composants de votre moteur pour identifier précisément chaque anomalie.',
        'img1': 'https://images.unsplash.com/photo-1486006920555-c77dce18193b?w=600&q=80',
        'card_title2': 'Entretien & Révision',
        'card_desc2': 'Vidange, filtres, niveaux : préservez les performances de votre véhicule et la garantie constructeur.',
        'img2': 'https://images.unsplash.com/photo-1517524206127-48bbd363f3d7?w=600&q=80',
        'card_title3': 'Liaison au Sol & Freins',
        'card_desc3': 'Contrôle complet et remplacement des pièces d\'usure pour une tenue de route sécurisée.',
        'img3': 'https://images.unsplash.com/photo-1580273916550-e323be2ae537?w=600&q=80',
    },
    'bijouterie': {
        'default_color': '#d4af37',
        'subtitle': 'Élégance & Précieux',
        'title': 'Nos Collections d\'Exception',
        'card_title1': 'Bagues & Solitaires',
        'card_desc1': 'Des créations intemporelles en métaux précieux et gemmes rares pour immortaliser vos plus beaux moments.',
        'img1': 'https://images.unsplash.com/photo-1605100804763-247f67b3557e?w=600&q=80',
        'card_title2': 'Colliers & Bracelets',
        'card_desc2': 'La finesse de l\'orfèvrerie pour habiller délicatement votre cou et vos poignets au quotidien.',
        'img2': 'https://images.unsplash.com/photo-1522312346375-d1a52e2b99b3?w=600&q=80',
        'card_title3': 'Atelier de Création',
        'card_desc3': 'Confiez votre projet à notre maître joaillier pour façonner une pièce unique à votre image.',
        'img3': 'https://images.unsplash.com/photo-1535632066927-ab7c9ab60908?w=600&q=80',
    },
    'commerce': {
        'default_color': '#e76f51',
        'subtitle': 'Sélection & Qualité',
        'title': 'Notre Boutique en Ligne',
        'card_title1': 'Mode & Tendances',
        'card_desc1': 'Vêtements et accessoires sélectionnés pour leur coupe et le confort de leurs matières.',
        'img1': 'https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=600&q=80',
        'card_title2': 'Épicerie & Terroir',
        'card_desc2': 'Soutenir le goût authentique avec des délices artisanaux choisis chez nos producteurs locaux.',
        'img2': 'https://images.unsplash.com/photo-1542838132-92c53300491e?w=600&q=80',
        'card_title3': 'Objets & Cadeaux',
        'card_desc3': 'Faites plaisir ou offrez-vous des créations originales de créateurs indépendants.',
        'img3': 'https://images.unsplash.com/photo-1549465220-1a8b9238cd48?w=600&q=80',
    },
    'sport': {
        'default_color': '#00c896',
        'subtitle': 'Dépassez vos limites',
        'title': 'Nos Programmes Sportifs',
        'card_title1': 'Cardio & Force',
        'card_desc1': 'Entraînements à haute intensité pour stimuler votre métabolisme et brûler les graisses.',
        'img1': 'https://images.unsplash.com/photo-1517838277536-f5f99be501cd?w=600&q=80',
        'card_title2': 'Renforcement Profond',
        'card_desc2': 'Pilates et renforcement musculaire ciblé pour stabiliser votre posture et sculpter vos muscles.',
        'img2': 'https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=600&q=80',
        'card_title3': 'Coaching Sur-Mesure',
        'card_desc3': 'Un préparateur physique dédié pour construire des programmes alignés avec vos objectifs réels.',
        'img3': 'https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=600&q=80',
    },
    'default': {
        'default_color': '#3d5a80',
        'subtitle': 'Une réponse à vos besoins',
        'title': 'Nos Services & Solutions',
        'card_title1': 'Conseil Stratégique',
        'card_desc1': 'Bénéficiez d\'une étude personnalisée et de conseils avisés pour guider au mieux vos décisions.',
        'img1': 'https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=600&q=80',
        'card_title2': 'Services Clés en Main',
        'card_desc2': 'Déléguez en toute sérénité, nos équipes prennent en charge l\'intégralité des opérations complexes.',
        'img2': 'https://images.unsplash.com/photo-1521791136368-1a98227c30d5?w=600&q=80',
        'card_title3': 'Suivi & Assistance',
        'card_desc3': 'Un support disponible et à votre écoute pour vous accompagner pas à pas vers la réussite.',
        'img3': 'https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?w=600&q=80',
    }
}

CSS_PREVIEW_TEMPLATE = """
/* ── NOUVELLE SECTOR PREVIEW (ULTRA PREMIUM) ── */
:root {{
  --accent-color: {color};
}}
.section-suite-floue {{
  position: relative;
  padding: 8rem 4rem 14rem;
  background: #ffffff;
  overflow: hidden;
}}
.suite-container {{
  max-width: 1200px;
  margin: 0 auto;
  position: relative;
  z-index: 2;
}}
.suite-subtitle {{
  display: block;
  font-size: 0.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  color: var(--accent-color, #c8a96e);
  margin-bottom: 0.75rem;
  text-align: center;
}}
.suite-title {{
  font-family: inherit;
  font-size: clamp(2rem, 4vw, 3rem);
  font-weight: 800;
  color: #0f172a;
  text-align: center;
  margin-bottom: 4rem;
  letter-spacing: -0.02em;
}}
.suite-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 2.5rem;
}}
.suite-card {{
  background: #f8fafc;
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid rgba(15, 23, 42, 0.05);
  box-shadow: 0 4px 30px rgba(15, 23, 42, 0.02);
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}}
.suite-card:hover {{
  transform: translateY(-8px);
  box-shadow: 0 20px 40px rgba(15, 23, 42, 0.08);
}}
.suite-card-img {{
  height: 220px;
  background-size: cover;
  background-position: center;
  position: relative;
}}
.suite-card-img::after {{
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(to bottom, transparent, rgba(15, 23, 42, 0.2));
}}
.suite-card-body {{
  padding: 2rem;
}}
.suite-card-body h3 {{
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 0.75rem;
}}
.suite-card-body p {{
  color: #64748b;
  font-size: 0.95rem;
  line-height: 1.6;
}}

/* Overlay de flou progressif */
.suite-blur-overlay {{
  position: absolute;
  inset: 0;
  background: linear-gradient(to bottom, 
    rgba(255, 255, 255, 0) 0%, 
    rgba(255, 255, 255, 0.3) 15%, 
    rgba(255, 255, 255, 0.85) 45%, 
    #ffffff 70%
  );
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding-bottom: 6rem;
  z-index: 10;
}}
.suite-blur-card {{
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 24px;
  padding: 3rem;
  max-width: 580px;
  text-align: center;
  box-shadow: 0 30px 60px rgba(15, 23, 42, 0.12), 0 0 100px rgba(255, 255, 255, 0.5);
  animation: suite_float 6s ease-in-out infinite;
}}
@keyframes suite_float {{
  0%, 100% {{ transform: translateY(0); }}
  50% {{ transform: translateY(-6px); }}
}}
.suite-blur-tag {{
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--accent-color, #c8a96e);
  margin-bottom: 1rem;
}}
.suite-blur-title {{
  font-size: 1.6rem;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.3;
  margin-bottom: 1rem;
  letter-spacing: -0.01em;
}}
.suite-blur-text {{
  color: #64748b;
  font-size: 0.95rem;
  line-height: 1.6;
  margin-bottom: 2rem;
}}
.suite-blur-btn {{
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  background: #0f172a;
  color: #ffffff;
  padding: 1.1rem 2.5rem;
  border-radius: 9999px;
  text-decoration: none;
  font-weight: 700;
  font-size: 0.9rem;
  transition: all 0.3s ease;
  box-shadow: 0 10px 25px rgba(15, 23, 42, 0.2);
}}
.suite-blur-btn:hover {{
  background: var(--accent-color, #c8a96e);
  transform: translateY(-2px);
  box-shadow: 0 15px 30px rgba(15, 23, 42, 0.3);
}}

@media(max-width: 768px) {{
  .section-suite-floue {{
    padding: 6rem 1.5rem 10rem;
  }}
  .suite-blur-overlay {{
    padding-bottom: 4rem;
  }}
  .suite-blur-card {{
    padding: 2rem 1.5rem;
  }}
  .suite-grid {{
    grid-template-columns: 1fr;
  }}
}}
"""

HTML_PREVIEW_TEMPLATE = """
<section class="section-suite-floue">
  <div class="suite-container">
    <span class="suite-subtitle">{subtitle}</span>
    <h2 class="suite-title">{title}</h2>
    
    <div class="suite-grid">
      <!-- Card 1 -->
      <div class="suite-card">
        <div class="suite-card-img" style="background-image: url('{img1}')"></div>
        <div class="suite-card-body">
          <h3>{card_title1}</h3>
          <p>{card_desc1}</p>
        </div>
      </div>
      <!-- Card 2 -->
      <div class="suite-card">
        <div class="suite-card-img" style="background-image: url('{img2}')"></div>
        <div class="suite-card-body">
          <h3>{card_title2}</h3>
          <p>{card_desc2}</p>
        </div>
      </div>
      <!-- Card 3 -->
      <div class="suite-card">
        <div class="suite-card-img" style="background-image: url('{img3}')"></div>
        <div class="suite-card-body">
          <h3>{card_title3}</h3>
          <p>{card_desc3}</p>
        </div>
      </div>
    </div>
  </div>
  
  <!-- Blur Overlay over the section content -->
  <div class="suite-blur-overlay">
    <div class="suite-blur-card">
      <span class="suite-blur-tag">La suite vous attend</span>
      <h3 class="suite-blur-title">Vous voulez voir la suite de la maquette ?</h3>
      <p class="suite-blur-text">Nous pouvons personnaliser le reste du site et le mettre en ligne sous quelques jours.</p>
      <a href="tel:{{{{TELEPHONE}}}}" class="suite-blur-btn">Nous contacter — {{{{TELEPHONE}}}} ➔</a>
    </div>
  </div>
</section>
"""

# Let's read all templates and improve them
for sector, data in SECTORS_DATA.items():
    sector_dir = TEMPLATES_DIR / sector
    if not sector_dir.exists():
        continue
        
    for html_file in sector_dir.glob("*.html"):
        print(f"Enhancing: {html_file.relative_to(TEMPLATES_DIR.parent)}")
        content = html_file.read_text(encoding="utf-8")
        
        # 1. CSS Injection
        # Search for old CSS preview block (or style close tag if not found)
        css_preview = CSS_PREVIEW_TEMPLATE.format(color=data['default_color'])
        
        # Strip old preview CSS if present
        content = re.sub(r'/\* ── SUITE FLOUE ── \*/.*?(\n\s*\}\s*\n|\Z)', '', content, flags=re.DOTALL)
        content = re.sub(r'/\* ── NOUVELLE SECTOR PREVIEW.*? \*/.*?(\n\s*\}\s*\n|\Z)', '', content, flags=re.DOTALL)
        
        style_close_idx = content.find("</style>")
        if style_close_idx != -1:
            content = content[:style_close_idx] + css_preview + content[style_close_idx:]
            
        # 2. HTML Suite Floue injection
        html_preview = HTML_PREVIEW_TEMPLATE.format(
            subtitle=data['subtitle'],
            title=data['title'],
            card_title1=data['card_title1'],
            card_desc1=data['card_desc1'],
            img1=data['img1'],
            card_title2=data['card_title2'],
            card_desc2=data['card_desc2'],
            img2=data['img2'],
            card_title3=data['card_title3'],
            card_desc3=data['card_desc3'],
            img3=data['img3']
        )
        
        # Replace the old suite floue / page-preview / preview-overlay/preview-over blocks
        # Old sections start with comment "Suite floue" or "Page preview" and end before the next section/script/footer
        # For simplicity, we can do a pattern replacement:
        pattern = re.compile(
            r'<!-- Suite floue.*?-->.*?<!-- =+.*PROFIL A',
            re.DOTALL
        )
        if pattern.search(content):
            content = pattern.sub(html_preview + "\n\n<!-- ====================================================================\n     PROFIL A", content, count=1)
        else:
            # Try matching with simple script tags if PROFIL A comment is not present
            pattern2 = re.compile(
                r'<!-- Suite floue.*?-->.*?<script>',
                re.DOTALL
            )
            if pattern2.search(content):
                content = pattern2.sub(html_preview + "\n\n<script>", content, count=1)
            else:
                # If neither matches, we insert it just before the injection block
                inject_idx = content.find("<!-- =====================================================================")
                if inject_idx != -1:
                    content = content[:inject_idx] + html_preview + "\n\n" + content[inject_idx:]
                else:
                    body_close_idx = content.rfind("</body>")
                    if body_close_idx != -1:
                        content = content[:body_close_idx] + html_preview + content[body_close_idx:]

        # Clean double closing divs if left from broken old code
        content = re.sub(r'</section>\s*</div>\s*<div class="preview-over">.*?</div>\s*</div>', '</section>', content, flags=re.DOTALL)
        content = re.sub(r'</section>\s*</div>\s*<div class="preview-overlay">.*?</div>\s*</div>', '</section>', content, flags=re.DOTALL)

        html_file.write_text(content, encoding="utf-8")

print("FINISHED TEMPLATES ENHANCEMENT")
