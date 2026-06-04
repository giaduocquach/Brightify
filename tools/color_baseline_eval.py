"""B2 (V21) — Strong baselines cho editorial eval (Dacrema 2021 / Schnabel 2022).

V21 audit: "vượt random 6×" là sàn quá thấp; cần baselines mạnh hơn.
Thêm 3 baselines mới vào song song với production + VA-only:

  RANDOM      10 seeds, mean Qprec — sàn thấp nhất, kiểm soát tính ngẫu nhiên
  POPULARITY  top-k theo tần suất nghệ sĩ trong catalog — kiểm tra popularity bias
  NAIVE-COLOR top-k theo khoảng cách V-A nhưng dùng HSL trực tiếp (L→valence,
              S→arousal) KHÔNG qua ICEAS calibration — kiểm tra xem bridge có
              thêm giá trị so với chỉ dùng geometry màu sắc thô không

Nếu production > VA-only > Naive-color > Popularity > Random → bridge + calibration
đều thêm giá trị thật sự.

Run: python -m tools.color_baseline_eval [top_k]
"""
import json, os, sys
import colorsys
import numpy as np
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOP_K   = int(sys.argv[1]) if len(sys.argv) > 1 else 10
OUT     = "var/runtime/backtest/reports/color_baseline_eval.json"
GT_FILE = "var/runtime/backtest/ground_truth/color_editorial_gt_v1.json"

os.makedirs(os.path.dirname(OUT), exist_ok=True)

ICEAS_COLS = [
    ('#BE0032','red'), ('#F38400','orange'), ('#F3C300','yellow'),
    ('#FFB7C5','pink'), ('#008856','green'), ('#3AB09E','turquoise'),
    ('#0067A5','blue'), ('#9C4F96','purple'), ('#80461B','brown'),
    ('#F2F3F4','white'), ('#848482','grey'), ('#222222','black'),
]
HEX_REMAP = {
    '#FF0000':'#BE0032','#FF8000':'#F38400','#FFFF00':'#F3C300',
    '#FFC0CB':'#FFB7C5','#008000':'#008856','#40E0D0':'#3AB09E',
    '#0000FF':'#0067A5','#800080':'#9C4F96','#8B4513':'#80461B',
    '#FFFFFF':'#F2F3F4','#808080':'#848482','#000000':'#222222',
}


def _quadrant(v, a):
    if v >= 0.5 and a >= 0.5: return 'Q1'
    if v <  0.5 and a >= 0.5: return 'Q2'
    if v <  0.5 and a <  0.5: return 'Q3'
    return 'Q4'


def _hex_to_hsl(hex_c: str) -> tuple[float, float, float]:
    """hex → (h, s, l) each in [0, 1]."""
    hex_c = hex_c.lstrip('#')
    r, g, b = (int(hex_c[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)  # returns (h, l, s)


def _naive_color_va(hex_c: str) -> tuple[float, float]:
    """Naive V-A from HSL geometry (no ICEAS calibration).

    Basis: Ou&Luo 2018 colour-emotion model (lightness↑→valence↑,
    chroma/saturation↑→arousal↑). Simpler than hsl_to_va; bypasses
    the Jonauskaite norm fitting entirely. Tests if ICEAS adds value.
    """
    h, l, s = _hex_to_hsl(hex_c)
    valence = 0.1 + 0.80 * l                   # lightness → valence
    arousal = 0.2 + 0.60 * s                   # saturation → arousal
    return float(np.clip(valence, 0, 1)), float(np.clip(arousal, 0, 1))


def _random_score(n_songs: int, top_k: int, seed: int) -> list[int]:
    rng = np.random.default_rng(seed)
    return rng.choice(n_songs, size=top_k, replace=False).tolist()


def _popularity_score(popularity: np.ndarray, top_k: int) -> list[int]:
    return np.argsort(popularity)[::-1][:top_k].tolist()


def _naive_color_score(rec, hex_c: str, top_k: int) -> list[int]:
    cv, ca = _naive_color_va(hex_c)
    from config import COLOR_SCORE_VA_SIGMA_V, COLOR_SCORE_VA_SIGMA_A
    sv, sa = rec.song_va[:, 0], rec.song_va[:, 1]
    scores = np.exp(-0.5 * (((sv - cv) / COLOR_SCORE_VA_SIGMA_V) ** 2 +
                            ((sa - ca) / COLOR_SCORE_VA_SIGMA_A) ** 2))
    return np.argsort(scores)[::-1][:top_k].tolist()


def _va_only_score(rec, hex_c: str, top_k: int) -> list[int]:
    from config import COLOR_SCORE_VA_SIGMA
    cv, ca = rec.color_mapper.hsl_to_va(hex_c)
    cva = np.array([cv, ca])
    d   = np.sqrt(np.sum((rec.song_va - cva) ** 2, axis=1))
    scores = np.exp(-(d ** 2) / (2 * COLOR_SCORE_VA_SIGMA ** 2))
    return np.argsort(scores)[::-1][:top_k].tolist()


def _production_score(rec, hex_c: str, top_k: int) -> list[int]:
    df = rec.recommend_by_colors(hex_c, top_k=top_k)
    if df is None or df.empty: return []
    return df['original_index'].tolist()


def _qprec(recs: list[int], tq: str, song_quadrants: list[str]) -> float:
    if not recs: return 0.0
    return sum(1 for r in recs if song_quadrants[r] == tq) / len(recs)


def main():
    from core.recommendation_engine import get_recommender
    rec = get_recommender()
    n   = rec.n_songs
    sq  = [_quadrant(rec.song_va[i, 0], rec.song_va[i, 1]) for i in range(n)]

    # Popularity proxy: artist frequency
    art_col    = rec.artist_col or 'artists'
    artists    = rec.df[art_col].fillna('__unknown__').astype(str).values
    art_freq   = Counter(artists)
    popularity = np.array([art_freq[a] for a in artists], float)

    # Load GT
    raw_gt = json.load(open(GT_FILE))
    gt_raw = raw_gt.get('colors', raw_gt)
    gt = {HEX_REMAP.get(old, old): v for old, v in gt_raw.items()}

    N_RANDOM_SEEDS = 10
    baselines = ['random', 'popularity', 'naive_color', 'va_only', 'production']
    scores    = {b: [] for b in baselines}   # per-color Qprec
    per_color = {}

    print(f"\nCOLOR BASELINE EVAL  top_k={TOP_K}")
    hdr = f"{'color':20} {'tq':>4} {'rand':>6} {'pop':>6} {'naive':>6} {'va':>6} {'prod':>6}"
    print(hdr)
    print("-" * len(hdr))

    for hx, name in ICEAS_COLS:
        entry = gt.get(hx)
        if not entry or not entry.get('relevant'):
            continue
        cv, ca = rec.color_mapper.hsl_to_va(hx)
        tq     = _quadrant(cv, ca)

        # Random: mean over 10 seeds
        rand_qprecs = [_qprec(_random_score(n, TOP_K, s), tq, sq) for s in range(N_RANDOM_SEEDS)]
        rand_mean   = float(np.mean(rand_qprecs))
        rand_std    = float(np.std(rand_qprecs))

        pop_q     = _qprec(_popularity_score(popularity, TOP_K), tq, sq)
        naive_q   = _qprec(_naive_color_score(rec, hx, TOP_K), tq, sq)
        va_q      = _qprec(_va_only_score(rec, hx, TOP_K), tq, sq)
        prod_q    = _qprec(_production_score(rec, hx, TOP_K), tq, sq)

        scores['random'].append(rand_mean)
        scores['popularity'].append(pop_q)
        scores['naive_color'].append(naive_q)
        scores['va_only'].append(va_q)
        scores['production'].append(prod_q)

        # "wins" vs baselines
        wins = sum([prod_q > rand_mean, prod_q > pop_q, prod_q > naive_q])
        per_color[hx] = {
            'name': name, 'target_quadrant': tq,
            'random_mean': round(rand_mean, 3), 'random_std': round(rand_std, 3),
            'popularity': round(pop_q, 3),
            'naive_color': round(naive_q, 3),
            'va_only': round(va_q, 3),
            'production': round(prod_q, 3),
            'prod_wins_vs': wins,
        }
        print(f"{name+' '+hx:20} {tq:>4}  "
              f"{rand_mean:.2f}  {pop_q:.2f}  {naive_q:.2f}  {va_q:.2f}  {prod_q:.2f}")

    # Aggregate
    def _agg(key):
        vals = scores[key]
        return round(float(np.mean(vals)), 4), round(float(np.std(vals)), 4)

    print("-" * len(hdr))
    rand_m, rand_s   = _agg('random')
    pop_m,  pop_s    = _agg('popularity')
    naive_m, naive_s = _agg('naive_color')
    va_m,   va_s     = _agg('va_only')
    prod_m, prod_s   = _agg('production')

    print(f"{'MEAN':20} {'':>4}  "
          f"{rand_m:.2f}  {pop_m:.2f}  {naive_m:.2f}  {va_m:.2f}  {prod_m:.2f}")
    print(f"{'STD':20} {'':>4}  "
          f"{rand_s:.2f}  {pop_s:.2f}  {naive_s:.2f}  {va_s:.2f}  {prod_s:.2f}")

    # Ordering check: production should beat all 3 non-VA baselines
    ordering = {
        "prod > random":     bool(prod_m > rand_m),
        "prod > popularity": bool(prod_m > pop_m),
        "prod > naive_color":bool(prod_m > naive_m),
        "va_only > random":  bool(va_m   > rand_m),
        "naive > random":    bool(naive_m > rand_m),
        "prod ≥ va_only":    bool(prod_m >= va_m - 0.005),  # small tolerance
    }

    print(f"\n=== BASELINE ORDERING (target: prod > all baselines) ===")
    all_pass = True
    for label, result in ordering.items():
        sym = '✓' if result else '✗'
        print(f"  {sym} {label}")
        if not result:
            all_pass = False

    # Expected-vs-actual for random
    print(f"\n=== RANDOM BASELINE CALIBRATION ===")
    print("  Expected Qprec for random ≈ catalog quadrant fraction:")
    q_dist = Counter(sq)
    for tq_check in ['Q1','Q2','Q3','Q4']:
        expected = q_dist[tq_check] / n
        actual   = float(np.mean([v['random_mean'] for v in per_color.values()
                                  if v['target_quadrant'] == tq_check] or [0]))
        print(f"    {tq_check}: expected {expected:.3f}  actual {actual:.3f}")

    report = {
        "top_k":      TOP_K,
        "n_seeds_random": N_RANDOM_SEEDS,
        "macro_qprec": {
            "random":      rand_m, "popularity":   pop_m,
            "naive_color": naive_m, "va_only":      va_m,
            "production":  prod_m,
        },
        "ordering_checks": ordering,
        "all_ordering_pass": all_pass,
        "per_color": per_color,
        "naive_color_method": (
            "HSL geometry only: valence=0.1+0.8*L, arousal=0.2+0.6*S. "
            "Bypasses ICEAS calibration. Tests if Jonauskaite norms add value. "
            "Basis: Ou&Luo 2018 colour-emotion (lightness→pleasure, chroma→activity)."),
        "basis": (
            "Dacrema et al. 2021 (ACM TOIS reproducibility); "
            "Schnabel 2022 (offline eval guidelines); "
            "Abdollahpouri 2021 (popularity bias)."),
    }
    json.dump(report, open(OUT, "w"), ensure_ascii=False, indent=2)
    print(f"\n  saved → {OUT}")
    print(f"\n  Overall: {'ALL ordering checks PASS ✓' if all_pass else 'SOME ordering checks FAIL — see above'}")
    return report


if __name__ == "__main__":
    main()
