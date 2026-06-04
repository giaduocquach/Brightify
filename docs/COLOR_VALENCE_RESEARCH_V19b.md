# Valence cho nhạc Việt — Kết quả 2 luồng research (V19b)

> Hoàn thiện 2 luồng deep-research về MERT-valence bị cắt do session limit (HANDOFF 2026-06-04).
> Chạy lại 2026-06-04, có web-search + đối chiếu nguồn + tự kiểm chứng đối nghịch.
> Builds on V19 (`COLOR_FACTOR_UPGRADE_PLAN_V19.md`) + V18 (`COLOR_FEATURE_REARCHITECTURE_V18.md`).

## Bối cảnh quyết định
- Catalog 5.548 bài nhạc Việt, **100% có lời**.
- Match màu↔bài bằng **khoảng cách V-A** (heteroscedastic RBF: σ_A=0.14 hẹp, σ_V=0.20 rộng).
- Nhãn v4: arousal = MERT-95M probe (Ridge/DEAM, CV R²=0.58); **valence = LLM qwen3 đọc lời** (chưa validate trên người Việt).
- Màu→V-A neo theo Jonauskaite 2020 ICEAS (12 màu, global).
- **Ràng buộc đau thương:** calibrate trục valence (isotonic/rescale tuyệt đối) đã **phá matching 2 lần** (NDCG 0.65→0.29; discriminant 4/4→0/4). Gốc rễ = Saerens 2002 *calibration ≠ alignment*: hệ matching chỉ cần nhất quán TƯƠNG ĐỐI; rescale 1 phía phá commensurability. Pearson/ICC affine-invariant nên không phát hiện được lệch-thang.

---

## LUỒNG 1 — Có nên XÂY MERT/audio-valence probe? → **NO-GO** (CONDITIONAL rất hẹp)

| # | Phát hiện | Nguồn | Tin cậy |
|---|-----------|-------|---------|
| 1 | "Valence gap" phổ quát: R² arousal ≫ valence trong toàn bộ MER. MFCC: A≈0.29 / V≈0.10. | Unimodal MER (DEAM); PLOS ONE 2017 (Aljanaki) | cao |
| 2 | Trần valence audio-only **in-domain** với SSL mạnh ≈ 0.50–0.57 R² (KHÔNG phải 0.2–0.3 — đó là của hand-crafted). MERT-only: DEAM V=0.497/A=0.595; EmoMusic V=0.566/A=0.740; PMEmo V=0.523/A=0.767. | arXiv:2502.03979 (Kang & Herremans 2025) | cao |
| 3 | **Cross-corpus = sụp đổ, đặc biệt valence.** EmoMusic→PMEmo: V=−0.09; →WCMED: V=−0.68 (R² ÂM = tệ hơn đoán trung bình). | arXiv:2510.04688 (2025) | cao |
| 4 | Thêm chord/key vào MERT cải thiện valence rất ít (+0.013…+0.030 R²) — khớp F4 nội bộ. | arXiv:2502.03979 Table II | cao |
| 5 | 95M vs 330M: lợi ích cho emotion không đáng kể → **không cần** 330M. Multi-layer aggregation (vs layer-8 đơn) là đòn bẩy chưa khai thác. | MERT (Li 2023); MARBLE | trung bình |
| 6 | Valence không chuyển xuyên văn hóa; mode trưởng/thứ là cue văn hóa-đặc thù (ballad buồn Việt dùng trưởng — F4 r=+0.023). | GlobalMood (arXiv:2505.09539) + F4 nội bộ | cao (hướng) / trung bình (số VN) |
| 7 | Lời là đòn bẩy valence đã validate: thêm lời 46.6%→57.1% (4-lớp). audio→arousal, lời→valence. | Hu & Downie ISMIR 2010; Delbouys ISMIR 2018 | cao |

**VERDICT:** 🔴 **NO-GO.** Lý do mạnh nhất: với 100% bài có lời, valence thuộc về lời (đã kiểm chứng), trong khi probe audio-valence từ DEAM (Western) vấp hình phạt cross-corpus khiến **R² rơi xuống âm** trên domain Việt, cộng mode trưởng/thứ đảo ngược. v4 hiện tại (arousal=MERT, valence=LLM-lời) đang **đúng khoa học**.

**Chỉ chuyển CONDITIONAL nếu:** (1) xuất hiện tỷ lệ đáng kể bài KHÔNG lời (instrumental → audio là fallback duy nhất — hiện KHÔNG thỏa); hoặc (2) một thử nghiệm ensemble nhỏ chứng minh gain DƯƠNG qua backtest. Nếu vẫn thử: **đừng dùng DEAM cross-corpus**; dùng distant-supervision in-culture (playlist Việt→quadrant), MERT-95M multi-layer, gate bằng backtest.

---

## LUỒNG 2 — Chiến lược valence tốt nhất (A/B/C/D) + KEY UNLOCK

| Phương án | Gain (VN) | Chi phí | Rủi ro phá commensurability | Tin cậy |
|---|---|---|---|---|
| **A** Audio→valence probe | Thấp (trần MER thấp) | TB–cao (cần nhãn VN) | TB | cao |
| **B** Cải thiện+calibrate LLM-lời | **TB–cao** | Thấp–TB (prompt+dev-set nhỏ) | **Cao NẾU raw-distance; ≈0 NẾU rank-matching** | cao |
| **C** Calibrate theo phân phối (label-shift) | TB (sửa skew buồn) | Thấp | Cao (chính dạng rescale đã làm hỏng) | TB |
| **D** Late-fusion audio+lyrics | TB–cao | TB (2 nhánh+tune) | TB (thang hỗn hợp mới) | cao |

**KEY UNLOCK (quyết định toàn báo cáo): chuyển matching valence sang RANK/QUANTILE scale-invariant TRƯỚC.**
- Ràng buộc "không được calibrate valence" KHÔNG phải vấn đề của valence — là vấn đề của **matching dùng khoảng cách tuyệt đối** (raw-distance RBF đòi 2 trục đồng-thang).
- Rank-fusion bất biến thang theo định nghĩa: RRF `Σ 1/(k+rank)`, k≈60, "no calibration/normalization between systems" (Cormack SIGIR 2009).
- Quantile normalization làm 2 phân phối trùng khít **mà bảo toàn thứ hạng** (Bolstad 2003) → isotonic/rescale valence KHÔNG đổi quantile → **không thể phá matching**.
- Copula: rank correlation chỉ phụ thuộc copula, bất biến dưới mọi biến đổi đơn điệu marginal (column transform không đổi rank-corr).
- Skew buồn 47–54% được quantile-transform **hấp thụ tự nhiên** (trải lại [0,1] theo thứ hạng).
- Lưu ý: rank-matching mất thông tin *độ lớn* khoảng cách valence — vô hại vì σ_V=0.20 vốn rộng (ít tin valence). **Giữ RBF cho arousal** (σ_A=0.14 hẹp, tin cậy) → matching lai: quantile cho valence + RBF cho arousal.

**Khuyến nghị ROI có thứ hạng:**
1. **(LÀM TRƯỚC, rẻ, gỡ chốt vĩnh viễn)** Chuyển matching valence → quantile/rank scale-invariant. Đo lại bằng chính NDCG + discriminant 4/4 cũ.
2. **(Gain cao nhất sau khi an toàn — Option B)** Cải thiện LLM-lời: rubric tốt hơn + few-shot anchor + ensemble + **isotonic calibrate trên dev-set VN nhỏ có nhãn người** (giảm JSD 8–14%, Inoshita 2026). **Giữ Qwen native Việt — TUYỆT ĐỐI không dịch sang tiếng Anh** (GlobalMood: dịch EN không cải thiện, mean r=0.13 < fine-tune bản địa).
3. **(Bổ trợ — Option C nhẹ)** Dùng phân phối mood từ playlist VN làm prior sửa over-negativity, kiểu Steck re-rank/quantile-target, KHÔNG rescale per-song.
4. **(Sau cùng — Option D)** Fusion w_lyrics>w_audio. **(Bỏ — Option A)** audio-valence probe.

---

## Tóm tắt 1 câu (hội tụ 2 luồng)
**KHÔNG xây MERT-audio-valence** (cross-corpus → R² âm, mode Việt ngược, lời đã đủ); thay vào đó **đổi matching valence sang rank/quantile scale-invariant** (gỡ vĩnh viễn ràng buộc đã phá calibration 2 lần) rồi mới **cải thiện + isotonic-calibrate LLM-lời native Việt** trên một dev-set người-chấm nhỏ. Gate mọi thay đổi bằng `tools.run_f1_validation`.

## Claims CHƯA kiểm chứng / cần thận trọng
- Cormack 2009 RRF: PDF gốc không parse; tính bất-biến-thang xác nhận qua 2 nguồn thứ cấp + công thức khớp.
- Không có paper nào đo **trực tiếp trên nhạc Việt**; mọi số là ngoại suy từ low-resource/non-English (GlobalMood). "r≈0.34–0.50 affect VN" khớp khoảng nhưng không có số chính xác.
- MERT-paper báo R²V>R²A trên EmoMusic = nghi lỗi hướng cột (ngược mọi reproduction) → tin theo 2502.03979 (A>V).
- Delta Ridge-vs-MLP, multi-layer-vs-layer8 cụ thể cho valence: không có số định lượng.
- σ_V=0.20 "đủ rộng để rank-matching vô hại" + áp Steck cho V-A liên tục: đánh giá kỹ thuật của tác giả report, cần A/B backtest xác nhận.
