# CLAUDE.md — Instructions système pour Claude Code

Ce fichier est chargé automatiquement à chaque session Claude Code.
Il s'applique à toutes les conversations dans ce projet.

---

## Règle n°1 : Lire le README avant de toucher un module

**OBLIGATOIRE** : avant de modifier, créer ou refactorer quoi que ce soit dans un dossier,
lire son `README.md` s'il existe.

Ces fichiers contiennent :
- L'intention de design et les contraintes
- Ce qui est isolé volontairement et pourquoi
- Les connexions à d'autres modules (et ce qu'il ne faut PAS dupliquer)
- Les règles spécifiques au module

Si tu ignores le README et casses une contrainte explicitement documentée, c'est une erreur.

---

## Règle n°2 : Tout nouveau module doit avoir un README

Quand tu crées un nouveau dossier / module / agent :
1. Crée un `README.md` dans ce dossier
2. Documente : rôle, structure, flux de données, règles à respecter, connexions avec l'existant
3. Si le module est isolé volontairement, explique pourquoi et comment il se branchera plus tard

---

## Règle n°3 : Lire AGENTS.md avant tout changement email/copywriting

`AGENTS.md` (racine du projet) est la source de vérité pour le pipeline email.
Lire avant tout changement lié à : emails, copywriting, templates, envoi, audit.

---

## Architecture générale du projet

```
prospection-machine/
├── AGENTS.md           ← règles pipeline email (lire avant tout changement email)
├── CLAUDE.md           ← ce fichier
│
├── [Pipeline Maps — NE PAS MODIFIER sans raison explicite]
│   ├── scraper/        ← Google Maps scraper
│   ├── auditeur/       ← PageSpeed + GMB audit
│   ├── copywriter/     ← détection situation S1-S8
│   ├── envoi/          ← email_builder + resend_sender
│   ├── templates/      ← templates HTML profil A/B/C/D
│   ├── agents/         ← redacteur, expediteur, auditeur, scraper...
│   └── dashboard/      ← Flask app + routes API
│
├── [Pipeline Sniper — module isolé, NE PAS connecter à l'ancien sans validation]
│   └── sniper/         ← README.md obligatoire à lire en premier
│
└── database/           ← SQLite partagé entre les deux pipelines
```

---

## Principes de modification

- **Ne jamais modifier ce qui marche** sans raison explicite demandée par l'utilisateur
- **Ne jamais "améliorer" du code non demandé** (pas de refactoring opportuniste)
- **Isolation intentionnelle** : si un module est dans son propre dossier, c'est voulu — ne pas fusionner sans demander
- **Connexion progressive** : les nouveaux modules s'intègrent à l'existant uniquement quand validés

---

## Base de données

- SQLite unique : `data/prospection.db`
- Tables partagées entre l'ancien et le nouveau pipeline
- `migrate_db()` dans `database/schema.py` pour les migrations — appelé au démarrage Flask
- Ne jamais modifier le schéma directement — passer par `migrate_db()`
