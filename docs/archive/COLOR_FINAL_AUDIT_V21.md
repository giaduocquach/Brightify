# Audit cuối recommend-by-colour (V21) — sau Phase 1-4

> 2026-06-04. Kết hợp 2 luồng deep-research mới (bridge-model completeness + eval-rigor)
> với verify trạng thái thực. Kết luận trung thực: cái gì xong, cái gì còn yếu.

## Phán quyết 1 dòng
Feature **hoàn thiện về CHỨC NĂNG + có cơ sở khoa học cho THIẾT KẾ**, nhưng **EVALUATION chưa đạt chuẩn nghiêm ngặt của RecSys research** — 3 lỗ hổng rigor (point-estimate trên n nhỏ, baseline yếu, calibration bằng số magic chưa tune) + vài chiều completeness còn thiếu. **Tất cả sửa được không cần người.** "ALL PASS" trước đây là so với gate còn lỏng.

---

## A. Mô hình cầu nối (khoa học đã tốt nhất chưa?) → 2D V-A DEFENSIBLE

| Câu hỏi | Verdict | Nguồn |
|---|---|---|
| Thêm Dominance/PAD? | ❌ KHÔNG — không định lượng được lợi ích ở màu (Jonauskaite power ηp² không tách), dư thừa ở nhạc (tension r=−0.94 valence), marginal nơi khác | Valdez&Mehrabian 1994; Jonauskaite 2020; Eerola&Vuoskoski 2011 |
| Chuyển sang discrete? | ❌ KHÔNG — Cowen 2020 (13 emotion) cho thấy V-A bỏ sót *một phần*, NHƯNG dimensional thắng discrete cho nhạc nhập nhằng (R²=0.80 vs 0.73) | Cowen PNAS 2020; Frontiers 2023 |
| Tọa độ màu tốt hơn? | 🟡 CÓ — hồi quy CIELAB liên tục (Ou&Luo 2018, có data châu Á) > centroid-lookup ISCC-NBS tĩnh. ROI cao nhất nếu nâng bridge | Ou et al. 2018 Color Res&App |
| Cross-modal deep? | 🟡 Tương lai — Music2Palette 2025 vượt baseline thủ công NHƯNG cần data cặp màu↔nhạc (chưa có VN) | arXiv:2507.04758 |

→ **2D V-A giữ nguyên là đúng.** Nâng cấp khả dĩ (CIELAB liên tục) là tùy chọn ROI trung bình, KHÔNG bắt buộc.

---

## B. Độ nghiêm ngặt EVALUATION — 🔴 lỗ hổng thật (gồm lỗi Phase 1-4 của tôi)

| # | Lỗ hổng | Mức | Chi tiết |
|---|---|---|---|
| B1 | **Point-estimate trên n=12** | 🔴 MUST | L1 r=0.92 thực ra CI Fisher-z **[0.74, 0.98]** — rộng. Mọi metric cần CI/bootstrap, không phải 1 số. (Schnabel 2022) |
| B2 | **Baseline quá yếu** | 🔴 MUST | "vượt random 6×" — random là sàn thấp nhất. Cần popularity + naive-nearest-color + content-only, tune đầy đủ (Dacrema 2021 reproducibility) |
| B3 | **Phase 1 calibration = số magic** | 🔴 MUST | variance-expand về std=0.18 tùy ý + blend 0.65/0.35 CHƯA tune. Đúng ra: quantile-map arousal về DEAM/PMEmo (đã có), tune blend bằng Spearman vs proxy dưới CV. (Maraun 2013) |
| B4 | **Không FDR correction** | 🔴 MUST | battery nhiều test ở α=0.05 → lạm phát false-positive. Cần Benjamini-Hochberg |
| B5 | **Popularity-bias suite thiếu** | 🟡 SHOULD | coverage 2% = cờ đỏ. Thêm Gini + entropy + ARP trên phân phối item |
| B6 | **Artist fairness thiếu** | 🟡 SHOULD | KG artist-bias đã biết. Gini-trên-artist + group fairness |
| B7 | **Serendipity/robustness thiếu** | 🟡 SHOULD | unexpectedness label-free Pᵢ(u)−Pᵢ(U); robustness = perturb màu ε → Kendall-τ top-k |

---

## C. Trần bất khả kháng (chấp nhận)
- Không claim "validated cho người Việt" — không bộ norm nào (Jonauskaite/Ou) chứa VN; pair-study người là cách duy nhất. ĐÃ chấp nhận.

---

## KẾT LUẬN
- **Cơ sở khoa học (thiết kế):** ✅ đầy đủ, 2D V-A đúng, không cần thêm chiều.
- **Backtest:** 🟡 CÓ chạy (L1/T/ED/L3 + beyond-accuracy) nhưng CHƯA nghiêm — thiếu CI, baseline mạnh, FDR; calibration có số magic.
- **Chuẩn feature gợi ý:** 🟡 đạt phần lõi (relevance/diversity/novelty/coverage/calibration) nhưng thiếu popularity-bias/fairness/serendipity/robustness.
- **"Đã tốt nhất chưa?"** Chưa — nhưng các gap còn lại là về *độ chặt đo lường*, không phải *chất lượng gợi ý*, và đều fix được không cần người.

## Lộ trình V21 (nếu làm tiếp)
**MUST (rigor):** B3 quantile-map+tune blend → B2 strong baselines → B1 CI/bootstrap → B4 FDR.
**SHOULD (completeness):** B5 popularity-bias → B6 artist fairness → B7 serendipity/robustness.
**OPTIONAL (bridge):** CIELAB liên tục (Ou 2018).

## Nguồn chính
Palmer 2013 PNAS · Whiteford 2018 · Jonauskaite 2020 · Cowen 2020 PNAS · Eerola&Vuoskoski 2011 · Ou&Luo 2018 · Music2Palette 2025 (arXiv:2507.04758) · Schnabel 2022 (arXiv:2211.01261) · Dacrema 2021 TOIS · Maraun 2013 J.Climate · Steck 2018 · Vargas&Castells 2011 · Kaminskas&Bridge 2017 · Abdollahpouri 2021 · Fisher transformation.
