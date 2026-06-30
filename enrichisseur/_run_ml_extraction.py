# -*- coding: utf-8 -*-
"""
enrichisseur/_run_ml_extraction.py

Lance l'extraction ML (raw_text) puis le structuring
pour les secteurs cliniques_esthetiques et ecoles_formation.
"""

import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SECTEURS = ["cliniques_esthetiques", "ecoles_formation"]

print("=" * 60)
print("ETAPE 1 : Extraction raw text des mentions legales")
print(f"Secteurs : {', '.join(SECTEURS)}")
print("=" * 60)

from enrichisseur.extract_responsables_ml import main as extract_main
extract_main(limit=None, secteurs=SECTEURS)

print()
print("=" * 60)
print("ETAPE 2 : Structuration des donnees extraites")
print("=" * 60)

from enrichisseur.structure_ml_notes import main as structure_main
structure_main(limit=None, secteurs=SECTEURS)

print()
print("=" * 60)
print("Termine !")
print("=" * 60)
