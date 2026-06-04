"""Bước C1 — Spot-check valence: old prompt vs new prompt (Qwen3) + Gemini decoupled.

So sánh 3 cách gán valence trên 50 bài đại diện:
  A: Old prompt (thang 0-1 float, coarse) — Qwen3:8b [current production]
  B: New prompt (thang 0-100 int, CoT, few-shot anchor) — Qwen3:8b
  C: Decoupled model (Gemini via API, hoặc gemma2:2b nếu không có key)

Chạy: python -m tools.spotcheck_valence [--skip-c]
GEMINI_API_KEY phải có trong .env hoặc environment.
"""
import json, sys, time, requests, random, os
import numpy as np
import pandas as pd
from collections import Counter
from scipy import stats

# Load .env (tools chạy CLI không qua app.py nên phải tự load)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

OLLAMA  = "http://localhost:11434/api/generate"
MODEL_A = "qwen3:8b"
MODEL_B = "qwen3:8b"
MODEL_C_OLLAMA = "gemma2:2b"          # fallback nếu không có Gemini key
GEMINI_MODEL   = "models/gemini-2.5-flash"  # thinking_budget=0 → nhanh như Flash
OUT_DIR = "var/runtime/backtest/reports"
os.makedirs(OUT_DIR, exist_ok=True)

# ── Old prompt (production v4) ──────────────────────────────────────────────
OLD_PROMPT = """Bạn là chuyên gia phân tích âm nhạc Việt Nam. Hãy đánh giá bài hát sau:
Tên bài: {title}
Lời bài hát:
{lyrics}

Trả về JSON:
{{"valence": <0..1, 0=rất buồn/tiêu cực, 1=rất vui/tích cực>, "arousal": <0..1, 0=rất tĩnh/êm dịu/chậm rãi, 1=rất mạnh mẽ/dữ dội/sôi động>}}
QUAN TRỌNG: valence và arousal ĐỘC LẬP — đừng để cái này quyết định cái kia."""

# ── New prompt (C1 candidate: 0-100, CoT, few-shot anchor) ──────────────────
NEW_PROMPT = """Bạn là chuyên gia phân tích cảm xúc âm nhạc Việt Nam. Đọc kỹ lời bài hát dưới đây.

Bài hát: {title}
Lời:
{lyrics}

HƯỚNG DẪN CHẤM ĐIỂM:
- Đọc toàn bộ lời → nhận biết tâm trạng chủ đạo (vui, buồn, tức, thư giãn, …)
- Dùng thang VALENCE 0–100 (số nguyên, KHÔNG làm tròn về bội số 10):
    0–15  = cực kỳ buồn bã, tuyệt vọng, đau khổ (VD: "Em ơi anh không thể sống thiếu em")
   16–35  = buồn, tiêu cực, u sầu (VD: bài hát về chia tay, cô đơn)
   36–55  = trung tính / lẫn lộn cảm xúc
   56–75  = tích cực, vui vẻ nhẹ nhàng
   76–100 = rất vui, phấn khích, lạc quan (VD: "Cuộc sống thật tươi đẹp!")
- Dùng thang AROUSAL 0–100:
    0–30  = chậm, êm dịu, thư thái
   31–60  = vừa phải
   61–100 = sôi động, mạnh mẽ, dữ dội
- VALENCE và AROUSAL ĐỘC LẬP (bài buồn có thể sôi động, bài vui có thể chậm).
- Hãy dùng mọi giá trị trong khoảng, ví dụ: 23, 41, 67, 82, … KHÔNG chỉ 20, 40, 60, 80.

Bước 1 – Mô tả ngắn tâm trạng (1-2 câu):
Bước 2 – Cho điểm:

Trả về JSON DUY NHẤT (không giải thích thêm sau JSON):
{{"reasoning": "...(1-2 câu mô tả tâm trạng)...", "valence": <0-100 int>, "arousal": <0-100 int>}}"""

# Prompt cho model C (Gemini hoặc gemma2) — tiếng Việt, finer scale
DECOUPLED_PROMPT = """Bạn là chuyên gia phân tích cảm xúc âm nhạc Việt Nam.
Đọc kỹ lời bài hát dưới đây và đánh giá cảm xúc CHỦ ĐẠO trong lời (không phải giai điệu).

Bài hát: {title}
Lời:
{lyrics}

Thang điểm VALENCE 0–100 (số nguyên, dùng mọi giá trị, KHÔNG làm tròn về bội số 10):
  0–15  = cực kỳ đau khổ, tuyệt vọng
  16–35 = buồn, cô đơn, tiếc nuối
  36–55 = lẫn lộn / trung tính / bittersweet
  56–75 = tích cực, vui nhẹ, hy vọng
  76–100= rất vui, phấn khởi, hạnh phúc

Thang AROUSAL 0–100 (cường độ năng lượng — ĐỘC LẬP với valence):
  0–30  = chậm, nhẹ nhàng, êm dịu
  31–60 = vừa phải
  61–100= sôi động, mạnh mẽ, cuồng nhiệt

Ví dụ neo: "Khóc Cùng Em" (chia tay đau lòng)→valence≈12; "Nơi Này Có Anh" (tình yêu hạnh phúc)→valence≈78

Chỉ trả về JSON (không giải thích thêm):
{{"valence": <0-100 int>, "arousal": <0-100 int>, "reasoning": "mô tả tâm trạng 1 câu"}}"""


def call_gemini(prompt, timeout=30):
    """Gọi Gemini API (google-genai SDK mới)."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types
        import re
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=512,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        text = resp.text.strip()
        # strip markdown code fences
        text = re.sub(r'```[a-z]*\n?', '', text).strip('`').strip()
        matches = list(re.finditer(r'\{[\s\S]*?\}', text))
        if not matches:
            return None
        d = json.loads(matches[-1].group())
        v = float(d.get("valence", 50))
        a = float(d.get("arousal", 50))
        if v > 1.5:
            v /= 100.0
            a /= 100.0
        return {"valence": round(v, 4), "arousal": round(a, 4),
                "reasoning": d.get("reasoning", "")}
    except Exception:
        if os.environ.get("DEBUG_GEMINI"):
            import traceback; traceback.print_exc()
        return None


def call_ollama(model, prompt, timeout=90):
    try:
        # /no_think disables Qwen3 reasoning chain (saves tokens, avoids timeout)
        full_prompt = "/no_think\n" + prompt if "qwen3" in model else prompt
        r = requests.post(OLLAMA, json={
            "model": model, "prompt": full_prompt, "stream": False,
            "options": {"temperature": 0.1, "num_predict": 512}
        }, timeout=timeout)
        text = r.json().get("response", "")
        # Strip thinking blocks if present, then find last JSON object
        import re
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        matches = list(re.finditer(r'\{[^{}]+\}', text, re.DOTALL))
        if not matches:
            return None
        m = matches[-1]  # use last JSON found (after any reasoning text)
        d = json.loads(m.group())
        v = d.get("valence")
        a = d.get("arousal")
        if v is None or a is None:
            return None
        # normalise to 0-1
        if float(v) > 1.5:  # 0-100 scale
            v = float(v) / 100.0
            a = float(a) / 100.0
        return {"valence": round(float(v), 4), "arousal": round(float(a), 4),
                "reasoning": d.get("reasoning", "")}
    except Exception as e:
        return None


def sample_songs():
    """50 bài đại diện: 10 happy-editorial, 10 stuck-at-0.20-in-happy, 10 sad-clear,
    10 high-v4-valence, 10 random."""
    v4 = json.load(open("data/emotion_labels_v4.json"))
    df = pd.read_csv("data/vietnamese_music_processed_full.csv",
                     usecols=["track_id","track_name","primary_artist","plain_lyrics"])
    df["track_id"] = df["track_id"].astype(str)
    gt = json.load(open("var/runtime/backtest/ground_truth/color_editorial_gt_v1.json"))

    v4_map = {tid: float(v.get("valence", 0.5)) for tid, v in v4.items()}
    df["llm_v"] = df["track_id"].map(v4_map)
    df = df[df["plain_lyrics"].notna() & (df["plain_lyrics"].str.len() > 100)]

    colors_data = gt["colors"]
    happy_idxs = set()
    for ci in colors_data.values():
        if ci.get("target_mood") == "happy":
            happy_idxs.update(ci.get("relevant", []))

    df_happy   = df[df.index.isin(happy_idxs)]
    df_unhappy = df[~df.index.isin(happy_idxs)]

    rng = random.Random(42)

    # Group A: happy-editorial with high v4-V (LLM agrees they're happy)
    g_happy_high = df_happy[df_happy["llm_v"] >= 0.70].sample(min(10, len(df_happy[df_happy["llm_v"]>=0.70])), random_state=42)
    # Group B: happy-editorial but stuck at V=0.20 (LLM disagrees)
    g_happy_stuck = df_happy[df_happy["llm_v"] == 0.20].sample(min(10, len(df_happy[df_happy["llm_v"]==0.20])), random_state=42)
    # Group C: non-happy editorial with V=0.00 (clear sad/angry)
    g_sad_clear = df_unhappy[df_unhappy["llm_v"] <= 0.05].sample(min(10, len(df_unhappy[df_unhappy["llm_v"]<=0.05])), random_state=42)
    # Group D: high v4-V songs overall (LLM confident happy)
    g_high_v = df[df["llm_v"] >= 0.80].sample(min(10, len(df[df["llm_v"]>=0.80])), random_state=42)
    # Group E: random
    g_random = df.sample(min(10, len(df)), random_state=99)

    groups = {
        "A_happy_editorial_high_V": g_happy_high,
        "B_happy_editorial_stuck_020": g_happy_stuck,
        "C_sad_clear": g_sad_clear,
        "D_high_v4_valence": g_high_v,
        "E_random": g_random,
    }

    songs = []
    for gname, gdf in groups.items():
        for _, row in gdf.iterrows():
            lyrics = str(row["plain_lyrics"])[:1200]
            songs.append({
                "group": gname,
                "track_id": row["track_id"],
                "title": row["track_name"],
                "artist": row["primary_artist"],
                "lyrics": lyrics,
                "v4_valence": float(row["llm_v"]),
            })
    return songs


def run(skip_c=False):
    songs = sample_songs()
    print(f"Sampled {len(songs)} songs across {len(set(s['group'] for s in songs))} groups\n")

    # Chọn model C: Gemini (ưu tiên) → gemma2:2b (fallback)
    use_gemini = False
    model_c_available = False
    model_c_label = "none"
    if not skip_c:
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if gemini_key:
            try:
                import google.generativeai as genai
                result = call_gemini(DECOUPLED_PROMPT.format(title="test", lyrics="Vui vẻ hạnh phúc"))
                if result:
                    use_gemini = True
                    model_c_available = True
                    model_c_label = GEMINI_MODEL
                    print(f"✓ Gemini ({GEMINI_MODEL}) via API — decoupled model C\n")
                else:
                    print("✗ Gemini key có nhưng call thất bại — thử gemma2 fallback\n")
            except Exception as e:
                print(f"✗ Gemini error: {e} — thử gemma2 fallback\n")
        if not use_gemini:
            try:
                r = requests.post(OLLAMA, json={"model": MODEL_C_OLLAMA, "prompt": "hi",
                                                "stream": False}, timeout=10)
                if r.status_code == 200:
                    model_c_available = True
                    model_c_label = MODEL_C_OLLAMA
                    print(f"✓ {MODEL_C_OLLAMA} (Ollama fallback) — model C\n")
            except:
                print("✗ Không có model C — chạy 2-way (A vs B)\n")

    results = []
    for i, song in enumerate(songs):
        title = song["title"]
        lyrics = song["lyrics"]
        sys.stdout.write(f"\r[{i+1}/{len(songs)}] {title[:40]:<40}")
        sys.stdout.flush()

        res = {"song": song}

        # A: old prompt, Qwen3
        prompt_a = OLD_PROMPT.format(title=title, lyrics=lyrics[:1500])
        res["A_old_qwen3"] = call_ollama(MODEL_A, prompt_a)

        # B: new prompt, Qwen3
        prompt_b = NEW_PROMPT.format(title=title, lyrics=lyrics[:1200])
        res["B_new_qwen3"] = call_ollama(MODEL_B, prompt_b)

        # C: decoupled model (Gemini hoặc gemma2 fallback)
        if model_c_available:
            prompt_c = DECOUPLED_PROMPT.format(title=title, lyrics=lyrics[:1200])
            if use_gemini:
                res["C_decoupled"] = call_gemini(prompt_c)
            else:
                res["C_decoupled"] = call_ollama(MODEL_C_OLLAMA, prompt_c, timeout=60)

        results.append(res)

    print("\n\nDone. Analysing...\n")

    # Analysis
    variants = ["A_old_qwen3", "B_new_qwen3"]
    if model_c_available:
        variants.append("C_decoupled")

    report = {
        "n_songs": len(songs),
        "model_c": model_c_label,
        "model_c_available": model_c_available,
        "groups": {}, "variants": {},
    }

    # Per-variant stats
    for var in variants:
        vals = [r[var]["valence"] for r in results if r.get(var)]
        if not vals:
            continue
        rounded = [round(v * 10) / 10 for v in vals]
        cnt = Counter(rounded)
        dominant_pct = max(cnt.values()) / len(vals)
        n_unique = len(cnt)
        report["variants"][var] = {
            "n_scored": len(vals),
            "mean": round(float(np.mean(vals)), 3),
            "median": round(float(np.median(vals)), 3),
            "std": round(float(np.std(vals)), 3),
            "dominant_value": float(max(cnt, key=cnt.get)),
            "dominant_pct": round(dominant_pct, 3),
            "n_unique_rounded_01": n_unique,
            "top_values": [{"v": float(v), "n": int(c), "pct": round(c/len(vals),3)}
                           for v, c in sorted(cnt.items(), key=lambda x:-x[1])[:6]],
        }

    # Separability: groups A (happy_high + high_v) vs C (sad_clear)
    for var in variants:
        happy_scores = [r[var]["valence"] for r in results
                       if r.get(var) and r["song"]["group"] in
                       ("A_happy_editorial_high_V", "D_high_v4_valence")]
        sad_scores   = [r[var]["valence"] for r in results
                       if r.get(var) and r["song"]["group"] == "C_sad_clear"]
        if happy_scores and sad_scores and len(happy_scores) > 2 and len(sad_scores) > 2:
            u, p = stats.mannwhitneyu(happy_scores, sad_scores, alternative="greater")
            auc = u / (len(happy_scores) * len(sad_scores))
            report["variants"][var]["separability_happy_vs_sad"] = {
                "n_happy": len(happy_scores), "n_sad": len(sad_scores),
                "happy_mean": round(float(np.mean(happy_scores)), 3),
                "sad_mean":   round(float(np.mean(sad_scores)), 3),
                "auc": round(float(auc), 3), "p": round(float(p), 4),
                "separable": bool(auc > 0.70 and p < 0.05),
            }

        # Group B (happy-editorial stuck at 0.20): how many now move?
        stuck_scores = [r[var]["valence"] for r in results
                       if r.get(var) and r["song"]["group"] == "B_happy_editorial_stuck_020"]
        if stuck_scores:
            moved = sum(1 for v in stuck_scores if v > 0.40)
            report["variants"][var]["stuck_020_moved_above_040"] = {
                "n": len(stuck_scores), "moved": moved,
                "pct_moved": round(moved/len(stuck_scores), 3),
                "mean": round(float(np.mean(stuck_scores)), 3),
            }

    # Print summary
    print("=" * 64)
    print("SPOT-CHECK C1: OLD vs NEW PROMPT")
    print("=" * 64)

    for var in variants:
        v = report["variants"].get(var, {})
        if not v:
            continue
        print(f"\n[{var}]  n={v['n_scored']}  mean={v['mean']}  std={v['std']}  "
              f"dominant={v['dominant_value']:.1f}({v['dominant_pct']*100:.0f}%)  "
              f"unique={v['n_unique_rounded_01']}")
        if "separability_happy_vs_sad" in v:
            s = v["separability_happy_vs_sad"]
            sep = "✓ SEPARABLE" if s["separable"] else "✗ NOT SEPARABLE"
            print(f"  Separability: happy_mean={s['happy_mean']}  sad_mean={s['sad_mean']}  "
                  f"AUC={s['auc']}  p={s['p']}  → {sep}")
        if "stuck_020_moved_above_040" in v:
            m = v["stuck_020_moved_above_040"]
            print(f"  Stuck-020 songs: {m['moved']}/{m['n']} moved above 0.40 → "
                  f"mean now {m['mean']}")

    # Verdict
    a_sep = report["variants"].get("A_old_qwen3", {}).get("separability_happy_vs_sad", {})
    b_sep = report["variants"].get("B_new_qwen3", {}).get("separability_happy_vs_sad", {})
    a_ok = a_sep.get("separable", False)
    b_ok = b_sep.get("separable", False)

    print("\n" + "=" * 64)
    if not a_ok and b_ok:
        verdict = "NEW PROMPT WINS — upgrade relabeling"
        action = "Chạy relabel_llm với new prompt trên toàn catalog"
    elif a_ok and b_ok:
        verdict = "BOTH OK — new prompt gives finer scale (preferred)"
        action = "Chạy relabel_llm với new prompt (finer scale = better matching)"
    elif not a_ok and not b_ok:
        verdict = "NEITHER SEPARATES — prompt không đủ, cần thêm few-shot hoặc model mạnh hơn"
        action = "Thử gemma2 hoặc cải thiện thêm few-shot anchor"
    else:
        verdict = "OLD OK, NEW WORSE — giữ nguyên, inspect"
        action = "Debug new prompt, có thể coT confuses model"
    print(f"VERDICT: {verdict}")
    print(f"ACTION: {action}")
    print("=" * 64)

    report["VERDICT"] = verdict
    report["ACTION"] = action
    report["raw"] = [
        {"group": r["song"]["group"], "title": r["song"]["title"],
         "v4_old": r["song"]["v4_valence"],
         "A": r["A_old_qwen3"]["valence"] if r.get("A_old_qwen3") else None,
         "B": r["B_new_qwen3"]["valence"] if r.get("B_new_qwen3") else None,
         "C": r["C_decoupled"]["valence"] if r.get("C_decoupled") else None,
         "B_reasoning": (r["B_new_qwen3"] or {}).get("reasoning", ""),
        } for r in results
    ]

    out = f"{OUT_DIR}/spotcheck_c1.json"
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nsaved → {out}")
    return report


if __name__ == "__main__":
    skip_c = "--skip-c" in sys.argv
    run(skip_c=skip_c)
