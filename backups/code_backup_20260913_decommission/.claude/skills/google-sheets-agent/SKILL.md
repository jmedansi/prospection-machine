---
name: google-sheets-agent
description: Activated when any file uses gspread, reads or writes to Google Sheets, or references leads_bruts, leads_audites, emails_envoyes, or config_comptes.
---

# Règles pour Google Sheets

## Connexion
- Toujours utiliser get_config() de config_manager pour le credentials path
- Toujours ouvrir le spreadsheet par ID, jamais par nom
- Toujours vérifier que la feuille existe avant d'écrire

## Lecture
- Toujours utiliser get_all_records() pour lire tous les leads
- Filtrer en Python après lecture, pas avec des requêtes Sheets
- Mettre en cache les lectures (5 minutes) pour éviter les appels répététés

## Écriture
- Toujours utiliser append_row() pour les nouveaux leads
- Toujours utiliser update_cell() pour modifier une cellule existante
- Jamais écrire dans leads_bruts depuis l'auditeur
- Jamais écrire dans leads_audites depuis le scraper
- Après chaque écriture : logger "✓ Écrit : {nom} dans {feuille}"

## Colonnes attendues par feuille
leads_bruts : nom, adresse, site_web, telephone, gmb_id, rating, reviews_count, email, date_scraping, keyword
leads_audites : nom, site_web, date_audit, mobile_score, lcp_ms, cls, has_https, has_meta_description, h1_count, has_contact_button, has_schema, score_priorite, top3_problems, rapport_resume, email_objet, email_corps, statut
emails_envoyes : nom, email, date_envoi, objet, statut_envoi
