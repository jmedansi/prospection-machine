#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Simple monitor: affiche les dernières lignes du log du worker et les comptes
de la file d'attente toutes les 5 secondes.
"""
import time
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(ROOT, 'audit_worker.log')
QBASE = os.path.join(ROOT, 'audit_queue')

def tail_lines(path, n=20):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
            return lines[-n:]
    except Exception:
        return []

def count_dir(name):
    p = os.path.join(QBASE, name)
    try:
        return len([f for f in os.listdir(p) if f.endswith('.json')])
    except Exception:
        return 0

def print_status():
    os.system('cls')
    print('Audit Monitor —', datetime.now().isoformat())
    print('-' * 60)
    print('Worker log (last 20 lines):')
    for l in tail_lines(LOG, 20):
        print(l)
    print('-' * 60)
    print('Queue counts:')
    print('  pending:   ', count_dir('pending'))
    print('  processing:', count_dir('processing'))
    print('  history:   ', count_dir('history'))
    print('-' * 60)

if __name__ == '__main__':
    try:
        while True:
            print_status()
            time.sleep(5)
    except KeyboardInterrupt:
        print('\nMonitor stopped')
