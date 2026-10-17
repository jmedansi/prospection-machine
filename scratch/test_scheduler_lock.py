"""Tests unitaires du verrou scheduler — sur fichier TEMPORAIRE, base intouchée."""
import os, sys, tempfile, subprocess, time

sys.path.insert(0, r'D:\prospection-machine')
from dashboard import scheduler as S

TMP = os.path.join(tempfile.mkdtemp(), '.scheduler.lock')
S._scheduler_lock_path = TMP

ok = fail = 0


def check(label, cond, detail=''):
    global ok, fail
    if cond:
        ok += 1
        print(f'  PASS  {label}')
    else:
        fail += 1
        print(f'  FAIL  {label}   {detail}')


def reset():
    S._LOCK_RELEASED = False
    if os.path.exists(TMP):
        os.remove(TMP)


def pid_mort():
    """PID réellement mort (processus lancé puis terminé)."""
    p = subprocess.Popen([sys.executable, '-c', 'pass'])
    pid = p.pid
    p.wait(timeout=15)
    for _ in range(20):
        if not S._pid_running(pid):
            return pid
        time.sleep(0.1)
    return None


DEAD = pid_mort()
print(f'PID mort utilisé pour les tests : {DEAD}\n')

print('1. Lock absent -> acquisition')
reset()
r = S._acquire_scheduler_lock()
check('acquisition réussie', r is True, f'retour={r}')
check('fichier créé', os.path.exists(TMP))
contenu = open(TMP, encoding='utf-8').read()
check('format pid|création', '|' in contenu, f'contenu={contenu!r}')
check('contient notre PID', contenu.split('|')[0] == str(os.getpid()))
check('owner_alive = True (nous)', S._lock_owner_alive() is True)

print('\n2. Lock déjà tenu par un processus VIVANT -> refus (pas de 2e scheduler)')
r = S._acquire_scheduler_lock()
check('second acquire refusé', r is False, f'retour={r}')

print('\n3. Release -> on ne supprime QUE notre propre lock')
S._release_scheduler_lock()
check('notre lock libéré', not os.path.exists(TMP))
check('idempotent (2e appel sans effet)', S._release_scheduler_lock() is None)

print('\n4. Lock ORPHELIN ancien format (PID mort, ex. "3536") -> reprise')
reset()
if DEAD:
    open(TMP, 'w').write(str(DEAD))
    check('owner_alive = False (PID mort)', S._lock_owner_alive() is False)
    r = S._acquire_scheduler_lock()
    check('reprise réussie', r is True, f'retour={r}')
    check('lock réécrit avec notre identité',
          open(TMP, encoding='utf-8').read().split('|')[0] == str(os.getpid()))
else:
    print('  SKIP  (pas de PID mort disponible)')

print('\n5. Lock ORPHELIN nouveau format (pid|création incorrecte) -> reprise')
reset()
if DEAD:
    open(TMP, 'w').write(f'{DEAD}|12345')
    check('owner_alive = False (pid mort)', S._lock_owner_alive() is False)
    r = S._acquire_scheduler_lock()
    check('reprise réussie', r is True, f'retour={r}')

print('\n6. PID RÉEMPLACÉ (PID vivant MAIS heure de création différente) -> reprise')
reset()
mauvaise_cle = (S._pid_start_key(os.getpid()) or 0) + 999999
open(TMP, 'w').write(f'{os.getpid()}|{mauvaise_cle}')
check('owner_alive = False (création != )', S._lock_owner_alive() is False)
r = S._acquire_scheduler_lock()
check('reprise réussie malgré PID vivant', r is True, f'retour={r}')

print('\n7. PID vivant avec la VRAIE clé (un vrai pair en vie) -> refus')
reset()
cle = S._pid_start_key(os.getpid())
open(TMP, 'w').write(f'{os.getpid()}|{cle}')
check('owner_alive = True (vrai pair)', S._lock_owner_alive() is True)
check('acquisition refusée', S._acquire_scheduler_lock() is False)

print('\n8. Contenu corrompu / vide -> on reprend (pas de blocage définitif)')
for contenu in ('', 'nimporte quoi', '12|abc', '3536|'):
    reset()
    open(TMP, 'w').write(contenu)
    etat = S._lock_owner_alive()
    r = S._acquire_scheduler_lock()
    check(f'contenu {contenu!r}: pas de blocage',
          etat is False and r is True, f'etat={etat} acquis={r}')

print('\n9. Release ne touche JAMAIS le lock d\'un tiers')
reset()
autre = DEAD or 1
open(TMP, 'w').write(f'{autre}|424242')
S._LOCK_RELEASED = False
S._release_scheduler_lock()
check('lock étranger préservé', os.path.exists(TMP))
check('contenu inchangé', open(TMP, encoding='utf-8').read() == f'{autre}|424242')

print('\n10. Race : le contenu change pendant qu\'on juge le lock -> on n\'en supprime pas un autre')
reset()
if DEAD:
    # Un VRAI pair vivant, pour tester le cas « un concurrent écrit pendant qu\'on juge ».
    pair = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
    try:
        cle_pair = S._pid_start_key(pair.pid)
        contenu_pair = f'{pair.pid}|{cle_pair}'
        ancien = str(DEAD)                   # lock orphelin qu\'on juge au départ

        orig_raw = S._lock_raw
        etat = {'n': 0}

        def raw_piege():
            """Fichier RÉEL, mais le « pair » écrit son lock juste avant notre
            re-vérification (tout 3e appel) — c'est la fenêtre de la race."""
            etat['n'] += 1
            if etat['n'] == 3:
                open(TMP, 'w').write(contenu_pair)
            return orig_raw()

        S._lock_raw = raw_piege
        try:
            open(TMP, 'w').write(ancien)     # état au début de l\'acquisition
            r = S._acquire_scheduler_lock()
            contenu = open(TMP, encoding='utf-8').read()
        finally:
            S._lock_raw = orig_raw
        check('lock du pair INTACT (jamais supprimé)', contenu == contenu_pair,
              f'contenu={contenu!r} attendu={contenu_pair!r}')
        check('a finalement cédé la main', r is False, f'retour={r}')
        check('a bien vu la fenêtre de race', etat['n'] >= 3, f'appels={etat["n"]}')
    finally:
        pair.terminate()
        pair.wait(timeout=15)
else:
    print('  SKIP  (pas de PID mort disponible)')

reset()
print(f'\n{"="*60}\nRESULTAT : {ok} OK / {fail} ECHEC')
sys.exit(1 if fail else 0)
