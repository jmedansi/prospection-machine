
# Vérification exacte du matching
line_success = "   [SQLite] [OK] Audit enregistré avec succès pour Test Lead"
line_fail = "   [SQLite] [ERROR] Audit marqué comme ÉCHOUÉ pour Test Lead"

ll_success = line_success.lower()
ll_fail = line_fail.lower()

print(f"Success line (lowered): '{ll_success}'")
print(f"Fail line (lowered): '{ll_fail}'")

# Test match succès
match_success = ("[sqlite] audit" in ll_success and "enregistr" in ll_success) or "audit enregistr" in ll_success
print(f"\nSuccess pattern match: {match_success}")

# Test match échec  
match_fail_1 = "echoue" in ll_fail
match_fail_2 = "audit_echoue" in ll_fail
print(f"'echoue' in fail line: {match_fail_1}")
print(f"'audit_echoue' in fail line: {match_fail_2}")

# L'accent est le problème
print(f"\nCheck: 'é' == 'e'? {'é' == 'e'}")
print(f"'échoué'.lower() = '{'ÉCHOUÉ'.lower()}'")
print(f"'echoue' in 'échoué': {'echoue' in 'échoué'}")

# Il y a aussi un problème dans le elif: si le pattern succès matche AUSSI 
# sur la ligne échoué, le elif ne sera jamais atteint
match_success_on_fail = ("[sqlite] audit" in ll_fail and "enregistr" in ll_fail) or "audit enregistr" in ll_fail
print(f"\nDoes success pattern match on FAIL line? {match_success_on_fail}")
# La ligne d'echec: "[sqlite] [error] audit marqué comme échoué pour test lead"
# Contient "[sqlite]" et "audit" et... "enregistr"? NON -> pas de match ici, OK

# Vérification aussi du pattern de la ligne d'echec dans main.py L176:
line_fail_2 = "   [ERREUR] Échec de l'analyse après 3 tentatives — aucune donnée exploitable"
ll_fail_2 = line_fail_2.lower()
match_fail_on_2 = "echoue" in ll_fail_2
print(f"\n--- Other error lines ---")
print(f"Line: '{ll_fail_2}'")
print(f"'echoue' in this: {match_fail_on_2}")
print(f"'échec' in this: {'échec' in ll_fail_2}")

# Check line L221 from main.py
line_fail_3 = "   [ERREUR] Audit echoue apres 3 tentatives - pas de rapport genere"
ll_fail_3 = line_fail_3.lower()
match_fail_on_3 = "echoue" in ll_fail_3
print(f"\nLine L221: '{ll_fail_3}'")
print(f"'echoue' in this: {match_fail_on_3}")
