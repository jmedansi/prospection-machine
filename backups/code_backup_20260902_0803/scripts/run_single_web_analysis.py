import sys
import asyncio
from auditeur.agents.web_analyzer import run_web_analysis

if len(sys.argv) < 2:
    print('Usage: python scripts/run_single_web_analysis.py <url> [report_dir]')
    sys.exit(1)

url = sys.argv[1]
report_dir = sys.argv[2] if len(sys.argv) > 2 else None

res = asyncio.run(run_web_analysis(url, report_dir=report_dir))
import json
print(json.dumps(res, ensure_ascii=False, indent=2))
