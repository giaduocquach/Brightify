"""Build a non-circular V-A ground truth from the Vietnamese human gold-set (audit V17).

WHY: The existing L2-LLM GT was built by Qwen3 judging lyrics against raw-v4 V-A — making
it circular with the engine (same LLM, same V-A scale). Applying valence calibration broke
that GT because it changed the scale the GT was implicitly calibrated to.

NEW GT: for each of the 12 ICEAS colours, find gold-set songs whose *human-rated* V-A is
close to the colour's V-A. Human ratings are independent of both the LLM judge and the
engine's v4 labels → no circularity. Approach is identical to Whiteford 2018 (emotion
mediates colour↔music; here: colour V-A → find songs with similar human perceived V-A).

Usage: python -m tools.build_human_va_gt [relevance_radius]   (default 0.22)
Output: var/runtime/backtest/ground_truth/color_human_va_gt.json
"""
from __future__ import annotations
import csv, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

RATINGS_DIR = 'var/goldset/ratings'
OUT = 'var/runtime/backtest/ground_truth/color_human_va_gt.json'

ICEAS_COLORS = [
    ('#BE0032', 'red'), ('#F38400', 'orange'), ('#F3C300', 'yellow'),
    ('#FFB7C5', 'pink'), ('#008856', 'green'), ('#3AB09E', 'turquoise'),
    ('#0067A5', 'blue'), ('#9C4F96', 'purple'), ('#80461B', 'brown'),
    ('#F2F3F4', 'white'), ('#848482', 'grey'), ('#222222', 'black'),
]


def load_human_va(ratings_dir: str) -> dict:
    """Return {track_id: (mean_valence, mean_arousal)} from all rater files."""
    per: dict[str, list] = {}
    for f in sorted(os.listdir(ratings_dir)):
        if not f.endswith('.csv'): continue
        for row in csv.DictReader(open(os.path.join(ratings_dir, f))):
            try:
                v = float(row['rater_valence']); a = float(row['rater_arousal'])
                if 0 <= v <= 1 and 0 <= a <= 1:
                    per.setdefault(row['track_id'], []).append((v, a))
            except (ValueError, KeyError): pass
    return {tid: (float(np.mean([x[0] for x in pts])),
                  float(np.mean([x[1] for x in pts])))
            for tid, pts in per.items() if len(pts) >= 2}


def main() -> int:
    radius = float(sys.argv[1]) if len(sys.argv) > 1 else 0.22

    from core.advanced_color_mapping import get_advanced_color_mapper
    cm = get_advanced_color_mapper(vietnamese=False)

    human = load_human_va(RATINGS_DIR)
    tids = list(human.keys())
    hva  = np.array([human[t] for t in tids])   # (N, 2)

    gt = {}
    print(f"\n12-colour human-V-A GT  (radius={radius})")
    print(f"gold-set songs: {len(tids)}")
    print(f"\n{'colour':<12} {'color_V':>8} {'color_A':>8} {'relevant':>9}")
    for hex_c, name in ICEAS_COLORS:
        cv, ca = cm.hsl_to_va(hex_c)
        cva = np.array([cv, ca])
        dists = np.sqrt(np.sum((hva - cva)**2, axis=1))
        rel = [tids[i] for i in np.where(dists <= radius)[0]]
        gt[hex_c] = {'name': name, 'color_va': [round(cv,3), round(ca,3)],
                     'relevant_tids': rel, 'n_relevant': len(rel)}
        print(f"{name:<12} {cv:>8.3f} {ca:>8.3f} {len(rel):>9}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(gt, open(OUT,'w'), indent=2, ensure_ascii=False)
    print(f"\nsaved → {OUT}")
    med = np.median([v['n_relevant'] for v in gt.values()])
    print(f"median relevant/colour: {med:.0f}  (target ≥5; if too low raise radius)")
    if med < 5:
        print("WARNING: median relevant < 5 — try radius 0.28")
    return 0


if __name__ == '__main__':
    sys.exit(main())
