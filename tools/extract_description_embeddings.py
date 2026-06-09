"""
Build text description embeddings for sub-genre discrimination.

Problem: raw lyrics at 6% weight → VN-SBERT sees 200-500 noisy words → embedding too diffuse
         → can't distinguish "rap love" vs "rap flex" vs "rap life"

Solution (TTMR++ ICASSP 2024; CrossMuSim Huawei 2025):
  Build a SHORT, STRUCTURED description from metadata + TF-IDF keywords:
  "vui vẻ, nhịp nhanh, năng lượng cao, giọng trưởng, tiệc, bạn bè, flex, chill"

  TF-IDF extracts words most CHARACTERISTIC of each song vs the full catalog.
  VN-SBERT encodes this 15-word description → embedding much more discriminative.

Literature basis:
  - arXiv:2404.02342: SBERT semantic r=-0.65 (best predictor of lyric similarity)
    Topic/TF-IDF r=-0.13 (not significant) — so we use SBERT to encode, TF-IDF only for keyword selection
  - CrossMuSim: structured aspect descriptions beat raw lyrics for music retrieval
  - TTMR++: metadata enriched description → nDCG +15% over tag-only

Output: data/description_embeddings.npy  (5138, 768) L2-normalised
        data/description_metadata.json   stats + sample descriptions

Usage:
    python -m tools.extract_description_embeddings [--top-k 4] [--batch 64]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import config as cfg

OUT_NPY  = str(cfg.DATA_DIR / "description_embeddings.npy")
OUT_META = str(cfg.DATA_DIR / "description_metadata.json")

# Vietnamese emotion → display name
EMO_VI = {
    "happy": "vui vẻ", "excited": "phấn khích", "peaceful": "bình yên",
    "calm": "thư thái", "melancholic": "u sầu", "sad": "buồn",
    "tense": "căng thẳng", "angry": "giận dữ",
}

# pyvi stop words (common VN function words to exclude from TF-IDF)
VN_STOPWORDS = {
    "của", "và", "là", "có", "trong", "không", "được", "cho", "với",
    "một", "những", "các", "này", "đó", "như", "khi", "thì", "mà",
    "anh", "em", "tôi", "ta", "mình", "người", "nhau", "rồi", "đã",
    "vẫn", "cũng", "hay", "hoặc", "nếu", "vì", "để", "từ", "đến",
    "sẽ", "còn", "lại", "thôi", "ơi", "ừ", "ah", "uh", "à", "ạ",
    "bài", "hát", "nhạc", "lời", "tiếng", "mãi", "cứ", "đi", "về",
    "ra", "lên", "xuống", "đây", "kia", "đâu", "sao", "thế", "nào",
}


def build_tfidf_keywords(lyrics_list: list[str], track_ids: list[str],
                         top_k: int = 5) -> dict[str, list[str]]:
    """TF-IDF keyword extraction via sklearn — more robust than manual implementation.

    Returns {track_id: [kw1, ..., kwN]} — most characteristic words per song.
    avg pairwise cosine of keyword-only descriptions = 0.210 (vs 0.544 raw lyrics).
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(
        max_features=8000,
        min_df=3,          # word must appear in ≥3 songs
        max_df=0.80,       # word must appear in <80% of songs
        token_pattern=r"[a-záàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ]{3,}",
        sublinear_tf=True,
    )
    tfidf_mat = vec.fit_transform(lyrics_list)
    feature_names = vec.get_feature_names_out()

    result = {}
    for i, tid in enumerate(track_ids):
        row_vec = tfidf_mat[i].toarray()[0]
        top_idx = row_vec.argsort()[::-1][:top_k]
        kws = [feature_names[j] for j in top_idx if row_vec[j] > 0]
        result[tid] = kws

    return result


def build_description(row, keywords: list[str]) -> str:
    """Build keyword-focused description: emotion label + TF-IDF keywords.

    Design choice: keywords-only avg pairwise cosine = 0.210 vs 0.544 raw lyrics.
    Structured template (nhịp X, năng lượng Y) raises cosine to 0.713 because
    shared structural tokens dominate → less discriminative. Emotion + TF-IDF only.
    """
    parts = []

    # Mood label (categorical, highly discriminative)
    emo = str(row.get("fused_emotion", "") or "").lower()
    if emo and emo in EMO_VI:
        parts.append(EMO_VI[emo])

    # TF-IDF keywords — most characteristic words of this song vs the corpus
    parts.extend(keywords)

    return " ".join(parts) if parts else "nhạc"


def run(top_k: int = 4, batch_size: int = 64, verbose: bool = True) -> None:
    import pandas as pd, time
    from sentence_transformers import SentenceTransformer

    df = pd.read_csv(cfg.PROCESSED_FILE)
    n  = len(df)
    lyr_col = "lyrics_cleaned" if "lyrics_cleaned" in df.columns else "plain_lyrics"
    lyrics = df[lyr_col].fillna("").astype(str).tolist()
    track_ids = df["track_id"].astype(str).tolist()

    if verbose:
        print(f"[desc] Catalog: {n} songs")
        print(f"[desc] Building TF-IDF keywords (top_k={top_k})...")

    t0 = time.time()
    kw_map = build_tfidf_keywords(lyrics, track_ids, top_k=top_k)
    if verbose:
        print(f"[desc] TF-IDF done in {time.time()-t0:.1f}s")

    # Build descriptions
    descriptions = []
    for i, row in df.iterrows():
        tid = str(row["track_id"])
        kws = kw_map.get(tid, [])
        desc = build_description(row, kws)
        descriptions.append(desc)

    # Sample for inspection
    samples = [(df.iloc[i]["track_name"], descriptions[i]) for i in [0, 100, 500, 1000, 2000]]
    if verbose:
        print("\n[desc] Sample descriptions:")
        for name, desc in samples:
            print(f"  {str(name)[:30]:30s} → {desc}")

    # Encode with VN-SBERT
    if verbose:
        print(f"\n[desc] Encoding {n} descriptions with VN-SBERT...")
    model = SentenceTransformer(cfg.VNSBERT_MODEL)
    t1 = time.time()
    embeddings = model.encode(
        descriptions, batch_size=batch_size, normalize_embeddings=True,
        show_progress_bar=verbose, convert_to_numpy=True,
    )
    elapsed = time.time() - t1

    # Anisotropy check
    rng = np.random.default_rng(42)
    idx = rng.choice(n, min(500, n), replace=False)
    sub = embeddings[idx].astype(np.float64)
    cos = sub @ sub.T
    mask = ~np.eye(len(sub), dtype=bool)
    avg_cos = float(cos[mask].mean())
    raw_lyr_avg = 0.5437  # from vnsbert_embeddings baseline

    np.save(OUT_NPY, embeddings.astype(np.float32))
    meta = {
        "model": cfg.VNSBERT_MODEL,
        "n_songs": n, "dim": embeddings.shape[1],
        "top_k_tfidf": top_k,
        "elapsed_s": round(elapsed, 1),
        "avg_pairwise_cosine": round(avg_cos, 4),
        "raw_lyrics_baseline": raw_lyr_avg,
        "sample_descriptions": [{"song": n, "desc": d} for n, d in samples],
        "approach": "metadata + TF-IDF keywords → VN-SBERT encode (TTMR++ / CrossMuSim style)",
    }
    with open(OUT_META, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)

    if verbose:
        print(f"\n[desc] Done in {elapsed:.1f}s")
        print(f"[desc] avg pairwise cosine: {avg_cos:.4f}  (raw lyrics: {raw_lyr_avg})")
        more_disc = "✅ MORE discriminative" if avg_cos < raw_lyr_avg else "⚠️ less discriminative"
        print(f"[desc] {more_disc} than raw lyrics")
        print(f"[desc] Saved → {OUT_NPY}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top-k", type=int, default=4, help="TF-IDF keywords per song")
    ap.add_argument("--batch", type=int, default=64)
    args = ap.parse_args(argv)
    os.chdir(str(PROJECT_ROOT))
    run(top_k=args.top_k, batch_size=args.batch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
