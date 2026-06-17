# Recommend-by-Colour — Kiến trúc lại trên cơ sở khoa học (V18)

Date: 2026-06-03. Tổng hợp 3 luồng deep-research (scale-alignment · song-emotion arch · end-to-end
validation) + 2 thực nghiệm calibration thất bại. Mục tiêu: giữ đúng triết lý **màu → cảm xúc → nhạc**,
đưa song-emotion về sạch **audio→arousal + lyrics→valence**, mọi bước verifiable.

---

## 0. Triết lý ĐÚNG và đã được khoa học chống lưng

Whiteford 2018 (i-Perception): dùng **partialling test** chứng minh match nhạc↔màu **được trung gian
bởi Valence-Arousal** — sau khi loại biến cảm xúc, mọi tương quan tri-giác màu↔nhạc sụp về vô nghĩa.
Palmer 2013 (PNAS): tương quan cảm-xúc-nhạc ↔ cảm-xúc-màu-được-chọn r=.89–.99 trong **tác vụ người
match trực tiếp**. → Cây cầu V-A là đúng. **Giữ nguyên triết lý.**

---

## 1. Vì sao 2 lần calibration thất bại (chẩn đoán đã được xác nhận)

**Calibration ≠ Alignment** (Saerens 2002; Alexandari 2020 ICML):
- *Calibration* = chỉnh một tín hiệu khớp thang tuyệt đối (đúng khi giá trị được tiêu thụ trực tiếp).
- *Alignment* = làm hai biểu diễn **tương thích với nhau** để khoảng cách/thứ hạng có nghĩa (đúng cho
  matching/retrieval).
- Mình đã làm calibration (sửa valence bài về thang người) trong một hệ **matching** chỉ cần
  alignment → kéo lệch một bên → vỡ.

**Bằng chứng "đắt giá" nhất (Thread 3):** *Pearson/ICC từng-phía BẤT BIẾN với phép dịch affine* →
**về mặt toán học không thể phát hiện** lỗi lệch-thang đã phá matching. Gold-set "pass" (ICC 0.96)
nhưng ghép lại vỡ — đúng signature này. → **per-piece validation là cần, KHÔNG đủ.**

**Catalog-skew (47% sad) là mấu chốt:** rank/quantile-match thuần sẽ map "màu trung tính → bài trung
vị = sad". Phải **chia bớt prior catalog** (label-shift, Saerens/Lipton) hoặc lái phân bố kết quả theo
**màu query** chứ không theo catalog (Steck 2018 Calibrated Recommendations).

**Cảnh báo culture-offset:** ICEAS là *global*, rater là *Việt* → một phần lệch thang nằm ngay ở
**phía màu**, không chỉ phía bài.

---

## 2. Kiến trúc đích — Song-emotion (audio→arousal + lyrics→valence)

Đồng thuận literature (Hu&Downie 2010; Delbouys 2018; MERGE 2024; Yang&Chen 2012):
**arousal là thuộc tính audio, valence là thuộc tính lyrics** — nhưng **fusion cải thiện valence**.

```
AUDIO ─► MERT embedding ─► AROUSAL probe (DEAM)      ─► A    (giữ nguyên; r=0.83 vs người Việt ✓)
                          └► VALENCE_audio probe (mới) ─► V_A  (phụ — "phanh" LLM over-negativity)
LYRICS ─► LLM Qwen3 đọc lời ─► VALENCE_lyrics          ─► V_L  (chính)

FUSE (chỉ valence, late, học trọng số, w_L > w_A):
   V_raw   = w_L·V_L + w_A·V_A           (nhạc không lời ⇒ w_L=0, fallback audio)
   V_final = isotonic_calibrate(V_raw)    ← sửa "quá tiêu cực" (chỉ áp khi cũng đã lo phía màu!)
   conf    = g(|V_L − V_A|, lyrics_present)   ← độ tin = mức đồng thuận 2 kênh (auditable)
LABEL: fused_emotion = Russell_quadrant(V_final, A)   ← suy ra từ V-A, KHÔNG mô hình rời
```

- **Arousal: giữ audio-only** (đồng thuận mạnh nhất; thêm lyrics chỉ thêm nhiễu).
- **Valence: lyrics CHÍNH + audio PHỤ (late-fusion)** — audio kéo bài "nhạc vui/lời buồn" về trung
  tính, đúng cái lỗi sad/tense RMSE 0.23 cần.
- **Categorical suy ra từ V-A** (Eerola 2011: dimensional ≥ discrete; tránh "sad nhưng valence dương").
- **Uncertainty trung thực:** Watcharasupat 2025 — model-variance KHÔNG bắt được rater-disagreement;
  dùng **đồng thuận 2 kênh |V_L−V_A|** làm proxy độ tin, auditable, ship được.
- **47% sad = một phần artifact** (LLM English-norm mis-map ballad Việt) → calibrate + fusion sẽ giảm;
  audit lại phân bố sau mỗi fix.

**Hợp đồng verifiable (gate trước khi ship):** arousal r≥0.83+CCC · audio-valence báo r/RMSE riêng ·
lyrics-valence post-calib RMSE ≪ 0.23 trên subset sad/tense · **fusion ablation phải thắng kênh đơn
tốt nhất** trên cùng hold-out, không thì ship lyrics-only-calibrated · calibration curve gần đường chéo.

---

## 3. Kiến trúc đích — Cây cầu & Matching (phần đã làm sai)

**Nguyên tắc: anchor CẢ HAI phía về một thang tham chiếu chung phi-prior — KHÔNG calibrate một bên lẻ.**

1. **Thang tham chiếu chung:** tập anchor nhỏ trên thang người Việt — Russell circumplex landmarks +
   một ít cặp màu↔mood↔bài do rater Việt chấm. (Isotonic nếu ≥1000 điểm; Platt/affine nếu vài chục.)
2. **Map đơn điệu mỗi trục cho MỖI modality về anchor** → color-V và song-V đồng-calibrate → lỗi
   "đen vs bài-buồn" biến mất theo cấu trúc.
3. **Chống skew:** chia bớt mật độ catalog (label-shift) HOẶC lái phân bố kết quả theo màu query
   (Steck 2018). Kiểm tra: màu trung tính KHÔNG trả kết quả lệch-sad.
4. **Giữ RBF nhưng σ theo trục (heteroscedastic):** σ HẸP cho arousal (r=0.83, tin), σ RỘNG cho valence
   (r=0.70, nhiễu/lệch) — cách chuẩn mã hóa "tin arousal hơn valence", hạn chế tác hại valence lệch.
5. **Fallback rank-based** (quantile theo *reference*, không theo catalog) — A/B với RBF.

---

## 4. Kiến trúc đích — Validation (chuyển sang gold-standard thật)

**Quyết định gold-set: GIỮ song-V-A gold-set nhưng HẠ vai trò** (neo calibration + đầu vào test
falsify). KHÔNG bỏ. Nhưng **thêm cái còn thiếu = gold-standard thật:**

**Color-song-match gold-set (đúng cách Palmer/Whiteford):** người Việt chấm trực tiếp **"bài này hợp
màu này không"**:
- Palette phủ V-A (không phải 12 ad-hoc — dùng kiểu mảng 16–24 màu tile đều, gồm các cặp đối nghịch).
- ~60–120 bài stratified 4 quadrant (dùng 208 bài làm khung).
- 2 tác vụ: **rating 1–7** (graded) + **forced-choice** kiểu Palmer (chọn màu hợp nhất/kém nhất → relevant/hard-negative).
- ≥15–20 rater; ICC(2,k)≥.75 / Krippendorff α≥.67. **Judge ≠ labeler** (sửa circularity L2/Qwen — Kriegeskorte 2009).

**3 test falsify cây cầu (chạy TRƯỚC khi tin điểm composed):**
- **S2 Commensurability:** fit `color_VA ≈ a·song_VA + b` trên cặp chấm cả 2 modality → hợp lệ chỉ khi
  **a≈1±0.15, b≈0**; lệch → phải align rồi test lại. *(Đây là test bắt được lỗi mà Pearson/ICC mù.)*
- **S3 Mediation (Whiteford):** V-A-distance dự đoán fit; sau khi loại V-A, tương quan tri-giác dư
  phải sụp (p>.05). Sụp ⇒ match đúng là cảm-xúc-trung-gian.
- **S4 Retrieval non-circular:** P@k/nDCG/MRR + Spearman(VA-dist, human-fit) trên gold-set match,
  judge≠labeler, beat baseline shuffle-màu + hue-only.

| Stage | Test | Pass bar |
|---|---|---|
| S0a | color→V-A vs ICEAS | r≥.80 (có .85) |
| S0b | song→V-A vs human | ICC(2,k)≥.75 (có .96) |
| S1 | match gold-set tin cậy | ICC≥.75 / α≥.67 |
| S2 | commensurability a,b | a≈1, b≈0 |
| S3 | emotion-mediation | V-A sig; tri-giác dư n.s. |
| S4 | retrieval end-to-end | beat baseline p<.05 |
| S5 | opposite-colour (L3) | tách > chance |

---

## 5. Lộ trình (mỗi bước verifiable, rủi ro thấp → cao)

| # | Việc | Cần data người? | Đo bằng | Trạng thái |
|---|---|---|---|---|
| **R1** | **Heteroscedastic RBF** (σ_arousal hẹp, σ_valence rộng) — mã hóa arousal>valence (đã validate) | KHÔNG | L3 + human-VA GT + S2 | làm được NGAY |
| **R2** | **Audio-valence probe** (MERT→valence) + late-fusion w_L>w_A + ablation | dùng gold-set 208 có sẵn | ablation hold-out | làm được, vừa |
| **R3** | **Co-calibration 2 phía** về anchor chung (gồm calibrate màu về rater Việt) | cần **color-V-A** 12+ màu (nhỏ) | S2 (a≈1,b≈0) | cần data nhỏ |
| **R4** | **Anti-skew** (label-shift / Steck) — màu trung tính không lệch sad | KHÔNG | phân bố kết quả vs query | làm được, vừa |
| **R5** | **Color-song-match gold-set** + bộ test S2/S3/S4 + sửa L2 circular | cần **match ratings** (lớn) | S1–S4 | gold-standard, cần data |
| **R6** | Re-derive categorical từ V-A; audit lại 47% sad sau R2/R3 | — | phân bố vs human | sau R2/R3 |

**Nguyên tắc xuyên suốt:** gate mọi thay đổi đụng matching bằng **metric end-to-end** (human-fit
ranking), KHÔNG bằng lỗi từng-phía (đó là cái đã giấu lỗi). Mỗi bước có ablation/test riêng.

---

## 6. Bắt đầu từ đâu (khuyến nghị)
- **R1 (heteroscedastic RBF)** — làm ngay, không cần data mới, mã hóa đúng "tin arousal hơn valence"
  mà gold-set đã chứng minh; gate L3 + human-VA GT.
- Song song chuẩn bị **R3+R5 data** (color-V-A 12 màu + một ít cặp màu-bài) — nhỏ, mở khóa
  co-calibration + gold-standard validation.
- R2 (audio-valence probe) khi muốn sửa gốc bias valence.

## Nguồn chính
Palmer 2013 PNAS · Whiteford 2018 i-Perception · Saerens 2002 Neural Comput · Alexandari 2020 ICML ·
Lipton 2018 ICML · Steck 2018 RecSys · Sun&Saenko 2016 CORAL · Niculescu-Mizil&Caruana 2005 ·
Hu&Downie 2010 ISMIR · Delbouys 2018 ISMIR · MERGE 2024 · Yang&Chen 2012 TIST · Eerola&Vuoskoski 2011 ·
Watcharasupat 2025 · Kriegeskorte 2009 Nat Neurosci · Jonauskaite 2020 Psych Sci.
</content>
