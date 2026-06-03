"""
test_reproducibility.py — Test de reproductibilité Lighthouse.

Compare la variance des métriques sur 3 runs consécutifs de la même URL.
"""
import sys, os, json, time, subprocess, tempfile, shutil

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LIGHTHOUSE_TIMEOUT_S = 180

# Détection binaire
def _find_lighthouse() -> str:
    path = shutil.which("lighthouse")
    if path:
        return path
    for c in [
        r"C:\Users\jmeda\AppData\Roaming\npm\lighthouse.cmd",
        r"C:\Users\jmeda\AppData\Roaming\npm\lighthouse",
    ]:
        if os.path.exists(c):
            return c
    return "lighthouse"

BIN = _find_lighthouse()


def run_lighthouse(url: str, throttle: str = "simulate") -> dict:
    """Run lighthouse once, return key metrics + raw audit data."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out = f.name
    start = time.time()
    try:
        proc = subprocess.run(
            [
                BIN, url,
                f"--output-path={out}",
                "--output=json",
                "--form-factor=mobile",
                f"--throttling-method={throttle}",
                "--chrome-flags=--headless --no-sandbox --disable-dev-shm-usage",
                "--quiet", "--no-enable-error-reporting",
                "--disable-storage-reset",
            ],
            timeout=LIGHTHOUSE_TIMEOUT_S,
            capture_output=True, text=True,
        )
        elapsed = round(time.time() - start, 1)
        if proc.returncode != 0:
            return {"success": False, "error": f"rc={proc.returncode}", "elapsed_s": elapsed}
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        audits = data.get("audits", {})
        cats = data.get("categories", {})
        perf = cats.get("performance", {})
        return {
            "success": True,
            "score": round(perf.get("score", 0) * 100) if perf.get("score") else None,
            "lcp_ms": round(audits.get("largest-contentful-paint", {}).get("numericValue", 0)),
            "fcp_ms": round(audits.get("first-contentful-paint", {}).get("numericValue", 0)),
            "tbt_ms": round(audits.get("total-blocking-time", {}).get("numericValue", 0)),
            "cls": round(audits.get("cumulative-layout-shift", {}).get("numericValue", 0), 4),
            "si_ms": round(audits.get("speed-index", {}).get("numericValue", 0)),
            "elapsed_s": elapsed,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "TIMEOUT", "elapsed_s": round(time.time()-start, 1)}
    except Exception as e:
        return {"success": False, "error": str(e)[:200], "elapsed_s": round(time.time()-start, 1)}
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass


def run_repro_test(url: str, throttle: str = "simulate", runs: int = 3):
    """Run N times and compute variance."""
    print(f"\n{'='*65}")
    print(f"  Repro: {url}")
    print(f"  Mode : {throttle}  |  Runs : {runs}")
    print(f"{'='*65}")

    results = []
    for i in range(runs):
        print(f"  Run {i+1}/{runs} ... ", end="", flush=True)
        r = run_lighthouse(url, throttle=throttle)
        results.append(r)
        if r.get("success"):
            print(f"score={r['score']}  LCP={r['lcp_ms']}ms  TBT={r['tbt_ms']}ms  ({r['elapsed_s']}s)")
        else:
            print(f"ECHEC: {r.get('error')}")

    ok = [r for r in results if r.get("success")]
    if len(ok) < 2:
        print("\n  [!] Pas assez de runs réussis pour calculer la variance.\n")
        return results

    # Stats
    scores = [r["score"] for r in ok if r.get("score")]
    lcps = [r["lcp_ms"] for r in ok if r.get("lcp_ms")]
    fcps = [r["fcp_ms"] for r in ok if r.get("fcp_ms")]
    tbts = [r["tbt_ms"] for r in ok if r.get("tbt_ms")]
    clss = [r["cls"] for r in ok if r.get("cls") is not None]

    def variance(vals):
        m = sum(vals) / len(vals)
        var = sum((x - m) ** 2 for x in vals) / len(vals)
        cv = (var ** 0.5) / m * 100 if m else 0
        return m, var ** 0.5, cv

    print(f"\n  {'--- '+throttle.upper()+' ---':>40}")
    print(f"  {'Métrique':<20} {'Moyenne':>12} {'Écart-type':>12} {'CV (%)':>10}")
    print(f"  {'-'*54}")

    for name, vals in [("Score", scores), ("LCP (ms)", lcps),
                        ("FCP (ms)", fcps), ("TBT (ms)", tbts),
                        ("CLS", clss)]:
        if vals:
            m, sd, cv = variance(vals)
            print(f"  {name:<20} {m:>10.1f}  {sd:>10.2f}  {cv:>8.1f}%")

    # Interprétation
    if scores:
        cv_score = variance(scores)[2]
        cv_lcp = variance(lcps)[2] if lcps else 999
        print(f"\n  Interpretation :")
        print(f"    Score CV  = {cv_score:.1f}%  ", end="")
        if cv_score < 5:
            print("[STABLE]")
        elif cv_score < 15:
            print("[MOYEN]")
        else:
            print("[INSTABLE]")
        print(f"    LCP CV   = {cv_lcp:.1f}%  ", end="")
        if cv_lcp < 10:
            print("[STABLE]")
        elif cv_lcp < 25:
            print("[MOYEN]")
        else:
            print("[INSTABLE]")
    print()
    return results


# ================================================================

URLS = [
    "https://electricien-paris.fr",       # site PME rapide
    "https://depann-assistance.com",      # site PME moyen
    "https://trouver-avocats.fr",         # site PME lent
]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", type=str, help="URL unique")
    parser.add_argument("--runs", type=int, default=3, help="Nombre de runs")
    parser.add_argument("--devtools", action="store_true",
                        help="Test aussi en mode devtools")
    args = parser.parse_args()

    urls = [args.url] if args.url else URLS

    for url in urls:
        run_repro_test(url, throttle="simulate", runs=args.runs)
        if args.devtools:
            print(f"\n  --- Passage en mode devtools ---")
            run_repro_test(url, throttle="devtools", runs=args.runs)
