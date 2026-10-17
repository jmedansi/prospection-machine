"""Contrôle strict : réconciliation des comptes (éligibles / adresses distinctes / excédent)."""
import sqlite3, sys
from collections import Counter
sys.stdout.reconfigure(encoding='utf-8')

DB = 'file:D:/prospection-machine/data/prospection.db?mode=ro'

CAND = """
SELECT p.id, LOWER(TRIM(p.email)) AS email, p.liste_id, l.nom AS liste_nom,
       c.id AS campagne_id, c.nom AS campagne_nom
FROM prospects p
JOIN listes l ON p.liste_id = l.id
JOIN campagnes c ON c.id = l.campagne_id
WHERE p.statut = 'qualifie' AND p.ecarte = 0 AND p.ne_plus_contacter = 0
  AND p.email IS NOT NULL AND TRIM(p.email) != ''
  AND LOWER(TRIM(p.email)) NOT IN (SELECT LOWER(email) FROM suppression_list)
"""


def main():
    conn = sqlite3.connect(DB, uri=True)
    conn.row_factory = sqlite3.Row
    cands = [dict(r) for r in conn.execute(CAND)]

    print(f'Total éligibles (toutes campagnes) : {len(cands)}')

    # ── Contrôle 1 : par campagne ──────────────────────────────────────────
    print()
    print('=' * 80)
    print('CONTRÔLE 1 — par campagne')
    print('=' * 80)
    by = {}
    for c in cands:
        by.setdefault(c['campagne_id'], []).append(c)
    for cid, lst in sorted(by.items(), key=lambda kv: -len(kv[1])):
        cnt = Counter(x['email'] for x in lst)
        dup_addrs = {k: v for k, v in cnt.items() if v > 1}
        extra = sum(v - 1 for v in cnt.values())
        print(f'  [{cid}] {(lst[0]["campagne_nom"] or "?")[:34]:34} '
              f'éligibles={len(lst):4}  adresses={len(cnt):4}  '
              f'adresses en double={len(dup_addrs):3}  envois excédentaires={extra:3}')
        assert len(lst) - len(cnt) == extra, 'incohérence campagne'

    # ── Contrôle 2 : campagne Restauration — Maps, détail liste par liste ──
    print()
    print('=' * 80)
    print('CONTRÔLE 2 — détail des listes de la campagne « Restauration — Maps »')
    print('=' * 80)
    resto = [c for c in cands if (c['campagne_nom'] or '').startswith('🗺')]
    bl = {}
    for c in resto:
        bl.setdefault(c['liste_id'], []).append(c)
    tot_l = tot_a = tot_e = 0
    for lid, lst in sorted(bl.items()):
        cnt = Counter(x['email'] for x in lst)
        extra = sum(v - 1 for v in cnt.values())
        dup = {k: v for k, v in cnt.items() if v > 1}
        tot_l += len(lst); tot_a += len(cnt); tot_e += extra
        print(f'  liste {lid:>4} « {(lst[0]["liste_nom"] or "?")[:28]:28} » '
              f'éligibles={len(lst):4} adresses={len(cnt):4} '
              f'doublons={len(dup):3} excédent={extra:3}')
    print(f'  {"SOMME DES LISTES":40} éligibles={tot_l:4} adresses={tot_a:4} '
          f'doublons=?  excédent={tot_e:3}')
    cnt_all = Counter(x['email'] for x in resto)
    print(f'  {"CAMPAGNE (agrégé)":40} éligibles={len(resto):4} adresses={len(cnt_all):4} '
          f'adresses en double={sum(1 for v in cnt_all.values() if v > 1):3} '
          f'excédent={sum(v-1 for v in cnt_all.values()):3}')
    print(f'  (écart somme/agrégé = {tot_e - sum(v-1 for v in cnt_all.values())} '
          f'=> adresses identiques réparties sur PLUSIEURS listes de la campagne)')

    # ── Contrôle 3 : top doublons dans la campagne ─────────────────────────
    print()
    print('=' * 80)
    print('CONTRÔLE 3 — top adresses en double (campagne Restauration — Maps)')
    print('=' * 80)
    top = sorted(((k, v) for k, v in cnt_all.items() if v > 1), key=lambda kv: -kv[1])
    for k, v in top[:12]:
        lids = sorted({c['liste_id'] for c in resto if c['email'] == k})
        print(f'  x{v:<3} {k:44} listes={lids}')
    print(f'  ... {len(top)} adresses en double au total dans cette campagne')

    # ── Contrôle 4 : chevauchement inter-campagnes ─────────────────────────
    print()
    print('=' * 80)
    print('CONTRÔLE 4 — adresses présentes dans PLUSIEURS campagnes')
    print('=' * 80)
    addr_camp = {}
    for c in cands:
        addr_camp.setdefault(c['email'], set()).add(c['campagne_id'])
    cross = {k: v for k, v in addr_camp.items() if len(v) > 1}
    print(f'  => {len(cross)} adresses éligibles dans 2+ campagnes')
    for k, v in list(cross.items())[:10]:
        print(f'     {k:44} campagnes={sorted(v)}')

    conn.close()


if __name__ == '__main__':
    main()
