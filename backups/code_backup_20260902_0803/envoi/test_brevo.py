# -*- coding: utf-8 -*-
"""
Test d'envoi Brevo en isolation.
Lance : python envoi/test_brevo.py
"""

from brevo_sender import send_prospecting_email

print("\n" + "="*50)
print("TEST BREVO — Machine de Prospection Incidenx")
print("="*50 + "\n")

# ═══ TEST 1 — DRY RUN ═══
print("TEST 1 — Dry Run (aucun email envoyé)\n")

result = send_prospecting_email(
    prospect_email = "test@example.com",
    prospect_nom   = "Restaurant Test",
    email_objet    = "votre site met 5,8 secondes à charger sur mobile",
    email_corps    = """Bonjour,

J'ai regardé votre site ce matin.
Sur mobile, il charge en 5,8s — vos visiteurs partent
avant de voir vos services.

J'ai préparé votre audit ici : [lien rapport]

15 minutes cette semaine ?

Jean-Marc DANSI
jmedansi@incidenx.com""",
    lien_rapport   = "https://drive.google.com/test",
    dry_run        = True
)

print(f"Résultat dry run : {result['statut']}")

if result['statut'] == 'dry_run':
    print("✅ Dry run OK\n")
else:
    print("❌ Problème dry run\n")


# ═══ TEST 2 — ENVOI RÉEL ═══
print("TEST 2 — Envoi réel sur jmedansi@incidenx.com\n")

confirm = input(
    "Envoyer un email de test à jmedansi@incidenx.com ? (oui/non) : "
)

if confirm.lower() != "oui":
    print("Test annulé.")
    exit()

result = send_prospecting_email(
    prospect_email = "jmedansi@incidenx.com",
    prospect_nom   = "Jean-Marc DANSI",
    email_objet    = "[TEST] Machine de Prospection — Incidenx",
    email_corps    = """Bonjour Jean-Marc,

Ceci est un email de test de la machine de prospection Incidenx.

Si tu reçois cet email dans ta boîte principale (pas spam),
Brevo est correctement connecté et le domaine incidenx.com
est bien authentifié.

La machine est prête.

Jean-Marc DANSI
jmedansi@incidenx.com""",
    dry_run = False
)

print(f"\n{'='*50}")
if result['success']:
    print("✅ Email envoyé avec succès !")
    print(f"Message ID : {result['message_id']}")
    print("\nVérifie maintenant :")
    print("  1. Ta boîte mail jmedansi@incidenx.com")
    print("  2. L'email est dans la boîte principale (pas spam)")
    print("  3. L'expéditeur affiché est 'Jean-Marc DANSI'")
    print("  4. Dashboard Brevo → Logs → email visible")
else:
    print("❌ Échec de l'envoi")
    print(f"Erreur : {result['erreur']}")
    print("\nVérifie :")
    print("  1. BREVO_API_KEY dans ton .env")
    print("  2. BREVO_SENDER_EMAIL=jmedansi@incidenx.com")
    print("  3. Domaine incidenx.com validé dans Brevo")
print(f"{'='*50}\n")
