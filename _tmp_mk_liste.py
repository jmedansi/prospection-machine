# -*- coding: utf-8 -*-
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, r"D:\prospection-machine")
from database.listes import create_liste
r = create_liste(44, "Agences E-commerce - Partenariats",
                 description="Pilote camp44 : agences e-commerce vérifiées (web).",
                 secteur="E-commerce", source="import", objectif="general")
print("RESULT:", r)
