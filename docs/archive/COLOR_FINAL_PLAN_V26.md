# Recommend-by-Colour — PLAN FINAL (V26): NỀN KHOA HỌC → BUILD → BACKTEST → TEST → TINH CHỈNH

> 2026-06-10. Tài liệu **chốt** feature recommend-by-colour. Ràng buộc giữ nguyên:
> **không dùng dữ liệu hành vi người dùng**, **không có dataset nhạc Việt gán nhãn V-A**.
>
> Khác V25 ở đâu: V25 = dựng lại nền KH + phán quyết hướng đi. **V26 = vòng deep-research thứ 2
> (nguồn mới + xác minh) + chạy thực nghiệm R1 thật + đóng gói thành plan vòng đời đầy đủ một feature
> recommend** (cơ sở → build → backtest → test → loop cải thiện đến trần). Đây là tài liệu để **chốt và thực thi**.
>
> Builds on: V25 (nền KH 6 trục), V24 (rigor harness), V19/V19b (factor + valence), V17 (audit).

---

## 0. KẾT LUẬN ĐIỀU HÀNH (đọc trước)

**Phán quyết:** Sau 2 vòng deep-research độc lập + 14 vòng lặp thiết kế, kết luận **không đổi và được củng cố thêm**:
kiến trúc hiện tại (color → V-A → match song-V-A, emotion làm trung gian) **đúng hướng khoa học**. V26 KHÔNG đập đi xây lại.
Việc còn lại là **3 tinh chỉnh có cơ sở số liệu** + **đóng chặt khung test cho khỏi tautology** + **viết đúng ngôn ngữ claim**.

**Cái mới quan trọng nhất của V26 (so với V25):**

1. **R1 đã có SỐ THẬT** (chạy `tools/phase3_cielab_experiment.py`, n=12 ICEAS, LOO-CV):
   phán quyết đúng KHÔNG phải "giữ HSL" hay "chuyển hết CIELAB" mà là **HYBRID** —
   **valence → CIELAB-Lch** (r 0.85 vs 0.76, **monotonicity L→V 0.81 vs 0.44**),
   **arousal → giữ Whiteford-HSL** (r 0.74 vs CIELAB-regression sụp còn 0.21 do overfit n=12).
2. **Bằng chứng cross-modal định lượng MỚI** (PLOS ONE 2015, pone.0144013): emotion-mediated model giải thích
   **60–75% variance** màu khi ghép nhạc→màu, **thắng audio-only ở 3/4 chiều màu**; lightness d=0.74, hue/b* d=0.48.
   → củng cố trực tiếp cơ chế emotion-as-mediator (mạnh hơn nguồn V25 đã có).
3. **MER meta-analysis MỚI** (ACM 3796518): arousal r=0.81 > valence r=0.67; **NN KHÔNG thắng linear/tree ở regression.**
   → vừa củng cố σ_A<σ_V, vừa **bác bỏ ý "thêm deep model sẽ tốt hơn"** cho trục V-A.
4. **Tín hiệu văn hóa LÀ THẬT và MẠNH** (SVM đoán quốc tịch từ color-emotion **80.2%**, AUC 0.928).
   → term `−0.19·redness` (đỏ→giảm valence, kiểu Tây) là sai-văn-hóa-VN rõ; nhưng sửa ra sao cần quyết (R3).

**3 việc ROI cao nhất (no-data):** **R1 hybrid CIELAB-valence** · **R5 test end-to-end khó hơn (chống tautology)** · **R2 củng cố valence decoupled.**

| Trục | Quyết định hiện tại | Phán quyết V26 | Bằng chứng |
|---|---|---|---|
| Emotion-mediation (color→emotion→music) | ✅ Đúng | **Củng cố mạnh hơn** | Palmer 2013 (r .89–.99); Whiteford 2018 (mediation strong-form); **PLOS 2015: 60–75% var, beats audio-only 3/4** |
| Không gian 2D V-A | ✅ Đúng | Giữ | Whiteford PARAFAC; GlobalMood cross-culture |
| σ_A < σ_V heteroscedastic | ✅ Đúng | **Củng cố** | **MER meta: A r=.81 > V r=.67**; Delbouys; cả phía màu (Springer 2012) |
| arousal=audio, valence=lời, KHÔNG audio-valence Tây | ✅ Đúng | Giữ | cross-corpus valence âm; mode trưởng/thứ đảo ở VN (F4) |
| Color→V-A: **valence bằng HSL** | 🟠 Cải tiến được | **→ CIELAB-Lch** (hybrid) | **phase3 exp: r .85 vs .76, mono .81 vs .44**; Ou&Luo; Ou cross-cult (chroma↔Activity r=.86) |
| Color→V-A: **arousal bằng HSL/Whiteford** | ✅ Đúng | **Giữ** (CIELAB-reg overfit) | phase3 exp: HSL .74 vs CIELAB .21 |
| Valence = Gemini-đọc-lời | 🔴 Mắt xích yếu | Củng cố decoupled (R2) | corroborate yếu ρ=0.263; rủi ro circular (Kriegeskorte) |
| `−0.19·redness` | 🟠 Sai văn hóa VN | Quyết R3 (doc vs overlay) | Jonauskaite; **SVM-country 80.2%** |
| Test end-to-end = editorial-GT | 🔴 Tautological | Thêm test khó hơn (R5) | Dacrema; double-dipping |
| RRF + targeting-error + battery + CI/FDR | ✅ Đúng | Giữ | Cormack; Dacrema rigor |
| Màu-làm-input + UX (WCAG, cap 2) | ✅ Đúng | Giữ | Manchester Colour Wheel (validated lâm sàng) |

---

## 1. SYNTHESIS DEEP-RESEARCH V26 (nguồn + độ tin)

> Quy ước độ tin: **[VERIFIED]** = vote 3-0 hoặc đã fetch-confirm trong V25; **[SOURCED]** = nguồn primary đã fetch
> nhưng adversarial-verify bị abstain do session limit (KHÔNG bị bác — cần đọc full-text khi trích luận văn);
> **[CONTESTED]** = có vote bác. 27 nguồn primary tổng cộng.

### Trục 1 — Emotion là trung gian color↔music (cơ chế nền)
- **[SOURCED]** **PLOS ONE 2015 (pone.0144013)** — *nguồn mới mạnh nhất V26.* Mô hình hồi quy **có biến cảm xúc giải thích 60–75% variance** từng tham số màu (Size 75%, Lightness 74%, b* 66%), **vượt mô hình audio-only ở 3/4 chiều màu**. Effect sizes: nhạc vui → màu sáng hơn (**d=0.74**); năng lượng cao → đỏ/vàng hơn, thấp → xanh (**b* d=0.48**). → định lượng hoá trực tiếp cơ chế của ta.
- **[SOURCED]** **Palmer 2013 PNAS (1212562110)** — emotional ratings nhạc↔màu tương quan **r=0.89–0.99**; nhanh+trưởng→màu bão hoà/sáng/vàng, chậm+thứ→nhạt/tối/xanh.
- **[SOURCED]** **Whiteford 2018 (i-Perception, Sage 2041669518808535)** — bỏ nội dung cảm xúc thì tương quan tri-giác-nhạc↔màu **rớt về không-ý-nghĩa** → strong-form mediation. (V25 đã fetch-confirm PARAFAC ra đúng V+A.)
- ⇒ **Cơ chế đúng, giờ có cả effect size.** Không đổi.

### Trục 2 — Màu → cảm xúc / V-A
- **[VERIFIED 3-0]** **Valdez & Mehrabian 1994** — `Pleasure=.69·B+.22·S`, `Arousal=−.31·B+.60·S`, `Dominance=−.76·B+.32·S`. Brightness+saturation là driver chính. → khớp công thức valence hiện tại nặng S & L.
- **[CONTESTED 1-2]** "Arousal tăng theo S nhưng GIẢM theo B, và phải tách B/S thành 2 predictor ngược dấu" — bị bác 2/3. Lý do hợp lý: V&M đo trên màu nền tĩnh; Wilms&Oberfeld thấy **cả 3** chiều ảnh hưởng arousal, dấu của brightness không đơn giản. → **KHÔNG dựa cứng vào dấu brightness-arousal của V&M**; dùng Whiteford cho arousal (đang làm — đúng).
- **[VERIFIED 3-0]** **Jonauskaite 2020** — color-emotion phổ quát **r=.88 / 30 nước / 4598 người**, NHƯNG **nationality dự đoán beyond universal**, similarity cao hơn khi gần ngôn ngữ/địa lý.
- **[SOURCED]** **SVM đoán country từ color-emotion = 80.2% (AUC .928)**, n=711 (TQ/Đức/Hy Lạp/Anh) — tín hiệu văn hóa **mạnh, đo được**. Nhưng in-group advantage khi *dự đoán màu từ cảm xúc* chỉ **2–10% (M=6.1%)** → văn hóa modulate, không lật đổ. → R3: term redness VN đáng xét, nhưng đừng overlay nặng tay.
- **[SOURCED]** **Ou cross-cultural (col emotion analysis)** — 3 nhân tố Activity/Potency/Temperature; **Activity↔chroma r=0.86, Potency↔lightness r=0.95** (7 vùng, 214 màu). → bằng chứng định lượng **CIELAB chroma & lightness** là predictor affect tốt → hậu thuẫn R1.
- **[SOURCED]** **Ou & Luo 2004 (Wiley col.20010)** + **Wilms & Oberfeld 2018** — model color-emotion định lượng trên CIELAB; saturation tác động arousal lớn nhất (η²=.69).
- ⇒ **CIELAB Lch là không gian đúng cho valence** (xác nhận bởi cả Ou-cross-cult + experiment của ta). Văn hóa có thật nhưng nhỏ ở mức dự-đoán-màu.

### Trục 3 — Music Emotion Recognition (MER)
- **[SOURCED]** **MER meta-analysis (ACM 3796518)** — *mới.* Regression: **arousal r=0.81 > valence r=0.67**; categorical MCC 0.87; **NN không trội hơn linear/tree ở regression** (NN arousal chỉ r=0.66). → (a) củng cố σ_A<σ_V; (b) **bác ý "thêm deep model V-A sẽ tốt hơn"**.
- **[SOURCED]** **arXiv 2302.13321** — multi-modal (11 feature Spotify + lyric sentiment/TF-IDF/ANEW) **dự đoán valence tốt hơn audio-only** → ủng hộ valence=lyrics-fusion.
- **[SOURCED]** **DEAM 1802 bài** + **PMEmo 794 bài** (static + dynamic V-A annotations, human GT) — **dùng làm cross-corpus GT cho R5** (non-VN, human thật).
- ⇒ Thiết kế (arousal=MERT-probe, valence=lyrics) đúng. Mắt xích yếu: valence-lời chưa validate độc lập mạnh (→R2).

### Trục 4 — Cross-modal matching / retrieval & deep learning
- **[SOURCED]** **Nakatsuka WACV 2023** (Content-Based Music-Image Retrieval, self+cross-modal embedding memory) + **arXiv 2009.05103 / 2501.1094 / 2412.05831** — CLIP-style joint embedding **tồn tại và mạnh KHI có dữ liệu cặp**. Ta KHÔNG có cặp (màu/ảnh ↔ nhạc) cho người Việt → **học end-to-end joint-embedding bị loại** (cần data cặp). Đây là xác nhận khoảng trống, không phải hướng đi.
- **[SOURCED]** **RRF (Cormack 2009)** + **Dacrema 2021 (aaai.12051)** — rank-fusion robust; phải thắng baseline mạnh. → giữ RRF + beats-baseline.
- ⇒ Giữ V-A RBF + RRF. Deep cross-modal = KHÔNG (no paired data).

### Trục 5 — Đánh giá không có người dùng (label-free)
- **[SOURCED]** **Dacrema** (thắng random/popularity/NN), **Docear offline-vs-online study** (offline ≠ online — cẩn trọng claim), **arXiv 2308.12610** (eval methodology). → khung V24 (targeting-error + structural battery + CI/FDR + beats-baseline) đúng phương pháp.
- Lỗ hổng tự nhận (V25): editorial-GT **tautological** với scorer V-A-only; rủi ro **circular** (Gemini label + Gemini judge). → R5.
- ⇒ Khung đánh giá là điểm MẠNH; cần thêm test **ngoài cơ chế scorer** (cross-corpus DEAM/PMEmo).

### Trục 6 — Color science nền
- **[SOURCED]** **CIELAB / color appearance model (CIECAM)** — sRGB/HSL **không đồng đều tri-giác**; CIELAB Lch device-independent + xấp xỉ đều. → R1.
- **[SOURCED]** **Manchester Colour Wheel (Carruthers 2010)** — màu = công cụ biểu đạt mood validated lâm sàng → biện minh màu-làm-input.

**Nguồn mới V26 đáng đọc full-text khi viết luận văn:** PLOS ONE 2015 pone.0144013 (effect sizes cross-modal) · MER meta ACM 3796518 (A vs V, NN không trội) · Ou cross-cultural (chroma/lightness r) · Nakatsuka WACV 2023 (vì sao KHÔNG dùng joint-embedding).

---

## 2. ĐÁNH GIÁ TOÀN DIỆN HƯỚNG ĐI HIỆN TẠI

### 2.1 ĐÚNG — giữ nguyên (giờ có thêm bằng chứng)
- Emotion-mediation V-A cho bài đầy đủ — **PLOS 2015 cho effect size, không chỉ định tính**.
- 2D V-A; σ_A<σ_V — **MER meta r=.81/.67 là số mới nhất**.
- arousal=audio / valence=lời; bỏ audio-valence Tây.
- arousal màu = Whiteford/HSL (**experiment xác nhận HSL thắng CIELAB-reg trên arousal**).
- RRF + targeting-error + structural battery + CI/FDR + beats-baseline.
- Màu-làm-input + UX (WCAG, cap 2 màu, journey waypoint sigmoid).

### 2.2 YẾU thật — xếp theo ROI (no-data)
| Ưu tiên | Vấn đề | Bằng chứng V26 | Hệ quả | Trạng thái code |
|---|---|---|---|---|
| 🔴 R1 | valence màu dùng HSL (không tri-giác-đều, mono L→V chỉ 0.44) | phase3 exp + Ou-cross-cult | journey kém mượt; valence màu kém chính xác | code đã recalibrate HSL r=.77; **chưa có CIELAB** |
| 🔴 R5 | editorial-GT trùng cơ chế scorer V-A | Dacrema; double-dipping | gate "đẹp" nhưng mất sức phân biệt | có harness; **chưa có cross-corpus** |
| 🔴 R2 | valence-lời corroborate yếu (ρ=.263); rủi ro circular | Kriegeskorte; Phase 2 | mắt xích yếu nhất trục valence | chưa có panel decoupled |
| 🟠 R3 | `−0.19·redness` sai văn hóa VN | Jonauskaite; SVM-country 80.2% | đỏ bị kéo valence xuống ngược trực giác Việt | đang hardcode trong `hsl_to_va` |
| 🟠 R4 | matching khoảng-cách-tuyệt-đối dễ vỡ commensurability; catalog lệch buồn | Saerens; Steck | quantile-adaptive (bản đúng) chưa thử | constant-σ đã fail |
| 🟡 R6 | ngôn ngữ claim dễ over-state | Jonauskaite (nation matters) | rủi ro học thuật | config đã ghi 1 phần |

### 2.3 Cạm bẫy literature dự án ĐÃ tránh đúng (không tự phá)
Calibrate một phía valence (Saerens) · audio-valence Tây (cross-corpus) · tin point-estimate (Dacrema → đã thêm CI/FDR) · over-fit n=12 weight (→ V-A-only + grouped-CV) · học joint-embedding không data cặp.

---

## 3. BRAINSTORM — LÀM TỐT HƠN MÀ KHÔNG CẦN DỮ LIỆU NGƯỜI DÙNG

### 3.1 Tín hiệu: nên THÊM gì, SỬA gì, BỎ gì?

**SỬA — color→valence sang CIELAB-Lch (R1, ROI cao nhất).**
Thay nhánh valence trong `hsl_to_va` bằng hồi quy CIELAB `[L*, a*, b*, C*, cos h, sin h]`. Coefficients đã có từ experiment
(`w_valence = [0.707, −0.636, −0.101, 0.554, 0.142, −0.049]`). **Giữ arousal Whiteford-HSL nguyên.**
*Lý do:* valence CIELAB r .85 vs .76 + **monotonicity L→V 0.81 vs 0.44** (quan trọng cho nội suy journey 2 màu); Ou-cross-cult chroma↔Activity r=.86.

**KHÔNG THÊM tín hiệu audio-valence / deep model.** MER meta: NN không thắng linear/tree ở V-A regression; cross-corpus valence Tây→Việt âm. Thêm chỉ làm hại — đã chứng minh (F4).

**CÂN NHẮC THÊM (tùy chọn, gate cứng): perceptual-color-distance phụ cho tie-break.** Khi nhiều bài cùng khoảng V-A,
dùng CIEDE2000 giữa màu query và "màu đại diện" của bài (suy từ song-V-A → màu) để xếp tinh. Rủi ro: vòng lặp V-A→màu→V-A.
→ chỉ làm nếu R5 cho thấy V-A-only mất sức phân biệt; mặc định **KHÔNG**.

**BỎ:** không có tín hiệu thừa rõ rệt (F2 đã bỏ lyr/emo-cosine). Giữ scorer V-A thuần.

### 3.2 Trọng số: tinh chỉnh gì?
- **σ_V, σ_A (0.20 / 0.14):** có nền (MER r .81/.67 → tỉ lệ ~0.14/0.18 nếu map tuyến tính; hiện 0.14/0.20 — hợp lý).
  Đề xuất: **grid-search nhỏ σ_V∈{0.16,0.18,0.20,0.22}, σ_A∈{0.12,0.14,0.16}** dưới targeting-error + battery, chọn theo CV chứ không tay.
- **−0.19·redness (R3):** quyết định chính sách, không phải tuning. 2 lựa chọn ở §4 Phase 1.
- **Journey sigmoid + cap 2 màu:** giữ (Iso-Principle, choice-overload meta ≈ 0).

### 3.3 Ý tưởng "no-data" khác đã cân nhắc & phán quyết
| Ý tưởng | Phán quyết | Lý do |
|---|---|---|
| Học joint-embedding màu↔nhạc (CLIP-style) | ❌ | Không có data cặp VN; Nakatsuka cần paired |
| Refit color→V-A trên hàng **châu Á** của ICEAS OSF (proxy VN) | 🟡 tùy chọn | thích nghi *một phần* văn hóa, no-data; chỉ giữ nếu thắng TE |
| Quantile/rank matching adaptive-σ (R4) | 🟡 tùy chọn | bản constant-σ fail; bản σ∝mật-độ chưa thử |
| Distant-supervision qua editorial mood playlist | ✅ đã có | nhưng tautological → cần cross-corpus bổ sung (R5) |
| Cross-corpus chấm song-V-A vs DEAM/PMEmo | ✅ làm (R5) | human-GT thật, ngoài cơ chế scorer |

---

## 4. PLAN FINAL — VÒNG ĐỜI ĐẦY ĐỦ MỘT FEATURE RECOMMEND

> Nguyên tắc xuyên suốt: **mọi thay đổi tín hiệu/trọng số phải gate bằng `tools/color_eval_rigor.py`
> (targeting-error + structural battery T1–T4 + beats-baseline + CI/FDR), KHÔNG per-piece, KHÔNG calibrate một phía,
> dùng matching scale-invariant khi đụng commensurability.** Đây là tinh chỉnh có kiểm soát, không teardown.

### PHASE 0 — Đóng băng nền khoa học ✅ (xong)
- Tài liệu nền: V25 (6 trục/29 nguồn) + §1 V26 (nguồn mới + verify).
- **Verify:** mọi quyết định cốt lõi có ≥1 nguồn primary [VERIFIED]/[SOURCED]. → **PASS** (đã có).
- **Output:** đoạn "cơ sở khoa học" cho luận văn/hội đồng (dùng §0–§1 + bảng nguồn §6).

### PHASE 1 — Tinh chỉnh tín hiệu (build, có gate)
Thứ tự theo ROI; mỗi bước là 1 commit độc lập, gate riêng.

**1A. R6 — Ngôn ngữ claim trung thực** (rẻ, làm ngay)
- Cập nhật block VALIDATION CLAIMS trong `config.py` + doc cuối: tách rõ **validated** (structural battery; targeting beats-baseline 5–6×; color-emotion universal r=.88; emotion-mediation 60–75% var PLOS 2015) vs **NOT** (human VN — trần).
- Câu chuẩn hội đồng: *"scientifically grounded + self-consistent + khớp vùng mood người-curate + corroborated bởi 1 model VN độc lập (ρ=0.263, yếu) + cross-corpus với human-GT non-VN (R5)"* — **KHÔNG "validated cho người Việt".**
- **Sửa mis-citation** `config.py:247`: "Eerola & Anderson arXiv:2302.13321 r≈0.81 vs r≈0.17" → đúng là **arXiv:2302.13321 = Krols et al "Multi-Modality in Music"** (multimodal>audio cho valence); con số **arousal r=.81 / valence r=.67 thuộc Eerola & Anderson 2026 (ACM 3796518, MER meta)**. Cập nhật cả `.claude/rules/ai-ml.md` nếu có dẫn lại.
- **Verify:** doc liệt kê đủ 2 cột; không câu nào claim "validated VN"; citation σ trỏ đúng nguồn. → đọc lại.

**1B. R1 — Color→valence: HSL → CIELAB-Lch (hybrid)** 🔴 ROI cao nhất
- Thêm nhánh valence CIELAB vào `core/advanced_color_mapping.py::hsl_to_va` **sau cờ** `COLOR_VALENCE_CIELAB` (default off → bật khi gate pass). **Arousal giữ Whiteford-HSL.**
- Transcribe coefficients từ experiment (hoặc refit lại + đọc full-text Ou&Luo Part I để lấy bảng hệ số chuẩn nếu muốn nền học thuật chắc hơn).
- **Verify (GATE CỨNG, theo thứ tự):**
  1. `python -m tools.phase3_cielab_experiment` — xác nhận lại valence Δr>0, mono L→V tăng. ✅ (đã: +0.09, 0.81 vs 0.44)
  2. `tools/color_eval_rigor.py` với CIELAB-valence bật: **targeting-error KHÔNG regress** (≤ 0.043 + CI overlap) + **T1 monotonicity tăng** + **T2 slope≈1 giữ**.
  3. `tools/color_journey_sequencing.py`: **monotonicity ρ ≥ hiện tại (0.896)** + max-gap ≤ 15% (journey mượt hơn là kỳ vọng chính).
  - Pass cả 3 → bật mặc định + xoá nhánh HSL-valence. Regress bất kỳ → giữ HSL, ghi negative result.
- **Lưu ý trung thực:** n=12 → CI rộng; bằng chứng quyết định là **monotonicity trên 200 màu + targeting-error trên catalog thật**, KHÔNG phải r trên 12 điểm.

**1C. R3 — Term văn hóa redness** 🟠 (quyết định chính sách — xem §5 câu hỏi chốt)
- **(a) Khuyến nghị:** giữ thuần-global, **document rõ giới hạn** (đỏ VN=may; SVM-country 80.2% chứng tỏ văn hóa thật nhưng in-group advantage dự-đoán-màu chỉ 6%). Rẻ, an toàn học thuật.
- **(b) Tùy chọn:** cờ `COLOR_VN_OVERLAY` opt-in giảm/đảo `−0.19·redness` cho đỏ no-bão-hoà-cao. Chỉ giữ nếu **không regress** TE.
- **Verify:** nếu (b), gate `color_eval_rigor` + ghi rõ là overlay tùy chọn.

### PHASE 2 — Backtest / khung đánh giá (đã mạnh, vá lỗ hổng)
Hiện có (giữ): `color_eval_rigor.py` (TE + bootstrap CI 10k + Benjamini-Hochberg FDR + baselines random/popularity/VA-only/valence-only/arousal-only) · `color_structural_battery.py` (T1–T4) · `color_journey_sequencing.py` · `color_baseline_eval.py` · ground-truth ICEAS non-circular (`backtest_v2/ground_truth/`).

**2A. R5 — Test end-to-end KHÓ HƠN (chống tautology)** 🔴
- **Cross-corpus V-A check:** chấm song-V-A của catalog bằng pipeline hiện tại, so với **DEAM (1802) / PMEmo (794)** human-GT (trên tập bài có thể map hoặc proxy theo đặc trưng). Báo cáo correlation + culture-penalty (kỳ vọng valence Việt lệch — ghi trung thực).
- **Discriminant pairs ngoài V-A:** cặp bài cùng quadrant V-A nhưng khác tín hiệu khác (tempo/MERT cluster) — kiểm scorer có phân biệt được không (tránh "mọi thứ trong quadrant = giống nhau").
- **Judge decoupled:** nếu dùng LLM-judge cho relevance, **không phải Gemini** (nguồn nhãn) — tránh double-dipping (Kriegeskorte).
- **Verify:** có ≥1 test dùng GT **ngoài cơ chế scorer V-A**; report kèm CI; ghi rõ giới hạn culture.

**2B. R2 — Củng cố trục valence (decoupled, no-data)** 🔴
- Panel valence **độc lập Gemini:** ViSoBERT + PhoBERT-sentiment + 1 LLM khác họ; rubric tiếng Việt **không dịch EN** (GlobalMood: dịch hại).
- Calibrate Gemini theo panel **CHỈ KHI** cải thiện TE dưới **artist-grouped nested CV** + dùng matching scale-invariant (không phá commensurability).
- Phân tích bài bất đồng (hip-hop code-switching, nhạc cưới bị label sai) → lọc/xử lý riêng.
- **Verify:** agreement panel↔Gemini tăng so với ρ=0.263; TE không regress dưới nested-CV. Không đạt → giữ nguyên + ghi.

### PHASE 3 — Test (regression + structural, tự động)
- **Unit/integration:** `test/test_color_reco.py` (σ_A<σ_V; quadrant 9 centroid; cap=2; journey monotonic ρ>0.5; artist diversity ≤40%; V-A∈[0,1]). **Thêm test** cho CIELAB-valence nếu 1B pass (mono L→V > HSL; 12 centroid vẫn đúng quadrant).
- **Negative control:** `color_negative_control.py` — shuffle song-V-A phải làm TE xấu đi rõ (tín hiệu thật, không phải artifact).
- **Verify:** toàn bộ `pytest test/test_color_reco.py` PASS + negative-control phân tách rõ.

### PHASE 4 — Loop cải thiện đến trần (tinh chỉnh sau khi đo)
> Chỉ vào Phase 4 sau khi Phase 1–3 xanh. Mỗi vòng: thay 1 thứ → gate → giữ/bỏ theo số.
1. **Grid-search σ_V/σ_A** dưới TE + battery (CV, không tay) → chốt cặp tốt nhất.
2. **R4 quantile-adaptive σ∝mật-độ** (tùy chọn) — chỉ nếu R5 cho thấy catalog-skew làm hại; bản constant-σ đã fail.
3. **ICEAS hàng-châu-Á refit** (tùy chọn) — proxy văn hóa VN, no-data; giữ nếu thắng TE.
4. **Re-run full rigor** sau mỗi thay đổi; cập nhật bảng claim (1A).
- **Tiêu chí dừng (trần):** không còn thay đổi nào cải thiện TE vượt CI **và** structural battery toàn PASS **và** journey mono ≥0.9. Khi đó **đóng băng** — đây là trần offline no-data (giống kết luận similar-song V2).

### Thứ tự & công sức
```
1A R6 claim doc        █        rẻ, làm ngay
1B R1 CIELAB-valence    █████    ROI cao nhất; experiment đã xanh, cần gate production
2A R5 test khó hơn      ████     chống tautology — giá trị hội đồng cao
2B R2 valence decoupled ██████   vá mắt xích yếu nhất
1C R3 redness           █        quyết policy (a) doc / (b) overlay
P4 grid-σ + tùy chọn    ████     sau khi P1–3 xanh
```

### DỨT KHOÁT KHÔNG LÀM (giữ từ V24/V25)
❌ Pair-study người · ❌ gold-set người mới · ❌ audio-valence Tây · ❌ calibrate một phía ·
❌ học joint-embedding màu↔nhạc end-to-end (cần data cặp VN) · ❌ thêm deep model cho V-A regression (MER meta: không thắng linear/tree).

---

## 5. CÂU HỎI CHỐT — ĐÃ QUYẾT (2026-06-10)
1. **Phạm vi V26:** ✅ **ĐÓNG BĂNG plan + nền ở đây.** Chưa thực thi code. Phase 1+ chờ lệnh riêng.
2. **R3 redness:** ✅ **(a) giữ thuần-global + document giới hạn.** KHÔNG mở VN-overlay. Lý do: SVM-country cho thấy văn hóa thật nhưng in-group advantage dự-đoán-màu chỉ ~6%; overlay từng bị loại; an toàn học thuật. → term `−0.19·redness` GIỮ NGUYÊN trong code; doc cuối ghi rõ "đỏ VN=may là giới hạn đã biết của model global".
3. **R1 CIELAB:** ⏳ treo theo (1) — khi nào bật thực thi, gate production (TE không regress + journey mono tăng) là điều kiện duy nhất để bật `COLOR_VALENCE_CIELAB`.

---

## 6. NGUỒN (primary, peer-reviewed) — V26 (V25 + mới)
**Mới V26 (vòng deep-research thứ 2):**
PLOS ONE 2015 cross-modal music→colour (pone.0144013, emotion 60–75% var, beats audio-only 3/4) ·
MER meta-analysis (ACM 3796518, A r=.81 > V r=.67, NN không trội) ·
Ou cross-cultural colour-emotion (Activity↔chroma r=.86, Potency↔lightness r=.95) ·
Nakatsuka WACV 2023 (content-based music-image retrieval, cross-modal embedding memory) ·
Eerola/Anderson multimodal valence (arXiv 2302.13321) · DEAM (1802) · PMEmo (794) ·
color-emotion SVM-country 80.2% (PMC6774957) · Docear offline-vs-online eval study · arXiv 2009.05103 / 2501.1094 / 2412.05831 (cross-modal DL).

**Từ V25 (đã fetch-confirm 2026-06-08):**
Palmer 2013 PNAS (1212562110) · Whiteford 2018 (Sage 2041669518808535, PMC6240980) · Jonauskaite 2020 (PubMed 32900287, r=.88) · Ou & Luo 2004 (Wiley col.20010) · Wilms & Oberfeld 2018 · Springer 2012 (s11704-012-0154-y) · Valdez & Mehrabian 1994 (PubMed 7996122) · GlobalMood 2025 (arXiv 2505.09539) · MER data-gap (arXiv 2510.04688) · RRF Cormack 2009 · Iso-Principle Starcke 2024 · Dacrema 2021 (aaai.12051) · Kriegeskorte 2009 (double-dipping) · Carruthers 2010 (Manchester Colour Wheel, PMC2829580) · Scheibehenne 2010 · Steck 2018 · Saerens 2002 · MTMM Campbell&Fiske 1959.

> ⚠️ **Trạng thái xác minh V26 (cập nhật 2026-06-10, ĐÃ verify lại sau khi reset limit):**
> deep-research vòng 2 fetch/extract 27 nguồn/128 claims; phase adversarial-verify ban đầu bị cắt do session limit
> (4 confirmed 3-0, 1 contested 1-2, 20 abstain 0-0 — KHÔNG bị bác). **Đã verify lại trực tiếp các claim LOAD-BEARING:**
> - ✅ **PLOS 2015 (pone.0144013):** 4/4 CONFIRMED (emotion 60–75% var: Size 75/Light 74/b* 66; beats audio-only 3/4; happy d=0.74, low-tension d=0.78; energy→hue d=0.48). **Caveat: N=22 (19 sau loại), 27 excerpt phim nhạc — N nhỏ.**
> - ✅ **DEAM (pone.0173392):** 2/2 CONFIRMED (1802 bài CC, 2Hz V-A; "arousal tốt, valence completely unsatisfactory").
> - ✅ **MER meta (ACM 3796518, Eerola & Anderson 2026):** CONFIRMED arousal r=.81 vs valence r=.67; MCC 0.87; NN KHÔNG trội regression (linear V=.784/A=.882, tree V=.750/A=.809 > SVM/NN; NN trội ở classification MCC=.931). 34 studies, 290 models.
> - ✅ **SVM-country (Jonauskaite 2019, rsos.190741):** CONFIRMED 80.2% acc, n=711, 4 nước, country-specific. **UNVERIFIED:** AUC 0.928 / in-group 6.1% / white-China (không truy cập full-text — đừng trích số cụ thể đến khi đọc PDF).
> - ✅ **arXiv 2302.13321 (Krols et al "Multi-Modality in Music"):** CONFIRMED multimodal>audio cho valence. **⚠️ MIS-CITATION cần sửa (1A):** `config.py:247` ghi "Eerola & Anderson arXiv:2302.13321 r≈0.81 vs r≈0.17" — SAI: 2302.13321 là Krols et al, KHÔNG chứa số đó; r=.81/.67 thuộc ACM 3796518. Sửa attribution (không đổi thiết kế — σ_A<σ_V còn vững hơn nhờ meta thật).
> - ✅ **Gao 2007 cross-cultural (col.20321):** CONFIRMED định tính (chroma+lightness là factor trội, hue & văn hóa "very limited" — hậu thuẫn R1 + R3 global). **UNVERIFIED:** số r=.86/.95 cụ thể (không thấy trong snippet).
> - ✅ Palmer/Whiteford/Jonauskaite-.88/Valdez-Mehrabian: đã fetch-confirm V25 (+2 cái confirmed 3-0 lần này).
> - ⚠️ **Contested (1-2):** "arousal giảm theo brightness, phải tách oppositely-signed" — over-claim bị bác; KHÔNG ảnh hưởng (ta dùng Whiteford cho arousal).
> **Kết luận verify:** tất cả claim load-bearing CONFIRMED → plan vững hơn. Còn lại = sub-number chưa khoá (đánh dấu UNVERIFIED) + ~103 claim non-load-bearing chưa verify (không trong plan).
> **Trước khi trích luận văn:** đọc full-text để khoá AUC 0.928, in-group 6.1%, Ou r=.86/.95; còn lại đã verify.

---

## PHỤ LỤC A — TRIAGE 128 CLAIM (giải trình "103 claim chưa verify")

> 2026-06-10. deep-research trích **128 claim** nhưng workflow chỉ đưa **top-25** vào verify trước khi hết session.
> Để không "bỏ mù" 103 claim còn lại, đã **khôi phục toàn bộ 128 từ transcript agent** và triage. Kết luận:
> **~90 trùng lặp/không áp dụng (bỏ có lý do), ~13 có giá trị (đã verify nhóm quyết-định + tích hợp dưới).**

### A.1 BỎ — có lý do (≈90 claim)
- **Trùng anchor đã verify** (color-emotion & MER cơ bản): r=.88 universal, Valdez-Mehrabian, Whiteford η²/Spearman, Ou&Luo 3-factor, metadata dataset ICEAS (DOI/ngày/N), Palmer US+Mexico, 12 SD scales, hue ordering valence/arousal, brightness chromatic≈achromatic… → **đã phủ bởi 25-verify hoặc V25.**
- **Không áp dụng kiến trúc của ta** (collaborative-filtering cold-start, semi-personalization, CTR, deep cross-modal cụ thể ta KHÔNG build): Deezer cold-start P@50, k-means warm-segment, contrastive fusion missing-modality, HRFormer/CLIP-ViT/MERT encoder blueprint, CrossMuSim A/B Huawei, CDCML MSE 0.095… → tham chiếu, **không đổi quyết định** (ta đã chốt KHÔNG joint-embedding vì no paired VN data).

### A.2 GIỮ + TÍCH HỢP — claim mới có giá trị (≈13)
| # | Claim | Verify | Tác động plan |
|---|---|---|---|
| #11 | arousal↔sat r_s=.720 / redness .755 / lightness −.549; valence↔lightness .484 | khớp code (Whiteford) | **Nguồn gốc hệ số arousal 0.37/0.36/0.27** — ghi rõ provenance |
| #126 | **valence phi-tuyến theo saturation, đỉnh ở MỨC TRUNG (η²=.343); hue→valence p=.051 ns** | PDF binary, chưa re-fetch | 🟠 **R1 refinement:** term `+0.55·S` tuyến tính → cân nhắc **bậc-2 chroma** (đỉnh giữa) |
| #114 | **MMVA (2501.01094): match image↔music qua V-A, similarity từ V-A distance** | ✅ CONFIRMED | **Validation độc lập SOTA-2025** cho kiến trúc V-A-RBF của ta |
| #7 | **MuCED (2507.04758): 2,634 cặp music-palette expert-validated, căn Russell V-A** | ✅ CONFIRMED | 🟢 **Cơ hội R5:** GT cross-modal color↔music thật (non-VN) — dùng cross-corpus |
| #44/45 | Emo-CLIM: joint-embedding image↔music **lấy emotion làm mediator** ("emotion có nghĩa tương đương xuyên modal") | SOURCED | Củng cố emotion-mediator; template NẾU sau này có paired data |
| #89/97/113 | IMEMNet / IMEMNet-C: image→music VA-mediated, **eval human-free bằng VA annotations** (IAPS/NAPS/EMOTIC + DEAM) | SOURCED | Template eval cho R5 (Recall@K, MRR, không cần user) |
| #30/#107 | British vs Chinese chỉ khác ở **tense-relaxed & like-dislike** (valence/preference biến thiên văn hóa, structural factor ổn định); lợi ích multimodal chỉ ở **valence** | SOURCED | **Củng cố lý do bất đối xứng:** valence=lời (văn hóa) / arousal=audio (ổn định) |
| #74/50/75/95 | offline nDCG r=.28, MRR r=.30 với rating user (CTR r=.78); "offline eval probably not suitable" | SOURCED | 🔴 **R6 trần trung thực:** offline-metric là proxy yếu cho thoả-mãn-người-dùng — ghi rõ giới hạn |
| #17/18/19 | CIECAM02 chuẩn hơn CIELAB; CIELAB blue→purple bất thường, von Kries sai ở non-reference white | SOURCED (wiki) | **R1 note:** chọn CIELAB (không CIECAM) vì swatch UI **không biến thiên điều kiện nhìn**; nhận giới hạn blue |
| #87 | color→emotion classifier 38.7%; **turquoise/green/purple YẾU nhất** (~18%), red/black mạnh (68%) | SOURCED | **Giải thích "turquoise borderline"** đã document — turquoise vốn nhập nhằng color-emotion |
| #48 | affective factor giải thích **58%** variance color-choice vs **42.6%** perceptual | SOURCED | Thêm số cho emotion-mediation (cùng hướng PLOS 2015) |

### A.3 Hệ quả cho plan (cập nhật nhẹ, KHÔNG đổi hướng)
1. **R1** thêm sub-task: thử **term chroma bậc-2** (đỉnh-giữa, #126) cạnh CIELAB-Lch tuyến tính; gate như cũ.
2. **R5** thêm nguồn GT: **MuCED (2634) + IMEMNet-C** — cross-corpus color↔music human-free, ngoài cơ chế scorer (mạnh hơn editorial-GT). *Lưu ý: non-VN → vẫn culture-penalty.*
3. **R6** thêm câu trần: offline-metric tương quan yếu với thoả-mãn-người-dùng (nDCG r≈.28) → KHÔNG suy ra "người dùng sẽ thích".
4. **Provenance** hệ số arousal (#11) + **giải thích turquoise** (#87) → đưa vào doc luận văn.
5. **Không có claim nào trong 103 lật đổ hướng đi**; MMVA + MuCED + Emo-CLIM (đều dùng V-A/emotion mediator) **củng cố mạnh** kiến trúc hiện tại.
