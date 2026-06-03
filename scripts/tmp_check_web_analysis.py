import asyncio
import json
import sys
import os

# ajouter le dossier racine au path pour importer les modules du projet
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.append(ROOT)

from auditeur.agents.web_analyzer import run_web_analysis


async def main():
    res = await run_web_analysis('https://debouchagedu66.fr', report_dir='data/reports/2140_tmp')
    print(json.dumps(res, ensure_ascii=False, default=str, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
