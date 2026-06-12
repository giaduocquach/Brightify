"""Phase 4A — σ grid-search for COLOR_SCORE_VA_SIGMA_V and SIGMA_A (V26).

Searches over a 4×3 grid of (σ_V, σ_A) combinations and reports targeting-error
(Euclidean, mean over 12 ICEAS colours, bootstrap CI n=1k) for each combination.

Selection: best pair by TE where CI does NOT overlap with current default.
If no pair clearly beats current → keep default 0.20/0.14.

Run: python -m tools.color_sigma_grid
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

N_BOOT = 1_000   # faster than rigor's 10k — sufficient for grid comparison
TOP_K  = 10
OUT    = "var/runtime/backtest/reports/color_sigma_grid.json"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

SIGMA_V_GRID = [0.16, 0.18, 0.20, 0.22]
SIGMA_A_GRID = [0.12, 0.14, 0.16]

ICEAS_COLS = [
    ('#BE0032', 'red'),    ('#F38400', 'orange'), ('#F3C300', 'yellow'),
    ('#FFB7C5', 'pink'),   ('#008856', 'green'),  ('#3AB09E', 'turquoise'),
    ('#0067A5', 'blue'),   ('#9C4F96', 'purple'), ('#80461B', 'brown'),
    ('#F2F3F4', 'white'),  ('#848482', 'grey'),   ('#222222', 'black'),
]


def _top_k(scores: np.ndarray, k: int) -> list[int]:
    return np.argsort(scores)[::-1][:k].tolist()


def _rbf_score(song_va: np.ndarray, color_va: np.ndarray,
               sv: float, sa: float) -> np.ndarray:
    dv = song_va[:, 0] - color_va[0]
    da = song_va[:, 1] - color_va[1]
    return np.exp(-0.5 * ((dv / sv) ** 2 + (da / sa) ** 2))


def _te(idxs: list[int], song_va: np.ndarray, color_va: np.ndarray) -> float:
    if not idxs:
        return 1.0
    return float(np.mean(np.sqrt(np.sum(
        (song_va[idxs] - color_va) ** 2, axis=1))))


def _boot_ci(vals: list[float], n: int = N_BOOT, seed: int = 42) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    boots = [np.mean(rng.choice(vals, size=len(vals), replace=True)) for _ in range(n)]
    return float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def eval_sigma_pair(song_va: np.ndarray, color_mapper,
                    sv: float, sa: float) -> dict:
    """Evaluate (sv, sa) pair: mean TE ± bootstrap CI over all ICEAS colours."""
    te_vals = []
    for hx, _ in ICEAS_COLS:
        cv, ca = color_mapper.hsl_to_va(hx)
        color_va = np.array([cv, ca])
        scores = _rbf_score(song_va, color_va, sv, sa)
        idxs = _top_k(scores, TOP_K)
        te_vals.append(_te(idxs, song_va, color_va))
    mean_te = float(np.mean(te_vals))
    lo, hi = _boot_ci(te_vals)
    return {'sigma_v': sv, 'sigma_a': sa, 'te_mean': round(mean_te, 5),
            'te_ci_lo': round(lo, 5), 'te_ci_hi': round(hi, 5)}


def main():
    from core.recommendation_engine import get_recommender
    from config import COLOR_SCORE_VA_SIGMA_V as DEF_SV, COLOR_SCORE_VA_SIGMA_A as DEF_SA

    print("Loading recommender...")
    rec = get_recommender()
    song_va = rec.song_va
    mapper = rec.color_mapper

    print(f"n = {rec.n_songs} songs  |  "
          f"default σ_V={DEF_SV}, σ_A={DEF_SA}\n")

    print("=" * 65)
    print("SIGMA GRID SEARCH (σ_V × σ_A, targeting-error, n_boot=1k)")
    print("=" * 65)
    print(f"  {'σ_V':>5}  {'σ_A':>5}  {'TE':>8}  CI [lo, hi]")

    # Evaluate default first
    default = eval_sigma_pair(song_va, mapper, DEF_SV, DEF_SA)

    results = []
    for sv in SIGMA_V_GRID:
        for sa in SIGMA_A_GRID:
            r = eval_sigma_pair(song_va, mapper, sv, sa)
            is_default = (sv == DEF_SV and sa == DEF_SA)
            mark = ' ← current' if is_default else ''
            print(f"  {sv:5.2f}  {sa:5.2f}  {r['te_mean']:8.5f}  "
                  f"[{r['te_ci_lo']:.5f}, {r['te_ci_hi']:.5f}]{mark}")
            results.append(r)

    # Find best: lowest TE whose CI does NOT overlap with default CI
    def ci_overlap(a, b):
        return a['te_ci_lo'] <= b['te_ci_hi'] and b['te_ci_lo'] <= a['te_ci_hi']

    best_clear = None
    for r in results:
        if r['sigma_v'] == DEF_SV and r['sigma_a'] == DEF_SA:
            continue
        if r['te_mean'] < default['te_mean'] and not ci_overlap(r, default):
            if best_clear is None or r['te_mean'] < best_clear['te_mean']:
                best_clear = r

    best_ci = min(results, key=lambda x: x['te_mean'])

    print(f"\nDefault: σ_V={DEF_SV} σ_A={DEF_SA}  "
          f"TE={default['te_mean']:.5f} CI[{default['te_ci_lo']:.5f}, {default['te_ci_hi']:.5f}]")
    if best_clear:
        print(f"Best (CI no-overlap with default): "
              f"σ_V={best_clear['sigma_v']} σ_A={best_clear['sigma_a']}  "
              f"TE={best_clear['te_mean']:.5f} — UPDATE RECOMMENDED")
        verdict = 'update_recommended'
    else:
        print(f"Best raw: σ_V={best_ci['sigma_v']} σ_A={best_ci['sigma_a']}  "
              f"TE={best_ci['te_mean']:.5f} (CI overlaps default — NO clear winner)")
        print("→ KEEP DEFAULT σ_V=0.20 σ_A=0.14")
        verdict = 'keep_default'

    print("=" * 65)

    out = {
        'default': default,
        'grid': results,
        'best_clear_winner': best_clear,
        'verdict': verdict,
        'instructions': (
            'If verdict=update_recommended: set COLOR_SCORE_VA_SIGMA_V/A in config.py '
            'then re-run color_eval_rigor.py to confirm full gate passes.'
        ),
    }
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nsaved → {OUT}")


if __name__ == "__main__":
    main()
