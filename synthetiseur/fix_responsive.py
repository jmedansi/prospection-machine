"""
fix_responsive.py
Injecte un bloc CSS responsive complet dans tous les templates hero.
A exécuter une seule fois.
"""
import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "templates_sites"

RESPONSIVE_BLOCK = """
/* ── RESPONSIVE TABLET ── */
@media(max-width:1024px){
  nav{padding:1.5rem 2rem!important}
  .hero-content,.hero-inner,.hero-left{padding-left:2rem!important;padding-right:2rem!important}
}
/* ── RESPONSIVE MOBILE ── */
@media(max-width:768px){
  .nav-cta,.nav-rdv,.nav-tel{font-size:.62rem!important;padding:.5rem .875rem!important;white-space:nowrap}
  .hero-title{font-size:clamp(2rem,7.5vw,3rem)!important;line-height:1.1!important}
  .hero-desc,.hero-description,.hero-text{font-size:.88rem!important;max-width:100%!important}
  .hero-ctas,.cta-group{flex-direction:column!important;align-items:flex-start!important;gap:.75rem!important}
  .hero-content,.hero-inner,.hero-left{max-width:100%!important}
  .page-preview{height:auto!important;min-height:60vh!important}
}
/* ── RESPONSIVE SMALL PHONE ── */
@media(max-width:480px){
  nav{padding:.75rem 1rem!important}
  .hero-title{font-size:clamp(1.6rem,9vw,2.25rem)!important}
  .hero-content,.hero-inner,.hero-left{padding-left:1rem!important;padding-right:1rem!important;padding-bottom:6rem!important}
  .hero-desc,.hero-description,.hero-text{font-size:.83rem!important}
  .stat-num{font-size:1.3rem!important}
  .stat-block{padding:.75rem 1rem!important}
  .btn-contact,.btn-primary,.nav-cta,.nav-rdv{width:100%!important;text-align:center!important;justify-content:center!important}
}
"""

def fix_template(path: Path):
    html = path.read_text(encoding="utf-8")

    # Éviter d'injecter deux fois
    if "RESPONSIVE TABLET" in html:
        print(f"  ⏭  Déjà traité : {path.name}")
        return

    # Injecter juste avant </style>
    if "</style>" not in html:
        print(f"  ⚠️  Pas de </style> : {path.name}")
        return

    html = html.replace("</style>", RESPONSIVE_BLOCK + "</style>", 1)
    path.write_text(html, encoding="utf-8")
    print(f"  ✅ Patché : {path.name}")


if __name__ == "__main__":
    files = list(TEMPLATES_DIR.rglob("*-hero-*.html"))
    print(f"\n{len(files)} templates trouvés\n")
    for f in sorted(files):
        fix_template(f)
    print("\nDone.\n")
