"""
Phase 2 — Self-supervised metric head on frozen MERT embeddings.

Method: SimCSE-style unsupervised contrastive learning (Gao et al. EMNLP 2021).
  - Frozen MERT embeddings (768-dim) are the backbone — no audio re-processing.
  - A shallow MLP head (768→384→128, ReLU+Dropout between layers) is trained.
  - Positive pairs: same embedding passed through head TWICE with different
    dropout masks — dropout acts as minimal stochastic augmentation.
  - Negatives: all other songs in the batch (in-batch negatives).
  - Loss: NT-Xent (InfoNCE) with temperature τ=0.05.
  - Optional hard negatives: down-weight same-artist pairs in the loss
    (Flexer 2016: artist identity is the dominant confound in music similarity).

Architecture (MERIT-style, arXiv:2605.27346):
  Linear(768→384) → ReLU → Dropout(p) → Linear(384→128) → L2-norm

Output:
  data/mert_proj_embeddings.npy        (N, 128) float32, L2-normalised
  data/mert_proj_metadata.json         training stats

The projected matrix is drop-in compatible with recommendation_engine.py
(just a different mert_matrix with dim=128 instead of 768).

Usage:
    python -m tools.train_mert_head [--epochs 50] [--batch 256] [--lr 3e-4]
    python -m tools.train_mert_head --embeddings data/mert_embeddings_multilayer.npy
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
    """NT-Xent loss for a batch of (z1[i], z2[i]) positive pairs.

    z1, z2: (B, D) L2-normalised
    Diagonal of sim matrix = positive (same song, different dropout).
    Off-diagonal = in-batch negatives.

    artist_ids (optional): (B,) int tensor; same-artist pairs get their
    similarity score suppressed (multiplied by 0.3) before softmax,
    which steers the model away from artist-identity shortcuts.
    """
    import torch
    import torch.nn.functional as F

    B = z1.shape[0]
    # Concatenate: first B = z1 views, next B = z2 views
    z = torch.cat([z1, z2], dim=0)          # (2B, D)
    sim = torch.mm(z, z.t()) / temp          # (2B, 2B)

    # Suppress self-similarity on diagonal
    mask_self = torch.eye(2 * B, device=z.device).bool()
    sim = sim.masked_fill(mask_self, -1e9)

    # Optional: suppress same-artist pairs
    if artist_ids is not None:
        a = torch.cat([artist_ids, artist_ids], dim=0)  # (2B,)
        same_artist = (a.unsqueeze(0) == a.unsqueeze(1)) & ~mask_self
        # Scale down same-artist similarities (suppress artist-identity shortcut)
        sim = sim * torch.where(same_artist, torch.tensor(0.3, device=z.device), torch.tensor(1.0, device=z.device))

    # Positive targets: z1[i] <-> z2[i] (cross-view)
    labels = torch.cat([
        torch.arange(B, 2 * B, device=z.device),
        torch.arange(0, B,     device=z.device),
    ])
    loss = F.cross_entropy(sim, labels)
    return loss


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
        print(f"[head] Training: epochs={epochs} batch={batch_size} lr={lr} "
              f"τ={temp} dropout={dropout}")
        print(f"  Architecture: {in_dim}→{hidden}→{out_dim} (L2-norm output)")
        print(f"  Songs: {N}  batches/epoch: {N // batch_size + 1}")

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
        "epochs": epochs, "batch_size": batch_size, "lr": lr,
        "best_loss": round(best_loss, 6),
        "n_songs": N,
        "elapsed_s": round(elapsed_total, 1),
        "method": "SimCSE-dropout unsupervised contrastive (Gao et al. EMNLP 2021)",
        "artist_hard_neg": artist_col is not None,
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
        epochs=args.epochs, batch_size=args.batch, lr=args.lr,
        artist_col=artist_col,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
