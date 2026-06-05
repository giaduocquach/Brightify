"""J2 (V23) — Sequencing backtest for the 2-colour mood JOURNEY.

Validates CLAIM A (the ordering algorithm produces a smooth A→B path) — offline,
deterministic, NO humans. Does NOT validate CLAIM B (users prefer it → user-test).

4 metrics, each vs a SHUFFLED-ORDER baseline (same song set, random order). The
journey ordering must beat shuffle on smoothness — falsifiable, NOT tautological:
  1. adjacent-variation : Σ‖VA(i)−VA(i+1)‖  → journey ≪ shuffled
  2. monotonicity       : Spearman(path-position t, sequence index) → ρ > 0.7
  3. whiplash count     : # large direction-reversals along journey axis → ≈ 0
  4. endpoints          : first song near colour A, last near colour B

Run: python -m tools.color_journey_sequencing
"""
import json, os, sys
import numpy as np
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT   = "var/runtime/backtest/reports/color_journey_sequencing.json"
TOP_K = 10
N_SHUFFLE = 20
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# Antonym colour pairs spanning the V-A space → meaningful journeys
JOURNEY_PAIRS = [
    ('#848482', '#F3C300', 'grey→yellow  (buồn→vui)'),
    ('#222222', '#FFB7C5', 'black→pink   (u sầu→phấn khích)'),
    ('#0067A5', '#BE0032', 'blue→red     (sâu lắng→mãnh liệt)'),
    ('#80461B', '#F2F3F4', 'brown→white  (căng→thư thái)'),
]


def _adjacent_variation(va_seq):
    """Σ Euclidean distance between consecutive V-A points."""
    if len(va_seq) < 2:
        return 0.0
    return float(np.sum([np.linalg.norm(va_seq[i+1] - va_seq[i])
                         for i in range(len(va_seq)-1)]))


def _whiplash_count(va_seq, axis, thresh=0.4):
    """# of consecutive steps that move BACKWARD along the journey axis by >thresh
    (a large reversal = mood-whiplash)."""
    if len(va_seq) < 2:
        return 0
    axis_n = axis / (np.linalg.norm(axis) + 1e-9)
    proj = [float(p @ axis_n) for p in va_seq]
    return int(sum(1 for i in range(len(proj)-1)
                   if (proj[i+1] - proj[i]) < -thresh))


def run():
    from core.recommendation_engine import get_recommender
    rec = get_recommender()

    rng = np.random.default_rng(42)
    results = []

    print(f"JOURNEY SEQUENCING BACKTEST  top_k={TOP_K}")
    print(f"{'pair':32} {'adj_var':>8} {'shuf_var':>9} {'mono':>6} {'whip':>5} {'endpts':>8}")
    print("-" * 74)

    for hx_a, hx_b, label in JOURNEY_PAIRS:
        res = rec.recommend_by_colors([hx_a, hx_b], top_k=TOP_K)
        if res is None or res.empty or 'original_index' not in res.columns:
            continue
        idxs = [int(i) for i in res['original_index'].tolist()]
        va_seq = np.array([rec.song_va[i] for i in idxs])

        p1 = np.array(rec.color_mapper.hsl_to_va(hx_a))
        p2 = np.array(rec.color_mapper.hsl_to_va(hx_b))
        axis = p2 - p1

        # 1. adjacent variation (journey order)
        adj_var = _adjacent_variation(va_seq)

        # baseline: shuffled order, same songs, averaged over N_SHUFFLE
        shuf_vars = []
        for _ in range(N_SHUFFLE):
            perm = rng.permutation(len(va_seq))
            shuf_vars.append(_adjacent_variation(va_seq[perm]))
        shuf_var = float(np.mean(shuf_vars))

        # 2. monotonicity: position along axis vs sequence index
        t = [float((rec.song_va[i] - p1) @ axis / (axis @ axis + 1e-9)) for i in idxs]
        mono, _ = stats.spearmanr(t, np.arange(len(t)))
        mono = 0.0 if np.isnan(mono) else float(mono)

        # 3. whiplash
        whip = _whiplash_count(va_seq, axis)

        # 4. endpoints
        d_start = float(np.linalg.norm(rec.song_va[idxs[0]] - p1))
        d_end   = float(np.linalg.norm(rec.song_va[idxs[-1]] - p2))

        # 5. NEW: mid-coverage — songs with t in (0.3, 0.7) (catches 2-block)
        t_arr = np.array(t)
        mid_cov = int(((t_arr > 0.3) & (t_arr < 0.7)).sum())

        # 6. NEW: max-gap — largest single step along path (Saari: ≤15% ideal)
        t_sorted = np.sort(t_arr)
        max_gap = float(np.max(np.diff(t_sorted))) if len(t_sorted) > 1 else 1.0

        smoother = adj_var < shuf_var
        results.append({
            'pair': label, 'adj_var': round(adj_var,3), 'shuffled_var': round(shuf_var,3),
            'monotonicity': round(mono,3), 'whiplash': whip,
            'mid_coverage': mid_cov, 'max_gap': round(max_gap,3),
            'dist_start_to_A': round(d_start,3), 'dist_end_to_B': round(d_end,3),
            'smoother_than_shuffle': smoother,
        'mid_coverage': mid_cov, 'max_gap': round(max_gap,3),
        })
        print(f"{label:32} {adj_var:>8.3f} {shuf_var:>9.3f} {mono:>6.2f} {whip:>5} "
              f"mid={mid_cov} gap={max_gap:.2f} {d_start:.2f}/{d_end:.2f}")

    # Aggregate gate
    n = len(results)
    n_smoother = sum(r['smoother_than_shuffle'] for r in results)
    mean_mono  = float(np.mean([r['monotonicity'] for r in results])) if results else 0
    total_whip = sum(r['whiplash'] for r in results)
    mean_adj   = float(np.mean([r['adj_var'] for r in results])) if results else 0
    mean_shuf  = float(np.mean([r['shuffled_var'] for r in results])) if results else 0

    # Collect mid-coverage and max-gap per pair
    mid_coverages = [r.get('mid_coverage', 0) for r in results]
    max_gaps      = [r.get('max_gap', 1.0) for r in results]
    mean_mid = float(np.mean(mid_coverages)) if mid_coverages else 0
    mean_gap = float(np.mean(max_gaps)) if max_gaps else 1.0

    # Pass: ALL of the following must hold.
    # gate_mid: ≥2 songs at intermediate positions (t 0.3-0.7) on average
    #   → catches "2-block" artefact (0 mid songs) that gate_smoother missed
    # gate_gap: max step ≤ 0.40 → no single jump covers >40% of the path
    gate_smoother = n_smoother == n
    gate_mono     = mean_mono > 0.70
    gate_whip     = total_whip == 0
    gate_mid      = mean_mid >= 2.0   # NEW: require intermediate coverage
    gate_gap      = mean_gap <= 0.40  # NEW: no single large jump
    all_pass = gate_smoother and gate_mono and gate_whip and gate_mid and gate_gap

    print("-" * 74)
    print(f"\n=== SEQUENCING GATE ===")
    print(f"  Smoother than shuffle: {n_smoother}/{n}  "
          f"(mean adj_var {mean_adj:.3f} vs shuffled {mean_shuf:.3f})  "
          f"{'✓' if gate_smoother else '✗'}")
    print(f"  Monotonicity (ρ>0.70): {mean_mono:.3f}  {'✓' if gate_mono else '✗'}")
    print(f"  Whiplash count (=0):   {total_whip}  {'✓' if gate_whip else '✗'}")
    print(f"  Mid coverage (≥2/10):  {mean_mid:.1f}  {'✓' if gate_mid else '✗'} "
          f"← catches 2-block artefact")
    print(f"  Max gap (≤0.40):       {mean_gap:.3f}  {'✓' if gate_gap else '✗'} "
          f"← no large step jumps")
    print(f"\n  Overall: {'ALL PASS ✓' if all_pass else 'SOME FAIL ✗'}")
    print(f"\n  NOTE: validates the ORDERING ALGORITHM (claim A), not listener")
    print(f"        preference (claim B → user-test). Falsifiable vs shuffle baseline.")

    report = {
        'top_k': TOP_K, 'n_pairs': n,
        'gate': {'smoother_than_shuffle': gate_smoother, 'monotonicity': gate_mono,
                 'no_whiplash': gate_whip, 'all_pass': all_pass},
        'aggregate': {'n_smoother': n_smoother, 'mean_monotonicity': round(mean_mono,3),
                      'total_whiplash': total_whip,
                      'mean_adj_var': round(mean_adj,3), 'mean_shuffled_var': round(mean_shuf,3)},
        'pairs': results,
        'basis': 'Iso-Principle (Starcke&von Georgi 2024 d=0.52); affective arc (Neto 2025). '
                 'Validates ordering algorithm (claim A), not preference (claim B).',
    }
    json.dump(report, open(OUT,'w'), ensure_ascii=False, indent=2)
    print(f"\n  saved → {OUT}")
    return all_pass


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
