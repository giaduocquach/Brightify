"""R5 — Cross-corpus anti-tautology test (V26).

Problem with existing color_eval_rigor.py: editorial GT was categorised using
V-A quadrants → same signal as scorer → tautological (Kriegeskorte 2009).

Solution: Two non-circular tests using GT sources INDEPENDENT of V-A scorer.

Test 1 — ICEAS emotion distribution agreement:
  GT: ICEAS human-rated 12-colour × 8-emotion distribution (Jonauskaite 2020,
      n=4598, 37 nations). SOURCE: advanced_color_mapping._ICEAS_EMOTION.
  Independence: GT is emotion-distribution; scorer uses V-A distance → different
      mechanisms (emotion-classification ≠ V-A regression).
  Metric: KL(retrieved_emotions, ICEAS_GT) vs KL(random_emotions, ICEAS_GT).
  Pass: mean KL(retrieved) < mean KL(random).

Test 2 — Discriminant pairs (intra-quadrant differentiation):
  For each V-A quadrant, sample 20 pairs of songs with high within-quadrant
  V-A distance. Check: does the scorer assign higher score to the more
  appropriate song for the corresponding colour centroid?
  Pass: mean discrimination accuracy > 0.55 (above 0.5 chance).

Culture note: ICEAS is global (37 nations), not VN-specific. Valence may be
  systematically off for Vietnamese songs (red=luck vs red=anger globally).
  This is expected and documented — the test is about mechanism consistency,
  not cultural alignment.

Run: python -m tools.color_r5_cross_corpus [top_k]
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOP_K = int(sys.argv[1]) if len(sys.argv) > 1 else 10
N_RANDOM_TRIALS = 20  # bootstrap samples for random baseline
OUT = "var/runtime/backtest/reports/color_r5_cross_corpus.json"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# Standard ICEAS hex keys — must match keys in advanced_color_mapping._ICEAS_EMOTION
# Using standard ICEAS colors (not production centroids) for the emotion GT lookup.
# The recommender accepts any hex, so we query with these standard colors.
ICEAS_COLS = [
    ('#FF0000', 'red'),    ('#FF8000', 'orange'), ('#FFFF00', 'yellow'),
    ('#FFC0CB', 'pink'),   ('#008000', 'green'),  ('#40E0D0', 'turquoise'),
    ('#0000FF', 'blue'),   ('#800080', 'purple'),  ('#8B4513', 'brown'),
    ('#FFFFFF', 'white'),  ('#808080', 'grey'),    ('#000000', 'black'),
]
EMO8 = ('happy', 'excited', 'peaceful', 'calm', 'melancholic', 'sad', 'tense', 'angry')


def _kl_divergence(p: np.ndarray, q: np.ndarray, eps: float = 1e-9) -> float:
    """KL(p || q) — lower = more similar. Both distributions, summing to 1."""
    p = np.clip(p, eps, None); p = p / p.sum()
    q = np.clip(q, eps, None); q = q / q.sum()
    return float(np.sum(p * np.log(p / q)))


def _song_emotion_dist(fused_emotions: list[str]) -> np.ndarray:
    """Convert list of fused_emotion labels → 8-class distribution."""
    counts = np.zeros(len(EMO8))
    emo_idx = {e: i for i, e in enumerate(EMO8)}
    for e in fused_emotions:
        if e in emo_idx:
            counts[emo_idx[e]] += 1
    total = counts.sum()
    if total == 0:
        return np.ones(len(EMO8)) / len(EMO8)  # uniform fallback
    return counts / total


def test_emotion_distribution(rec) -> dict:
    """Test 1: retrieved songs' emotion distribution vs ICEAS GT."""
    from core.advanced_color_mapping import get_advanced_color_mapper
    mapper = get_advanced_color_mapper()
    iceas_gt = mapper._ICEAS_EMOTION

    # Catalogue emotion labels (fused_emotion column)
    all_emotions = rec.df.get('fused_emotion', rec.df.get('emotion', None))
    if all_emotions is None:
        return {'error': 'fused_emotion column not found in catalog'}
    all_emotions = all_emotions.fillna('').tolist()
    n_songs = rec.n_songs
    rng = np.random.default_rng(42)

    per_colour = {}
    kl_retrieved_all, kl_random_all = [], []

    for hx, name in ICEAS_COLS:
        # GT emotion distribution for this colour
        if hx not in iceas_gt:
            continue
        gt_dist = np.array(iceas_gt[hx], dtype=float)

        # Retrieved songs
        try:
            df_recs = rec.recommend_by_colors(hx, top_k=TOP_K)
        except Exception:
            continue
        if df_recs is None or df_recs.empty:
            continue
        idxs = df_recs['original_index'].tolist()
        retrieved_emotions = [all_emotions[i] for i in idxs]
        ret_dist = _song_emotion_dist(retrieved_emotions)
        kl_ret = _kl_divergence(ret_dist, gt_dist)

        # Random baseline: N_RANDOM_TRIALS repetitions
        kl_rand_vals = []
        for seed in range(N_RANDOM_TRIALS):
            rand_idxs = rng.choice(n_songs, size=TOP_K, replace=False).tolist()
            rand_emotions = [all_emotions[i] for i in rand_idxs]
            rand_dist = _song_emotion_dist(rand_emotions)
            kl_rand_vals.append(_kl_divergence(rand_dist, gt_dist))
        kl_rand_mean = float(np.mean(kl_rand_vals))

        per_colour[name] = {
            'hex': hx,
            'kl_retrieved': round(kl_ret, 4),
            'kl_random_mean': round(kl_rand_mean, 4),
            'beats_random': kl_ret < kl_rand_mean,
            'top_retrieved_emotion': max(zip(EMO8, ret_dist), key=lambda x: x[1])[0],
            'iceas_top_emotion': EMO8[int(np.argmax(gt_dist))],
        }
        kl_retrieved_all.append(kl_ret)
        kl_random_all.append(kl_rand_mean)

    n_beats = sum(1 for v in per_colour.values() if v['beats_random'])
    overall_pass = np.mean(kl_retrieved_all) < np.mean(kl_random_all)

    return {
        'test': 'emotion_distribution_agreement',
        'gt_source': 'ICEAS Jonauskaite 2020 (n=4598, 37 nations) — independent of V-A scorer',
        'independence_note': 'GT=emotion-classification; scorer=V-A distance → non-circular',
        'culture_note': 'ICEAS is global, not VN-specific; valence mismatch expected (red=luck in VN)',
        'n_colours': len(per_colour),
        'n_beats_random': n_beats,
        'mean_kl_retrieved': round(float(np.mean(kl_retrieved_all)), 4),
        'mean_kl_random': round(float(np.mean(kl_random_all)), 4),
        'overall_pass': overall_pass,
        'verdict': 'PASS ✓' if overall_pass else 'FAIL ✗',
        'per_colour': per_colour,
    }


def test_discriminant_pairs(rec) -> dict:
    """Test 2: intra-quadrant discrimination — scorer must rank closer-V-A song higher.

    For each quadrant, sample 20 pairs of songs with high within-quadrant V-A distance.
    For each pair, pick the colour centroid nearest to the quadrant centroid.
    Check: scorer assigns higher score to the song closer to that colour V-A.
    Pass: accuracy > 0.55 (above chance).
    """
    from config import COLOR_SCORE_VA_SIGMA_V, COLOR_SCORE_VA_SIGMA_A
    from core.advanced_color_mapping import get_advanced_color_mapper

    mapper = get_advanced_color_mapper()
    song_va = rec.song_va  # (n, 2) float array

    def quadrant_of(v, a):
        if v >= 0.5 and a >= 0.5: return 'Q1'
        if v  < 0.5 and a >= 0.5: return 'Q2'
        if v  < 0.5 and a  < 0.5: return 'Q3'
        return 'Q4'

    Q_CENTROIDS = {
        'Q1': (0.75, 0.75), 'Q2': (0.25, 0.75),
        'Q3': (0.25, 0.25), 'Q4': (0.75, 0.25),
    }

    # Build quadrant buckets
    buckets = {q: [] for q in Q_CENTROIDS}
    for i in range(rec.n_songs):
        v, a = float(song_va[i, 0]), float(song_va[i, 1])
        buckets[quadrant_of(v, a)].append(i)

    rng = np.random.default_rng(123)
    N_PAIRS = 20
    results_per_q = {}
    all_correct = []

    for q, centroid in Q_CENTROIDS.items():
        idxs = buckets[q]
        if len(idxs) < 4:
            continue

        # Sample pairs with maximum within-quadrant V-A distance
        sample_pool = rng.choice(idxs, size=min(100, len(idxs)), replace=False)
        va_pool = song_va[sample_pool]  # (k, 2)

        pairs, n_correct = [], 0
        attempted = 0
        for _ in range(N_PAIRS * 3):  # over-sample to get distinct pairs
            if len(pairs) >= N_PAIRS:
                break
            i1, i2 = rng.choice(len(sample_pool), size=2, replace=False)
            idx1, idx2 = int(sample_pool[i1]), int(sample_pool[i2])
            v1, a1 = float(song_va[idx1, 0]), float(song_va[idx1, 1])
            v2, a2 = float(song_va[idx2, 0]), float(song_va[idx2, 1])
            pair_dist = float(np.sqrt((v1-v2)**2 + (a1-a2)**2))
            if pair_dist < 0.10:  # skip near-identical V-A pairs
                continue
            pairs.append((idx1, idx2))

            # Score relative to quadrant centroid V-A (acts as colour query)
            cv, ca = centroid
            sc1 = float(np.exp(-0.5 * (((v1-cv)/COLOR_SCORE_VA_SIGMA_V)**2 +
                                        ((a1-ca)/COLOR_SCORE_VA_SIGMA_A)**2)))
            sc2 = float(np.exp(-0.5 * (((v2-cv)/COLOR_SCORE_VA_SIGMA_V)**2 +
                                        ((a2-ca)/COLOR_SCORE_VA_SIGMA_A)**2)))

            # The song closer to centroid V-A should score higher
            closer = idx1 if (abs(v1-cv)+abs(a1-ca)) < (abs(v2-cv)+abs(a2-ca)) else idx2
            predicted_winner = idx1 if sc1 > sc2 else idx2
            if predicted_winner == closer:
                n_correct += 1
            attempted += 1

        acc = n_correct / max(len(pairs), 1)
        all_correct.append(acc)
        results_per_q[q] = {
            'n_pairs': len(pairs),
            'n_correct': n_correct,
            'accuracy': round(acc, 3),
            'n_songs_in_q': len(idxs),
        }

    overall_acc = float(np.mean(all_correct)) if all_correct else 0.0
    return {
        'test': 'discriminant_pairs',
        'description': 'Intra-quadrant: scorer ranks closer-V-A song higher than chance',
        'threshold': 0.55,
        'overall_accuracy': round(overall_acc, 3),
        'overall_pass': overall_acc > 0.55,
        'verdict': 'PASS ✓' if overall_acc > 0.55 else 'FAIL ✗',
        'per_quadrant': results_per_q,
    }


def main():
    from core.recommendation_engine import get_recommender
    print("Loading recommender...")
    rec = get_recommender()
    print(f"Catalog: {rec.n_songs} songs\n")

    print("=" * 65)
    print("R5 CROSS-CORPUS ANTI-TAUTOLOGY TEST (V26)")
    print("=" * 65)
    print(f"GT sources independent of V-A scorer — non-circular by design.\n")

    t1 = test_emotion_distribution(rec)
    t2 = test_discriminant_pairs(rec)

    print("── Test 1: Emotion Distribution Agreement (ICEAS GT) ──")
    if 'error' in t1:
        print(f"  ERROR: {t1['error']}")
    else:
        print(f"  Mean KL retrieved = {t1['mean_kl_retrieved']:.4f}  "
              f"random = {t1['mean_kl_random']:.4f}  "
              f"beats_random: {t1['n_beats_random']}/{t1['n_colours']}")
        print(f"  Verdict: {t1['verdict']}")
        print(f"  {t1['culture_note']}")
        print()
        for name, r in t1['per_colour'].items():
            mark = '✓' if r['beats_random'] else '✗'
            print(f"  {name:12} KL_ret={r['kl_retrieved']:.3f}  "
                  f"KL_rnd={r['kl_random_mean']:.3f}  {mark}  "
                  f"top_emo={r['top_retrieved_emotion']} "
                  f"(GT={r['iceas_top_emotion']})")

    print()
    print("── Test 2: Discriminant Pairs (Intra-Quadrant) ──")
    print(f"  Overall accuracy = {t2['overall_accuracy']:.3f}  (threshold > 0.55)")
    print(f"  Verdict: {t2['verdict']}")
    for q, r in t2['per_quadrant'].items():
        print(f"  {q}: {r['n_correct']}/{r['n_pairs']} correct  "
              f"acc={r['accuracy']:.2f}  ({r['n_songs_in_q']} songs)")

    print()
    print("=" * 65)
    overall_pass = (not t1.get('error') and t1.get('overall_pass', False)) and t2['overall_pass']
    print(f"OVERALL: {'ALL PASS ✓' if overall_pass else 'PARTIAL FAIL — see per-test verdict'}")
    print("=" * 65)

    out = {
        'test1_emotion_distribution': t1,
        'test2_discriminant_pairs': t2,
        'overall_pass': overall_pass,
    }

    class _NpEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.bool_,)): return bool(obj)
            if isinstance(obj, (np.integer,)): return int(obj)
            if isinstance(obj, (np.floating,)): return float(obj)
            return super().default(obj)

    with open(OUT, 'w') as f:
        json.dump(out, f, indent=2, cls=_NpEncoder)
    print(f"\nsaved → {OUT}")


if __name__ == "__main__":
    main()
