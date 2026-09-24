# -*- coding: utf-8 -*-
# Import pilote e-commerce camp44 - DONNEES ASCII SEULES (accents retirees
# pour fiabilite du round-trip d'ecriture). Ne contient QUE des champs verifies.
import sys, io, json
sys.path.insert(0, r"D:\prospection-machine")
from database.listes import create_liste
from database.prospects import bulk_import

CAMP = 44
MOT = "agence e-commerce"

ROWS = [
    dict(nom="Axome", email="hello@axome.com", telephone="+33 4 77 81 38 13",
         telephone="04 77 81 38 13" if False else "+33 4 77 81 38 13",
