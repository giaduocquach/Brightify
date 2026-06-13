"""Phase 3 — Bayesian / Gaussian-Process colour→V-A with principled per-colour uncertainty.

The served colour→valence is a Ridge fit on 12 ICEAS anchors (point estimate, no uncertainty).
n=12 ⇒ predictions are uncertain, but Ridge can't say HOW uncertain. This upgrades the SAME
linear model class to its Bayesian analog (BayesianRidge — posterior over weights → predictive
std) and a Gaussian Process (Markov 2013, music-emotion GP) — both give a **per-colour σ**.
Turns the "n=12 wide-CI" limitation into a modeled, reportable output, and adds a genuine
probabilistic-ML component without changing the point estimates much (validated by LOO-CV).

Run: python -m tools.color_va_bayesian
"""
from __future__ import annotations
import json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.phase3_cielab_experiment import ICEAS, oklab_features


def _loo(model_fn, X, y):
    """Leave-one-out CV → (Pearson r, RMSE) of held-out predictions."""
    from scipy.stats import pearsonr
    n = len(y); preds = np.zeros(n)
    for i in range(n):
        tr = [j for j in range(n) if j != i]
        m = model_fn(); m.fit(X[tr], y[tr])
        preds[i] = m.predict(X[i:i+1])[0]
    r = pearsonr(preds, y)[0]
    rmse = float(np.sqrt(np.mean((preds - y) ** 2)))
    return r, rmse, preds


def main() -> int:
    from sklearn.linear_model import BayesianRidge, Ridge
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import RBF, ConstantKernel as C, WhiteKernel
    from sklearn.preprocessing import StandardScaler

    hexes = [r[0] for r in ICEAS]; names = [r[3] for r in ICEAS]
    X = np.array([oklab_features(h) for h in hexes])
    Xs = StandardScaler().fit_transform(X)
    targets = {"valence": np.array([r[1] for r in ICEAS]),
               "arousal": np.array([r[2] for r in ICEAS])}

    def gp_fn():
        k = C(1.0, (1e-2, 1e2)) * RBF(2.0, (0.5, 10.0)) + WhiteKernel(0.05, (1e-3, 0.5))
        return GaussianProcessRegressor(kernel=k, normalize_y=True, alpha=1e-6, n_restarts_optimizer=4)

    out = {}
    for axis, y in targets.items():
        print(f"\n=== colour→{axis.upper()} : Ridge (current) vs Bayesian vs GP (n=12, LOO-CV) ===")
        r_ridge, rm_ridge, _ = _loo(lambda: Ridge(alpha=1.0), Xs, y)
        r_br, rm_br, _ = _loo(lambda: BayesianRidge(), Xs, y)
        r_gp, rm_gp, _ = _loo(gp_fn, Xs, y)
        print(f"  Ridge        LOO-CV r={r_ridge:+.3f}  RMSE={rm_ridge:.3f}  (point estimate, no uncertainty)")
        print(f"  BayesianRidge LOO-CV r={r_br:+.3f}  RMSE={rm_br:.3f}  (+ predictive σ)")
        print(f"  GaussianProc  LOO-CV r={r_gp:+.3f}  RMSE={rm_gp:.3f}  (+ predictive σ, Markov 2013)")

        # full-fit per-colour uncertainty (BayesianRidge predictive std + GP std)
        br = BayesianRidge().fit(Xs, y)
        mu_br, sd_br = br.predict(Xs, return_std=True)
        gp = gp_fn().fit(Xs, y)
        mu_gp, sd_gp = gp.predict(Xs, return_std=True)
        print(f"  per-colour predictive σ (BayesianRidge): mean={sd_br.mean():.3f}  "
              f"min={sd_br.min():.3f}({names[sd_br.argmin()]})  max={sd_br.max():.3f}({names[sd_br.argmax()]})")
        for i, nm in enumerate(names):
            out.setdefault(nm, {})[axis] = {
                "mean": round(float(mu_br[i]), 4), "std_bayesridge": round(float(sd_br[i]), 4),
                "std_gp": round(float(sd_gp[i]), 4), "human": round(float(y[i]), 4)}

    json.dump(out, open("data/color_va_uncertainty.json", "w"), ensure_ascii=False, indent=2)
    print("\n→ data/color_va_uncertainty.json (per-colour mean + σ for valence & arousal)")
    # headline: highest-uncertainty colours (where the n=12 fit is least sure)
    val_sd = {nm: out[nm]["valence"]["std_bayesridge"] for nm in out}
    top = sorted(val_sd, key=val_sd.get, reverse=True)[:3]
    print(f"  most-uncertain valence colours: {', '.join(f'{n}(σ={val_sd[n]:.3f})' for n in top)}")
    print("  → can widen matching σ_V for high-σ colours (uncertainty-aware retrieval, optional).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
