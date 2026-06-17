"""Phase 3 — Beyond-accuracy quality metrics for recommend_by_colours.

No human labels needed. Three dimensions (Vargas & Castells 2011 RecSys):
  1. Calibration-KL  — does result quadrant-distribution match colour V-A target?
                        Steck 2018: KL(result_dist || target_dist). Lower = better.
  2. EILD            — Expected Intra-List Diversity: mean pairwise V-A distance
                        in top-k results. Higher = more diverse (avoids near-clones).
  3. Coverage        — fraction of 5548 catalog songs reachable across all 12 colours.

Also computes and reports:
  4. Random baseline comparison (same metrics for random top-k).
  5. Popularity baseline (top-k by artist-frequency proxy).

Run: python -m tools.color_quality_metrics [top_k]
"""
import json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOP_K   = int(sys.argv[1]) if len(sys.argv) > 1 else 10
OUT     = "var/runtime/backtest/reports/color_quality_metrics.json"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

ICEAS_CENTROIDS = [
    ('#BE0032','red'), ('#F38400','orange'), ('#F3C300','yellow'),
    ('#FFB7C5','pink'), ('#008856','green'), ('#3AB09E','turquoise'),
    ('#0067A5','blue'), ('#9C4F96','purple'), ('#80461B','brown'),
    ('#F2F3F4','white'), ('#848482','grey'), ('#222222','black'),
]


def _quadrant(v, a):
    if v >= 0.5 and a >= 0.5: return 'Q1'
    if v <  0.5 and a >= 0.5: return 'Q2'
    if v <  0.5 and a <  0.5: return 'Q3'
    return 'Q4'


def _kl_div(p, q, eps=1e-9):
    """KL(p||q): p = observed dist, q = target dist."""
    p = np.array(p, float) + eps
    q = np.array(q, float) + eps
    p /= p.sum(); q /= q.sum()
    return float(np.sum(p * np.log(p / q)))


def _eild(indices, song_va):
    """Mean pairwise Euclidean distance in V-A space — higher = more diverse."""
    if len(indices) < 2:
        return 0.0
    pts = song_va[np.array(indices, int)]
    n = len(pts)
    total = 0.0; count = 0
    for i in range(n):
        for j in range(i + 1, n):
            total += float(np.linalg.norm(pts[i] - pts[j]))
            count += 1
    return total / count if count else 0.0


def main():
    from core.recommendation_engine import get_recommender
    rec = get_recommender()
    n   = rec.n_songs
    song_va = rec.song_va          # (n, 2)

    # Popularity proxy: artist frequency (higher = more popular in catalog)
    art_col = rec.artist_col or 'artists'
    artists = rec.df[art_col].fillna('__unknown__').astype(str).values
    from collections import Counter
    art_freq = Counter(artists)
    popularity = np.array([art_freq[a] for a in artists], float)
    popularity /= popularity.max()      # → [0, 1]

    all_q = [_quadrant(song_va[i, 0], song_va[i, 1]) for i in range(n)]
    catalog_q_dist = Counter(all_q)
    for q in ['Q1','Q2','Q3','Q4']:
        catalog_q_dist.setdefault(q, 0)

    rng = np.random.default_rng(42)

    all_prod_idxs = set()
    per_color = {}

    print(f"\nBEYOND-ACCURACY QUALITY METRICS  top_k={TOP_K}")
    print(f"{'colour':<12} {'KL_prod':>8} {'KL_rand':>8} {'KL_pop':>8} "
          f"{'EILD_prod':>10} {'EILD_rand':>10} {'target_q':>8}")
    print("-" * 74)

    for hex_c, name in ICEAS_CENTROIDS:
        cv, ca = rec.color_mapper.hsl_to_va(hex_c)
        tq = _quadrant(cv, ca)

        # Target distribution: 100% in the colour's quadrant
        target_dist = np.array([
            1.0 if q == tq else 0.0
            for q in ['Q1','Q2','Q3','Q4']])

        # Production recommendations
        df_prod = rec.recommend_by_colors(hex_c, top_k=TOP_K)
        prod_idx = df_prod['original_index'].tolist() if (
            df_prod is not None and not df_prod.empty and 'original_index' in df_prod.columns
        ) else []
        all_prod_idxs.update(prod_idx)

        prod_q = [all_q[i] for i in prod_idx]
        prod_dist = np.array([prod_q.count(q) for q in ['Q1','Q2','Q3','Q4']], float)

        # Random baseline
        rand_idx = rng.choice(n, size=TOP_K, replace=False).tolist()
        rand_q = [all_q[i] for i in rand_idx]
        rand_dist = np.array([rand_q.count(q) for q in ['Q1','Q2','Q3','Q4']], float)

        # Popularity baseline: top-k by artist frequency
        pop_idx = np.argsort(popularity)[::-1][:TOP_K].tolist()
        pop_q = [all_q[i] for i in pop_idx]
        pop_dist = np.array([pop_q.count(q) for q in ['Q1','Q2','Q3','Q4']], float)

        kl_prod = _kl_div(prod_dist, target_dist)
        kl_rand = _kl_div(rand_dist, target_dist)
        kl_pop  = _kl_div(pop_dist,  target_dist)
        eild_prod = _eild(prod_idx, song_va)
        eild_rand = _eild(rand_idx, song_va)

        prod_pct_correct = prod_q.count(tq) / len(prod_q) if prod_q else 0

        print(f"{name+' '+hex_c:<20} {kl_prod:8.3f} {kl_rand:8.3f} {kl_pop:8.3f} "
              f"{eild_prod:10.4f} {eild_rand:10.4f} {tq} ({prod_pct_correct:.0%})")

        per_color[hex_c] = {
            'name': name, 'target_quadrant': tq,
            'prod_in_target_pct': round(prod_pct_correct, 3),
            'kl_prod': round(kl_prod, 4),
            'kl_rand': round(kl_rand, 4),
            'kl_pop':  round(kl_pop,  4),
            'eild_prod': round(eild_prod, 4),
            'eild_rand': round(eild_rand, 4),
        }

    # Aggregate
    kl_prod_mean  = np.mean([v['kl_prod'] for v in per_color.values()])
    kl_rand_mean  = np.mean([v['kl_rand'] for v in per_color.values()])
    kl_pop_mean   = np.mean([v['kl_pop']  for v in per_color.values()])
    eild_prod_mean = np.mean([v['eild_prod'] for v in per_color.values()])
    eild_rand_mean = np.mean([v['eild_rand'] for v in per_color.values()])
    coverage      = len(all_prod_idxs) / n

    print("-" * 74)
    print(f"{'MEAN':<20} {kl_prod_mean:8.3f} {kl_rand_mean:8.3f} {kl_pop_mean:8.3f} "
          f"{eild_prod_mean:10.4f} {eild_rand_mean:10.4f}")

    print(f"\n=== SUMMARY ===")
    print(f"  Calibration KL:  prod={kl_prod_mean:.3f}  rand={kl_rand_mean:.3f}  "
          f"pop={kl_pop_mean:.3f}  "
          f"{'✓ prod<rand' if kl_prod_mean < kl_rand_mean else '✗ prod≥rand'}")
    print(f"  EILD diversity:  prod={eild_prod_mean:.4f}  rand={eild_rand_mean:.4f}  "
          f"{'(rand richer — expected)' if eild_rand_mean > eild_prod_mean else ''}")
    print(f"  Catalog coverage: {len(all_prod_idxs)}/{n} = {coverage:.1%}")

    report = {
        'top_k': TOP_K,
        'calibration_kl': {
            'production_mean': round(float(kl_prod_mean), 4),
            'random_mean':     round(float(kl_rand_mean), 4),
            'popularity_mean': round(float(kl_pop_mean),  4),
            'prod_beats_random': bool(kl_prod_mean < kl_rand_mean),
        },
        'eild_diversity': {
            'production_mean': round(float(eild_prod_mean), 4),
            'random_mean':     round(float(eild_rand_mean), 4),
        },
        'catalog_coverage': {
            'unique_songs_reachable': len(all_prod_idxs),
            'total_songs': n,
            'coverage_pct': round(float(coverage), 4),
        },
        'per_color': per_color,
        'basis': 'Vargas&Castells RecSys 2011; Steck RecSys 2018',
    }
    json.dump(report, open(OUT, 'w'), ensure_ascii=False, indent=2)
    print(f"\n  saved → {OUT}")
    return report


if __name__ == "__main__":
    main()
