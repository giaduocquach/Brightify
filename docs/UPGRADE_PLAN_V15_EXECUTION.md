# Brightify — Plan Thực Thi Nâng Cấp V15 (chi tiết)

> Biến đánh giá khoa học trong `FEATURE_RESEARCH_EVALUATION_V15.md` thành **kế hoạch thực thi
> từng bước**: mỗi việc có *mục tiêu · cơ sở (cite) · file/method cụ thể · metric nghiệm thu ·
> công sức (S≤0.5d / M≤2d / L>2d) · demo · rủi ro*.
> **Ngày:** 2026-06-02 · **Trạng thái:** Đề xuất — chờ duyệt.

## 0. Nguyên tắc
- **Backtest-gated:** mọi thay đổi hành vi phải qua `tools/backtest_v2` với CI (bootstrap) — **không tụt số** so baseline.
- **Tách bạch:** refactor/metric KHÔNG trộn với đổi thuật toán trong cùng commit.
- **Demo-first cho bảo vệ:** ưu tiên việc cho ra *case A≠B rõ ràng* + có số liệu.
- Production hiện: nhãn **v4** (valence-lời LLM + arousal-audio MERT), similar dùng lyrics 0.50 + MERT 0.335, crossfade LUFS/Camelot/downbeat đã có data.

---

# PHASE A — Đại tu phương pháp đánh giá (🔴 ưu tiên cao nhất)
*Lý do: con số "quadrant-match 100%" là vòng tròn, hội đồng sẽ bắt. Cần metric chuẩn IR trước khi tinh chỉnh bất cứ gì.*

### A1 — Thay quadrant-match bằng Recall@K / P@K / mAP / MRR (color + image)
- **Cơ sở:** Emo-CLIM báo P@5 + MRR [arXiv:2308.12610]; IR best-practice (Recall/mAP/MRR). quadrant-match dùng GT proxy cùng pipeline V-A → tự nhất quán, không hợp lệ.
- **File:** `tools/backtest_v2/ground_truth/color_va_gt.py` (đã có `color_recall_at_k`), thêm `precision_at_k`, `mrr`, `map_at_k`. Báo cáo ở `tools/backtest_v2/cli.py` (lệnh color backtest).
- **Cách:** giữ GT proxy v4 nhưng **siết θ** để relevant-set ~100-300/màu (không 619); báo Recall@{1,5,10}, P@{5,10}, mAP@10, MRR. Bỏ in "100%".
- **Metric nghiệm thu:** in đủ 4 metric; ghi rõ "proxy GT, not gold standard".
- **Effort:** M · **Demo:** bảng metric thật cho 12 màu.

### A2 — Validate MERT→arousal probe trên MusAV
- **Cơ sở:** MusAV (ISMIR 2022, MTG) — 2092 track, **relative-pairwise** V-A (tin cậy hơn nhãn tuyệt đối). [mtg.github.io/musav-dataset]
- **File:** mới `tools/validate_arousal_musav.py` (tải MusAV audio→MERT→probe; đo **pairwise accuracy** arousal: % cặp probe xếp đúng thứ tự so nhãn người).
- **Cách:** dùng probe Ridge đã có (`tools/mert_arousal_probe.py`); tải MusAV (~vài GB) như DEAM; extract MERT; so cặp.
- **Metric nghiệm thu:** pairwise-accuracy arousal (kỳ vọng ≥0.70 — uy tín cho "arousal từ audio").
- **Effort:** M (cần tải audio) · **Demo:** "probe đúng thứ tự arousal X% trên benchmark độc lập".

### A3 — Beyond-accuracy metrics cho similar-song
- **Cơ sở:** Kaminskas & Bridge TiiS 2017 [10.1145/2926720] — accuracy không đủ. Đang **enforce** diversity (MMR/DPP) nhưng **không đo**.
- **File:** mới `tools/backtest_v2/metrics/beyond_accuracy.py`: `ild()` (intra-list diversity trên embedding), `novelty()` (−log popularity), `serendipity()` (relevant ∧ unexpected vs popularity-baseline), `coverage()` (% catalog từng xuất hiện), `gini_popularity()`. Nối vào `tools/backtest_v2/improve/ablation.py` + report.
- **Metric nghiệm thu:** in 5 metric kèm CI; thiết lập baseline iter_0.
- **Effort:** M · **Demo:** bảng "không chỉ NDCG mà còn đa dạng/mới/coverage".

### A4 — Stratify mọi backtest theo tầng popularity
- **Cơ sở:** GT editorial lệch head (Berenzweig ISMIR 2003); popularity-bias (MDPI 2025).
- **File:** `tools/backtest_v2/` — thêm cột tầng (head/mid/tail theo play_count hoặc proxy) + báo NDCG/Recall theo tầng.
- **Metric nghiệm thu:** bảng metric × 3 tầng; phát hiện gate nào tụt ở tail.
- **Effort:** S-M.

### A5 — Bộ human-rated nhỏ (trần thực sự)
- **Cơ sở:** MuCED (2634 cặp expert-refined) [2507.04758]; XAB triplet là gold-standard (paper 2026).
- **Cách:** (a) ~200 cặp *màu/ảnh → bài* chấm Likert "hợp không"; (b) ~150 *XAB triplet* cho similar ("A giống B hay C hơn"). Tool thu thập đơn giản (CSV + UI nhẹ hoặc Google Form).
- **Metric nghiệm thu:** correlation giữa offline-metric và human-rating → chứng minh proxy GT đáng tin.
- **Effort:** L (cần người chấm — có thể bạn + vài người). *Tùy chọn nếu kịp.*

---

# PHASE B — Sửa logic gợi ý (rẻ, impact cao, demo rõ)

### B1 — Cap per-artist trong similar-song 🔴
- **Cơ sở:** lặp nghệ sĩ = **than phiền #1** (ISMIR 2011; filter-bubble Nature 2024); khớp ghi chú KG-artist-bias.
- **File:** `core/recommendation_engine.py` `recommend_by_song` → `_fast_rank(..., max_per_artist=N)` (param đã tồn tại!). Đặt `MAX_PER_ARTIST_SIMILAR` ở `config.py` (mặc định 2).
- **Cách:** bật cap; backtest NDCG (không tụt) + đo **artist-spread** tăng + ILD tăng.
- **Metric nghiệm thu:** NDCG@10 ≥ baseline (CI), artist-spread@10 tăng rõ.
- **Effort:** S · **Demo:** trước/sau — list giảm lặp nghệ sĩ thấy rõ.

### B2 — Journey: metric đo được + harness demo 🔴
- **Cơ sở:** coherence `coh=1−s²→/σ²` (EPJ 2025, PMC11923031); Iso-Principle (Starcke 2021 RCT, MDPI 18/23/12486).
- **File:** mới `tools/backtest_v2/journey_metrics.py`: `coherence()`, `trajectory_rmse()` (so đường Bézier), `monotonic_progress()`, `step_variance()`, `start_end_fidelity()`. Hàm `generate_emotion_journey` đã có.
- **Cách:** sinh journey A (vd sad→happy), baseline B (shuffle cùng bài), B' (jump-to-target). Đo cả 3.
- **Metric nghiệm thu:** A: coherence cao, RMSE thấp, ~100% monotonic; B/B' fail. Bảng + **V-A trajectory plot**.
- **Effort:** M · **Demo:** 1 biểu đồ V-A 3 đường = vừa eval vừa demo. Reframe "Iso-Principle-guided trajectory".

### B3 — Bản địa hóa màu cho VN
- **Cơ sở:** Jonauskaite 2020 (quốc gia dự báo vượt phổ quát); VN: trắng=tang, đỏ=may, tím=hoài niệm.
- **File:** `core/advanced_color_mapping.py` — thêm lớp override VN cho màu loaded (trắng→valence thấp/tang; đỏ→valence cao/lễ; tím→hoài niệm) áp SAU `hsl_to_va`, có cờ `VN_COLOR_ADJUST`.
- **Cách:** override có chú thích nguồn; đo lại color→emotion accuracy + (nếu có) bộ human VN.
- **Metric nghiệm thu:** màu loaded VN ra cảm xúc đúng văn hóa; demo trắng→buồn (khác Tây).
- **Effort:** M · **Lưu ý:** trước đây bạn chọn "giữ phổ quát" — cân nhắc lại vì hội đồng VN sẽ đánh giá cao điểm bản địa (và publishable).

---

# PHASE C — Feature AI mới (wow + giá trị, dùng model sẵn có)

### C1 — "Vì sao bài này" (explanation layer) 🟢 ROI cao nhất
- **Cơ sở:** transparency=trust (peer-reviewed); **luật DSA 2024** yêu cầu giải thích recommender.
- **File:** `core/recommendation_engine.py` trả về *signal deltas* thật (V-A dist, MERT sim, Camelot, lyric-theme overlap) kèm mỗi bài; `api/` truyền; qwen3 (offline hoặc realtime nhẹ) render 1 câu Việt. Frontend hiện chip.
- **Cách quan trọng:** **số liệu là THẬT** từ engine; LLM chỉ *diễn đạt* (không bịa).
- **Metric nghiệm thu:** mỗi rec có lý do đúng signal; A/B bật-tắt (định tính + nếu có user, trust survey).
- **Effort:** M · **Demo:** bật/tắt explanation — lộ ra fusion đa tín hiệu mà đối thủ không nói được.

### C2 — NL mood search "đúng" (structured) 🟢
- **Cơ sở:** Spotify NL search +4% listen-time nhưng **fail nuance** (lyrics/BPM) [SAGE/reviews].
- **File:** nâng `recommend_by_lyrics_keywords`/search: qwen3 parse text → {V-A target, lyric-keywords, tempo/energy range} → retrieve PhoBERT+MERT+V-A có ràng buộc.
- **Metric nghiệm thu:** chạy đúng prompt Spotify fail ("buồn nhưng muốn nhảy", "nhạc mưa chậm") → ta honor lyric+tempo.
- **Effort:** M-L · **Demo:** side-by-side prompt nuance.

### C3 — Discovery dial (Quen ↔ Phiêu lưu) 🟢
- **Cơ sở:** filter-bubble = pain #1; Spotify thêm "steer" 2025.
- **File:** `config.py` + `recommend_by_song`/similar — slider nới bán kính MERT/V-A + phạt popularity (long-tail VN).
- **Metric nghiệm thu:** slider 0 vs max → mean catalog-distance ↑, mean popularity ↓ (đo được).
- **Effort:** M · **Demo:** 2 list cùng seed, số đo khác rõ.

### C4-C8 (phác thảo — làm sau)
- **C4 Q&A lời** (qwen3+PhoBERT) · **C5 ảnh CLIP-affective** (nâng từ chỉ-màu) · **C6 visualizer cảm xúc** (per-segment V-A→palette) · **C7 auto-DJ journey + giải thích chuyển** (journey+crossfade+qwen3) · **C8 hồ sơ gu chỉnh-được (NL)**.

**LLM concierge:** gộp C1+C2+C3 thành *NL retrieval grounded + hiện lý do + steering* — KHÔNG "DJ persona" chatty (chỗ Spotify bị chê opacity).

---

# PHASE D — Nâng cao (phụ thuộc data, sau bảo vệ)
- **D1** Learned re-ranker (Emo-CLIM/CDCML style) trên top-N màu/ảnh — cần ~vài nghìn nhãn (xây bằng recipe MuCED).
- **D2** Benchmark **MuQ-MuLan vs MERT** cho audio similarity (2 paper 2026 nói MuQ dẫn).
- **D3** Serendipity/popularity-debias term cho similar (sau khi A3 đo được).
- **D4** Bộ dữ liệu màu↔nhạc-Việt expert-refined (publishable).

---

# 5. Lịch trình & cổng nghiệm thu

| Đợt | Việc | Gate |
|---|---|---|
| **Trước bảo vệ** | A1, A2, B1, B2, C1 | Metric chuẩn thay 100%; per-artist NDCG≥baseline; journey đo+plot; explanation chạy |
| Kế tiếp | A3, A4, B3, C2, C3 | beyond-accuracy baseline; VN-color; NL search |
| Sau | A5, D1-D4 | human-rated; learned re-ranker; MuQ benchmark |

**Đề xuất bắt đầu:** B1 (cap per-artist, S) → B2 (journey metrics, M) → A1 (color metrics, M) → C1 ("vì sao bài này", M). Bốn cái này cho buổi bảo vệ một bộ "đo được + wow + trung thực".

# 6. Rủi ro
- Đổi θ/metric có thể làm số color "xấu đi" so với 100% giả — **đó là mục đích** (số thật). Giải thích rõ với hội đồng.
- VN-color override có thể gây tranh luận (override khoa học phổ quát) → trình bày như *lớp bản địa có nguồn*, có cờ tắt.
- Mọi đổi hành vi → backtest CI trước khi merge (đã có harness + bài học regression _fast_rank).
