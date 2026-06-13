"""Fit an isotonic-regression calibration curve: v4_valence → mean_human_valence.

Gold-set (audit V17, P0 #2) showed LLM-derived v4 valence systematically under-estimates
the perceived positivity of sad/tense/melancholic Vietnamese music by ~0.20–0.30 vs
human raters (Pearson r=0.70, RMSE=0.231 before calibration). Isotonic regression
(Barlow 1972 / scikit-learn) is appropriate: it is monotone-preserving (rank order of
valence is meaningful and should be kept) and non-parametric (no assumed functional form).

Output: data/valence_calibration.json  — 2 arrays (x_vals, y_vals) used for
np.interp at inference. Also updates data/emotion_labels_v4.json in-place with the
calibrated valence (key 'valence_cal'), leaving the original 'valence' intact.

Usage: python -m tools.build_valence_calibration
"""
from __future__ import annotations
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from sklearn.isotonic import IsotonicRegression

RATINGS_DIR = 'var/goldset/ratings'
V4_FILE     = 'data/emotion_labels_v4.json'
CAL_FILE    = 'data/valence_calibration.json'


def load_human_mean(ratings_dir: str) -> dict:
    """Return {track_id: mean_human_valence} averaged across all rater files."""
    per_song: dict[str, list[float]] = {}
    for f in sorted(os.listdir(ratings_dir)):
        if not f.endswith('.csv'): continue
        for row in csv.DictReader(open(os.path.join(ratings_dir, f))):
            try:
                v = float(row['rater_valence'])
                if 0.0 <= v <= 1.0:
                    per_song.setdefault(row['track_id'], []).append(v)
            except (ValueError, KeyError):
                pass
    return {tid: float(np.mean(vals)) for tid, vals in per_song.items() if vals}


def main() -> int:
    v4 = json.load(open(V4_FILE))
    human = load_human_mean(RATINGS_DIR)
    common = [tid for tid in human if tid in v4]
    print(f'Gold-set songs with v4 match: {len(common)} / {len(human)}')

    x = np.array([float(v4[t].get('valence', 0.5)) for t in common])
    y = np.array([human[t] for t in common])

    # Baseline
    rmse_pre  = float(np.sqrt(np.mean((x - y) ** 2)))
    r_pre     = float(np.corrcoef(x, y)[0, 1])
    print(f'\nBefore calibration:  Pearson r={r_pre:+.3f}  RMSE={rmse_pre:.3f}')

    # Fit isotonic regression (increasing=True: higher v4 → higher human)
    iso = IsotonicRegression(increasing=True, out_of_bounds='clip')
    iso.fit(x, y)

    x_cal = iso.predict(x)
    rmse_post = float(np.sqrt(np.mean((x_cal - y) ** 2)))
    r_post    = float(np.corrcoef(x_cal, y)[0, 1])
    print(f'After  calibration:  Pearson r={r_post:+.3f}  RMSE={rmse_post:.3f}')
    print(f'Improvement:         ΔRMSE={rmse_pre-rmse_post:+.3f}  Δr={r_post-r_pre:+.3f}')

    # Persist the calibration curve (x_vals/y_vals for np.interp)
    # Use the isotonic breakpoints for a compact representation.
    x_pts = iso.X_thresholds_.tolist()
    y_pts = iso.y_thresholds_.tolist()
    # Pad edges so interp clips correctly outside training range.
    x_pts = [0.0] + x_pts + [1.0]
    y_pts = [float(iso.predict([0.0])[0])] + y_pts + [float(iso.predict([1.0])[0])]
    cal = {'x_vals': x_pts, 'y_vals': y_pts,
           'meta': {'n_goldset': len(common), 'rmse_pre': round(rmse_pre, 4),
                    'rmse_post': round(rmse_post, 4), 'r_pre': round(r_pre, 4),
                    'r_post': round(r_post, 4)}}
    json.dump(cal, open(CAL_FILE, 'w'), indent=2)
    print(f'\nCalibration curve saved → {CAL_FILE}  ({len(x_pts)} breakpoints)')

    # Write 'valence_cal' into v4 for all 5548 songs (original 'valence' kept intact)
    all_v = np.array([float(v4[t].get('valence', 0.5)) for t in v4])
    all_v_cal = iso.predict(all_v)
    for t, vc in zip(v4.keys(), all_v_cal):
        v4[t]['valence_cal'] = round(float(vc), 4)
    json.dump(v4, open(V4_FILE, 'w'), ensure_ascii=False)
    print(f'Added "valence_cal" to all {len(v4)} songs in {V4_FILE}')

    # Per-emotion summary (sanity check)
    from collections import defaultdict
    by_emo: dict[str, list] = defaultdict(list)
    for t in common:
        by_emo[v4[t].get('label', '?')].append(
            (float(v4[t].get('valence', 0.5)),
             float(v4[t].get('valence_cal', 0.5)),
             human[t]))
    print('\nPer-emotion calibration check:')
    print(f'  {"emotion":<12} {"v4_raw":>8} {"v4_cal":>8} {"human":>8} {"n":>4}')
    for emo in ['happy','excited','peaceful','calm','melancholic','sad','tense','angry']:
        d = by_emo.get(emo, [])
        if not d: continue
        vr=np.mean([x[0] for x in d]); vc=np.mean([x[1] for x in d]); vh=np.mean([x[2] for x in d])
        print(f'  {emo:<12} {vr:>8.3f} {vc:>8.3f} {vh:>8.3f} {len(d):>4}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
