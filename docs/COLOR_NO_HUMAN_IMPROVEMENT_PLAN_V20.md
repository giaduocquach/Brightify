# Kế hoạch cải thiện recommend-by-colour KHÔNG cần người (V20)

> 2026-06-04. Tổng hợp 2 luồng deep-research (arousal-fix + validation-no-human), có nguồn trích dẫn.
> Mục tiêu: đưa feature lên mức cao nhất khả thi mà KHÔNG thu thập nhãn người, vẫn đúng cơ sở KH.
> Trần bất khả kháng (chấp nhận): không claim "validated cho tri giác người Việt" — cần human pair-study.

## Chẩn đoán gốc (đã verify bằng data)
- Vấn đề #1 (arousal chưa validate VN) và #3 (catalog lệch Q3=44.5%, grey→Q3=70%) là **MỘT vấn đề**: arousal probe (Ridge/DEAM) bị **nén phương sai do domain-shift** (mean 0.45, std 0.14, chỉ 3.8% >0.7; nhạc gym mean 0.461 dù tempo 115BPM). Nén arousal → đẩy bài vào quadrant thấp → skew.
- Valence đã fix (v5 Gemini). Arousal là mắt xích còn lại.

---

## RESEARCH KEY FINDINGS

### Luồng 1 — Arousal fix (không cần người)
- **Nén phương sai xuyên-corpus là artifact đã ghi nhận** (Hu & Yang 2017 IEEE TAC: cross-cultural MER degrade rõ, **arousal transfer tốt hơn valence**). Ridge MSE co biên độ về mean khi gặp domain mới (shrinkage).
- **Arousal chuyển giao Tây→Việt là chính danh KH** — arousal là phản ứng phổ quát với đặc tính audio mức thấp; valence mới bị văn hoá trung gian (Egermann 2015 Frontiers; Schubert 2004; Gabrielsson&Lindström 2001). → KHÔNG cần nghi ngờ toàn probe, chỉ cần sửa nén.
- **⚠️ Insight đối kháng quan trọng:** recalibrate đơn điệu (z-score/quantile) **bất biến Spearman** → sửa được *scale/phân phối* (quan trọng vì matching dùng khoảng cách V-A tuyệt đối) nhưng **KHÔNG sửa lỗi ranking per-item**. Muốn sửa "gym đọc ra trung tính" ở mức từng bài → **phải anchor vào proxy audio** (loudness trội nhất, tempo, onset-rate, spectral-flux).
- **Retrain = ROI thấp nhất:** probe DEAM R²=0.58 đã sát SOTA single-set 0.60 (arXiv:2502.03979); multi-dataset chỉ +0.02 arousal. Vấn đề là domain-shift, không phải năng lực probe. (Layer 8 có thể không tối ưu — unified MER dùng layer 5+6 — flag, có thể test sau.)

**Công thức đề xuất (ROI cao→thấp):**
1. **Proxy-arousal label-free** từ Essentia: z-score(loudness/LUFS chuẩn hoá, tempo, onset-rate, spectral-flux), trọng số ưu tiên loudness (Schubert).
2. **Blend** `0.6·MERT_arousal + 0.4·proxy` (tinh chỉnh qua backtest) → sửa ranking.
3. **Quantile-match** blend → phân phối tham chiếu DEAM∪PMEmo → khôi phục phương sai + cố định thang quadrant.
4. Gate: (a) Spearman(arousal, loudness/tempo) tăng; (b) gym/EDM > ballad/lo-fi; (c) std & %>0.7 khớp tham chiếu; (d) held-out R² PMEmo/EmoMusic không tụt.

### Luồng 2 — Validation no-human (MTMM framing)
- Battery hiện tại = **MTMM construct-validation** (Campbell&Fiske 1959): convergent (L1+editorial+LLM) + discriminant (L3). Distant-supervision có tiền lệ (MoodyLyrics/Çano 2017, Last.fm tags). **Claim được** construct validity + self-consistency + vượt baseline; **KHÔNG claim** validated-cho-người-Việt.
- **L3 → PoLL panel** (Verga 2024): {Qwen3 + Gemini 2.5-flash + 1 họ khác} bỏ phiếu, KHÔNG đổi sang 1 judge đơn. Prompt tiếng Việt + bắt giải thích, swap thứ tự (position bias), báo cáo Fleiss κ, **giữ judge ≠ labeler** (self-preference Panickssery 2024). Trần cứng κ≈0.3 cho tiếng Việt (EMNLP 2025) — coi L3 là bổ trợ.
- **Skew xử lý có nguyên tắc:** post-rank calibration KL (Steck 2018) hoặc prior-shift SLD (Saerens 2002), KHÔNG pre-weight hằng số. **Gate chống che-giấu:** toggle anti-skew on/off; nếu tắt làm per-quadrant recall quadrant thiểu số sập → signal hỏng, phải sửa scorer (= arousal), không đậy bằng anti-skew.
- **Chống tautology:** giữ pipeline nhãn editorial TÁCH HẲN scorer; thêm **random + popularity baseline** bắt buộc vượt; nDCG/MRR/MAP.
- **Beyond-accuracy không cần người** (Vargas&Castells 2011): calibration-KL (trung tâm), EILD (đa dạng V-A), EFD/EPC (chống popularity-bias), catalog coverage. RRF multi-màu đã chính danh (Cormack 2009).

---

## KẾ HOẠCH PHASED (mọi bước gate, không người)

### PHASE 1 — Sửa arousal (root cause của #1 + #3) ⭐ ưu tiên cao nhất
- `tools/build_arousal_proxy.py`: tính audio-arousal prior từ Essentia (loudness/tempo/onset/spectral-flux), z-score, loudness-weighted.
- `tools/recalibrate_arousal.py`: blend 0.6 MERT + 0.4 proxy → quantile-match về DEAM∪PMEmo → `data/arousal_v2.json`.
- `tools/validate_arousal.py` (gate battery): Spearman vs proxy, gym>ballad distant-supervision, distribution sanity, cross-corpus held-out R².
- Cập nhật `_recompute_song_va` dùng arousal_v2. Gate `run_f1_validation` + arousal battery.

### PHASE 2 — Re-derive quadrant + re-đánh giá skew
- Regenerate v5 labels với arousal mới (valence Gemini giữ nguyên). Đo lại Q3%.
- Quyết định anti-skew: nếu skew tự sửa → giảm/tắt anti-skew; nếu còn → chuyển sang Steck-KL re-rank có nguyên tắc (thay inverse-density hiện tại). Gate toggle on/off (per-quadrant recall).

### PHASE 3 — Nâng độ chặt validation
- L3 → PoLL panel (Qwen3+Gemini+1), prompt VN+giải thích, swap order, báo cáo Fleiss κ.
- Thêm baseline random + popularity vào editorial eval; thêm nDCG/MRR/MAP.
- Thêm beyond-accuracy: calibration-KL, EILD, EFD, coverage → `tools/color_quality_metrics.py`.

### PHASE 4 — Polish
- Unit test regression cho color path (`test/test_color_reco.py`).
- Turquoise borderline (V=0.51) — chấp nhận hoặc tinh chỉnh.
- Ghi rõ "honesty ceiling" vào doc/README.

## Nguồn chính
Hu&Yang 2017 IEEE TAC · Egermann 2015 Frontiers · Schubert 2004 Music Perception · Gabrielsson&Lindström 2001 OUP · arXiv:2502.03979 Unified MER · MARBLE NeurIPS 2023 · CORAL arXiv:1612.01939 · Campbell&Fiske 1959 · Verga 2024 PoLL arXiv:2404.18796 · Panickssery 2024 NeurIPS · Multilingual LLM-judge EMNLP 2025 arXiv:2505.12201 · Steck 2018 RecSys · Saerens 2002 Neural Comput · Vargas&Castells 2011 RecSys · Cormack 2009 SIGIR · Çano MoodyLyrics 2017.
