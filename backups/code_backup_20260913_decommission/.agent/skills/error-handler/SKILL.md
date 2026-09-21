---
name: error-handler
description: Activated when writing any try/except block, handling API errors, or managing retry logic in any file of this project.
---

# Règles de gestion d'erreurs

## Structure standard
Chaque appel API externe doit suivre ce pattern :
  try:
      résultat = appel_api()
      return résultat
  except Exception as e:
      log_error(f"{nom_fonction} | {url} | {str(e)[:120]}")
      return valeur_par_défaut

## Erreurs connues à gérer
- 429 (quota) → switch_to_next() depuis config_manager, retry
- 403 (accès refusé) → logger, statut = "acces_refuse", skip
- ConnectionError → statut = "site_inaccessible", skip
- Timeout → statut = "timeout", skip
- JSONDecodeError → retry 1 fois, puis statut = "erreur_parsing"

## Format du log
Toujours logger dans errors.log avec ce format :
  [YYYY-MM-DD HH:MM:SS] | NIVEAU | FONCTION | MESSAGE
Niveaux : INFO, WARNING, ERROR

## Ce qu'on ne fait jamais
- Ne jamais laisser un except Exception: pass sans logger
- Ne jamais raise une exception sans la logger d'abord
- Ne jamais crasher le script entier pour un seul lead raté
