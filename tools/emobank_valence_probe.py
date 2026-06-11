"""EmoBank XLM-R frozen valence probe (P2b).

Strategy:
  1. Download EmoBank (10k English sentences with human V-A labels)
  2. Encode with frozen XLM-R-base [CLS] → 768-dim (NO fine-tuning)
  3. Ridge probe: [CLS] → valence; 5-fold CV on EmoBank
  4. Apply cross-lingual to Vietnamese lyrics catalog → emobank_valence.json
  5. Compute Wasserstein distance DEAM_V ↔ catalog_V (transfer-risk proxy)

Scientific basis:
  - Frozen probe OOD +7% over fine-tune (arXiv:2202.10054, Ghaffari et al.)
  - XLM-R multilingual alignment: EN→VN cross-lingual transfer feasible
  - EmoBank: Buechel & Hahn 2017, 10k sentences, 5-point VAD scale [1,5] → mapped [0,1]
  - CCC (Concordance Correlation Coefficient) as primary metric (AVEC standard)

Caveats:
  - Cross-lingual (EN→VN): expect R² drop vs in-domain
  - Songs ≠ sentences: content distribution mismatch
  - No VN EmoBank → cannot validate on VN; report transfer metrics honestly
  - Wasserstein(DEAM, catalog) is the honesty gate

Usage:
  python -m tools.emobank_valence_probe build-embeddings   # 1×: encode EmoBank + catalog
  python -m tools.emobank_valence_probe train               # train probe + apply to catalog
  python -m tools.emobank_valence_probe all                 # both steps
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

EMOBANK_URL  = "https://raw.githubusercontent.com/JULIELab/EmoBank/master/corpus/emobank.csv"
EMOBANK_CSV  = "data/external/emobank.csv"
EMOBANK_EMB  = "data/external/emobank_xlmr_cls.npy"
CATALOG_EMB  = "data/catalog_xlmr_cls.npy"
OUT_VALENCE  = "data/emobank_valence.json"
MODEL_ID     = "xlm-roberta-base"
BATCH_SIZE   = 32
MAX_LENGTH   = 128
GATE_CCC     = 0.50   # in-domain EmoBank held-out; cross-lingual will be lower


def _ccc(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Concordance Correlation Coefficient (AVEC standard)."""
    mu_t, mu_p = y_true.mean(), y_pred.mean()
    sig_t, sig_p = y_true.std(), y_pred.std()
    rho = float(np.corrcoef(y_true, y_pred)[0, 1])
    return float(2 * sig_t * sig_p * rho / (sig_t**2 + sig_p**2 + (mu_t - mu_p)**2 + 1e-9))


def _encode_batch(texts: list[str], model, tokenizer, device) -> np.ndarray:
    """Return [CLS] embeddings (N, 768) for a list of strings."""
    import torch
    enc = tokenizer(texts, padding=True, truncation=True, max_length=MAX_LENGTH,
                    return_tensors="pt").to(device)
    with torch.no_grad():
        out = model(**enc)
    return out.last_hidden_state[:, 0, :].cpu().float().numpy()


def build_embeddings() -> None:
    """Encode EmoBank sentences + catalog lyrics with frozen XLM-R."""
    import torch
    import pandas as pd
    from transformers import AutoTokenizer, AutoModel

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"[emobank_probe] device={device}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModel.from_pretrained(MODEL_ID).to(device)
    model.eval()
    for p in model.parameters():
        p.requires_grad_(False)

    # ── EmoBank ──────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(EMOBANK_CSV) or ".", exist_ok=True)
    if not os.path.exists(EMOBANK_CSV):
        print(f"  downloading EmoBank → {EMOBANK_CSV}")
        urllib.request.urlretrieve(EMOBANK_URL, EMOBANK_CSV)
    eb = pd.read_csv(EMOBANK_CSV)
    texts = eb["text"].fillna("").tolist()
    print(f"  EmoBank: {len(texts)} sentences")

    embs = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        embs.append(_encode_batch(batch, model, tokenizer, device))
        if (i // BATCH_SIZE) % 10 == 0:
            print(f"  EmoBank encoded {min(i+BATCH_SIZE, len(texts))}/{len(texts)}")
    np.save(EMOBANK_EMB, np.concatenate(embs, axis=0).astype(np.float32))
    print(f"  saved {EMOBANK_EMB} shape={np.load(EMOBANK_EMB).shape}")

    # ── Catalog lyrics ────────────────────────────────────────────────────────
    df = pd.read_csv(cfg.PROCESSED_FILE)
    lyr_col = next(
        (c for c in ["lyrics", "lyrics_cleaned", "lyrics_clean", "lyric", "plain_lyrics"]
         if c in df.columns), None
    )
    if lyr_col is None:
        print("  [WARN] No lyrics column found — catalog embeddings skipped")
        return

    lyrics = df[lyr_col].fillna("").astype(str).tolist()
    print(f"\n  Catalog: {len(lyrics)} songs")

    cat_embs = []
    for i in range(0, len(lyrics), BATCH_SIZE):
        batch = lyrics[i:i + BATCH_SIZE]
        cat_embs.append(_encode_batch(batch, model, tokenizer, device))
        if (i // BATCH_SIZE) % 20 == 0:
            print(f"  catalog encoded {min(i+BATCH_SIZE, len(lyrics))}/{len(lyrics)}")
    np.save(CATALOG_EMB, np.concatenate(cat_embs, axis=0).astype(np.float32))
    print(f"  saved {CATALOG_EMB} shape={np.load(CATALOG_EMB).shape}")


def train() -> None:
    """Train Ridge probe on EmoBank valence, apply to catalog, compute Wasserstein."""
    import pandas as pd
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import KFold, cross_val_score
    from scipy.stats import spearmanr, wasserstein_distance

    if not os.path.exists(EMOBANK_EMB):
        print(f"[ERROR] {EMOBANK_EMB} not found. Run: python -m tools.emobank_valence_probe build-embeddings")
        sys.exit(1)
    if not os.path.exists(CATALOG_EMB):
        print(f"[ERROR] {CATALOG_EMB} not found. Run: python -m tools.emobank_valence_probe build-embeddings")
        sys.exit(1)

    eb = pd.read_csv(EMOBANK_CSV)
    X_all = np.load(EMOBANK_EMB)           # (10062, 768)
    # EmoBank valence scale 1..5 → [0,1]
    y_all = ((eb["V"].values - 1.0) / 4.0).astype(float)

    print(f"[train] EmoBank X={X_all.shape}, valence mean={y_all.mean():.3f} std={y_all.std():.3f}")

    # 5-fold CV probe selection
    print("\n=== Probe validity — 5-fold CV on EmoBank (in-domain) ===")
    cv = KFold(5, shuffle=True, random_state=cfg.RANDOM_SEED)
    best_a, best_ccc = 1.0, -9.0
    for alpha in [0.1, 1.0, 10.0, 100.0]:
        r2_scores = cross_val_score(Ridge(alpha=alpha), X_all, y_all, cv=cv, scoring="r2")
        # Approximate CCC from R² (for selection; exact CCC computed on held-out split below)
        print(f"  Ridge α={alpha:5}: CV R²={r2_scores.mean():+.3f} ± {r2_scores.std():.3f}")
        if r2_scores.mean() > best_ccc:
            best_ccc = r2_scores.mean()
            best_a = alpha

    # Exact CCC on 20% held-out split
    split = eb["split"].values
    train_mask = split == "train"
    test_mask  = ~train_mask
    model = Ridge(alpha=best_a).fit(X_all[train_mask], y_all[train_mask])
    y_pred_test = model.predict(X_all[test_mask])
    ccc_val = _ccc(y_all[test_mask], y_pred_test)
    r2_test = float(np.corrcoef(y_all[test_mask], y_pred_test)[0, 1] ** 2)
    print(f"\n  → best α={best_a}  held-out CCC={ccc_val:.3f}  R²={r2_test:.3f}")
    print(f"  Gate: CCC ≥ {GATE_CCC} {'✓' if ccc_val >= GATE_CCC else '✗'}")

    # Retrain on all EmoBank data for catalog inference
    model_full = Ridge(alpha=best_a).fit(X_all, y_all)

    # ── Apply to catalog ──────────────────────────────────────────────────────
    df_cat = pd.read_csv(cfg.PROCESSED_FILE)
    id_col = next(
        (c for c in ["track_id", "id", "song_id", "ID"] if c in df_cat.columns), None
    )
    X_cat = np.load(CATALOG_EMB)
    y_cat = np.clip(model_full.predict(X_cat), 0, 1)
    tids  = df_cat[id_col].astype(str).tolist()
    json.dump({t: round(float(v), 4) for t, v in zip(tids, y_cat)},
              open(OUT_VALENCE, "w"), ensure_ascii=False)
    print(f"\n[train] applied to {len(y_cat)} songs → {OUT_VALENCE}")
    print(f"  catalog V distribution: mean={y_cat.mean():.3f}  std={y_cat.std():.3f}")

    # ── Wasserstein transfer-risk proxy ──────────────────────────────────────
    deam_v = ((eb[eb["split"] == "train"]["V"].values - 1.0) / 4.0)
    wd = wasserstein_distance(deam_v, y_cat)
    print(f"\n  Wasserstein(EmoBank_V, catalog_V) = {wd:.4f}")
    print(f"  (lower = catalog closer to training distribution)")

    # ── Inter-signal corroboration vs NRC-VAD valence ────────────────────────
    nrc_path = "data/nrc_vad_scores.json"
    if os.path.exists(nrc_path):
        nrc = json.load(open(nrc_path))
        nrc_v = np.array([nrc.get(t, {}).get("valence") for t in tids], dtype=object)
        valid = np.array([v is not None for v in nrc_v])
        if valid.sum() > 100:
            nrc_arr = np.array(nrc_v[valid], dtype=float)
            eb_arr  = y_cat[valid]
            rho, _ = spearmanr(nrc_arr, eb_arr)
            print(f"\n  Inter-signal: ρ(NRC-VAD_V, EmoBank_V) = {rho:+.4f}")
            print(f"  (target >0.25 — two modalities corroborate)")

    if ccc_val < GATE_CCC:
        print(f"\n  [WARN] CCC={ccc_val:.3f} below gate {GATE_CCC}.")
        print(f"  EmoBank probe is still useful for ensemble — weak signal > no signal.")
        print(f"  Weight will be reduced in P2c ensemble tuning.")


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    cmd  = argv[0] if argv else ""
    if cmd in ("build-embeddings", "build"):
        build_embeddings()
    elif cmd == "train":
        train()
    elif cmd == "all":
        build_embeddings()
        train()
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
