"""État des lots de validation Telegram (+ horodatage) — pour suivi post-redémarrage."""
import sqlite3, sys, datetime
from datetime import date

sys.stdout.reconfigure(encoding='utf-8')
DB = 'file:D:/prospection-machine/data/prospection.db?mode=ro'

conn = sqlite3.connect(DB, uri=True)
conn.row_factory = sqlite3.Row

print('HEURE MAINTENANT :', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
print('scheduler PID dans lock :', end=' ')
try:
    print(open('D:/prospection-machine/.scheduler.lock').read().strip())
except OSError:
    print('(absent)')

print()
print('relance_batches :')
rows = conn.execute('SELECT callback_id, campagne_id, liste_id, position, count, statut, '
                    'created_at, updated_at, tentatives '
                    'FROM relance_batches ORDER BY created_at').fetchall()
for r in rows:
    print(f'  {r["callback_id"]:20} pos={r["position"]} cnt={r["count"]:>3} '
          f'statut={r["statut"]:7} tent={r["tentatives"]} '
          f'cree={r["created_at"]} maj={r["updated_at"]}')
print()
print(f'TOTAL = {len(rows)}')

# Les dues attendues (rappel) pour comparer après le cycle de 10 min
print()
print('Lots qu\'on attendrait (campagne 44) :')
print('  v2_batch_44_163  pos=3 cnt=39  (position 2 -> 3 : doit être redemandé)')
print('  v2_batch_44_155  pos=1 cnt=10  (aucun lot)')
print('  v2_batch_44_181  pos=2 cnt=4   (aucun lot)')
print('  v2_batch_44_180  pos=2 cnt=1   (aucun lot)')
conn.close()
