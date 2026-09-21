from synthetiseur.mockup_generator import generate_mockup

# Test avec un faux lead sans site
lead_test = {
  "id":            1,
  "nom":           "Clinique Santé Plus",
  "ville":         "Cotonou",
  "adresse":       "Rue des Palmiers, Cotonou",
  "telephone":     "+229 21 00 00 00",
  "category":      "clinique médicale",
  "reviews_count": 45,
  "rating":        4.2,
  "logo_url":      None,
}

result = generate_mockup(lead_test)

print(f"Succès      : {result['success']}")
print(f"Template    : {result['template_used']}")
print(f"Secteur     : {result['secteur']}")
print(f"Desktop     : {result['screenshot_desktop']}")
print(f"Mobile      : {result['screenshot_mobile']}")

# Si un succès, ouvrir avec start sous Windows
import subprocess
import os
import platform

if result['success'] and os.path.exists(result['screenshot_desktop']):
    if platform.system() == 'Windows':
        os.startfile(result['screenshot_desktop'])
    else:
        subprocess.run(["xdg-open", result["screenshot_desktop"]])
