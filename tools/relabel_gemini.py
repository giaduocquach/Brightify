"""C2 — Relabel valence toàn catalog bằng Gemini 2.5-flash.

Giữ nguyên AROUSAL từ v4 (MERT-probe, tin cậy).
Chỉ thay VALENCE bằng Gemini (khắc phục Qwen3 coarse-10pt + 47% stuck-020).

Output: data/emotion_labels_v5.json  (same schema as v4)
Config key: RELABELED_EMOTIONS_FILE → set to v5 sau khi hoàn tất.

Chạy: python -m tools.relabel_gemini
GEMINI_API_KEY phải có trong .env hoặc environment.

Resumable: chạy lại sẽ bỏ qua bài đã có src='gemini_v5'.
"""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as cfg

# ── Config ────────────────────────────────────────────────────────────────────
GEMINI_MODEL   = "models/gemini-2.5-flash"
MAX_WORKERS    = 5       # concurrent requests — safe cho free tier 15 RPM
CHECKPOINT_N   = 100     # save every N songs
OUT_FILE       = "data/emotion_labels_v5.json"
MIN_LYRICS_LEN = 30

# ── Prompt (0-100 scale, CoT, few-shot anchor, native Việt) ──────────────────
PROMPT = """Bạn là chuyên gia phân tích cảm xúc âm nhạc Việt Nam.
Đọc kỹ lời bài hát và đánh giá cảm xúc CHỦ ĐẠO trong lời (không phải giai điệu hay tempo).

Bài hát: {title}
Lời:
{lyrics}

Thang VALENCE 0–100 (số nguyên, dùng mọi giá trị, KHÔNG làm tròn về bội số 10):
  0–15  = cực kỳ đau khổ, tuyệt vọng, bi thương
  16–35 = buồn, cô đơn, tiếc nuối, chia tay
  36–55 = bittersweet, trung tính, lẫn lộn cảm xúc
  56–75 = tích cực, vui nhẹ, hy vọng, lãng mạn
  76–100= rất vui, phấn khởi, hạnh phúc, hào hứng

Neo ví dụ: "Khóc Cùng Em"→12  "Tình Đắng Như Ly Cà Phê"→22  "Nơi Này Có Anh"→78  "Chơi Như Tụi Mỹ"→88

Thang AROUSAL 0–100 (cường độ năng lượng — ĐỘC LẬP hoàn toàn với valence):
  0–30  = chậm, nhẹ nhàng, ballad tĩnh
  31–60 = vừa phải
  61–100= sôi động, mạnh mẽ, cuồng nhiệt

Chỉ trả về JSON (không giải thích thêm):
{{"valence": <int 0-100>, "arousal": <int 0-100>, "reasoning": "<1 câu mô tả tâm trạng lời>"}}"""


def _gemini_client():
    from google import genai
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def call_gemini_valence(client, title: str, lyrics: str) -> dict | None:
    """Gọi Gemini, trả về {"valence": 0-1, "arousal": 0-1, "reasoning": str}."""
    import re
    from google.genai import types

    prompt = PROMPT.format(title=title or "", lyrics=(lyrics or "")[:1400])
    try:
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
        text = re.sub(r"```[a-z]*\n?", "", text).strip("`").strip()
        matches = list(re.finditer(r"\{[\s\S]*?\}", text))
        if not matches:
            return None
        d = json.loads(matches[-1].group())
        v = float(d.get("valence", 50))
        a = float(d.get("arousal", 50))
        if v > 1.5:   # 0-100 scale → 0-1
            v /= 100.0
            a /= 100.0
        return {
            "valence": round(max(0.0, min(1.0, v)), 4),
            "arousal": round(max(0.0, min(1.0, a)), 4),
            "reasoning": str(d.get("reasoning", ""))[:200],
        }
    except Exception:
        return None


def run():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: GEMINI_API_KEY không có trong .env hoặc environment")
        sys.exit(1)

    # Load data
    df = pd.read_csv(cfg.PROCESSED_FILE)
    if "track_id" not in df.columns:
        df["track_id"] = range(len(df))
    lyr_col = "lyrics_cleaned" if "lyrics_cleaned" in df.columns else "plain_lyrics"

    # Load v4 (arousal source) + v5 checkpoint
    v4 = json.load(open(cfg.RELABELED_EMOTIONS_FILE))
    out: dict = {}
    if os.path.exists(OUT_FILE):
        out = json.load(open(OUT_FILE))
        done = sum(1 for v in out.values() if v.get("src") == "gemini_v5")
        print(f"[v5] resume: {len(out)} entries, {done} already gemini_v5")

    # Load emotion fusion for label derivation
    from core.emotion_analysis import get_emotion_analyzer
    _, _, fusion = get_emotion_analyzer()

    # Build todo list
    todos = []
    for row in df.itertuples():
        tid = str(row.track_id)
        if out.get(tid, {}).get("src") == "gemini_v5":
            continue  # already done
        lyr = str(getattr(row, lyr_col, "") or "")
        todos.append({
            "tid": tid,
            "title": str(getattr(row, "track_name", "") or ""),
            "lyrics": lyr,
            "has_lyrics": len(lyr) > MIN_LYRICS_LEN,
        })

    print(f"[v5] {len(todos)} bài cần label (tổng catalog {len(df)})")
    print(f"[v5] model={GEMINI_MODEL} workers={MAX_WORKERS}")
    print()

    client = _gemini_client()
    t0 = time.time()
    done_count = sum(1 for v in out.values() if v.get("src") == "gemini_v5")
    error_count = 0
    lock_checkpoint = __import__("threading").Lock()

    def label_one(item):
        tid, title, lyrics, has_lyrics = (
            item["tid"], item["title"], item["lyrics"], item["has_lyrics"])
        v4e = v4.get(tid, {})

        if not has_lyrics:
            # No lyrics → keep v4 entry, mark source
            return tid, {**v4e, "src": "v4_no_lyrics"}

        res = call_gemini_valence(client, title, lyrics)
        if res is None:
            # Gemini failed → keep v4 entry
            return tid, {**v4e, "src": "v4_fallback"}

        # Combine: valence from Gemini, arousal from v4 (MERT-based)
        gem_v = res["valence"]
        v4_a  = float(v4e.get("arousal", 0.5))
        label = fusion.get_emotion_label(gem_v, v4_a)
        return tid, {
            "valence":   gem_v,
            "arousal":   v4_a,
            "label":     label,
            "reasoning": res["reasoning"],
            "src":       "gemini_v5",
        }

    processed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(label_one, item): item for item in todos}
        for fut in as_completed(futures):
            try:
                tid, entry = fut.result()
                out[tid] = entry
                if entry["src"] == "gemini_v5":
                    done_count += 1
                else:
                    error_count += 1
            except Exception as e:
                item = futures[fut]
                v4e = v4.get(item["tid"], {})
                out[item["tid"]] = {**v4e, "src": "v4_fallback"}
                error_count += 1

            processed += 1
            if processed % CHECKPOINT_N == 0:
                with lock_checkpoint:
                    json.dump(out, open(OUT_FILE, "w"), ensure_ascii=False, indent=None)
                elapsed = time.time() - t0
                rate = elapsed / processed
                eta  = rate * (len(todos) - processed) / 60
                pct  = processed / len(todos) * 100
                print(f"  [{processed}/{len(todos)} {pct:.0f}%]  "
                      f"gemini={done_count}  fallback={error_count}  "
                      f"ETA {eta:.0f}min  ({rate:.1f}s/song)")

    # Final save
    json.dump(out, open(OUT_FILE, "w"), ensure_ascii=False, indent=None)

    elapsed_min = (time.time() - t0) / 60
    print(f"\n[v5] DONE — {len(out)} entries → {OUT_FILE}  ({elapsed_min:.0f}min)")
    print(f"  gemini_v5={done_count}  v4_fallback={error_count}")

    # Distribution
    import collections
    labels = [v.get("label") for v in out.values()]
    dist = collections.Counter(labels)
    print("\n=== v5 label distribution ===")
    for lbl, cnt in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {lbl:15} {cnt:5}  ({cnt/len(labels)*100:.1f}%)")

    # Valence distribution vs v4
    import numpy as np
    v5_vals = np.array([v["valence"] for v in out.values() if v.get("src") == "gemini_v5"])
    v4_vals = np.array([float(v.get("valence", 0.5)) for v in v4.values()])
    print(f"\n=== Valence: v4 → v5 ===")
    print(f"  v4: mean={v4_vals.mean():.3f}  median={np.median(v4_vals):.3f}  std={v4_vals.std():.3f}")
    print(f"  v5: mean={v5_vals.mean():.3f}  median={np.median(v5_vals):.3f}  std={v5_vals.std():.3f}")
    print(f"  v4 stuck-at-0.20: {(v4_vals==0.2).mean()*100:.1f}%")
    from collections import Counter as C2
    v5_dom = C2(round(v,1) for v in v5_vals).most_common(3)
    print(f"  v5 top-3 values: {v5_dom}")

    print(f"\nNext: update config.py RELABELED_EMOTIONS_FILE = '{OUT_FILE}'")
    print("Then: python -m tools.run_f1_validation 10")


if __name__ == "__main__":
    run()
