# -*- coding: utf-8 -*-
"""Import agences e-commerce (pilote) dans campagne 44."""
import sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"D:\prospection-machine")
from database.listes import create_liste
from database.prospects import bulk_import

CAMP = 44
MOT = "agence e-commerce"
LBL = dict(dirigeant="", foncion="", email_2="")

def row(nom, ent, email, tel, site, ville, secteur, **extra):
    d = dict(LBL)
    d.update(extra)
    return dict(nom=nom, entreprise=ent, email=email, telephone=tel,
                site_web=site, ville=ville, secteur=secteur,
                data_extra=d)

ROWS = [
    row("Axome", "Axome", "hello@axome.com", "+33 4 77 81 38 13", "https://www.axome.com", "Saint-Etienne", "E-commerce",
        ia_signaux="Magento 2 expert + PrestaShop (Ste Etienne/Paris, depuis 2005). Contact confirme.",
        ia_opportunite="E-commerce", ia_reco="A traiter", verif="site officiel", mot_cle=MOT),
    row("Itis Commerce", "Itis Commerce", "contact@itis-commerce.com", "04 28 29 46 08", "https://www.itis-commerce.com", "Lyon", "E-commerce",
        ia_signaux="Magento/BigCommerce. Fondateur Christophe Vidal. Contact confirme.",
        ia_opportunite="E-commerce", ia_reco="A traiter", verif="site officiel", mot_cle=MOT),
    row("Soledis", "Soledis", "contact@soledis.com", "02 97 46 30 40", "https://www.soledis.com", "Vannes", "E-commerce",
        ia_signaux="PrestaShop top agence FR (Vannes/Nantes). Depuis 2001. Contact confirme.",
        ia_opportunite="E-commerce", ia_reco="A traiter", verif="site officiel", mot_cle=MOT),
    row("Agillia", "Agillia", "contact@agillia.fr", "07 51 84 52 06", "https://www.agillia.fr", "Paris", "E-commerce",
        ia_signaux="PrestaShop (Paris). Dir. pub. Ludovic Guyot. Contact confirme.",
        ia_opportunite="E-commerce", ia_reco="A traiter", verif="site officiel", mot_cle=MOT),
    row("Artich.io", "Artich.io", "contact@artich.io", "+33 6 09 88 30 38", "https://www.artich.io", "Paris", "E-commerce",
        ia_signaux="Shopify Plus (Paris). Dir. pub. David Atlan. Contact confirme.",
        ia_opportunite="E-commerce", ia_reco="A traiter", verif="site officiel", mot_cle=MOT),
]

def main():
    ck = create_liste(CAMP, "Agences e-commerce - Partenariats",
                      "Pilote e-commerce : agences e-commerce FR verifiees (web).",
                      secteur="E-commerce", objectif="web")
    if not ck.get("success"):
        print("ERREUR create_liste:", ck); return
    liste = ck["liste"]
    print("Liste OK #", liste["id"])
    res = bulk_import(liste["id"], ROWS, source="import")
    print("Import:", {k: v for k, v in res.items() if k not in ("liste",)})

if __name__ == "__main__":
    main()
