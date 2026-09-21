# -*- coding: utf-8 -*-
"""
test_lighthouse_batch.py — Test de résistance : Lighthouse CLI vs PageSpeed API en batch.

Objectif : valider si Lighthouse CLI peut remplacer l'auditeur actuel
pour des campagnes de 200 audits sans planter.

Usage :
    # Test rapide (10 URLs par défaut)
    python tests/test_methods/test_lighthouse_batch.py --quick

    # Lister les URLs depuis la base SQLite (200 premiers leads)
    python tests/test_methods/test_lighthouse_batch.py --from-db --limit 200

    # Depuis un fichier (une URL par ligne)
    python tests/test_methods/test_lighthouse_batch.py --from-file urls.txt

    # URLs inline
    python tests/test_methods/test_lighthouse_batch.py --urls "https://site1.com" "https://site2.com"

    # Sec — comparer avec PageSpeed API en plus
    python tests/test_methods/test_lighthouse_batch.py --from-db --limit 20 --compare
"""
import sys
import os
import json
import time
import subprocess
import tempfile
import argparse
import shutil
from datetime import datetime
from typing import Optional

# Force UTF-8 output for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT)

# ── Configuration ──────────────────────────────────────────────────────────
LIGHTHOUSE_TIMEOUT_S = 180
# 0 = séquentiel; 1+ = N workers en parallèle (risqué mémoire)
PARALLEL_WORKERS = 0


# =========================================================================
#  1. Lighthouse CLI
# =========================================================================

def _find_lighthouse() -> str:
    """Détecte le chemin du binaire lighthouse."""
    # 1. shutil.which
    path = shutil.which("lighthouse")
    if path:
        return path
    # 2. Windows npm global
    for candidate in [
        r"C:\Users\jmeda\AppData\Roaming\npm\lighthouse.cmd",
        r"C:\Users\jmeda\AppData\Roaming\npm\lighthouse",
    ]:
        if os.path.exists(candidate):
            return candidate
    # 3. which via shell
    try:
        result = subprocess.run(
            ["where", "lighthouse"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[0]
    except Exception:
        pass
    return "lighthouse"  # fallback — peut planter


LIGHTHOUSE_BIN = _find_lighthouse()


def lighthouse_audit(url: str, strategy: str = "mobile",
                     real_throttle: bool = False) -> Optional[dict]:
    """Lance Lighthouse en subprocess, retourne les métriques clés.

    real_throttle=False → --throttling-method=simulate (rapide, ~15-30s par URL)
    real_throttle=True  → --throttling-method=devtools (lent, ~60-120s par URL)
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        output_path = f.name

    throttle = "devtools" if real_throttle else "simulate"
    start = time.time()
    try:
        proc = subprocess.run(
            [
                LIGHTHOUSE_BIN, url,
                f"--output-path={output_path}",
                "--output=json",
                f"--form-factor={strategy}",
                f"--throttling-method={throttle}",
                "--chrome-flags=--headless --no-sandbox --disable-dev-shm-usage",
                "--quiet",
                "--no-enable-error-reporting",
                "--disable-storage-reset",
            ],
            timeout=LIGHTHOUSE_TIMEOUT_S,
            capture_output=True,
            text=True,
        )

        elapsed = round(time.time() - start, 1)

        if proc.returncode != 0:
            return {
                "url": url,
                "strategy": strategy,
                "success": False,
                "error": f"returncode={proc.returncode}: {proc.stderr[:200]}",
                "elapsed_s": elapsed,
            }

        with open(output_path, encoding="utf-8") as f:
            data = json.load(f)

        audits = data.get("audits", {})
        cats = data.get("categories", {})
        perf = cats.get("performance", {})

        lcp = audits.get("largest-contentful-paint", {}).get("numericValue")
        fcp = audits.get("first-contentful-paint", {}).get("numericValue")
        tbt = audits.get("total-blocking-time", {}).get("numericValue")
        cls = audits.get("cumulative-layout-shift", {}).get("numericValue")
        si = audits.get("speed-index", {}).get("numericValue")
        score = perf.get("score")

        return {
            "url": url,
            "strategy": strategy,
            "success": True,
            "score": round(score * 100) if score else None,
            "lcp_ms": round(lcp) if lcp else None,
            "fcp_ms": round(fcp) if fcp else None,
            "tbt_ms": round(tbt) if tbt else None,
            "cls": round(cls, 4) if cls else None,
            "speed_index_ms": round(si) if si else None,
            "source": "lighthouse-devtools",
            "elapsed_s": elapsed,
        }

    except subprocess.TimeoutExpired:
        elapsed = round(time.time() - start, 1)
        return {
            "url": url, "strategy": strategy, "success": False,
            "error": f"TIMEOUT ({LIGHTHOUSE_TIMEOUT_S}s)",
            "elapsed_s": elapsed,
        }
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        return {
            "url": url, "strategy": strategy, "success": False,
            "error": str(e)[:200],
            "elapsed_s": elapsed,
        }
    finally:
        try:
            os.unlink(output_path)
        except OSError:
            pass


# =========================================================================
#  2. PageSpeed API (baseline existante)
# =========================================================================

def pagespeed_audit(url: str, strategy: str = "mobile") -> Optional[dict]:
    """Appel PageSpeed API — tel qu'utilisé dans l'auditeur actuel."""
    import requests as req

    api_key = os.getenv("GOOGLE_API_KEY")
    psi_url = (
        f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        f"?url={url}&strategy={strategy}"
        f"&category=performance&category=seo"
    )
    if api_key:
        psi_url += f"&key={api_key}"

    start = time.time()
    try:
        resp = req.get(psi_url, timeout=45)
        resp.raise_for_status()
        data = resp.json()

        lh = data.get("lighthouseResult", {})
        crux = data.get("loadingExperience", {})
        audits = lh.get("audits", {})
        perf = lh.get("categories", {}).get("performance", {})

        # CrUX (vraies données terrain)
        crux_metrics = crux.get("metrics", {})
        crux_lcp = None
        if crux_metrics and "LARGEST_CONTENTFUL_PAINT_MS" in crux_metrics:
            crux_lcp = crux_metrics["LARGEST_CONTENTFUL_PAINT_MS"].get("percentile")

        # Lab data (Lighthouse simulé 4G)
        raw_lcp = audits.get("largest-contentful-paint", {}).get("numericValue")
        raw_fcp = audits.get("first-contentful-paint", {}).get("numericValue")
        raw_tbt = audits.get("total-blocking-time", {}).get("numericValue")
        raw_cls = audits.get("cumulative-layout-shift", {}).get("numericValue")
        raw_si = audits.get("speed-index", {}).get("numericValue")
        score = perf.get("score")

        elapsed = round(time.time() - start, 1)

        return {
            "url": url,
            "strategy": strategy,
            "success": True,
            "score": round(score * 100) if score else None,
            "lcp_ms": round(raw_lcp) if raw_lcp else None,
            "fcp_ms": round(raw_fcp) if raw_fcp else None,
            "tbt_ms": round(raw_tbt) if raw_tbt else None,
            "cls": round(raw_cls, 4) if raw_cls else None,
            "speed_index_ms": round(raw_si) if raw_si else None,
            "crux_lcp_ms": crux_lcp,
            "source": "pagespeed-api",
            "elapsed_s": elapsed,
        }

    except Exception as e:
        elapsed = round(time.time() - start, 1)
        return {
            "url": url, "strategy": strategy, "success": False,
            "error": str(e)[:200], "source": "pagespeed-api",
            "elapsed_s": elapsed,
        }


# =========================================================================
#  3. Batch runner
# =========================================================================

def run_batch(urls: list[str], method: str = "lighthouse",
              strategy: str = "mobile", parallel: int = 0,
              real_throttle: bool = False) -> list[dict]:
    """Exécute une méthode sur une liste d'URLs."""
    results = []
    total = len(urls)
    errors = 0
    t_start = time.time()

    def _run(url):
        if method == "lighthouse":
            return lighthouse_audit(url, strategy=strategy, real_throttle=real_throttle)
        return pagespeed_audit(url, strategy=strategy)

    for i, url in enumerate(urls):
        tick = time.time()
        print(f"  [{i+1}/{total}] {url[:60]:60s} ... ", end="", flush=True)
        result = _run(url)
        elapsed_site = round(time.time() - tick, 1)
        results.append(result)

        if result.get("success"):
            s = result.get("score", "?")
            l = result.get("lcp_ms", "?")
            print(f"score={s}  lcp={l}ms  ({elapsed_site}s)")
        else:
            errors += 1
            print(f"ECHEC  ({elapsed_site}s): {result.get('error', '?')}")

    total_elapsed = round(time.time() - t_start, 1)
    successes = total - errors

    summary = {
        "method": method,
        "strategy": strategy,
        "total": total,
        "successes": successes,
        "errors": errors,
        "success_rate": round(successes / total * 100, 1) if total else 0,
        "total_elapsed_s": total_elapsed,
        "avg_per_url_s": round(total_elapsed / total, 1) if total else 0,
        "results": results,
    }

    return summary


def print_summary(summary: dict):
    """Affiche le récapitulatif d'un batch."""
    s = summary
    rate = s["success_rate"]
    color = "OK" if rate >= 90 else "WARN" if rate >= 70 else "ECHEC"

    print(f"\n{'='*60}")
    print(f"  RÉCAPITULATIF — {s['method']} ({s['strategy']})")
    print(f"{'='*60}")
    print(f"  Total     : {s['total']}")
    print(f"  Succès    : {s['successes']}")
    print(f"  Échecs    : {s['errors']}")
    print(f"  Taux      : {s['success_rate']}%  [{color}]")
    print(f"  Durée     : {s['total_elapsed_s']}s  ({s['total_elapsed_s']/60:.1f}min)")
    print(f"  Moyenne   : {s['avg_per_url_s']}s par URL")

    if s["results"]:
        ok = [r for r in s["results"] if r.get("success")]
        if ok:
            scores = [r["score"] for r in ok if r.get("score")]
            lcps = [r["lcp_ms"] for r in ok if r.get("lcp_ms")]
            fcps = [r["fcp_ms"] for r in ok if r.get("fcp_ms")]
            tbts = [r["tbt_ms"] for r in ok if r.get("tbt_ms")]
            clss = [r["cls"] for r in ok if r.get("cls") is not None]
            print(f"\n  Métriques (moyennes sur {len(ok)} succès):")
            if scores:
                print(f"    Score     : {sum(scores)/len(scores):.0f}/100  "
                      f"(min={min(scores)}, max={max(scores)})")
            if lcps:
                print(f"    LCP       : {sum(lcps)/len(lcps):.0f}ms  "
                      f"(min={min(lcps)}, max={max(lcps)})")
            if fcps:
                print(f"    FCP       : {sum(fcps)/len(fcps):.0f}ms")
            if tbts:
                print(f"    TBT       : {sum(tbts)/len(tbts):.0f}ms")
            if clss:
                print(f"    CLS       : {sum(clss)/len(clss):.4f}")

    print(f"{'='*60}\n")


def print_comparison(lh_summary: dict, ps_summary: dict):
    """Compare les résultats Lighthouse vs PageSpeed API."""
    lh_ok = {r["url"]: r for r in lh_summary["results"] if r.get("success")}
    ps_ok = {r["url"]: r for r in ps_summary["results"] if r.get("success")}
    common = set(lh_ok.keys()) & set(ps_ok.keys())

    if not common:
        print("\n  Aucune URL commune à comparer.\n")
        return

    print(f"\n{'='*80}")
    print("  COMPARAISON Lighthouse vs PageSpeed API (URLs communes)")
    print(f"{'='*80}")
    print(f"{'URL':<45} {'Src Score':>10} {'Src LCP':>10} {'PS Score':>10} {'PS LCP':>10}")
    print("-" * 85)

    lh_scores, ps_scores = [], []
    lh_lcps, ps_lcps = [], []

    for url in sorted(common):
        l = lh_ok[url]
        p = ps_ok[url]
        ls = l.get("score") or 0
        ps = p.get("score") or 0
        ll = l.get("lcp_ms") or 0
        pl = p.get("lcp_ms") or 0
        short = url.replace("https://", "")[:42]
        print(f"{short:<45} {ls:>10} {ll:>10}ms {ps:>10} {pl:>10}ms")
        lh_scores.append(ls)
        ps_scores.append(ps)
        lh_lcps.append(ll)
        ps_lcps.append(pl)

    if lh_scores:
        print("-" * 85)
        print(f"{'Moyenne':<45} {sum(lh_scores)/len(lh_scores):>8.0f}/100     "
              f"{sum(ps_scores)/len(ps_scores):>8.0f}/100")
        print(f"{'Écart moyen score':<45} {abs(sum(lh_scores)-sum(ps_scores))/len(lh_scores):>8.1f} pts")
    if lh_lcps:
        print(f"{'Écart moyen LCP':<45} {abs(sum(lh_lcps)-sum(ps_lcps))/len(lh_lcps):>8.0f}ms")
    print(f"{'='*80}\n")


# =========================================================================
#  4. Sources d'URLs
# =========================================================================

def urls_from_db(limit: int = 200) -> list[str]:
    """Récupère les URLs depuis la base SQLite (leads_bruts)."""
    try:
        from database.db_manager import get_leads_pending
        leads = get_leads_pending()
        urls = []
        for l in leads:
            url = l.get("site_web", "").strip()
            if url and url.startswith(("http://", "https://")):
                urls.append(url)
            if len(urls) >= limit:
                break
        print(f"  [DB] {len(urls)} URLs récupérées depuis SQLite (limite={limit})")
        return urls
    except Exception as e:
        print(f"  [DB] Erreur lecture SQLite: {e}")
        return []


def urls_from_file(path: str) -> list[str]:
    """Lit les URLs depuis un fichier (une par ligne)."""
    if not os.path.exists(path):
        print(f"  [FILE] Fichier introuvable: {path}")
        return []
    with open(path) as f:
        urls = [
            line.strip() for line in f
            if line.strip() and not line.startswith("#")
        ]
    print(f"  [FILE] {len(urls)} URLs lues depuis {path}")
    return urls


def urls_from_test_set() -> list[str]:
    """Jeu de test par défaut — sites PME locales (représentatifs des leads)."""
    return [
        "https://depann-assistance.com",
        "https://trouver-avocats.fr",
        "https://www.mon-avocat.fr",
        "https://www.artisan-plombier-chauffagiste.fr",
        "https://www.maisondejardin.fr",
        "https://www.restaurant-laterrasse.fr",
        "https://www.coiffeur-bordeaux.fr",
        "https://electricien-paris.fr",
        "https://www.peintre-en-batiment.fr",
        "https://www.demenageur-pro.fr",
    ]


# =========================================================================
#  5. Point d'entrée
# =========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Test de résistance Lighthouse CLI en batch"
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--from-db", action="store_true",
                     help="URLs depuis la base SQLite")
    src.add_argument("--from-file", type=str,
                     help="Fichier avec une URL par ligne")
    src.add_argument("--urls", nargs="+",
                     help="URLs inline")

    parser.add_argument("--limit", type=int, default=200,
                        help="Nombre max d'URLs (défaut: 200)")
    parser.add_argument("--compare", action="store_true",
                        help="Compare avec PageSpeed API (2x plus long)")
    parser.add_argument("--strategy", choices=["mobile", "desktop"],
                        default="mobile",
                        help="Stratégie Lighthouse (défaut: mobile)")
    parser.add_argument("--output", type=str,
                        help="Sauvegarde des résultats en JSON")
    parser.add_argument("--quick", action="store_true",
                        help="Test rapide: 10 URLs uniquement")
    parser.add_argument("--real-throttle", action="store_true",
                        help="Utilise devtools throttling (lent mais réaliste) au lieu de simulate (rapide)")

    args = parser.parse_args()

    # Récupération des URLs
    if args.urls:
        urls = args.urls
    elif args.from_file:
        urls = urls_from_file(args.from_file)
    elif args.from_db:
        urls = urls_from_db(limit=args.limit)
    else:
        urls = urls_from_test_set()

    if args.quick:
        urls = urls[:10]

    if not urls:
        print("Aucune URL à tester.")
        sys.exit(1)

    if len(urls) > args.limit:
        urls = urls[:args.limit]

    print(f"\n{'#'*60}")
    print(f"  TEST BATCH LIGHTHOUSE — {len(urls)} URLs")
    print(f"  Stratégie: {args.strategy}")
    if args.compare:
        print(f"  Comparaison PageSpeed API ACTIVÉE (durée x2)")
    print(f"{'#'*60}\n")

    # 1) Lighthouse
    throttle_mode = "devtools (réel)" if args.real_throttle else "simulate (rapide)"
    print(f"\n--- Phase 1: Lighthouse CLI [{throttle_mode}] ---")
    lh_results = run_batch(urls, method="lighthouse", strategy=args.strategy,
                           real_throttle=args.real_throttle)
    print_summary(lh_results)

    # 2) PageSpeed API (optionnel)
    ps_results = None
    if args.compare:
        print(f"\n--- Phase 2: PageSpeed API ---")
        ps_results = run_batch(urls, method="pagespeed", strategy=args.strategy)
        print_summary(ps_results)

    # 3) Comparaison
    if args.compare and ps_results:
        print_comparison(lh_results, ps_results)

    # 4) Export JSON
    if args.output:
        export = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "total_urls": len(urls),
                "strategy": args.strategy,
                "compare": args.compare,
            },
            "lighthouse": {
                "summary": {k: v for k, v in lh_results.items() if k != "results"},
                "errors": [
                    r for r in lh_results["results"] if not r.get("success")
                ],
            },
        }
        if ps_results:
            export["pagespeed"] = {
                "summary": {k: v for k, v in ps_results.items() if k != "results"},
            }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(export, f, indent=2, ensure_ascii=False)
        print(f"\nRésultats exportés dans {args.output}")

    # Verdict
    lh_rate = lh_results["success_rate"]
    if lh_rate >= 90:
        print(f"\n  VERDICT: Lighthouse STABLE ({lh_rate}% succès) — viable pour remplacement.")
    elif lh_rate >= 70:
        print(f"\n  VERDICT: Lighthouse MOYEN ({lh_rate}% succès) — à améliorer avant remplacement.")
    else:
        print(f"\n  VERDICT: Lighthouse INSTABLE ({lh_rate}% succès) — ne pas remplacer l'auditeur actuel.")

    total_time = lh_results["total_elapsed_s"]
    if ps_results:
        total_time += ps_results["total_elapsed_s"]
    print(f"  Temps total: {total_time}s ({total_time/60:.1f}min)")
    print()


if __name__ == "__main__":
    main()
