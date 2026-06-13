# Recommend-by-Colour — PLAN CHỈNH SỬA LẦN CUỐI (V24)

> 2026-06-08. Ràng buộc CHỐT: **không thu thập nhãn người mới**, **không có dataset nhạc Việt**
> (đã tìm exhaustive — không tồn tại công khai). Mục tiêu: đưa feature từ "thiết kế tốt,
> đo lỏng" → "đo nghiêm, dọn sạch, claim trung thực" rồi **ĐÓNG**. Không mở hướng mới cần data.
>
> Builds on: V21 audit (lỗ hổng rigor), V19 factor plan (V-A-only), V23 journey merge.

---

## Phase 0 — Thực tế dữ liệu (ĐÃ KHẢO SÁT — kết luận)

**KHÔNG có** dataset nhạc Việt gán V-A/mood (audio hay song-level). Tài nguyên no-human dùng được:

- **Bộ gán valence độc lập (khác họ Gemini):** `5CD-AI/Vietnamese-Sentiment-visobert` (XLM-R),
  `wonrax/phobert-base-vietnamese-sentiment` (PhoBERT). Output: polarity NEG/POS/NEU (proxy valence, KHÔNG arousal).
- **Calibrate text-valence VN:** UIT-VSMEC (6.927, 7 cảm xúc), UIT-VSFC (16k polarity). *Domain = mạng xã hội, KHÔNG phải lời nhạc.*
- **Màu→cảm xúc:** ICEAS raw OSF (CC-BY 4.0; có TQ/Nhật/Ấn/Philippines, **không VN**; là term↔term, không phải toạ độ). Ou&Luo 2004 hệ số CIELAB→affect (transcribe từ paper).
- **Validate arousal audio:** DEAM, PMEmo (V-A liên tục, Tây). GlobalMood (Hàn) làm proxy văn hóa.

**Trần chấp nhận (không vượt được nếu không có người):** KHÔNG claim "validated cho người Việt".
Claim tối đa hợp lệ: *"có cơ sở khoa học + tự nhất quán + khớp vùng mood người-curate + được một model tiếng Việt độc lập corroborate"*.

---

## Phase 1 — ĐỘ CHẶT ĐÁNH GIÁ (🔴 MUST, no-human, ƯU TIÊN SỐ 1)

> Đây là lỗ hổng lớn nhất (V21). Trả lời trực tiếp câu hội đồng/leader: *"Sao biết nó tốt?"*
> Toàn bộ tính bằng code trên catalog — 0 người, 0 dataset mới.

| # | Việc | Chi tiết |
|---|---|---|
| 1A | **Baseline mạnh** (Dacrema 2021) | random · popularity (artist-freq) · **nearest-V-A-only** · single-signal (chỉ-arousal / chỉ-valence). Scorer production PHẢI thắng mới được claim. |
| 1B | **Metric mục tiêu chính = V-A targeting error** | Khoảng cách giữa V-A màu yêu cầu và phân bố V-A của top-k trả về (Euclid + Mahalanobis). Đây là "relevance" không cần nhãn người. |
| 1C | **Steck KL-calibration** | Single màu: KL(phân bố quadrant yêu cầu ‖ trả về). 2 màu: quỹ đạo A→B có khớp đường thẳng V-A không hay sụp về vùng phổ biến. |
| 1D | **CI + FDR ở mọi nơi** | Bootstrap CI cho mọi metric; Fisher-z CI cho tương quan (L1 r=0.92 → CI [0.74,0.98]); Benjamini-Hochberg cho battery nhiều test. Bỏ mọi point-estimate. |
| 1E | **Beyond-accuracy** | coverage, Gini, entropy, ARP (popularity bias — Abdollahpouri), intra-list diversity, serendipity label-free (Vargas&Castells), robustness (nhiễu màu ε → Kendall-τ top-k). |

**Triển khai:** tool mới `tools/color_eval_rigor.py`, nối vào `tools/run_f1_validation.py`. Một report JSON + bảng số có CI.
**GATE / DONE:** production thắng *tất cả* baseline trên targeting-error với CI không chồng — HOẶC báo cáo trung thực chỗ chưa thắng. Không sửa số cho đẹp.

---

## Phase 2 — VALIDATE VALENCE BẰNG MODEL ĐỘC LẬP (🔴 MUST, no-human, vá mắt xích yếu nhất)

> Valence (Gemini-đọc-lời) là mắt xích yếu nhất + rủi ro circular. GIỜ có thể cross-check
> bằng model tiếng Việt **khác họ** mà KHÔNG cần người.

1. Chạy `5CD-AI/Vietnamese-Sentiment-visobert` (XLM-R, độc lập Gemini+PhoBERT) trên toàn bộ lời → polarity → proxy valence.
2. (Tùy chọn) thêm `wonrax/phobert-...-sentiment` → panel 3 bên.
3. Đo đồng thuận với Gemini v5c: Spearman ρ, quadrant-agreement, Cohen's κ. Phân tích bài bất đồng.
4. **Calibrate CÓ ĐIỀU KIỆN:** chỉ isotonic-align Gemini theo panel **NẾU** cải thiện targeting-error (1B) dưới CV. Gate cứng — KHÔNG calibrate một phía phá commensurability (đã hỏng 2 lần: L2 0.65→0.29).

**Triển khai:** `tools/valence_decoupled_validate.py`. Model tải HF (CPU ok).
**GATE / DONE:** ra được con số đồng thuận. Claim mới hợp lệ: *"nhãn valence được một model tiếng Việt độc lập corroborate (ρ=…)"* — KHÔNG phải "validated by humans".

---

## Phase 3 — HIỆN ĐẠI HOÁ MAP MÀU→V-A (🟡 SHOULD, no-data, trả lời "rule-based/n=12")

> Biến công thức HSL fit tay (12 điểm) → hồi quy có cơ sở. Đây là chỗ "rule-based" đáng nâng.

1. Thay `hsl_to_va` bằng **hồi quy CIELAB (Ou & Luo 2004)** — dùng hệ số đã công bố (transcribe). Liên tục toàn gamut, nội suy hành trình mượt hơn, có panel châu Á.
2. (Tùy chọn) refit trên **ICEAS OSF hàng châu Á** (TQ/Nhật/Ấn/Philippines) làm proxy văn hóa gần VN nhất — thích nghi văn hóa *một phần* không cần data VN.

**GATE / DONE:** KHÔNG được regress Phase-1 (targeting/calibration) + battery cấu trúc (T1 monotonicity, T2 slope≈1). Regress → giữ nguyên `hsl_to_va` hiện tại. *Đây là tùy chọn ROI trung bình, không bắt buộc để "đóng".*

---

## Phase 4 — DỌN NỢ & ĐÓNG KHUNG TRUNG THỰC (🔴 MUST, rẻ)

1. **Xóa `color_to_valence_arousal`** (khối `if h<=30 elif…` — đây MỚI là rule-based kiểu cũ thật sự); chuyển `color_to_audio` sang `hsl_to_va`.
2. **Dọn config chết:** `COLOR_SCORE_VALENCE_QUANTILE`, hằng anti-skew (đang OFF), `LABEL_BOOST`/`CROSS_MOOD_PENALTY`=0 — xóa hoặc đánh dấu inactive rõ ràng. Config phải phản ánh đúng lõi thực (= 1 kernel RBF 2D).
3. **Một nguồn sự thật** cho màu→V-A và màu→cảm xúc (loại bảng `emotion_color_profiles` hue-range nếu đã bị ICEAS thay).
4. **Doc cuối:** liệt kê rõ *cái gì đã validate* (structural, targeting, calibration, decoupled-valence agreement, beats-baseline) vs *cái gì KHÔNG* (human VN — trần chấp nhận). Ngôn ngữ claim trung thực để dùng trong luận văn.

---

## Phase 5 — DỨT KHOÁT KHÔNG LÀM (trần / do-not-retry)

- ❌ Pair-study người (ràng buộc) · ❌ thu thập gold-set mới.
- ❌ MERT/audio cho valence (cross-corpus DEAM→VN R² âm; mode VN ngược Tây — F4 đã chứng minh hại).
- ❌ Quantile-valence σ hằng (revert: ED 0.85→0.64).
- ❌ Gold-set 208 bài (provenance không tin — đã chốt bỏ).
- ❌ Calibrate một phía valence phá commensurability.
- ❌ Học cross-modal màu↔nhạc end-to-end (cần data cặp người Việt — không có).

---

## Thứ tự thực thi & công sức

```
Phase 1 (rigor)        ████████  ← làm TRƯỚC, giá trị cao nhất cho luận văn + production
Phase 2 (valence indep) ██████   ← vá mắt xích yếu nhất, no-human
Phase 4 (cleanup)      ███       ← rẻ, làm song song/cuối
Phase 3 (CIELAB)       █████     ← tùy chọn, chỉ làm nếu Phase 1 cho thấy targeting yếu
```

**Định nghĩa "ĐÓNG" (Definition of Done cho lần cuối):**
1. Phase 1 + 2 + 4 hoàn tất, gate pass, một report số có CI.
2. Production thắng baseline tầm thường (hoặc báo cáo trung thực).
3. Valence có cross-check độc lập.
4. Code sạch (không hàm/cfg chết), doc claim trung thực.
5. Commit. **Ngừng iterate.**

## Mỗi phase trả lời câu chất vấn nào

| Phase | Câu hội đồng / leader |
|---|---|
| 1 | "Sao biết nó tốt? Vượt baseline nào?" |
| 2 | "Valence VN tin được không? Có circular không?" |
| 3 | "Map màu n=12 thì học gì? Có rule-based/lỗi thời không?" |
| 4 | "Đâu là ML, đâu là luật? Code có sạch không?" |

## Nguồn
Palmer 2013 PNAS · Whiteford 2018 · Jonauskaite 2020 (ICEAS, OSF CC-BY) · Ou&Luo 2004 ColorRes&App ·
Cowen 2020 PNAS · Hu&Downie 2010 · Delbouys 2018 · MERGE 2024 · Dacrema 2021 TOIS · Schnabel 2022 ·
Steck 2018 RecSys · Vargas&Castells 2011 · Kaminskas&Bridge 2017 · Abdollahpouri 2021 · Starcke 2024 ·
GlobalMood 2505.09539 · UIT-VSMEC/VSFC (nlp.uit.edu.vn) · 5CD-AI/visobert · DEAM · PMEmo.
