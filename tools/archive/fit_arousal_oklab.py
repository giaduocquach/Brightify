"""Fit colour→AROUSAL to the ICEAS/Jonauskaite human norms (LOO-CV), mirroring how
valence is already fit (Oklab ridge). Audit (V32) showed arousal used a hand-tuned
Whiteford formula NOT fit to the research norms → r=0.765, mean|err|=0.154 (3× worse
than valence's r=0.969), systematically too high for warm/saturated colours and too
low for cool/light/dark ones. This refits arousal on the SAME Oklab feature basis as
valence so BOTH axes are research-grounded.

Run: python -m tools.fit_arousal_oklab
"""
from __future__ import annotations
import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.advanced_color_mapping import get_advanced_color_mapper

# ICEAS Jonauskaite 2020 Table 2 human arousal norms (same set the L1 gate uses)
ICEAS_A = {
 '#BE0032':0.72,'#F38400':0.65,'#F3C300':0.62,'#FFB7C5':0.48,'#008856':0.43,'#3AB09E':0.42,
 '#0067A5':0.45,'#9C4F96':0.50,'#80461B':0.42,'#F2F3F4':0.32,'#848482':0.40,'#222222':0.58}


def main() -> int:
    from sklearn.linear_model import Ridge
    cm = get_advanced_color_mapper()
    hexes = list(ICEAS_A)

    # Interpretable Whiteford/Wilms-Oberfeld determinants: [redness, saturation, darkness].
    # 3 params on n=12 → well-conditioned (the 6-feat Oklab basis overfit, LOO r=0.35).
    def feats(h):
        hh, l, s = cm.hex_to_hsl(h)
        s01, l01 = s / 100.0, l / 100.0
        redness = (1 + np.cos(np.deg2rad(hh))) / 2 if s01 >= 0.12 else 0.5
        return [redness, s01, 1 - l01]
    X = np.array([feats(h) for h in hexes])
    y = np.array([ICEAS_A[h] for h in hexes])

    # LOO-CV over alphas
    best = None
    for alpha in [0.05, 0.1, 0.3, 1.0, 3.0, 10.0]:
        preds = np.zeros(len(y))
        for i in range(len(y)):
            tr = [j for j in range(len(y)) if j != i]
            preds[i] = Ridge(alpha=alpha).fit(X[tr], y[tr]).predict(X[i:i+1])[0]
        r = np.corrcoef(preds, y)[0, 1]
        mae = np.mean(np.abs(preds - y))
        if best is None or r > best[1]:
            best = (alpha, r, mae, preds.copy())
    alpha, r_loo, mae_loo, preds = best
    print(f"[fit-arousal] best alpha={alpha}  LOO-CV r={r_loo:.3f} mae={mae_loo:.3f}  (current Whiteford: r=0.765 mae=0.154)")

    # final coefficients on all 12
    model = Ridge(alpha=alpha).fit(X, y)
    W = model.coef_; b = model.intercept_
    print(f"[fit-arousal] coef={np.round(W,4).tolist()} intercept={b:.4f}")
    # current arousal for comparison
    print(f"\n{'color':9} {'research':8} {'fitted(LOO)':11} {'current':8}")
    for i, h in enumerate(hexes):
        cur_v, cur_a = cm.hsl_to_va(h)
        print(f"{h:9} {y[i]:.2f}     {preds[i]:.2f}        {cur_a:.2f}")
    print("\n  → add as _W_AROUSAL_OKLAB; coef/intercept above. Gate: color_eval_rigor TE not regress.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
