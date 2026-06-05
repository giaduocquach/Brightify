# Recommend-by-Colour — Bản thực thi (V16-EXEC)

Date: 2026-06-02. Nguồn gốc: `docs/COLOR_FEATURE_DEEPDIVE_AND_UPGRADE_V16.md` (deep research, có nguồn).
Đây là bản **thực thi**: phạm vi đã chốt, thứ tự đã chốt, mỗi item có cổng kiểm chứng.

## Phạm vi (đã chốt với chủ dự án)
- **8 item:** E1, E2, E3, E4, E5, E6, E7, E8.
- **BỎ E9** (Vietnamese cultural overlay) và **BỎ E10** (per-user colour↔mood learning).
- **Nguyên tắc nền:** màu↔cảm xúc **thuần nghiên cứu quốc tế** (ICEAS/Jonauskaite 2020, Whiteford
  2018, Palmer 2013). Không yếu tố VN trong đường ranking.
  - Lưu ý kỹ thuật: đường ranking forward (`hsl_to_va`, `color_to_emotion_probs`) **đã** thuần
    global. `cultural_adjustments` trong `advanced_color_mapping.py` chỉ tác động `emotion_to_color`
    (chiều bài→màu, KHÔNG dùng khi recommend-by-color). Khi sinh nhãn/palette dùng
    `use_vietnamese_adaptation=False` để chắc chắn không nhánh VN nào len vào.

## Cổng kiểm chứng (áp cho mọi thay đổi đụng ranking)
- **L1 bridge** — `python -m tools.color_bridge_metrics` (khớp norm con người ICEAS).
- **L2 retrieval** — `python -m tools.color_retrieval_metrics` (NDCG@10/P@10 vs editorial + LLM-judge).
- **L3 discriminant** — `python -m tools.color_discriminant_metrics` (Cohen's d màu đối nghịch).
- UI: WCAG 1.4.1 (nhãn chữ + trạng thái chọn phi-màu) + touch ≥44px là yêu cầu cứng.

---

## Bộ 12 màu chốt (ICEAS canonical) — dùng cho E1+E3

12 màu cơ bản Berlin&Kay + turquoise = đúng 12 anchor engine đã fit dữ liệu con người lên.
**Bỏ "Lam thẫm" (navy)** — engine không có anchor; **thêm "Nâu"**. Hex = anchor key của engine.
V-A và cảm xúc dưới đây sinh trực tiếp từ engine (`use_vietnamese_adaptation=False`):

| Tên | Hex | V | A | Nhãn (top-emotion engine) |
|-----|-----|---|---|---------------------------|
| Đỏ | `#FF0000` | 0.61 | 0.86 | Đam mê · Mãnh liệt |
| Cam | `#FF8000` | 0.62 | 0.84 | Vui tươi · Năng động |
| Vàng | `#FFFF00` | 0.66 | 0.77 | Vui vẻ · Lạc quan |
| Hồng | `#FFC0CB` | 0.76 | 0.76 | Ngọt ngào · Phấn khích |
| Xanh lá | `#008000` | 0.65 | 0.65 | Tươi mát · Cân bằng |
| Ngọc | `#40E0D0` | 0.67 | 0.38 | Thư thái · Tươi mát |
| Xanh dương | `#0000FF` | 0.75 | 0.59 | Phấn chấn · Sâu lắng |
| Tím | `#800080` | 0.56 | 0.84 | Mãnh liệt · Sâu lắng |
| Nâu | `#8B4513` | 0.41 | 0.81 | Trầm mặc · Bất an |
| Trắng | `#FFFFFF` | 0.61 | 0.15 | Thanh thản · Tinh khôi |
| Xám | `#808080` | 0.41 | 0.32 | U hoài · Trầm lắng |
| Đen | `#000000` | 0.20 | 0.50 | U tối · Nặng nề |

**Vì sao 12 màu:** Berlin&Kay (phạm trù màu phổ quát) + khớp khít anchor engine (UI=mô hình); Hick's
Law chi phí log + màu nhận diện tiền-chú-ý + choice-overload mong manh (Scheibehenne 2010) → 10–15 ổn.
**Vì sao bộ này:** phủ đủ 4 góc V-A nhờ cả độ sáng/bão hòa (Manchester Colour Wheel — sắc độ mang
valence trái ngược): vui-sôi (Đỏ/Cam/Vàng), dễ chịu (Ngọc/Trắng/Xanh lá), trầm-buồn (Xám/Nâu/Đen).

**Chọn tối đa 3 màu** (giữ nguyên): 1=một tâm trạng, 2–3=một blend/hành trình đọc được; ≥4 blend bị
"rửa" về trung tính và round-robin chia quá mỏng. **Cách chọn:** một trang, multi-select đồng thời
(không wizard — chọn màu là việc so sánh); ô đã chọn có viền+tích (phi-màu, WCAG); mood pad V-A (E4)
bổ sung; hex giấu sau "Nâng cao".

---

## Thứ tự thực thi — 3 đợt

### 🟢 ĐỢT 1 — Đúng & trung thực (nền móng, rủi ro thấp)
> Làm trọn gói; 3 item phụ thuộc nhau.

- **E1 — Đồng bộ nhãn UI ↔ engine.** Sinh nhãn cảm xúc + `data-va` 12 màu từ `hsl_to_va` +
  `color_to_emotion_probs`. Sửa nhãn sai (blue "u sầu" → "Phấn chấn · Sâu lắng"). *Cổng:* không cần
  backtest; phải khớp số engine + WCAG nhãn.
- **E3 — Palette 12 màu ICEAS canonical.** Thay 12 swatch (bỏ navy, thêm nâu, hex anchor, phủ 4 góc).
  *Cổng:* L1 + L3.
- **E2 — Bỏ tín hiệu trùng + weights→config + tune.** Thay `emo_s` (≈`va_s`) bằng nguồn cảm xúc độc
  lập (nhãn v4/lyric-emotion); dời `0.40/0.30/0.30, σ=0.20, +0.12/−0.08` vào `config.py`; tune trên
  L2-LLM (paired bootstrap). *Cổng:* L1/L2/L3 (NDCG không giảm).

### 🟡 ĐỢT 2 — Tin tưởng & khác biệt
- **E6 — Chip "Vì sao bài này".** Trả `va_s/emo_s/lyr_s` (đã có trong `_color_score`) ra UI dưới dạng
  lời giải thích. *Cổng:* văn bản phản ánh đúng tín hiệu.
- **E4 — Mood pad Valence-Arousal.** Input 2D cạnh lưới, keyboard-operable, 4 góc có nhãn. *Cổng:* L2
  theo điểm V-A + accessibility.
- **E7 — Thẻ "Âm nhạc của bạn qua màu sắc".** Artifact chia sẻ (palette + top matches). PIL set
  `MAX_IMAGE_PIXELS`. *Cổng:* không cần backtest (tăng trưởng).

### 🔴 ĐỢT 3 — Chiều sâu (nặng nhất)
- **E8 — Núm "đào sâu"/novelty.** Dial deep-cuts↔hit; điều khiển popularity-debias (đã đo gini).
  *Cổng:* L2 + gini/coverage.
- **E5 — Multi-màu blend/journey.** Thay round-robin bằng 2 chế độ:
  - **Blend:** gộp V-A các màu thành tâm trạng trung bình → tìm bài khớp.
  - **Journey:** coi màu là mốc theo thứ tự, nội suy V-A dọc playlist (Iso-Principle, Altshuler 1948;
    Davis & Thaut 1989) → đầu trầm, cuối tươi, giữa chuyển mượt.
  Thêm `mode: blend|journey` ở `api/recommend.py`. *Cổng:* cần GT journey mới (V-A bài đầu≈màu đầu,
  bài cuối≈màu cuối, đơn điệu ở giữa) + L2. **Để cuối** vì sửa thuật toán + tốn công kiểm chứng nhất.

**Lý do thứ tự:** đúng → đáng tin & khác biệt → sâu & độc nhất. Công sức & rủi ro tăng dần; mỗi item
chỉ khởi động khi nền nó dựa vào đã chắc.

---

## File đụng vào (tham chiếu)
- `static/js/ui-pages.js:222-331` — 12 swatch (E1/E3); `:333-342` hex input (E4 disclosure).
- `core/advanced_color_mapping.py` — `hsl_to_va` (306-342), `color_to_emotion_probs` (266-290),
  `_ICEAS_EMOTION` (238-251).
- `core/recommendation_engine.py:581-596` — `_color_score` (E2); `:619-644` round-robin (E5).
- `config.py:174-175` — `WEIGHTS_COLOR_QUERY_*` (E2).
- `api/recommend.py:66-79` — request schema (E4/E5); `:112-145` endpoint (E6).
- Backtest: `tools/color_{bridge,retrieval,discriminant}_metrics.py`;
  `tools/backtest_v2/ground_truth/color_*.py`; `docs/PLAN_COLOR_BACKTEST_V15.md`.

## Trạng thái
- [x] **ĐỢT 1 XONG (2026-06-02):**
  - **E1+E3** — 12 swatch ICEAS canonical (bỏ navy, thêm Nâu); nhãn + data-va sinh từ engine;
    sửa blue "U sầu"→"Phấn chấn·Sâu lắng". WCAG selected-state (.cev2-check + aria-pressed).
    Đồng bộ palette presets. (`ui-pages.js`, `ai-discovery.js`, `styles.css`)
  - **E2** — (a) weights→`config.COLOR_SCORE_WEIGHTS/VA_SIGMA/LABEL_BOOST/CROSS_MOOD_PENALTY`;
    (b) emo_s đổi từ màu-album-art (nhiễu, corr w/ va_s=0.06) sang content `fused_emotion`
    one-hot (`recommendation_engine.py` `_song_emotion_content_vec`); (c) tune
    (`tools/color_weight_opt.py`): **0.35/0.55/0.10** → L2-LLM NDCG 0.498→0.654 (Δ+0.155,
    CI[+0.024,…]); L3 4/4 separated, d mạnh hơn; L1 không đổi.
- [x] **ĐỢT 2 XONG (2026-06-02):**
  - **E6** — `_build_color_why` trả breakdown tín hiệu thật per-song (single+multi),
    API passthrough, chip `.song-row-why` + CSS. Verified HTTP.
  - **E4** — ❌ **ĐÃ GỠ (2026-06-02)**: mood pad V-A trùng lặp với tab "Hành trình" sẵn có
    (các thẻ `jqm-card` đã chọn tâm trạng theo data-v/data-a). Đã xóa sạch mood pad UI +
    endpoint `/api/recommend/mood` + `recommend_by_va` + `MoodRecommendationRequest` + CSS +
    JS. Giữ lại refactor `_rank_by_color_features` (lõi dùng chung cho color/blend/journey).
  - **E7** — ❌ **ĐÃ GỠ (2026-06-03)** theo yêu cầu chủ dự án: bỏ thẻ chia sẻ (nút + canvas).
- [x] **ĐỢT 3 XONG (2026-06-02):**
  - **E8** — novelty/đào sâu dial. Proxy popularity = artist-freq (không có play-count),
    `_novelty_prior`+`_apply_novelty`; `novelty∈[0,1]` 0.5=neutral (backward-compat, gates
    không đổi). Config `COLOR_NOVELTY_*`; API `novelty`; slider UI. Verified monotonic:
    artist-freq top8 = 66.5 (0.0) → 22.5 (0.5) → 1.6 (1.0).
  - **E5** — multi-màu: **chỉ còn BLEND** (gộp 2–3 màu thành 1 mood trung bình), là mặc định &
    duy nhất. ~~journey~~ ❌ gỡ (trùng tab Hành trình riêng); ~~interleave + UI toggle + tham số
    `mode`~~ ❌ **gỡ (2026-06-03)** theo yêu cầu (blend là mặc định nên không cần chọn). Cũng gỡ
    `tools/color_journey_metrics.py`. Engine: multi luôn collapse→blend→single-query path.
  - **Bỏ ô nhập hex (2026-06-03)** — user thường không biết mã màu chính xác; chỉ còn 12 ô + presets.

**TẤT CẢ 8 ITEM (E1-E8) HOÀN TẤT.** (E9 VN-overlay + E10 per-user learning đã loại theo yêu cầu.)
</content>
</invoke>
