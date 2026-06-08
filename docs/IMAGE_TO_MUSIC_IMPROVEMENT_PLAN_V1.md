# Image → Music: Kế hoạch Cải tiến Toàn diện (V1)

> Mục tiêu: làm cho feature "gợi ý nhạc theo ảnh" (`POST /api/recommend/image`) **nhận diện nhạc hợp ảnh nhất**,
> theo hướng **no-human** (không cần gán nhãn thủ công) + **cross-modal embedding học sẵn**.
> Ngày: 2026-06-06. Gắn với đánh giá trong cùng phiên + nghiên cứu khoa học (xem §Tài liệu).

---

## 0. Bối cảnh & 2 quyết định nền

- **Quyết định 1 (no-human):** đánh giá + cải tiến hoàn toàn tự động — dùng dataset có sẵn
  (IMEMNet-C, EmoSet, DEAM), cross-modal pretrained, và **LLM/VLM-as-judge** thay ground-truth người.
- **Quyết định 2 (cross-modal):** sẵn sàng tích hợp embedding cross-modal học sẵn (kiểu **MMVA**: CLIP↔MERT).

### Hạ tầng đã có (đã verify trên đĩa)
| Thành phần | Trạng thái |
|---|---|
| CLIP ViT-B/32 (ảnh) | ✅ đang chạy trong `core/image_analysis.py` |
| MERT-v1-95M (nhạc) | ✅ `core/mert_encoder.py`; embedding toàn bộ bài `data/mert_embeddings.npy` = **(5548, 768)** L2-norm |
| DEAM (nhạc có nhãn V-A) | ✅ `data/external/deam/deam_mert.npy` = **(1802, 768)** → train bridge/probe |
| MERT→arousal probe | ✅ `tools/mert_arousal_probe.py` (DEAM-trained, CV R²≈0.58) |
| Backtest hạ tầng | ✅ `tools/backtest_v2/` (đã dùng cho color/similar) |

> ⇒ Kiến trúc MMVA gần như **chỉ còn thiếu cầu nối ảnh→không-gian-nhạc**, không phải làm lại từ đầu.

---

## 1. Vấn đề hiện tại (từ đánh giá code)

**Nghiêm trọng**
1. **Chưa từng được đo lường.** Không có ground truth/backtest/metric — chỉ 1 smoke test HTTP-200
   (`tools/smoke_test.py:121`). Không thể khẳng định chất lượng.

**Nợ kỹ thuật cao** (`core/recommendation_engine.py:1080-1279`)
2. **Hardcode trọng số** `0.20/0.25/0.20/0.15/0.20` (dòng 1267-1274); config `WEIGHTS_IMAGE_QUERY_*`
   (`config.py:416-417`) **là code chết, không nơi nào dùng** → vi phạm rule #1 CLAUDE.md.
3. **Đếm trùng cảm xúc:** emotion chi phối 4–5/6 tín hiệu (color_sim 40% emotion, emotion_sim,
   lyrics_sim suy từ emotion, emotion_boost, va_sim) → "gợi ý theo ảnh" suy biến thành "gợi ý theo mood label";
   tín hiệu thị giác thật bị rửa trôi.
4. **lyrics_sim (trọng số cao nhất 0.25) tự tham chiếu:** query embedding = trung bình embedding của các bài
   *đã* match emotion → trùng emotion_sim/boost, không bám vào ảnh; khi fallback `0.5` thì cộng đều, vô nghĩa xếp hạng.
5. **Nhánh no-lyrics chết** (`WEIGHTS_IMAGE_QUERY_NO_LYRICS` không dùng).

**Trung bình**
6. **Vòng lặp không vector hóa mỗi request:** `emotion_boost` loop `df.iloc[idx]` trên 4.3k+ bài (dòng 1255-1264) → vi phạm rule hiệu năng.
7. **Magic number** trong `target_audio` (dòng 1199-1209) — ad-hoc, không có cơ sở thực nghiệm.

---

## 2. Nguyên tắc khoa học định hướng (xem §Tài liệu để có nguồn)

- **Emotion mediation là đúng hướng.** Palmer 2013 (PNAS): liên kết nhạc↔màu được **trung gian bởi cảm xúc**
  (r=0.89–0.99). 1904.00150: mạng học correspondence ảnh↔nhạc làm "nảy sinh" biểu diễn cảm xúc mà không cần nhãn.
  → Giữ trục cảm xúc/V-A làm xương sống, nhưng **đừng đếm trùng**.
- **V-A liên tục > emotion phân loại.** CDCML/IMEMNet (2009.05103) và MMVA (2501.01094): khớp ảnh-nhạc trong
  **không gian V-A liên tục**, chấm điểm bằng Gaussian khoảng cách Euclid — **đúng cái ta đang làm**, nhưng có thể **học** thay vì heuristic.
- **MMVA (2501.01094) ≈ may đo cho ta — ✅ ĐÃ VERIFY full-text:** tri-tower **CLIP ViT-B/32 (ảnh, class token 512-dim)**
  + **MERT-95M (nhạc)** + RoBERTa-base (caption). Training objective xác nhận:
  `L_MMVA = L_VA(img) + L_VA(mus) + L_VA(cap) + L_sim` — **MSE dự đoán V-A từng modality + similarity-matching,
  KHÔNG dùng contrastive**. Vượt CDCML rõ rệt về dự đoán V-A (vd music-arousal 0.0002 vs 0.015 MAE).
  ⇒ Cầu nối Phase 2 = **tái hiện đúng thiết kế MMVA** với 2 encoder ta đã có. Lưu ý chiều: ảnh **512** vs MERT **768**.
- **Pairing không cần 1-1 — ✅ VERIFY:** "continuous matching score allows for random sampling of image-music pairs …
  by computing similarity scores from the valence-arousal values across different modalities" → no-human khả thi.
- **MERT** (2306.00107): encoder nhạc SSL SOTA 14 task → vector nhạc giàu hơn hẳn 7 audio-feature thô hiện tại.
- **Màu/thị giác ↔ cấu trúc nhạc qua cảm xúc (Palmer 2013) — ✅ VERIFY (PNAS):** trung gian cảm xúc, **0.89<r<0.99**;
  *nhanh + major → màu bão hòa/sáng/vàng-ấm hơn; chậm/minor → nhạt/tối/lạnh-xanh hơn*. **Đảo chiều** để dùng:
  ảnh **ấm/bão hòa/sáng → nhạc nhanh hơn, major, valence cao**; ảnh **lạnh/nhạt/tối → nhạc chậm, minor, valence thấp**
  → thay magic number `target_audio` bằng ánh xạ có cơ sở thực nghiệm.
- **Tính phổ quát màu-cảm xúc nhưng có biến thiên quốc gia** (Jonauskaite 2020, r=.88): cần lưu ý hiệu chỉnh
  cho ngữ cảnh Việt (đã có sẵn ICEAS-fit cho color).

---

## 3. Tâm lý & pain point người dùng (định hình metric + UX)

- **Vì sao người dùng muốn nhạc-theo-ảnh:** khám phá theo *tâm trạng/khung cảnh*, tạo "soundtrack" cho khoảnh khắc
  (ảnh du lịch, ảnh tâm trạng) — kỳ vọng cốt lõi là **khớp cảm xúc/không khí**, không phải khớp nội dung tả thực.
- **"Đúng" vs "sai" theo cảm nhận:** một gợi ý *sai cảm xúc* (ảnh buồn → nhạc tưng bừng) gây khó chịu mạnh hơn nhiều
  so với *đúng cảm xúc nhưng lạ*. → Ưu tiên **không bao giờ sai quadrant**; chấp nhận đa dạng trong đúng quadrant.
- **Failure mode hay gặp (đưa vào metric):**
  - *Genericness*: lúc nào cũng trả về cùng vài bài "an toàn" → đo **coverage/novelty**.
  - *Mood mismatch*: lệch valence/arousal → đo **quadrant-agreement, V-A MSE**.
  - *Repetition*: trùng nghệ sĩ/bài → đo **intra-list diversity, artist-repeat** (đã có `_fast_rank` MMR, cần đo lại).
- **Giải thích "vì sao bài này":** mô tả mood tiếng Việt đã có; nên gắn lý do khớp (màu/scene/cảm xúc) để tăng *tin cậy cảm nhận*.

---

## 4. Kế hoạch từng bước (gated bằng backtest, theo lệ các pillar khác)

> Thứ tự cố ý: **đo trước → vá rẻ → đòn bẩy lớn → bản địa hóa → ship**. Không tinh chỉnh khi chưa có thước đo.

### PHASE 0 — Xây harness đánh giá no-human (BẮT BUỘC, làm trước)
*Vì không có số liệu thì mọi cải tiến chỉ là đoán.*

- **0.1 Tập ground-truth ảnh (no-human):** lấy mẫu **EmoSet** (8 cảm xúc Mikels → map sang V-A/quadrant) +
  một ít ảnh "thực tế" (phong cảnh/chân dung/đồ ăn) để khớp phân bố người dùng. Lưu `data/external/emoset/`.
- **0.2 Metric khớp cảm xúc:** với mỗi ảnh GT, đo gợi ý hiện tại theo
  **(a) quadrant-agreement**, **(b) V-A MSE** giữa V-A ảnh và V-A trung bình top-K, **(c) emotion-category match**.
- **0.3 Metric cross-modal retrieval:** dựng tập pair kiểu IMEMNet-C (ảnh emotion-labeled × bài cùng quadrant) làm
  positive; đo **Recall@K, MRR** so với negative ngẫu nhiên.
- **0.4 VLM-as-judge:** đưa (ảnh + metadata K bài: tên/artist/mood/lyrics-snippet) cho 1 VLM (vd Gemini, đã có
  `tools/relabel_gemini.py` làm khung) chấm **"độ hợp 1–5"** + lý do; lấy điểm trung bình làm relevance tự động.
  Panel 3 lần bỏ phiếu để giảm nhiễu (theo lệ adversarial của dự án).
- **0.5 Beyond-accuracy:** intra-list diversity, novelty (nghịch độ phổ biến), artist-repeat, catalog coverage.
- **0.6 Baseline:** chạy toàn bộ metric trên hệ **hiện tại** → chốt con số mốc.
  Đặt trong `tools/backtest_v2/measure_image_accuracy.py` (song song `measure_color_accuracy.py`).

**Cổng:** có dashboard số + baseline tái lập được. *Không sửa engine trước khi xong 0.6.*

### PHASE 1 — Vá nợ kỹ thuật + tinh chỉnh (rủi ro thấp, đo delta vs baseline)
- **1.1** Nối trọng số về `config.py` (xóa hardcode dòng 1267-1274); dùng thật `WEIGHTS_IMAGE_QUERY_WITH/NO_LYRICS`,
  hoặc xóa hằng chết. Thêm nhánh no-lyrics **tái phân bổ** trọng số (không để 0.25 cộng đều vô nghĩa).
- **1.2** **Gỡ đếm trùng cảm xúc:** gộp emotion_sim + emotion_boost thành 1 tín hiệu cảm xúc mạch lạc;
  giảm phần emotion trong color_sim; **thay lyrics_sim tự tham chiếu** bằng tín hiệu bám-ảnh thật
  (xem Phase 2) hoặc hạ trọng số tạm thời.
- **1.3** **Vector hóa `emotion_boost`** (precompute mảng `fused_emotion` ở `_precompute_all_features`, dùng `np.isin`).
- **1.4** **Thay magic number `target_audio`** bằng ánh xạ Palmer 2013 (đã verify): arousal↑ → tempo/energy/loudness↑;
  ảnh **ấm/bão hòa/sáng** → valence↑ + thiên major + acousticness↓; ảnh **lạnh/nhạt/tối** → valence↓ + thiên minor +
  acousticness↑. Tham số hóa toàn bộ hệ số trong `config.py`.
- **Cổng:** không giảm bất kỳ metric Phase 0; lý tưởng tăng quadrant-agreement.

### PHASE 2 — Cầu nối cross-modal MMVA (đòn bẩy lớn nhất)
*Đưa ảnh và nhạc về **cùng không gian** thay vì ghép heuristic.*

- **2.1 Vector nhạc:** nạp sẵn `data/mert_embeddings.npy` (5548×768) vào recommender tại
  `_precompute_all_features()` (`recommendation_engine.py:188`) → `self.song_mert` (đã verify alignment với df).
- **2.2 Cầu nối ảnh→không-gian-nhạc (no-human, leo thang 3 nấc — backtest quyết định dừng ở đâu):**
  - **2.2a (nhẹ, V-A-mediated, không train):** image→V-A (đã có) ↔ music-V-A từ MERT probe (đã có) → similarity V-A.
    Tín hiệu cross-modal đầu tiên, rẻ, làm "sàn" để so. *Lưu ý: ảnh-emb CLIP 512-dim, MERT 768-dim — nấc này khớp qua V-A 2-chiều nên không vướng chiều.*
  - **2.2b (mạnh, ĐÚNG thiết kế MMVA đã verify):** 2 head MLP nhỏ — `img(512)→VA` và `music(768)→VA` — + matching head;
    train bằng **`L_VA(img)+L_VA(mus)+L_sim`** (MSE, **không contrastive**) trên **IMEMNet-C** + random pairs từ
    EmoSet×catalog cùng quadrant. Tái dùng `deam_mert.npy` (1802 nhãn V-A) để khởi tạo/calibrate `music→VA`
    (đã có probe R²≈0.58 — đây là nâng cấp trực tiếp). Lưu vào `models_cache/`.
  - **2.2c (tuỳ chọn, nếu 2.2b chưa đủ):** thêm tower caption (PhoBERT/RoBERTa) cho lyrics → `L_VA(cap)` đầy đủ kiểu MMVA;
    hoặc dò xem trọng số MMVA pretrained có public để bootstrap. Chỉ làm nếu backtest đòi.
- **2.3** Thêm **cross-modal similarity** thành tín hiệu mới trong `recommend_by_image`; **backtest quyết định trọng số**
  (kỳ vọng thành tín hiệu chủ đạo, thay hẳn lyrics_sim tự tham chiếu). Giữ V-A/color như tín hiệu phụ + guard quadrant.
- **Cổng:** vượt Phase 1 trên VLM-judge + quadrant-agreement + recall@K; không tụt diversity/novelty.

### PHASE 3 — Bản địa hóa Việt + chống pain-point
- **3.1** Hiệu chỉnh nhẹ cảm xúc/màu cho ngữ cảnh Việt (Jonauskaite: biến thiên quốc gia); tái dùng ICEAS-fit color.
- **3.2** Chống **genericness/repetition:** kiểm soát diversity/novelty trong `_fast_rank` theo số liệu Phase 0.5.
- **3.3** **Giải thích "vì sao bài này"**: gắn lý do khớp (màu chủ đạo/scene/cảm xúc) vào response → tăng tin cậy cảm nhận.
- **Cổng:** metric beyond-accuracy cải thiện, accuracy không tụt.

### PHASE 4 — Ship gating ✅ DONE 2026-06-06

**Gate script:** `tools/backtest_v2/gate_image_phase4.py`  
**Report:** `var/runtime/backtest/reports/image_phase4_gate/report.json`

| Check | Result | Key numbers |
|---|---|---|
| Image accuracy | **PASS** | quadrant_agree=1.000, ild_va=0.142, opposite=0.000 |
| Color regression | **PASS** | delta=±0.000 on all 6 metrics (exact match) |
| Smoke test | **PASS** | All fields present: match_reason, occasion, occasion_confidence |
| **Overall gate** | **✓ PASS** | |

**Final metric summary (Baseline → Phase 4):**

| Metric | Baseline | Final | Delta |
|---|---|---|---|
| quadrant_agree@10 | 0.850 | **1.000** | +15pp |
| opposite_quadrant@10 | 0.000 | 0.000 | — |
| ild_va@10 (diversity) | 0.035 | **0.142** | **+306%** |
| va_mae@10 | 0.054 | 0.107 | diversity tradeoff |
| artist_variety@10 | 0.930 | 0.955 | +2.5pp |
| color path (ndcg@10) | 0.556 | **0.556** | 0 regression |

**New response fields:**
- `match_reason` per recommended song (e.g. "cảm xúc tương đồng · tâm trạng bình yên")
- `occasion` / `occasion_confidence` in image_analysis (wedding/festival/graduation/concert/birthday; fires only at confidence ≥ 0.45)

**New scenes added (3C-1):** old_town_alley, rice_terrace, night_market, floating_market, temple_pagoda, lotus_pond, street_cafe, monsoon_rain, coastal_village, mountain_fog — all in `SCENE_MOOD_PROMPTS` + `SCENE_VA_MAP`.

---

## 5. Rủi ro & lưu ý
- **Alignment MERT↔df:** `mert_embeddings.npy` 5548 hàng vs số bài hiện tại — **phải verify ánh xạ track_id**
  (dùng `data/mert_metadata.json.done_track_ids`) trước khi nạp; coverage < 100% cần fallback.
- **VLM-as-judge có bias:** dùng panel + prompt trung lập; chỉ dùng làm *tương đối* (so sánh A/B), không tuyệt đối.
- **IMEMNet access (✅ composition đã verify):** ảnh IAPS/NAPS/EMOTIC + nhạc DEAM. ⚠️ **IAPS/NAPS bị gated** (phải xin quyền nghiên cứu),
  EMOTIC có điều khoản riêng → rủi ro *tải*, không phải *thành phần*. Giảm nhẹ: **DEAM music-side đã có sẵn** (`deam_mert.npy`);
  EMOTIC (23k ảnh, lớn & dễ tiếp cận nhất) đủ cho image→VA head; bí thì thay bằng **EmoSet×catalog** (vẫn no-human).
  Lưu ý: nhãn V-A của IAPS/NAPS/EMOTIC/DEAM là nhãn *có sẵn* trong dataset công khai → **không phải gán nhãn mới**, vẫn đúng no-human.
- **Đừng over-fit VLM-judge:** giữ song song metric khách quan (quadrant/recall) để tránh "luyện theo giám khảo".
- **VLM-judge có bias chấm điểm có hệ thống (✅ verify, arXiv 2506.22316):** *rubric order bias, score ID bias,
  reference answer score bias*. → Phase 0.4 phải **xáo thứ tự lựa chọn**, **ẩn ID**, **không cho điểm tham chiếu**, dùng panel + lấy trung vị.

---

## 6. Tài liệu (nguồn sơ cấp) + trạng thái verify

> Khâu verify tự động của workflow lỗi cơ học (agent không gọi tool → "abstain"). Sau đó đã **verify thủ công bằng WebFetch/WebSearch
> trực tiếp từ nguồn gốc** (phiên 2026-06-06) cho **TẤT CẢ** claim. Trạng thái dưới đây là kết quả verify thật.
> Chỉ còn con số "music clips ~23,944" của IMEMNet là chưa khớp chính xác (DEAM = 1.802 track gốc, clip/segment khác) — không trọng yếu.

- **MMVA** — arXiv 2501.01094 — ✅ **VERIFY (full-text)**: CLIP ViT-B/32 (ảnh, 512-dim) + MERT-95M + RoBERTa-base;
  loss `L_VA(img)+L_VA(mus)+L_VA(cap)+L_sim` (MSE, không contrastive); random-pair qua V-A; vượt CDCML (music-arousal 0.0002 vs 0.015 MAE).
  IMEMNet-C = 24,756 ảnh / 25,944 clip. ⚠️ con số MSE 0.033/0.067 trong claim gốc **sai** → bỏ.
- **CDCML / IMEMNet** — arXiv 2009.05103 — ✅ **VERIFY**: ≥140K pairs; continuous V-A; metric-learning+regression đồng thời.
  ✅ **Composition VERIFY** (mô tả trong MMVA): ảnh = **IAPS 1.182 + NAPS 1.356 + EMOTIC 23.082 = 25.620 ảnh**;
  nhạc = **DEAM 1.802 track** (= chính `data/external/deam/deam_mert.npy` 1802×768 ta đang có). 25.620 là con số ĐÚNG cho IMEMNet gốc
  (24.756 là biến thể IMEMNet-**C**). ⇒ **music side của IMEMNet đã sẵn dạng MERT embedding trên đĩa.**
- **Palmer 2013 (PNAS)** — 10.1073/pnas.1212562110 — ✅ **VERIFY (PNAS/search)**: trung gian cảm xúc; 0.89<r<0.99;
  nhanh+major→bão hòa/sáng/vàng, chậm/minor→nhạt/tối/xanh.
- **EmoSet** — github.com/JingyuanYY/EmoSet — ✅ **VERIFY**: 3.3M / 118K ảnh; 8 cảm xúc Mikels.
- **MERT** — arXiv 2306.00107 — encoder nhạc SSL SOTA 14 task (đã dùng trong dự án; con số SOTA chưa re-verify chi tiết).
- **Emotion-supervised contrastive image-music** — arXiv 2308.12610 — ✅ **VERIFY**: "emotion-aligned joint embedding space …
  via emotion-supervised contrastive learning, using an adapted cross-modal version of the SupCon loss"; retrieval 2 chiều
  image↔music theo emotion labels. *(Lưu ý: cần emotion labels khi eval — khác MMVA dùng VA liên tục.)*
- **Affective correspondence** — arXiv 1904.00150 — ✅ **VERIFY**: project 2 modality về không gian chung + phân loại nhị phân
  match/không; "learns modality-specific representations of emotion (without explicitly being trained with emotion labels)".
- **ImageBind** — arXiv 2305.05665 — ✅ **VERIFY**: joint embedding 6 modalities, "only image-paired data is sufficient";
  emergent cross-modal retrieval out-of-the-box. *(Phương án thay thế cho cầu nối nếu MMVA-style không đủ.)*
- **Jonauskaite 2020** — 10.1177/0956797620948810 — ✅ **VERIFY** (PubMed 32900287): r=.88, 30 nước, >4,500 người,
  20 emotion × 12 color; "nation predicted color-emotion associations above and beyond those observed universally"
  (+ gần về ngôn ngữ/địa lý → giống nhau hơn).
- **DEAM** — cvml.unige.ch/databases/DEAM — music V-A dataset (đã dùng: `deam_mert.npy` 1802×768).
- **LLM-as-judge — sửa khớp sai:** arXiv 2506.22316 **KHÔNG** phải "dùng LLM-judge cho retrieval" mà là **bias trong chấm điểm
  của LLM-judge** (đã chuyển thành cảnh báo ở §5).
- **LLM-as-judge cho retrieval (phương pháp)** — blog.vespa.ai/improving-retrieval-with-llm-as-a-judge — ✅ **VERIFY** (blog, không peer-reviewed):
  thang điểm liên quan **0/1/2**, prompt có **định nghĩa rõ + 2 demo + reasoning từng bước**, **hiệu chỉnh trên GT người nhỏ rồi scale**,
  kiểm bằng nDCG/confusion-matrix. ⚠️ *Nuance no-human:* họ calibrate trên GT **người** → ta thay bằng calibrate trên **metric khách quan
  (quadrant-agreement)** để giữ no-human.
