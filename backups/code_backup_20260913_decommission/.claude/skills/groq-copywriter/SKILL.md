---
name: groq-copywriter
description: Activated when modifying business_copywriter.py or any file containing handle_llm_call, SYSTEM_PROMPT, or FEW_SHOT. Provides rules for prompt engineering and email generation quality.
---

# Règles pour l'agent Copywriter

## Identité LLM
- Le persona s'appelle toujours Thomas
- Le SYSTEM_PROMPT ne change jamais sans validation explicite
- Les FEW_SHOT examples restent dans le fichier, ne pas les supprimer

## Règles du mail généré
- Maximum 5 phrases dans email_corps, jamais plus
- L'objet contient toujours un fait chiffré ou une observation précise
- Jamais de bullet points dans le corps du mail
- Jamais de formule de politesse en ouverture
- Le lien rapport s'intègre dans une phrase naturelle
- Le CTA est toujours une question, jamais une affirmation

## Validation du JSON retourné par Groq
- Toujours vérifier la présence des 3 clés :
  rapport_resume, email_objet, email_corps
- Si JSON invalide → retry 1 fois avec le même prompt
- Si 2ème échec → statut = "erreur_llm", passer au lead suivant
- Ne jamais envoyer un email sans avoir validé le JSON

## Qualité de l'email
- After generation, vérifier que email_corps contient le nom de l'établissement (personnalisation minimale)
- Vérifier que le lien rapport est bien présent dans email_corps
- Si absent → régénérer
