import os

base_path = r"d:\prospection-machine\synthetiseur\templates_sites"

list_1 = [
    r"sport\sport-hero-2-coach.html",
    r"restaurant\restaurant-hero-2-chaleureux.html",
    r"ong\ong-hero-1-mission.html",
    r"microfinance\microfinance-hero-1-confiance.html",
    r"juridique\juridique-hero-1-institutionnel.html",
    r"hotellerie\hotellerie-hero-2-urbain.html",
    r"hotellerie\hotellerie-hero-1-luxe.html",
    r"evenementiel\evenementiel-hero-2-creatif.html",
    r"comptable\comptable-hero-1-institutionnel.html",
    r"commerce\commerce-hero-2-artisan.html",
    r"commerce\commerce-hero-1-boutique.html",
    r"bijouterie\bijouterie-hero-2-tendance.html",
    r"bijouterie\bijouterie-hero-1-luxe.html"
]

# Correction: replace the too-aggressive fix with a subtle one
old_css_1 = """
    /* --- Fix taille titre PC --- */
    @media (min-width: 1024px) {
      .hero-title {
        font-size: clamp(2rem, 3.2vw, 2.8rem) !important;
      }
    }
"""

# Subtle: original max was 3.8rem, we bring it down just to 3.2rem
new_css_1 = """
    /* --- Fix taille titre PC --- */
    @media (min-width: 1024px) {
      .hero-title {
        font-size: clamp(2.4rem, 4vw, 3.2rem) !important;
      }
    }
"""

def update_file(filepath, old_css, new_css):
    full_path = os.path.join(base_path, filepath)
    if not os.path.exists(full_path):
        print(f"File not found: {full_path}")
        return

    with open(full_path, 'r', encoding='utf-8') as f:
        html = f.read()

    if old_css in html:
        html = html.replace(old_css, new_css)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Updated {filepath}")
    else:
        print(f"Pattern NOT FOUND in {filepath}")

for f in list_1:
    update_file(f, old_css_1, new_css_1)

print("Done!")
