# -*- coding: utf-8 -*-
# Cree la liste E-commerce dans la campagne 44 (pilote).
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"D:\prospection-machine")
from database.listes import create_liste
r = create_liste(44, "Agences E-commerce - Partenariats",
                 "Liste pilote e-commerce (campagne 44). Agences e-commerce FR verifiees web.",
                 secteur="E-commerce", source="import", objectif="ecommerce")
print("OK" if r.get("success") else ("ERR " + str(r)))
if r.get("success"):
    print("LISTE_ID", r["liste"]["id"])
