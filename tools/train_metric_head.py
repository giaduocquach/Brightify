"""
#5 — Learned Metric Head: MLP trained on playlist co-occurrence triplets.

Replaces hand-tuned weighted sum (0.82×MERT + 0.12×VA + 0.06×lyrics) with
a small MLP that LEARNS how to combine the 3 signals from data.

Ground truth (no user data): editorial playlist co-occurrence.
  positive: 2 songs in the same editorial playlist → similar
  negative: song from a different playlist (artist-aware sampling)
  → Standard "implicit positive" approach (industry standard, e.g. Spotify Radio)

Architecture:
  Input:  [mert_cos, va_sim, lyrics_cos]  ← 3 pre-computed signal scores
  Layer1: Linear(3→32) + ReLU
  Layer2: Linear(32→16) + ReLU
  Output: Linear(16→1) + Sigmoid  → similarity score ∈ [0,1]

Loss: Binary cross-entropy (positive=1, negative=0)
Vectorised inference: O(N) for full catalog (no per-query recompute).

Literature basis:
  McFee & Ellis (2011) "Learning Content Similarity for Music Recommendation"
  PMC10688627 auxiliary self-supervision + metric learning (+37% Recall@1)

Usage:
    python -m tools.train_metric_head [--epochs 200] [--lr 1e-3]
    python -m tools.train_metric_head --eval-only   # skip training, just eval
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import config as cfg

MODEL_NPZ = str(cfg.DATA_DIR / "metric_head_weights.npz")
MODEL_META = str(cfg.DATA_DIR / "metric_head_metadata.json")
GT_FILE = "var/runtime/backtest/ground_truth/editorial_playlists_v1.json"
VA_SIGMA_V = cfg.RECO_SONG_VA_SIGMA_V   # 0.22
VA_SIGMA_A = cfg.RECO_SONG_VA_SIGMA_A   # 0.14


# ── Signal computation ────────────────────────────────────────────────────────

def _build_signal_matrices(cat):
    """Precompute L2-normalised matrices for fast pair scoring."""
    mert = cat.rec.mert_matrix.astype(np.float32)          # (N, 768)
    lyric = cat.rec.embeddings_normalized.astype(np.float32)  # (N, 768)
    va   = cat.rec.song_va.astype(np.float32)               # (N, 2)
    return mert, lyric, va


def pair_scores(i: int, j: int, mert, lyric, va) -> np.ndarray:
    """Return [mert_cos, va_sim, lyrics_cos] ∈ [0,1]³ for a pair."""
    mc = float(mert[i] @ mert[j])
    mc = (mc + 1.0) / 2.0                     # [-1,1] → [0,1]
    dv = float(va[i, 0] - va[j, 0])
    da = float(va[i, 1] - va[j, 1])
    vc = float(np.exp(-0.5 * ((dv / VA_SIGMA_V)**2 + (da / VA_SIGMA_A)**2)))
    lc = float(lyric[i] @ lyric[j])
    lc = (lc + 1.0) / 2.0
    return np.array([mc, vc, lc], dtype=np.float32)


def batch_scores_vs_query(seed: int, mert, lyric, va) -> np.ndarray:
    """Score all N songs vs seed → (N, 3) feature matrix (vectorised)."""
    mc = mert @ mert[seed]                     # (N,)
    mc = (mc + 1.0) / 2.0
    dv = va[:, 0] - va[seed, 0]
    da = va[:, 1] - va[seed, 1]
    vc = np.exp(-0.5 * ((dv / VA_SIGMA_V)**2 + (da / VA_SIGMA_A)**2))
    lc = lyric @ lyric[seed]
    lc = (lc + 1.0) / 2.0
    return np.stack([mc, vc, lc], axis=1).astype(np.float32)   # (N, 3)


# ── MLP (numpy, no torch needed for 3-dim input) ─────────────────────────────

def _relu(x): return np.maximum(0, x)
def _sigmoid(x): return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))

def mlp_forward(X: np.ndarray, params: dict) -> np.ndarray:
    """(N, 3) → (N,) scores ∈ [0,1]."""
    h = _relu(X @ params["W1"] + params["b1"])    # (N, 32)
    h = _relu(h @ params["W2"] + params["b2"])    # (N, 16)
    return _sigmoid((h @ params["W3"] + params["b3"]).squeeze(-1))  # (N,)


def _init_params(seed=42) -> dict:
    rng = np.random.default_rng(seed)
    def he(fan_in, fan_out):
        return rng.standard_normal((fan_in, fan_out)).astype(np.float32) * np.sqrt(2 / fan_in)
    return {
        "W1": he(3, 32), "b1": np.zeros(32, dtype=np.float32),
        "W2": he(32, 16),"b2": np.zeros(16, dtype=np.float32),
        "W3": he(16, 1), "b3": np.zeros(1,  dtype=np.float32),
    }


def _bce_grad(X, y, params, l2=1e-4):
    """Binary cross-entropy + L2; returns loss (scalar) and grads (dict)."""
    N = len(X)
    # Forward
    h1 = _relu(X @ params["W1"] + params["b1"])    # (N, 32)
    h2 = _relu(h1 @ params["W2"] + params["b2"])   # (N, 16)
    logits = (h2 @ params["W3"] + params["b3"]).squeeze(-1)  # (N,)
    p = _sigmoid(logits)
    eps = 1e-7
    loss = float(-np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)))

    # L2 regularisation
    for k in ("W1","W2","W3"):
        loss += l2 * float(np.sum(params[k]**2)) / (2*N)

    # Backward
    dp = (p - y) / N                                          # (N,)
    dW3 = h2.T @ dp[:, None]                                  # (16, 1)
    db3 = np.array([dp.sum()])
    dh2 = dp[:, None] * params["W3"].T                        # (N, 16)
    dh2 *= (h2 > 0)                                           # ReLU mask
    dW2 = h1.T @ dh2
    db2 = dh2.sum(axis=0)
    dh1 = dh2 @ params["W2"].T
    dh1 *= (h1 > 0)
    dW1 = X.T @ dh1
    db1 = dh1.sum(axis=0)

    # Add L2 gradients
    grads = {"W1": dW1 + l2*params["W1"]/N,
             "b1": db1,
             "W2": dW2 + l2*params["W2"]/N,
             "b2": db2,
             "W3": dW3 + l2*params["W3"]/N,
             "b3": db3}
    return loss, grads


# ── Triplet mining from editorial playlists ───────────────────────────────────

def mine_triplets(playlists, mert, lyric, va, neg_per_pos: int = 2,
                  artist_col=None, artists=None, seed=42) -> tuple:
    """Build (X, y) from playlist co-occurrence.

    positive: 2 songs in same playlist, y=1
    negative: random song not in the playlist, different artist preferred, y=0
    """
    rng = np.random.default_rng(seed)
    N = mert.shape[0]

    X_list, y_list = [], []

    for pl in playlists:
        members = [m["catalog_idx"] for m in pl["matched"]]
        if len(members) < 2:
            continue
        member_set = set(members)
        pos_pairs = list(combinations(members, 2))

        for (i, j) in pos_pairs:
            X_list.append(pair_scores(i, j, mert, lyric, va))
            y_list.append(1.0)

            # Sample negatives (not in playlist, prefer different artist)
            for _ in range(neg_per_pos):
                for attempt in range(20):
                    k = int(rng.integers(0, N))
                    if k in member_set:
                        continue
                    if artists is not None and artists[i] == artists[k]:
                        continue  # prefer different artist
                    break
                X_list.append(pair_scores(i, k, mert, lyric, va))
                y_list.append(0.0)

    X = np.stack(X_list).astype(np.float32)
    y = np.array(y_list, dtype=np.float32)
    return X, y


# ── Training ─────────────────────────────────────────────────────────────────

def train(X, y, epochs=300, lr=2e-3, batch=512, l2=1e-4, verbose=True) -> dict:
    import time
    params = _init_params()
    rng = np.random.default_rng(42)
    N = len(X)
    best_loss = float("inf")
    best_params = None

    # Adam state
    m_state = {k: np.zeros_like(v) for k, v in params.items()}
    v_state = {k: np.zeros_like(v) for k, v in params.items()}
    beta1, beta2, eps = 0.9, 0.999, 1e-8
    step = 0

    t0 = time.time()
    for ep in range(1, epochs + 1):
        idx = rng.permutation(N)
        ep_loss = 0.0; n_batches = 0
        for start in range(0, N, batch):
            bi = idx[start:start + batch]
            loss, grads = _bce_grad(X[bi], y[bi], params, l2=l2)
            step += 1
            for k in params:
                m_state[k] = beta1 * m_state[k] + (1 - beta1) * grads[k]
                v_state[k] = beta2 * v_state[k] + (1 - beta2) * grads[k]**2
                m_hat = m_state[k] / (1 - beta1**step)
                v_hat = v_state[k] / (1 - beta2**step)
                params[k] -= lr * m_hat / (np.sqrt(v_hat) + eps)
            ep_loss += loss; n_batches += 1

        ep_loss /= max(n_batches, 1)
        if ep_loss < best_loss:
            best_loss = ep_loss
            best_params = {k: v.copy() for k, v in params.items()}

        if verbose and (ep % 50 == 0 or ep == 1):
            print(f"  epoch {ep:4d}/{epochs}  loss={ep_loss:.5f}  best={best_loss:.5f}  "
                  f"elapsed={time.time()-t0:.0f}s")

    if verbose:
        print(f"\n[head] best BCE loss = {best_loss:.5f}  ({time.time()-t0:.0f}s total)")
    return best_params


# ── Main ─────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--epochs",   type=int,   default=300)
    ap.add_argument("--lr",       type=float, default=2e-3)
    ap.add_argument("--l2",       type=float, default=1e-4)
    ap.add_argument("--neg",      type=int,   default=2, help="negatives per positive")
    ap.add_argument("--eval-only",action="store_true")
    args = ap.parse_args(argv)

    os.chdir(str(PROJECT_ROOT))

    if not os.path.exists(GT_FILE):
        print(f"[head] Editorial GT not found: {GT_FILE}")
        print("  Run: python -m tools.backtest_v2 run --ground-truth editorial_playlists_v1")
        return 1

    playlists = json.load(open(GT_FILE))
    print(f"[head] GT: {len(playlists)} playlists")

    from tools.backtest_v2.catalog import Catalog
    from tools.eval_similar_intrinsic import _stratified_seeds
    from tools.validate_weights import _compute_metrics, METRICS

    print("[head] Loading catalog…")
    cat = Catalog.load()
    mert, lyric, va = _build_signal_matrices(cat)

    # Artist array for negative mining
    artists = None
    if cat.artist_col:
        artists = cat.df[cat.artist_col].fillna("").astype(str).values

    if not args.eval_only:
        # --- Mine triplets ---
        print("[head] Mining triplets…")
        X, y = mine_triplets(playlists, mert, lyric, va,
                             neg_per_pos=args.neg, artists=artists)
        pos = int(y.sum()); neg = int((1 - y).sum())
        print(f"[head] Dataset: {len(X)} pairs  ({pos} pos, {neg} neg)")
        print(f"  Feature stats: mean={X.mean(axis=0).round(3)}  std={X.std(axis=0).round(3)}")

        # --- Train 80/20 split ---
        rng = np.random.default_rng(42)
        idx = rng.permutation(len(X))
        n_tr = int(len(X) * 0.8)
        X_tr, y_tr = X[idx[:n_tr]], y[idx[:n_tr]]
        X_va, y_va = X[idx[n_tr:]], y[idx[n_tr:]]

        print(f"\n[head] Training: epochs={args.epochs} lr={args.lr} l2={args.l2}")
        params = train(X_tr, y_tr, epochs=args.epochs, lr=args.lr, l2=args.l2)

        # Val loss + AUC
        p_va = mlp_forward(X_va, params)
        from sklearn.metrics import roc_auc_score
        try:
            val_auc = roc_auc_score(y_va, p_va)
        except Exception:
            val_auc = float("nan")
        eps = 1e-7
        val_loss = float(-np.mean(y_va*np.log(p_va+eps) + (1-y_va)*np.log(1-p_va+eps)))
        print(f"[head] Val BCE={val_loss:.5f}  AUC={val_auc:.4f}")

        # Baseline: weighted sum (current config weights)
        W_BASE = np.array([0.82, 0.12, 0.06], dtype=np.float32)
        p_base = (X_va * W_BASE).sum(axis=1)
        try:
            base_auc = roc_auc_score(y_va, p_base)
        except Exception:
            base_auc = float("nan")
        print(f"[head] Baseline weighted-sum AUC={base_auc:.4f}  "
              f"Δ={val_auc - base_auc:+.4f}")

        np.savez(MODEL_NPZ, **params)
        meta = {"epochs": args.epochs, "lr": args.lr, "l2": args.l2,
                "n_pairs": len(X), "n_pos": pos, "n_neg": neg,
                "val_bce": round(val_loss, 5), "val_auc": round(val_auc, 4),
                "baseline_auc": round(base_auc, 4), "auc_delta": round(val_auc-base_auc, 4)}
        json.dump(meta, open(MODEL_META, "w"), indent=2)
        print(f"[head] Saved → {MODEL_NPZ}")
    else:
        if not os.path.exists(MODEL_NPZ):
            print("[head] No trained model found. Run without --eval-only first."); return 1
        d = np.load(MODEL_NPZ)
        params = {k: d[k] for k in d}
        print(f"[head] Loaded weights from {MODEL_NPZ}")

    # --- Intrinsic eval: weighted-sum vs learned head ---
    print("\n[head] Intrinsic eval (60 seeds)…")
    rng_s = np.random.default_rng(42)
    seeds = _stratified_seeds(cat.df, 60, rng_s)

    # Monkey-patch recommend_by_song to use learned head for signal 7
    import core.recommendation_engine as _eng
    orig_rec = _eng.MusicRecommender.recommend_by_song

    def recommend_with_head(self, song_id_or_name, top_k=10, weights=None,
                            diversity_penalty=cfg.DIVERSITY_PENALTY):
        # Resolve index
        if isinstance(song_id_or_name, int):
            seed_idx = song_id_or_name
        else:
            mask = self.df['track_name'].str.contains(song_id_or_name, case=False, na=False)
            if mask.sum() == 0: return __import__('pandas').DataFrame()
            seed_idx = mask.idxmax()

        # Compute 3-signal feature matrix (N, 3)
        feats = batch_scores_vs_query(seed_idx, mert, lyric, va)  # (N, 3)
        final_scores = mlp_forward(feats, params)                  # (N,)
        final_scores[seed_idx] = -1.0

        return self._fast_rank(final_scores, top_k, diversity_penalty,
                               max_per_artist=cfg.MAX_PER_ARTIST_SIMILAR or None)

    # Eval weighted-sum
    w_prod = [0,0,0,0.06,0.12,0,0,0.82]
    m_ws = _compute_metrics(cat, seeds, w_prod)

    # Eval learned head
    _eng.MusicRecommender.recommend_by_song = recommend_with_head
    m_lh = _compute_metrics(cat, seeds, w_prod)  # weights ignored by patch
    _eng.MusicRecommender.recommend_by_song = orig_rec

    print(f"\n{'Metric':<20}  {'WeightedSum':>12}  {'LearnedHead':>12}  {'Δ':>8}")
    print("-" * 58)
    wins = 0
    for key, label, hib in METRICS:
        ws_v, lh_v = m_ws[key], m_lh[key]
        d = lh_v - ws_v
        mark = ""
        if hib is True  and d >  0.003: mark = "✓"; wins += 1
        if hib is True  and d < -0.003: mark = "✗"
        if hib is False and d < -0.003: mark = "✓"; wins += 1
        if hib is False and d >  0.003: mark = "✗"
        print(f"  {label:<18}  {ws_v:>12.4f}  {lh_v:>12.4f}  {d:>+7.4f} {mark}")
    print("-" * 58)
    print(f"  Learned head improvements: {wins}")

    adopt = wins >= 3
    print(f"\n[head] Verdict: {'ADOPT ✓' if adopt else 'DO NOT ADOPT ✗'} "
          f"({'≥3 improvements' if adopt else '<3 improvements'})")
    if adopt:
        print(f"  → Set ENABLE_METRIC_HEAD=True in config to use learned head in production.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
