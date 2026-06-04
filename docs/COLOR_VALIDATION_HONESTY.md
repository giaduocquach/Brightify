# Recommend-by-Colour — Honesty Ceiling & Known Limitations

> Date: 2026-06-04. Mô tả đúng những gì hệ thống đã và chưa validate được,
> theo tiêu chuẩn khoa học. Không over-claim, không under-claim.

---

## CÓ THỂ claim (đã validate, có cơ sở)

### 1. Construct validity qua MTMM triangulation (Campbell & Fiske 1959)
Battery 4 tầng độc lập, không có tầng nào circular với scorer:

| Tầng | Phép đo | Kết quả | Nguồn GT |
|---|---|---|---|
| **L1** | Colour→V-A vs ICEAS human norms (12 màu) | Valence Pearson r=0.92 | Jonauskaite 2020 (external) |
| **T1/T2/T3** | Structural battery: monotonicity, commensurability slope≈1, distribution | ALL PASS | Tính bất biến toán học |
| **ED** | Editorial playlist distant-supervision Việt, artist-grouped CV, macro-F1 | Qprec=0.854 | Playlist người curate (external) |
| **L3** | Discriminant: PoLL panel (Qwen3+Gemini), lyrics axis (≠ V-A math) | 4/4 SEP, AUC 0.92-1.00 | Verga 2024 PoLL |

### 2. Baseline vượt rõ ràng
- **Calibration KL**: production=2.533 vs random=14.632 vs popularity=14.833 (~6× tốt hơn random).
- **F1 ALL PASS** sau mọi phase; **smoke test 21/21**.

### 3. Arousal xuyên văn hoá là chính danh
Arousal được dẫn dắt bởi loudness/tempo (culture-neutral) → chuyển giao Tây→Việt đã validated qua proxy correlations: Spearman(arousal_v2, energy)=+0.81, (LUFS)=+0.73, (neg-danceability)=+0.86. Cơ sở: Schubert 2004; Egermann 2015 Frontiers.

### 4. Valence grounded (lyrics-dominant)
Valence=Gemini-từ-lời, basis: Hu&Downie 2010 ISMIR (lyrics nâng mood classification 46.6%→57.1%); Delbouys 2018 ISMIR (audio→arousal, lyrics→valence). Decoupled spot-check (Gemini vs Qwen, AUC=1.0 separability).

---

## KHÔNG THỂ claim (trần bất khả kháng, không phải lỗi triển khai)

### 🔴 "Đã validated cho cảm nhận màu↔nhạc của người Việt"
**Không thể claim** — không có ground-truth nào đo trực tiếp "người Việt thích bài này khi nhìn màu này hay không". Mọi source GT là proxy:
- ICEAS: survey người Tây (30 quốc gia, nhưng không đại diện Việt Nam đặc thù)
- Editorial playlist: người curate dựa trên mood/genre, không phải colour-matching
- PoLL judge: LLM đọc lời, κ=0.191 (ceiling ~0.3 cho tiếng Việt, EMNLP 2025)

**Fix duy nhất**: pair-study nhỏ (~30-50 người Việt, vài trăm cặp màu↔bài, thuật ngữ bản ngữ). Đây là lựa chọn đã cân nhắc kỹ và chấp nhận không làm.

### 🟡 "Arousal chính xác tuyệt đối cho từng bài"
CV R²=0.58 đo trên DEAM (Tây). Recalibration (Phase 1) cải thiện distribution (std 0.095→0.180, >0.7 tăng từ 0.2%→14.6%) và ranking (gap RAP vs tình cảm 0.051→0.078) nhưng **không đo được** R² trên nhạc Việt thật.

---

## Known Limitations (documented, không phải bugs)

### Turquoise (#3AB09E) — KL=20.7, Qprec=0.0
- **Root cause**: ISCC-NBS centroid V=0.510 (chỉ 0.01 trên ranh Q3/Q4). Gemini gán nhiều bài bittersweet V=0.48 → những bài này gần turquoise hơn bài Q4 có V=0.55+. Catalog Q3 (32%) > Q4 (14%) → Q3 thắng.
- **Lý do không fix**: thay đổi centroid là vi phạm chuẩn ISCC-NBS; recalibrate formula riêng cho cyan là ad-hoc.
- **Honest position**: turquoise V=0.510 *là* borderline về mặt khoa học màu sắc — không sai khi engine trả bài bittersweet cho màu này.

### Catalog coverage 2% (111/5548 songs)
Feature này là mood-matching, không phải discovery. Top-10 × 12 màu = 120 slots. Chấp nhận.

### EILD diversity thấp (0.032 vs random 0.401)
Expected: feature hẹp V-A → results gần nhau trong không gian V-A. Không phải lỗi — tăng diversity bằng cách tăng `DIVERSITY_PENALTY` trong config.

### PoLL κ=0.191 (< ceiling 0.3)
Dưới ceiling đã biết (~0.3 cho tiếng Việt, multilingual LLM judge). L3 là bằng chứng bổ trợ discriminant, không phải trọng tài tuyệt đối. Cite: EMNLP 2025 "How Reliable is Multilingual LLM-as-a-Judge?".

---

## Claim đúng cho thesis/defense

> "Hệ thống gợi ý màu→nhạc Brightify đạt **construct validity** qua triangulation 4-tầng (MTMM, Campbell & Fiske 1959): colour-emotion mapping khớp chuẩn ICEAS (r=0.92); structural battery PASS; editorial playlist distant-supervision (macro Qprec=0.854) vượt baseline random 6×; discriminant PoLL panel (Qwen3+Gemini) phân tách 4/4 cặp màu đối nghịch (AUC 0.92-1.00). Hệ thống KHÔNG claim validated-for-Vietnamese-perception — trần này đòi hỏi pair-study người Việt chưa thực hiện, một giới hạn khoa học được ghi nhận rõ."
