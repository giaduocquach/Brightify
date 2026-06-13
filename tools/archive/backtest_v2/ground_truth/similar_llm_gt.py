"""LLM-as-judge ground truth for recommend_by_song — v2 (de-circularized).

v2 vs v1 change: removed `fused_emotion` (mood label) from judge prompt.
  v1 flaw: `fused_emotion` is an engine-internal label used for ranking signal 7
  (mood_match) — exposing it to the judge creates a self-referential loop:
  judge rewards what the engine already rewards.  Soboroff SIGIR 2024 (arXiv:2409.15133).

v2 judge sees: title + tempo/energy cue + lyric snippet ONLY.
  (title is also in the engine's key but carries no ranking weight — acceptable.)

JUDGE (v2 honest status — verified 2026-06): qwen3:8b is the SOLE discriminating judge.
  A PoLL second judge (gemma2:2b) was added per Verga 2024 but found DEGENERATE on
  verification: gemma2:2b rubber-stamps ~99.9% of pairs as score=2 (binary Cohen's
  κ=+0.003 vs qwen3 — no agreement beyond chance). It does not discriminate, so
  "relevance = both >= 2" reduces to "qwen3 >= 2" (NDCG identical: +0.158 either way).
  gemma2 scores are still cached for transparency but DO NOT gate relevance materially.
  No capable second judge is available locally (others are coder/embedding models).
  → Treat this GT as DE-CIRCULARIZED qwen3 single-judge. The real v1→v2 win is removing
  fused_emotion from the prompt (Soboroff 2024), NOT the (failed) PoLL.

TREC-style pooling: pool = production top-N UNION N random negatives per seed.
Resumable: cache in similar_llm_gt_v2.json keyed by "{seed_idx}|{cand_idx}",
  value = {"q": qwen3_score, "g": gemma2_score}  (-1 = failed/unjudgeable).

Usage: python -m tools.backtest_v2.ground_truth.similar_llm_gt [n_seeds] [pool_prod] [pool_rand]
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Dict, List, Optional

import numpy as np

MODEL_PRIMARY   = "qwen3:8b"
MODEL_SECONDARY = "qwen2.5-coder:14b"   # replaces degenerate gemma2:2b (2026-06-05)
OLLAMA          = "http://localhost:11434/api/generate"
GT_DIR          = "var/runtime/backtest/ground_truth"
GT_FILE         = os.path.join(GT_DIR, "similar_llm_gt_v2.json")
GT_FILE_V1      = os.path.join(GT_DIR, "similar_llm_gt_v1.json")  # archived circular version

REL_THRESHOLD    = 2     # score >= 2 (of 0..3) => relevant
DEFAULT_N_SEEDS  = 30
DEFAULT_POOL_PROD = 15
DEFAULT_POOL_RAND = 10
SEED_RNG         = 42

# ── De-circularized prompt: NO fused_emotion, NO mood label ──────────────────
PROMPT = """/no_think
Bạn là nhà phê bình âm nhạc Việt Nam. Đánh giá mức độ TƯƠNG TỰ giữa hai bài hát.
Chỉ dựa vào lời và cảm giác âm nhạc — không xét nghệ sĩ hay độ nổi tiếng.
Trả JSON duy nhất: {{"score": <0..3>}}

0=hoàn toàn khác  1=ít liên quan  2=tương tự  3=rất tương tự (cùng playlist)

=== BÀI GỐC ===
Tên: {seed_title}
Nhịp/Năng lượng: {seed_feel}
Lời (trích):
{seed_lyrics}

=== BÀI SO SÁNH ===
Tên: {cand_title}
Nhịp/Năng lượng: {cand_feel}
Lời (trích):
{cand_lyrics}"""


def _call_ollama(model: str, prompt: str, timeout: int = 90) -> Optional[int]:
    """Call Ollama model, parse JSON score 0-3. Returns None on failure."""
    import requests
    try:
        r = requests.post(OLLAMA, json={
            "model": model, "prompt": prompt, "stream": False,
            "format": "json", "options": {"temperature": 0.0, "num_predict": 64},
        }, timeout=timeout)
        text = r.json().get("response", "")
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        out  = json.loads(text or "{}")
        s    = int(round(float(out.get("score", 0))))
        return max(0, min(3, s))
    except Exception:
        return None


def _judge(seed_title: str, seed_feel: str, seed_lyrics: str,
           cand_title: str, cand_feel: str, cand_lyrics: str,
           model: str = MODEL_PRIMARY) -> Optional[int]:
    """Pairwise similarity judge (0..3), no mood label — de-circularized."""
    prompt = PROMPT.format(
        seed_title=seed_title or "",
        seed_feel=seed_feel or "(không rõ)",
        seed_lyrics=(seed_lyrics or "")[:800],
        cand_title=cand_title or "",
        cand_feel=cand_feel or "(không rõ)",
        cand_lyrics=(cand_lyrics or "")[:800],
    )
    return _call_ollama(model, prompt)


def _song_info(row, lyr_col: str):
    """Return (title, feel, lyrics) — NO mood/emotion label."""
    title  = str(row.get("track_name", "") or "")
    tempo  = str(row.get("tempo_category", "") or "")
    energy = str(row.get("energy_level", "") or "")
    feel   = f"nhịp {tempo}, năng lượng {energy}" if (tempo or energy) else "(không rõ)"
    lyrics = str(row.get(lyr_col, "") or "")
    return title, feel, lyrics


def _stratified_seeds(df, n: int, rng: np.random.Generator) -> List[int]:
    """Sample n seed indices stratified by fused_emotion."""
    if "fused_emotion" not in df.columns:
        return rng.choice(len(df), size=min(n, len(df)), replace=False).tolist()
    groups = df.groupby("fused_emotion").indices
    per_group = max(1, n // len(groups))
    seeds: List[int] = []
    for idxs in groups.values():
        k = min(per_group, len(idxs))
        seeds.extend(int(i) for i in rng.choice(idxs, size=k, replace=False))
    chosen    = set(seeds)
    remaining = [i for i in range(len(df)) if i not in chosen]
    if len(seeds) < n and remaining:
        extra = min(n - len(seeds), len(remaining))
        seeds.extend(int(i) for i in rng.choice(remaining, size=extra, replace=False))
    return seeds[:n]


def build_similar_llm_gt(n_seeds: int  = DEFAULT_N_SEEDS,
                         pool_prod: int = DEFAULT_POOL_PROD,
                         pool_rand: int = DEFAULT_POOL_RAND,
                         verbose:  bool = True) -> dict:
    from tools.backtest_v2.catalog import Catalog

    cat = Catalog.load()
    df  = cat.df
    lyr_col = "lyrics_cleaned" if "lyrics_cleaned" in df.columns else "plain_lyrics"
    rng = np.random.default_rng(SEED_RNG)

    gt: dict = {}
    if os.path.exists(GT_FILE):
        gt = json.load(open(GT_FILE))
        if verbose:
            cached_q = sum(1 for v in gt.values()
                           for sc in v.get("judged", {}).values() if isinstance(sc, dict) and sc.get("q", -1) >= 0)
            print(f"[similar-llm-gt v2] resuming — {cached_q} qwen3 judgements cached")

    seeds = _stratified_seeds(df, n_seeds, rng)
    t0 = time.time(); n_calls = 0

    for seed_idx in seeds:
        key_s = str(seed_idx)
        entry = gt.get(key_s, {"seed_idx": seed_idx, "judged": {}})
        judged = entry["judged"]

        seed_row = df.iloc[seed_idx]
        s_title, s_feel, s_lyrics = _song_info(seed_row, lyr_col)
        entry["seed_title"] = s_title

        prod = cat.recommend_by_song(seed_idx, top_k=pool_prod)
        rand = rng.choice(cat.n, size=min(pool_rand, cat.n), replace=False).tolist()
        pool = list(dict.fromkeys([int(i) for i in prod] + [int(i) for i in rand]))
        entry["pool_prod"] = [int(i) for i in prod]

        for cand_idx in pool:
            ckey = str(cand_idx)
            sc   = judged.get(ckey, {})
            if not isinstance(sc, dict):          # migrate v1 int entries → skip
                continue
            need_q   = sc.get("q",   -2) == -2   # -2 = not yet attempted
            need_g14 = sc.get("g14", -2) == -2   # qwen2.5-coder:14b (replaces degenerate gemma2)
            # "g" (gemma2) kept for archive; never re-judged

            if not need_q and not need_g14:
                continue

            cand_row = df.iloc[cand_idx]
            c_title, c_feel, c_lyrics = _song_info(cand_row, lyr_col)
            if len(s_lyrics) < 30 or len(c_lyrics) < 30:
                sc.setdefault("q",   -1)
                sc.setdefault("g14", -1)
                judged[ckey] = sc
                continue

            if need_q:
                q = _judge(s_title, s_feel, s_lyrics, c_title, c_feel, c_lyrics, MODEL_PRIMARY)
                sc["q"] = -1 if q is None else q
                n_calls += 1

            if need_g14:
                g14 = _judge(s_title, s_feel, s_lyrics, c_title, c_feel, c_lyrics, MODEL_SECONDARY)
                sc["g14"] = -1 if g14 is None else g14
                n_calls += 1

            judged[ckey] = sc
            if verbose and n_calls % 30 == 0:
                rate = (time.time() - t0) / max(n_calls, 1)
                print(f"  judged {n_calls} ({rate:.1f}s/call)")

        # PoLL relevance: qwen3 AND qwen2.5-coder:14b both >= threshold.
        # Falls back to qwen3-only if g14 not yet available.
        relevant = []
        g14_available = any(isinstance(v, dict) and v.get("g14", -1) >= 0
                            for v in judged.values())
        for ckey, sc in judged.items():
            if not isinstance(sc, dict):
                continue
            q_score   = sc.get("q",   -1)
            g14_score = sc.get("g14", -1)
            if g14_available and g14_score >= 0:
                if q_score >= REL_THRESHOLD and g14_score >= REL_THRESHOLD:
                    relevant.append(int(ckey))
            else:
                if q_score >= REL_THRESHOLD:
                    relevant.append(int(ckey))

        entry["relevant"]  = sorted(relevant)
        entry["poll_mode"] = "qwen3+qwen14b" if g14_available else "qwen3-only"
        gt[key_s] = entry
        os.makedirs(GT_DIR, exist_ok=True)
        json.dump(gt, open(GT_FILE, "w"), ensure_ascii=False, indent=1)
        if verbose:
            n_judged = sum(1 for sc in judged.values() if isinstance(sc, dict) and sc.get("q", -1) >= 0)
            print(f"[similar-llm-gt v2] seed {seed_idx:4d} ({s_title[:28]:28s}): "
                  f"{len(relevant)} relevant / {n_judged} judged  [{entry['poll_mode']}]")

    print(f"[similar-llm-gt v2] DONE — {n_calls} new calls → {GT_FILE}")
    return gt


def load_similar_llm_gt(path: str = GT_FILE) -> dict:
    return json.load(open(path))


def build_query_gt_mapping(gt: dict) -> Dict[int, List[int]]:
    """Convert gt dict → {seed_idx: [relevant_idx, ...]}."""
    return {int(k): v["relevant"] for k, v in gt.items() if v.get("relevant")}


if __name__ == "__main__":
    ns = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N_SEEDS
    pp = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_POOL_PROD
    pr = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_POOL_RAND
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    build_similar_llm_gt(ns, pp, pr)
