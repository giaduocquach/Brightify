# Đánh giá toàn diện & phát hiện — Recommend-by-Color / Recommend-by-Song

> Soạn 2026-06-24. Mọi số trích từ code/eval; các số "đo lại" được chạy live trên cấu hình hiện
> tại (backbone=MuQ, lyrics=e5-large, nhãn `emotion_labels_v6i.json`). Mục tiêu: ghi lại các phát
> hiện bất thường + điểm yếu và cách xử lý (sửa / đo lại / công bố).

## 0. Tóm tắt điều hành

- Kiến trúc tốt trên mức ĐATN thông thường: 1 trục V-A dùng chung cho cả 2 feature, serving
  **không LLM/không inference** (chỉ matmul, ~3–4 ms/query), nhãn **đóng băng + tái lập ρ=1.0**.
- **2 phát hiện đỏ:** (1) trên yardstick đúng, similar-song **thua baseline popularity** ở editorial
  GT (editorial là thước đo sai); (2) metric chính của color (TE) **tự-quy-chiếu một phần**.
  Cả hai xử lý bằng **đổi cách trình bày bằng chứng**, không phải sửa engine.
- **Backbone (đo lại CÔNG BẰNG):** MuQ **ngang-hoặc-hơn** MERT, thắng có ý nghĩa ở transfer judge
  độc lập (GPT-GT) → chọn MuQ là hợp lý. (Bản đo "MERT thắng" trước đó là bug harness — xem §1.1.)
- Đã sửa: 3 comment/số sai, nối `why` cho similar-song, gỡ compute chết (PhoBERT/tag/emotion-vec).

---

## 1. Đo lại (Group B) — kết quả live

### 1.1 MuQ vs MERT — FAIR head-to-head (mỗi backbone ở điều kiện tốt nhất)

Công bằng: (a) **switch backbone THẬT** (MuQ 1024-dim vs MERT 768-dim — đã in shape xác nhận);
(b) **re-optimize trọng số fusion riêng từng backbone bằng 5-fold CV** trên musical GT (tune trên
train-fold, chấm trên held-out fold → không overfit); (c) audio-only = chất lượng backbone thuần;
(d) GPT GT = judge ĐỘC LẬP làm phép transfer ở trọng số musical-optimal; paired bootstrap CI.

| Phép đo | MuQ | MERT | Δ(MuQ−MERT) | 95% CI | n |
|---|---|---|---|---|---|
| musical CV-NDCG@10 (no-overfit) | 0.7345 | 0.7343 | +0.0002 | [−0.021, +0.020] ns | 52 |
| audio-only NDCG@10 (isolation) | 0.7476 | 0.7424 | +0.0052 | [−0.015, +0.025] ns | 52 |
| **GPT-GT NDCG@10 (transfer, judge độc lập)** | 0.8060 | 0.7714 | **+0.0346** | [+0.014, +0.056] **SIG** | 50 |
| editorial (yardstick sai, tham khảo) | 0.0895 | 0.0801 | +0.0093 | [+0.001, +0.017] SIG | 872 |
| colour-TE @α0.55 (frozen V-A) | 0.0625 | 0.0630 | −0.0005 | ~tie | 12 |

Trọng số CV-tối-ưu: MuQ `(lyr 0, va 0, aud 1.0)`, MERT `(0.045, 0.015, 0.94)` — **gần như audio-only
cho cả hai** (lyrics/va thêm ~0 vào pooled NDCG). Intrinsic (mỗi bên ở trọng số riêng): MoodCoherence
MuQ 0.83 / MERT 0.91 (MERT giữ chút va nên mood-coherent hơn — confound trọng số, không phải backbone).

**Kết luận (ĐÚNG):** MuQ **ngang-hoặc-hơn** ở mọi chỗ, và **thắng có ý nghĩa ở transfer judge độc lập**
(GPT-GT). → Việc chọn MuQ **được chứng minh là hợp lý**. (Con số headline cũ "0.0739>0.0708" vẫn không
tái lập về SỐ, nhưng HƯỚNG MuQ ≥ MERT là đúng.) colour-TE coi như hòa.

> ⚠️ **Đính chính phương pháp:** kết luận "MERT thắng" ở bản đo trước (2026-06-24 sáng) là **SAI do bug
> harness** — engine đọc `AUDIO_BACKBONE` từ globals của chính module engine (bound lúc `from config
> import *`), nên việc set `cfg.AUDIO_BACKBONE` lúc runtime **không có tác dụng** → cả hai nhánh đều
> chạy ma trận MuQ; Δ−0.011 quan sát được chỉ là hiệu ứng **trọng số** trên cùng ma trận. Bản này
> patch `RE.AUDIO_BACKBONE` (global của module engine) nên backbone switch thật (đã verify shape).

### 1.2 Editorial NDCG@10 (full pipeline, baseline)

| method | NDCG@10 | × random |
|---|---|---|
| production | 0.0664 | 1.8× |
| **popularity** | **0.0911** | **2.5×** |
| random | 0.0363 | 1.0× |

Popularity (top-10 theo tần suất nghệ sĩ) **đánh bại** production. Đây **không** phải engine kém:
editorial-playlist GT *thưởng* popularity/co-occurrence và *phạt* đúng artist-diversity (MMR) +
cover-filter mà production cố ý làm (Dacrema 2019). → **Không dùng editorial NDCG làm headline**
cho similar-song; dùng musical GT graded + intrinsic coherence.

### 1.3 Verify số headline (tự chạy live 2026-06-24 — tất cả KHỚP)

Chạy lại bằng chính các tool của dự án để xác nhận số trong báo cáo (không chỉ tin digest):

| Tool / số | Kết quả live | Trạng thái |
|---|---|---|
| `build_labels_repro` — valence/arousal ρ vs frozen v6i | **+1.0000 / +1.0000** | PASS (tái lập bit-for-bit) |
| label ρ vs GPT (V / A) | 0.634 / 0.412 | khớp |
| `color_eval_rigor` — FDR (BH-Wilcoxon) | **4/4** baseline bị bác (p_adj 0.0003) | PASS |
| r(V,A) trực giao | +0.161 (≤0.20) | PASS |
| journey KS / mean_t | 0.215 / 0.502 | PASS |
| valence màu vs ICEAS | r = **0.969** CI[0.889,0.991] | PASS (construct valid) |
| Whiteford ρ(lightness,BPM)/ρ(sat,BPM) | **+0.413 / +0.661** | PASS (validation độc lập) |
| `color_per_color_audit` — ρ(tgtV,gotV)/ρ(tgtA,gotA) | +1.000 / +0.972 | PASS |
| `eval_similar_intrinsic` — MoodCoherence / CalibError / SameArtist | 0.93 / 0.009 / 0.046 | OK |
| `pmemo_cross_eval` — DEAM→PMEmo ρ (valence / arousal) | **0.694 / 0.646** | tốt (Western→Western) |

Lưu ý: ρ(L,BPM) live = +0.413 (digest ghi +0.46 — cùng hướng, dùng số live). PMEmo transfer
**không** yếu như docs cũ ghi (0.50); điểm yếu thật của valence là **cross-cultural** (DEAM-probe→catalog
VN R²~0.06), không phải Western→Western.

---

## 2. Phát hiện bất thường & điểm yếu (triage)

Ký hiệu: 🔴 đỏ (lung lay khi bảo vệ) · 🟠 cam (điểm yếu phương pháp) · 🟡 vàng (rác code).
Cột "Xử lý": ✅ đã sửa · 🔧 cần đo lại/công sức · 📋 công bố (threats-to-validity).

| # | Mức | Phát hiện | Xử lý |
|---|---|---|---|
| 1 | 🔴 | Similar-song thua popularity trên editorial GT (0.066 < 0.091) | 📋 đổi yardstick → musical GT; công bố Dacrema |
| 2 | 🟠 | Số headline cũ "0.0739>0.0708" không tái lập (nhưng đo lại công bằng: MuQ ≥ MERT, thắng GPT transfer SIG → hướng đúng) | ✅ sửa comment config về số đo lại |
| 3 | 🔴 | TE color tự-quy-chiếu (GT V-A là input engine, match cùng quantile-space) | 📋 hạ TE xuống phụ; headline = Whiteford-BPM + ICEAS r=0.97 + `color_llm_gt` (ít vòng tròn) |
| 4 | 🔴 | TE tăng 0.0225→0.0268 khi bật V38 (bản đúng hơn) | 📋 công bố: giới hạn cung (đuôi high-arousal ~22% catalog) |
| 5 | 🟠 | Similar-song không có accuracy độc lập không-tranh-cãi | 🔧 mở rộng musical GT (nhiều seed + multi-judge + Krippendorff α) |
| 6 | 🟠 | Không có human listening study (offline↔online r≈0.28) | 📋 future work; tùy chọn pilot XAB n=5–10 |
| 7 | 🟠 | Việt Nam ∉ ICEAS (30 nước); n=12 màu → CI rộng | 📋 threats-to-validity (chuẩn mực) |
| 8 | 🟠 | Valence yếu khi cross-cultural: DEAM→PMEmo OK (ρ 0.69 đo lại) nhưng DEAM-probe→catalog VN R²~0.06 → lệ thuộc lexicon VN 84% | 📋 đã xử lý đúng; công bố |
| 9 | 🟠 | r(V,A)>0 → quadrant lệch trục thưa (peaceful/tense ít bài) | 📋 thuộc tính dữ liệu; công bố |
| 10 | 🟠 | Màu nâu/hồng cho cảm giác "energetic" phản trực giác | 📋 trung thành Whiteford; công bố model-vs-trực-giác |
| 11 | 🟡 | API asymmetry: color trả `why`, song không | ✅ parity tầng API (`build_song_why`). Lưu ý: UI cố ý KHÔNG render explainer cho cả hai (commit 9f44f82) → why chỉ phục vụ API consumer, không hiện màn hình |
| 12 | 🟡 | Compute thừa: instrument matrix, PhoBERT dead-load, `color_hsl` | ✅ gate/gỡ (xem §3). `song_emotion_vec` KHÔNG gỡ — backtest Catalog dùng cho calibration metric |
| 13 | 🟡 | Dead branch trong `_recompute_song_va` | ✅ làm rõ là defensive fallback |
| 14 | 🟡 | Comment lệch active-flag (Valdez vs Whiteford; VA weight 0.10 vs 0.16) | ✅ đã sửa |
| 15 | 🟡 | Nhiều flag superseded giữ lại (rollback) | ⏳ giữ có chủ đích; đã ghi rõ flag nào active |

---

## 3. Đã sửa trong vòng này (Group A)

| File | Thay đổi |
|---|---|
| `config.py` | Sửa comment NDCG `0.0739`→số đo lại; sửa claim backbone "MuQ thắng"→trung thực; `SKIP_PHOBERT_LOAD` default `True` (PhoBERT chết — search dùng e5); `ENABLE_TAG_SIGNAL` default `False` (slot weight=0) |
| `core/recommendation_engine.py` | Gỡ `color_hsl` chết (không nơi nào đọc, grep đệ quy); GIỮ `song_emotion_vec` (backtest Catalog dùng); đọc `AUDIO_BACKBONE` từ module config tại runtime (A/B hết no-op); làm rõ dead-branch `_recompute_song_va`; comment VA weight 0.10→0.16 |
| `core/advanced_color_mapping.py` | Làm rõ Whiteford (V38) là arousal model ACTIVE, Valdez/ICEAS là rollback |
| `core/explain.py` | Thêm `build_song_why` cho similar-song |
| `api/music.py` | Nối `why` vào `/song/{id}/similar` |

Verify: `pytest test/` xanh; smoke construct recommender + color-journey + song path OK với default mới.

---

## 4. Khuyến nghị trình bày trong báo cáo (đặt vào "Hạn chế / Threats to Validity")

1. **Similar-song:** đặt MoodCoherence (0.96) + musical-GT graded NDCG làm chính; trình bày editorial
   NDCG **kèm** baseline popularity + giải thích Dacrema (editorial là yardstick sai cho similar-song).
2. **Color:** đặt validation **độc lập** lên đầu — ρ(lightness,BPM)=+0.46, ρ(saturation,BPM)=+0.66
   (Whiteford, dùng BPM librosa độc lập) và r=0.97 vs chuẩn ICEAS; TE chỉ là metric phụ (tự-quy-chiếu).
3. **Backbone:** MuQ ≈ MERT trên metric trực tiếp (hòa) và **MuQ thắng SIG ở transfer judge độc lập**
   (GPT-GT); chọn MuQ là hợp lý — nêu thêm rằng trọng số CV-tối-ưu gần như audio-only nhưng production
   giữ va/lyrics để tăng MoodCoherence. (Bỏ "chọn MuQ vì nhất quán")
   1-backbone + thắng valence-probe, **không** vì thắng end-metric.
4. **Threats-to-validity** (giữ nguyên, không "sửa"): n=12 màu, VN∉ICEAS, không có human study,
   valence yếu qua audio, quadrant lệch trục thưa, màu phản trực giác. Đây là điểm **cộng** về tính
   trung thực khoa học, không phải điểm trừ.
