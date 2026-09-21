import os
from bs4 import BeautifulSoup
import re

base_path = r"d:\prospection-machine\synthetiseur\templates_sites"

css_fix = """
    /* --- Fix hauteur 100svh --- */
    @media (min-width: 1024px) {
      .hero-title {
        font-size: clamp(2rem, 3.2vw, 2.8rem) !important;
        margin-bottom: 1rem !important;
        line-height: 1.15 !important;
      }
      .hero-desc {
        font-size: 1rem !important;
        margin-bottom: 1.5rem !important;
      }
      .hero-actions, .hero-ctas {
        margin-top: 1rem !important;
      }
    }
"""

def update_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        html = f.read()

    # Check if fix is already applied
    if "/* --- Fix hauteur 100svh --- */" in html:
        return

    # Find the closing </style> tag and insert the fix just before it
    if '</style>' in html:
        html = html.replace('</style>', css_fix + '\n  </style>')
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"Fixed {os.path.basename(filepath)}")

sectors = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
for sector in sectors:
    dir_path = os.path.join(base_path, sector)
    for filename in os.listdir(dir_path):
        if filename.endswith('.html'):
            update_file(os.path.join(dir_path, filename))
print("Done!")
