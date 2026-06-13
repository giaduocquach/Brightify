"""
Phase 2b — Self-supervised metric head on frozen MERT embeddings with V-A preservation.

Method: SimCSE contrastive (Gao et al. EMNLP 2021) + V-A mood preservation (Phase 2b).

Loss = NT-Xent + λ_va × KL(p_VA ‖ q_proj)

  NT-Xent (unchanged from Phase 2):
    Positive = same embedding, two dropout masks. In-batch negatives.
    Same-artist pairs excluded from denominator (Flexer 2016).

  V-A Preservation loss (Phase 2b — fixes MoodCoherence drop):
    For each batch, compute V-A similarity distribution p_VA using Gaussian RBF
    on the per-song valence/arousal coordinates from RELABELED_EMOTIONS_FILE.
    Compute cosine similarity distribution q_proj in the projected space.
    KL(p_VA ‖ q_proj): projected space must reproduce the relative mood ordering
    from the V-A space — without forcing exact values (unlike MSE).
    This is analogous to knowledge distillation: V-A is the teacher,
    projected space is the student.

    Why KL not MSE: MSE forces exact match → collapses acoustic diversity.
    KL is soft: as long as nearest-VA neighbours are also nearest in proj,
    loss is low regardless of absolute scale. Preserves mood ranking without
    sacrificing timbral/rhythmic structure learnt by NT-Xent.

Architecture (MERIT-style, arXiv:2605.27346):
  Linear(768→384) → ReLU → Dropout(p) → Linear(384→128) → L2-norm

Output:
  data/mert_proj_embeddings.npy / _multilayer.npy   (N, 128) L2-normalised
  data/mert_proj_metadata.npy / _multilayer.json    training stats

Usage:
    # Phase 2b (default): NT-Xent + VA preservation
    python -m tools.train_mert_head --multilayer --artist-neg
    # Ablation: NT-Xent only (Phase 2 without VA)
    python -m tools.train_mert_head --multilayer --artist-neg --va-lambda 0
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config as cfg


# ── Model ────────────────────────────────────────────────────────────────────

def _build_head(in_dim: int = 768, hidden: int = 384, out_dim: int = 128,
                dropout: float = 0.15):
    import torch.nn as nn
    return nn.Sequential(
        nn.Linear(in_dim, hidden),
        nn.ReLU(),
        nn.Dropout(p=dropout),
        nn.Linear(hidden, out_dim),
    )


def _l2_norm(x):
    import torch
    return x / (x.norm(dim=1, keepdim=True) + 1e-9)


# ── NT-Xent loss (InfoNCE) ────────────────────────────────────────────────────

def nt_xent_loss(z1, z2, temp: float = 0.05, artist_ids=None):
    """NT-Xent (InfoNCE) loss for SimCSE positive pairs.

    z1, z2: (B, D) L2-normalised — same song, two different dropout passes.
    Positive: z1[i] ↔ z2[i]  (diagonal of the cross-view sim block).
    Negatives: all other songs in the batch.

    artist_ids (optional, Flexer 2016 artist-filter fix):
        Same-artist pairs are EXCLUDED from the denominator rather than
        treated as hard negatives.  Rationale: within-artist variation in a
        5138-song catalog with 1502 artists means same-artist pairs are
        "ambiguous" (neither clear positive nor clear negative).  Pushing
        them apart teaches artist-identity, not musical similarity.
        Implementation: set same-artist entries to -inf before logsumexp
        so they contribute zero to the denominator (= ignore, not negative).
    """
    import torch

    B = z1.shape[0]
    z  = torch.cat([z1, z2], dim=0)          # (2B, D)
    sim = torch.mm(z, z.t()) / temp           # (2B, 2B)

    # Self-similarity mask (diagonal)
    eye = torch.eye(2 * B, dtype=torch.bool, device=z.device)

    # Artist-exclusion mask: same-artist off-diagonal entries → ignore
    exclude = eye.clone()
    if artist_ids is not None:
        a = torch.cat([artist_ids, artist_ids], dim=0)        # (2B,)
        same_artist = (a.unsqueeze(0) == a.unsqueeze(1))       # (2B, 2B)
        exclude = exclude | (same_artist & ~eye)

    # Numerator: positive similarity (z1[i] ↔ z2[i], i.e. index B+i for z1[i])
    pos_idx_fwd = torch.arange(B, device=z.device)          # z1 rows → z2 cols
    pos_idx_bwd = torch.arange(B, 2 * B, device=z.device)  # z2 rows → z1 cols
    pos_sim = torch.cat([
        sim[pos_idx_fwd, pos_idx_fwd + B],
        sim[pos_idx_bwd, pos_idx_bwd - B],
    ])  # (2B,)

    # Denominator: logsumexp over all valid negatives (exclude self + same-artist)
    sim_denom = sim.masked_fill(exclude, -1e9)
    log_denom  = torch.logsumexp(sim_denom, dim=1)          # (2B,)

    loss = -(pos_sim - log_denom).mean()
    return loss


# ── V-A Preservation loss (Phase 2b) ─────────────────────────────────────────

def va_preservation_loss(z: "torch.Tensor", va: "torch.Tensor",
                         temp_va: float = 0.20) -> "torch.Tensor":
    """KL(p_VA ‖ q_proj): keep projected space consistent with V-A mood ordering.

    For each anchor i in the batch:
      p_VA[i, j]  = softmax(-d_VA(i,j) / temp_va)   — V-A teacher distribution
      q_proj[i,j] = softmax(cosine(z_i, z_j) / temp_va) — proj student distribution
    Minimising KL(p_VA ‖ q_proj) makes q_proj reproduce p_VA's shape:
    songs close in mood (V-A) should also be close in proj space.

    temp_va: lower = sharper focus on nearest VA neighbours (default 0.20).
    Diagonal (self) excluded via -inf mask before softmax.
    """
    import torch
    import torch.nn.functional as F

    B = z.shape[0]
    eye = torch.eye(B, dtype=torch.bool, device=z.device)

    # V-A pairwise distance → similarity
    diff = va.unsqueeze(0) - va.unsqueeze(1)          # (B, B, 2)
    va_dist = diff.pow(2).sum(-1).sqrt()              # (B, B) Euclidean
    va_logit = (-va_dist / temp_va).masked_fill(eye, -1e9)
    p = F.softmax(va_logit, dim=1)                    # target: (B, B)

    # Projected cosine similarity
    proj_logit = torch.mm(z, z.t()) / temp_va
    proj_logit = proj_logit.masked_fill(eye, -1e9)
    log_q = F.log_softmax(proj_logit, dim=1)          # (B, B) log-probs

    # KL(p ‖ q) = Σ p * (log p − log q); F.kl_div(log_q, p) = Σ p*(log p − log_q)
    return F.kl_div(log_q, p, reduction="batchmean")


def _load_song_va(n_songs: int) -> "np.ndarray | None":
    """Load per-song V-A from RELABELED_EMOTIONS_FILE (track_id keyed).

    Returns (N, 2) float32 [valence, arousal] or None if unavailable.
    """
    import json
    import pandas as pd
    try:
        with open(cfg.RELABELED_EMOTIONS_FILE) as fh:
            emo = json.load(fh)
        df = pd.read_csv(cfg.PROCESSED_FILE, usecols=["track_id"])
        va = np.full((n_songs, 2), 0.5, dtype=np.float32)
        for i, tid in enumerate(df["track_id"].astype(str)):
            entry = emo.get(tid)
            if isinstance(entry, dict):
                va[i, 0] = float(entry.get("valence", 0.5))
                va[i, 1] = float(entry.get("arousal", 0.5))
        return va
    except Exception as e:
        print(f"[head] WARNING: could not load song_va: {e} — VA loss disabled")
        return None


# ── Training loop ─────────────────────────────────────────────────────────────

def train(
    emb_path: str,
    out_npy: str,
    out_meta: str,
    in_dim: int = 768,
    hidden: int = 384,
    out_dim: int = 128,
    dropout: float = 0.15,
    temp: float = 0.05,
    temp_va: float = 0.20,
    va_lambda: float = 0.30,
    epochs: int = 50,
    batch_size: int = 256,
    lr: float = 3e-4,
    artist_col: str | None = None,
    verbose: bool = True,
) -> None:
    import torch
    import torch.optim as optim
    import pandas as pd

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if verbose:
        print(f"[head] device={device}  emb={emb_path}")

    # Load frozen embeddings
    raw = np.load(emb_path).astype(np.float32)
    N   = raw.shape[0]
    if raw.shape[1] != in_dim:
        in_dim = raw.shape[1]
        if verbose:
            print(f"[head] auto in_dim={in_dim} from embedding shape")
    emb_t = torch.from_numpy(raw).to(device)   # (N, in_dim) — frozen

    # V-A coordinates for mood preservation loss (Phase 2b)
    song_va_arr = None
    va_t = None
    if va_lambda > 0:
        song_va_arr = _load_song_va(N)
        if song_va_arr is not None:
            va_t = torch.from_numpy(song_va_arr).to(device)  # (N, 2)
            if verbose:
                print(f"[head] VA preservation: λ={va_lambda}  τ_va={temp_va}")
        else:
            va_lambda = 0.0   # disable gracefully if load failed

    # Optional artist IDs for hard-negative suppression
    artist_ids_arr = None
    if artist_col:
        try:
            df = pd.read_csv(cfg.PROCESSED_FILE)
            col = df[artist_col].fillna("").astype(str).values
            uniq = {v: i for i, v in enumerate(sorted(set(col)))}
            artist_ids_arr = np.array([uniq[v] for v in col], dtype=np.int64)
            if verbose:
                print(f"[head] artist_col='{artist_col}', {len(uniq)} unique artists")
        except Exception as e:
            if verbose:
                print(f"[head] artist_col skipped: {e}")

    # Build head
    head = _build_head(in_dim, hidden, out_dim, dropout).to(device)
    opt  = optim.AdamW(head.parameters(), lr=lr, weight_decay=1e-4)
    sched = optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    rng = np.random.default_rng(42)
    best_loss = float("inf")
    best_state = None

    if verbose:
        va_str = f"  VA-loss: λ={va_lambda} τ_va={temp_va}" if va_lambda > 0 else "  VA-loss: disabled"
        print(f"[head] Training: epochs={epochs} batch={batch_size} lr={lr} "
              f"τ={temp} dropout={dropout}")
        print(f"  Architecture: {in_dim}→{hidden}→{out_dim} (L2-norm output)")
        print(f"  Songs: {N}  batches/epoch: {N // batch_size + 1}")
        print(va_str)

    t0 = time.time()
    for ep in range(1, epochs + 1):
        head.train()
        idx_perm = rng.permutation(N)
        ep_loss  = 0.0
        n_batches = 0

        for start in range(0, N, batch_size):
            batch_idx = idx_perm[start: start + batch_size]
            if len(batch_idx) < 2:
                continue
            x = emb_t[batch_idx]                 # (B, in_dim)

            # Two forward passes with DIFFERENT dropout masks → positive pairs
            z1 = _l2_norm(head(x))
            z2 = _l2_norm(head(x))

            # Artist IDs for this batch
            a_ids = None
            if artist_ids_arr is not None:
                a_ids = torch.tensor(
                    artist_ids_arr[batch_idx], dtype=torch.long, device=device
                )

            loss = nt_xent_loss(z1, z2, temp=temp, artist_ids=a_ids)

            # Phase 2b: V-A preservation — KL(p_VA ‖ q_proj)
            # Use mean of z1/z2 (averaged dropout views) so VA loss isn't noisy.
            if va_lambda > 0 and va_t is not None:
                z_mean = _l2_norm((z1 + z2) * 0.5)
                va_batch = va_t[batch_idx]
                loss = loss + va_lambda * va_preservation_loss(z_mean, va_batch, temp_va)

            opt.zero_grad()
            loss.backward()
            opt.step()
            ep_loss  += loss.item()
            n_batches += 1

        sched.step()
        ep_loss /= max(n_batches, 1)

        if ep_loss < best_loss:
            best_loss  = ep_loss
            best_state = {k: v.cpu().clone() for k, v in head.state_dict().items()}

        if verbose and (ep % 10 == 0 or ep == 1):
            elapsed = time.time() - t0
            print(f"  epoch {ep:3d}/{epochs}  loss={ep_loss:.5f}  "
                  f"best={best_loss:.5f}  lr={sched.get_last_lr()[0]:.6f}  "
                  f"elapsed={elapsed:.0f}s")

    # Restore best checkpoint
    if best_state:
        head.load_state_dict(best_state)

    # Extract projected embeddings for entire catalog
    head.eval()
    proj_list = []
    with torch.no_grad():
        for start in range(0, N, batch_size * 2):
            x = emb_t[start: start + batch_size * 2]
            # No dropout at inference (head.eval())
            z = _l2_norm(head(x)).cpu().numpy()
            proj_list.append(z)

    proj = np.concatenate(proj_list, axis=0).astype(np.float32)   # (N, out_dim)

    # Verify unit-norm
    norms = np.linalg.norm(proj, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4), f"norm check failed: {norms.min():.4f}–{norms.max():.4f}"

    # Save
    Path(out_npy).parent.mkdir(parents=True, exist_ok=True)
    np.save(out_npy, proj)
    elapsed_total = time.time() - t0
    meta = {
        "source_embeddings": emb_path,
        "in_dim": in_dim, "hidden": hidden, "out_dim": out_dim,
        "dropout": dropout, "temp": temp,
        "va_lambda": va_lambda, "temp_va": temp_va,
        "epochs": epochs, "batch_size": batch_size, "lr": lr,
        "best_loss": round(best_loss, 6),
        "n_songs": N,
        "elapsed_s": round(elapsed_total, 1),
        "method": "SimCSE-dropout + VA-preservation KL (Phase 2b, 2026-06-08)",
        "artist_hard_neg": artist_col is not None,
        "va_preservation": va_lambda > 0 and song_va_arr is not None,
    }
    with open(out_meta, "w") as fh:
        json.dump(meta, fh, indent=2)

    if verbose:
        print(f"\n[head] DONE  best_loss={best_loss:.5f}  elapsed={elapsed_total:.0f}s")
        print(f"[head] Projected: {proj.shape}  norm range [{norms.min():.4f}, {norms.max():.4f}]")
        print(f"[head] Saved → {out_npy}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--embeddings", default=cfg.MERT_EMBEDDINGS_FILE,
                    help="Source MERT embedding .npy (default: single-layer)")
    ap.add_argument("--multilayer", action="store_true",
                    help="Use multilayer embeddings as source")
    ap.add_argument("--epochs",     type=int,   default=60)
    ap.add_argument("--batch",      type=int,   default=256)
    ap.add_argument("--lr",         type=float, default=3e-4)
    ap.add_argument("--dropout",    type=float, default=0.15)
    ap.add_argument("--temp",       type=float, default=0.05)
    ap.add_argument("--hidden",     type=int,   default=384)
    ap.add_argument("--out-dim",    type=int,   default=128)
    ap.add_argument("--artist-neg", action="store_true",
                    help="Suppress same-artist pairs as hard negatives")
    ap.add_argument("--va-lambda", type=float, default=0.30,
                    help="Weight of V-A mood preservation KL loss (0=disable, default 0.30)")
    ap.add_argument("--temp-va",   type=float, default=0.20,
                    help="Temperature for V-A softmax (lower=focus on nearest mood neighbours)")
    args = ap.parse_args(argv)

    os.chdir(str(PROJECT_ROOT))

    src = (cfg.MERT_EMBEDDINGS_MULTILAYER_FILE
           if args.multilayer else args.embeddings)

    # Output paths encode source so both can coexist
    suffix = "_multilayer" if args.multilayer or src == cfg.MERT_EMBEDDINGS_MULTILAYER_FILE else ""
    out_npy  = str(Path(cfg.DATA_DIR) / f"mert_proj_embeddings{suffix}.npy")
    out_meta = str(Path(cfg.DATA_DIR) / f"mert_proj_metadata{suffix}.json")

    if not os.path.exists(src):
        print(f"[head] ERROR: source embeddings not found: {src}")
        if args.multilayer:
            print("  Run first: python -m tools.extract_mert_multilayer")
        return 1

    artist_col = None
    if args.artist_neg:
        import pandas as pd
        df = pd.read_csv(cfg.PROCESSED_FILE, nrows=1)
        for c in ["artist", "artist_name", "artists", "primary_artist"]:
            if c in df.columns:
                artist_col = c
                break

    train(
        emb_path=src, out_npy=out_npy, out_meta=out_meta,
        hidden=args.hidden, out_dim=args.out_dim,
        dropout=args.dropout, temp=args.temp,
        temp_va=args.temp_va, va_lambda=args.va_lambda,
        epochs=args.epochs, batch_size=args.batch, lr=args.lr,
        artist_col=artist_col,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
