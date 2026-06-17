# V23 — Gộp "Hành trình" vào Recommend-by-Colour (Iso-Principle journey)

> 2026-06-05. Plan thực thi + backtest đầy đủ. Cơ sở: research V23 (2 luồng —
> Iso-Principle science + UX consolidation), docs deep-research lưu ở lịch sử.
> Nguyên tắc: tách RETRIEVAL (chọn bài nào — giữ RRF union) khỏi SEQUENCING
> (thứ tự phát — MỚI, Iso-Principle). Backtest chỉ validate thuật toán (claim A);
> trải nghiệm (claim B) để user-test sau.

## Quyết định cốt lõi
- **1 màu** = mood tĩnh coherent (giữ nguyên).
- **2–3 màu** = JOURNEY: đi mượt qua các waypoint V-A theo thứ tự chọn (Iso-Principle:
  khớp màu đầu → dịch dần tới màu cuối). THAY cho RRF-interleaved hiện tại (gây whiplash).
- Bỏ tab "Hành trình" riêng (gộp vào màu — progressive disclosure). *(cần xác nhận)*

## Thuật toán sequencing (cốt lõi)
```
retrieval (giữ): RRF union top-K — chọn bài tốt cho CẢ các waypoint
sequencing (mới):
  1. waypoints P1..Pn = V-A của các màu (theo thứ tự user chọn)
  2. path = đường gấp khúc P1→P2→...→Pn trong không gian V-A
  3. mỗi bài top-K → chiếu V-A lên path → vị trí t ∈ [0,1]
  4. sort theo t  → playlist đi mượt từ P1 đến Pn
  5. Iso: bài[0] khớp P1, bài[-1] khớp Pn; cho phép dao động cục bộ nhỏ (không ép phẳng)
```

---

## PHASES (mỗi phase gate riêng)

### J1 — Engine sequencing
- `recommendation_engine.py`: tách `_rank_by_color_features`:
  - len==1 → single (giữ).
  - len≥2 → retrieval RRF union (giữ) → **lớp sequencing mới** `_sequence_journey()` sort top-K theo vị trí dọc path.
- Config mới: `COLOR_JOURNEY_ENABLED=True`, `COLOR_JOURNEY_LOCAL_CONTRAST` (cho phép dao động nhỏ).
- "why" giữ attribution theo waypoint gần nhất.

### J2 — Backtest sequencing (CLAIM A, offline, không cần người) ⭐
`tools/color_journey_sequencing.py` — 4 metric + baseline:
| Metric | Định nghĩa | Pass khi |
|---|---|---|
| **adjacent-variation** | Σ‖VA(bài_i)−VA(bài_i+1)‖ | journey ≪ shuffled-union baseline |
| **monotonicity** | Spearman(t_position, sequence_index) | ρ > 0.7 |
| **whiplash count** | số lần đảo chiều biên-độ-lớn (>0.4) | ≈ 0 |
| **endpoints** | dist(bài[0], P1), dist(bài[-1], Pn) | nhỏ |
- **Baseline so sánh: shuffled/interleaved order** trên CÙNG song set → chứng minh journey-order giảm variation thật (falsifiable, KHÔNG tautology).
- Tích hợp vào `run_f1_validation` thành gate **SEQ**.
- Unit tests trong `test/test_color_reco.py` (deterministic).

### J3 — API metadata
- `api/recommend.py`: response thêm `journey: {ordered:true, from_mood, to_mood, waypoints:[{hex,mood,va}]}` cho UI.

### J4 — Frontend (UX grounded)
- `ai-discovery.js` / `ui-pages.js`: khi chọn màu thứ 2 → khung journey: dải gradient A→B + nhãn **"Từ [mood A] → [mood B]"** + mũi tên.
- Mỗi swatch: **tên mood + icon** hiển thị (không chỉ aria-label) — WCAG 1.4.1, hỗ trợ mù màu.
- Deprecate tab "Hành trình" riêng (redirect / xoá). *(xác nhận)*

### J5 — Gate tổng + commit
- `run_f1_validation` (L1/T/ED/L3/NC + SEQ mới) phải giữ nguyên trạng + SEQ pass.
- `test_color_reco.py` pass; smoke 21/21.
- Commit từng phase.

---

## Ranh giới trung thực
- Backtest J2 chứng minh **thuật toán sắp mượt A→B** (claim A) — KHÔNG chứng minh người nghe thích hơn (claim B → user-test, cùng trần con người).
- "Màu A→B = chuyển mood" là thiết kế-có-cơ-sở (Iso d=0.52 + màu→V-A validated ghép lại), chưa đo trực tiếp → nhãn chữ + mũi tên gánh nghĩa, không để màu tự nói.
- Thuần UX/sequencing — không đụng core khoa học → không phá trạng thái "đã hoàn thiện".

## Nguồn
Starcke & von Georgi 2024 (Iso d=0.52) · Heiderscheit&Madson 2015 · Neto 2025 (album arc) · Whiteford 2018 (màu→V-A tĩnh) · Nielsen progressive disclosure · Hick's Law · Moodplay (Andjelkovic 2019) · WCAG 1.4.1 · Emotionify (gradient precedent).
