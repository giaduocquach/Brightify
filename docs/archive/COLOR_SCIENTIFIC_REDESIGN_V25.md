# Recommend-by-Colour — NGHIÊN CỨU KHOA HỌC LẠI TỪ ĐẦU + ĐÁNH GIÁ TOÀN DIỆN + THIẾT KẾ LẠI (V25)

> 2026-06-08. Ràng buộc giữ nguyên: **không dùng dữ liệu người dùng thật**, **không có dataset nhạc Việt gán nhãn**.
> Mục tiêu tài liệu này: dựng lại nền khoa học vững (6 trục, có nguồn + độ mạnh bằng chứng) để (1) đánh giá
> trung thực thiết kế hiện tại và (2) chốt hướng thiết kế lại đúng. Đây là tài liệu nền KH cho luận văn/hội đồng.
>
> Nguồn: deep-research 6 luồng (29 nguồn primary peer-reviewed) + đối chiếu kho V12–V24 của dự án.
> Builds on: V24 (rigor + cleanup), V19/V19b (factor + valence), V17 (audit), V16 (deep-dive).

---

## 0. KẾT LUẬN ĐIỀU HÀNH (đọc cái này trước)

**Phán quyết tổng:** Sau 13 vòng lặp (V12→V24), kiến trúc hiện tại **ĐÚNG HƯỚNG về mặt khoa học ở hầu hết quyết định cốt lõi.**
Việc "nghiên cứu lại từ đầu" này **xác nhận** chứ không lật đổ hướng đi. Thiết kế lại = **tinh chỉnh có mục tiêu**, không phải đập đi xây lại.

| Trục | Quyết định hiện tại | Phán quyết KH |
|---|---|---|
| Cầu nối cảm xúc V-A (color→emotion→music) | ✅ Đúng | Palmer 2013, Whiteford 2018: r=.89–.99, mediation mạnh-form |
| Không gian 2D Valence–Arousal | ✅ Đúng | Whiteford PARAFAC: V+A là 2 trục latent trung gian; GlobalMood: V-A bền văn hóa |
| Heteroscedastic σ_A < σ_V | ✅ Đúng | Arousal dự đoán tốt hơn valence **cả từ màu LẪN từ audio** (2 nguồn độc lập) |
| Arousal=audio, Valence=lời | ✅ Đúng | Cross-corpus valence Tây→Á R² **âm**; mode trưởng/thứ đảo ở VN |
| KHÔNG dùng audio-valence Tây | ✅ Đúng | arXiv 2510.04688 data-gap; F4 đã chứng minh hại |
| RRF multi-màu + targeting-error + structural battery | ✅ Đúng | Cormack 2009; Dacrema 2021 baseline rigor |
| Màu-làm-input | ✅ Đúng + khoảng trống TT | Manchester Colour Wheel (Carruthers 2010, validated lâm sàng) |
| **Map màu→V-A bằng HSL fit tay (n=12)** | 🔴 **Điểm yếu** | Lit: phải dùng **CIELAB Lch** (Ou&Luo 2004) — tri-giác đúng, có panel Á |
| **Valence = Gemini-đọc-lời** | 🔴 **Mắt xích yếu nhất** | Chỉ có corroboration độc lập YẾU (ρ=0.263); rủi ro circular |
| **−0.19·redness (đỏ→tiêu cực)** | 🟠 **Sai văn hóa VN** | Đỏ Tây=giận; đỏ Việt=may/vui. Global-only bỏ sót culture (Jonauskaite) |
| Calibrate valence một phía | ✅ Đã tránh (đúng) | Saerens 2002: calibration ≠ alignment, phá commensurability |

**3 việc đáng làm nhất (ROI cao, no-data):** R1 CIELAB, R2 củng cố valence decoupled, R5 test end-to-end khó hơn (chống tautology). Chi tiết §8.

---

## 1. TRỤC 1 — CƠ CHẾ TRUNG GIAN CẢM XÚC (color ↔ music)

**Câu hỏi:** Cảm xúc có thật sự làm trung gian giữa màu và nhạc không? V-A có phải không gian trung gian đúng?

### Bằng chứng (MẠNH)
- **Palmer et al. 2013, PNAS (PMC3670360)** — *"Music–color associations are mediated by emotion."* Người chọn màu hợp với nhạc; tương quan giữa cảm-xúc-nhạc và cảm-xúc-màu **mạnh: 0.89 < r < 0.99** qua các chiều cảm xúc và **cả hai văn hóa (US + Mexico)**. Nhạc nhanh + trưởng → màu bão hòa/sáng/vàng hơn; chậm + thứ → nhạt/tối/xanh hơn. Thí nghiệm song song (nhạc↔khuôn-mặt-cảm-xúc, mặt↔màu) củng cố: ghép qua **cảm xúc chung**, không phải cross-modal cảm giác trực tiếp. *(Mức: PRIMARY, cross-cultural US+Mexico, ✅ đã fetch xác nhận 2026-06-08.)* **⚠️ Đính chính số:** con số lẻ "happy/sad r=.97" thuộc thí nghiệm **khuôn mặt** song song, KHÔNG phải ghép nhạc–màu; khi trích cho luận văn dùng **dải 0.89–0.99** cho nhạc–màu, đừng gán số per-dimension cho màu.
- **Whiteford et al. 2018, i-Perception 9(6):1–27 (PMC6240980, "Bach to the Blues")** — replicate Palmer; **PARAFAC** rút ra đúng **2 trục latent = arousal + valence** trung gian. *(✅ đã fetch xác nhận 2026-06-08.)* **Strong-form mediation:** mọi tương quan đặc-trưng-tri-giác giữa nhạc và màu trở nên **không còn ý nghĩa thống kê sau khi partial-out cảm xúc**. *(Mức: PRIMARY.)*
- **Spence/Oxford (crossmodal correspondences)** — tài khoản "emotional mediation" là cách giải thích tốt nhất cho stimuli phức tạp giàu cảm xúc; **không đòi hỏi tương tự tri-giác**. *(Mức: PRIMARY review.)*
- **Brill, Multisensory Research 35(5)** — nhạc + ánh sáng được chấm "hợp nhau" hơn khi tương đồng V-A; endorse Palmer. *(PRIMARY.)*
- **PLOS ONE 2025 (pone.0322449)** — tương quan **trực tiếp** acoustic-feature→visual **yếu (<0.5)**; sadness có mediation cao nhất → ủng hộ trung-gian-cảm-xúc hơn trực tiếp. *(PRIMARY.)*

### Cảnh báo / điều kiện biên (đã verify trong session này)
- **Frontiers 2024 (fpsyg.2024.1520131)** — với **color↔TIMBRE** (timbre nhạc cụ đơn lẻ, KHÔNG phải bài đầy đủ): **semantic mediation giải thích tốt hơn emotional** cho lightness/saturation; happy/sad ít dùng mô tả timbre. → **KHÔNG lật đổ** cho bài hát đầy đủ; chỉ giới hạn: ở **mức timbre** kênh ngữ-nghĩa mạnh hơn kênh cảm-xúc. Hệ recommend ghép **bài hát đầy đủ** → emotion-mediation vẫn là cơ chế đúng.
- Spence: emotion giải thích **một phần**, không 100% — còn phần dư trực-tiếp/structural. Nên KHÔNG over-claim "toàn bộ tương ứng màu-nhạc là cảm xúc".

### ⇒ Phán quyết trục 1
**V-A emotion bridge cho bài hát đầy đủ là cơ chế ĐÚNG và được validate mạnh.** Thiết kế hiện tại (color→V-A→song-V-A) đứng trên nền vững nhất trong cả feature. Không thay đổi cơ chế. Cạm bẫy duy nhất: ngôn ngữ claim không được nói "toàn bộ" tương ứng là do cảm xúc.

---

## 2. TRỤC 2 — MÀU → CẢM XÚC / VALENCE-AROUSAL

### Bằng chứng
- **Jonauskaite et al. 2020, Psychological Science (PubMed 32900287)** — color-emotion **phổ quát mạnh**: pattern similarity trung bình **r=.88** qua **30 quốc gia / 22 ngôn ngữ**. **NHƯNG:** *"nation-level identity predicts color-emotion associations beyond the universal pattern"* → **một model màu→cảm-xúc thuần-global sẽ bỏ sót có hệ thống các ánh xạ đặc-thù-văn-hóa.** *(PRIMARY, đây là nguồn neo của dự án.)*
- **Ou & Luo 2004, Color Research & Application 29(3):232–240 (DOI 10.1002/col.20010, Part I)** — 31 quan sát viên (**14 Anh + 17 Trung Quốc** — đã có panel Á) chấm 20 màu trên 10 thang; factor analysis rút về **3 nhân tố trực giao: colour activity / weight / heat**; dự đoán bằng **mô hình định lượng dựa CIELAB**; **culture-independent** (đồng thuận Ou/Sato/Xin&Cheng). *(✅ đã fetch xác nhận 2026-06-08; sample Anh+Trung là cơ sở "có panel Á".)*
- **Wilms & Oberfeld 2018, Psychological Research** — thí nghiệm giai thừa: **cả 3** chiều (hue, saturation, brightness) đều ảnh hưởng có ý nghĩa lên arousal & valence — **không chỉ hue**. Saturation tác động lớn nhất lên **arousal (η²=.693)** > hue (.588) > brightness (.459). Valence: brightness (η²=.491) + saturation. *(PRIMARY.)*
- **Springer 2012 (s11704-012-0154-y)** — model color-emotion trong **không gian V-A** dùng CIELAB Lch: **lightness & chroma quan hệ tuyến-tính-dương với CẢ valence LẪN arousal, mạnh hơn hue**; và **arousal dự đoán-được tốt hơn valence từ thuộc tính màu** — *gương đôi với bất đối xứng audio-MER!* *(PRIMARY.)*
- **Valdez & Mehrabian 1994, J Exp Psychol: General 123(4):394–409 (PubMed 7996122)** — Munsell + mô hình PAD; **brightness & saturation lái pleasure & arousal** mạnh nhất quán, hệ số chuẩn hóa: **Pleasure = .69·B + .22·S**, **Arousal = −.31·B + .60·S**, Dominance = −.76·B + .32·S. → khớp trực tiếp với việc công thức valence của ta nặng `S` và lightness. *(✅ đã fetch xác nhận 2026-06-08.)*

### Không gian màu: HSL/sRGB SAI, CIELAB/CAM ĐÚNG
- sRGB/HSL **không đồng đều tri-giác**: "saturation" HSL ≠ chroma tri-giác; cùng ΔHSL cho khác biệt cảm nhận rất khác nhau theo vùng màu. Hệ quả trong code hiện tại: vàng thuần (#FFFF00) L_HSL=50% nhưng sáng tri-giác rất cao → công thức valence theo l01 hụt; đỏ thuần sat=100% → vống arousal. **CIELAB device-independent + xấp xỉ đồng đều tri-giác** → là chuẩn cho mọi model color-emotion trong literature (Ou&Luo, Springer 2012 đều dùng CIELAB Lch).

### Văn hóa (đặc biệt Việt Nam)
- Đỏ: Tây = giận/nguy hiểm; **Việt = may mắn, hỉ sự, Tết**. Trắng: Tây = tinh khôi; **Việt = tang**. Vàng: **hoàng gia/trang nghiêm**. → Jonauskaite xác nhận nation matters. Dự án **CHỌN thuần-global** (quyết định có ý thức), nhưng term **−0.19·redness** (đỏ→giảm valence) là **mảnh sai-văn-hóa-VN rõ nhất** trong code.

### ⇒ Phán quyết trục 2
1. **CIELAB là không gian đúng**, không phải HSL. Map `hsl_to_va` fit tay (n=12) là điểm "rule-based/lỗi thời" thật sự (đã đúng khi V24 flag Phase 3). **Nên chuyển sang hồi quy CIELAB Lch kiểu Ou&Luo.**
2. Saturation/chroma + lightness là **driver affect chính** (thường > hue). Công thức valence hiện tại có `0.55·S` — đúng tinh thần, nhưng dùng S của HSL nên lệch.
3. **Arousal dễ hơn valence từ màu** → củng cố thêm cho σ_A < σ_V (giờ có bằng chứng từ *cả hai phía* màu và audio).
4. Global-only là trade-off hợp lệ NHƯNG phải **ghi rõ là giới hạn** và xem lại term redness cho VN.

---

## 3. TRỤC 3 — ÂM NHẠC → CẢM XÚC (MER)

### Bằng chứng
- **GlobalMood 2025 (arXiv 2505.09539)** — cấu trúc **V-A của music emotion BỀN qua văn hóa** (US/Pháp/Mexico/Hàn/Ai Cập) → V-A là không gian affect cross-culturally hợp lệ cho MER. **NHƯNG nghĩa của từ-cảm-xúc cụ thể phân kỳ** ngay cả giữa từ-điển-tương-đương → ưu tiên **chiều V-A** hơn nhãn categorical khi cross-culture. MER datasets chủ yếu Tây/Anh → thiên lệch; GlobalMood (1180 bài, 59 nước, 2519 người, 5 văn hóa, 988k ratings) sửa điều đó. *(PRIMARY.)*
- **Bất đối xứng arousal-dễ / valence-khó** từ audio: kinh điển (Yang, Eerola). Arousal ↔ tempo/loudness/onset/brightness (dự đoán tốt); valence ↔ harmony/mode/lyrics (khó).
- **Lyrics là đòn bẩy valence**: Hu & Downie 2010 (lời nâng phân loại mood), Delbouys 2018 (audio+lyrics đa-mô-thức), MERGE 2024. *(PRIMARY/đã dẫn.)*
- **Cross-corpus valence THẤT BẠI**: arXiv 2510.04688 "Data Distribution Gap in MER". Dự án ghi nhận EmoMusic→PMEmo valence **R²=−0.09**, →WCMED **R²=−0.68** (V19b). Arousal transfer tốt hơn valence.
- **Mode trưởng/thứ KHÔNG phải cue valence phổ quát**: F4 của dự án — VPop buồn `mean_mode=0.625` > vui `0.511` (ballad buồn dùng trưởng). Mọi tín hiệu audio-valence (mode, Essentia) **HURT** với nhạc Việt (r≈+0.02 đến +0.22 với LLM-V).

### ⇒ Phán quyết trục 3
**Thiết kế hiện tại (arousal=MERT-probe, valence=Gemini-lời) đúng KH.** Quyết định không dùng audio-valence Tây là **bắt buộc đúng** (cross-corpus âm + mode đảo). Mắt xích yếu thật sự: **valence-lời chưa có validation độc lập mạnh** (Phase 2: ρ=0.263 với XLM-R = corroboration YẾU; ViSoBERT không generalize). Không sửa được triệt để nếu không có data VN, nhưng củng cố được (xem R2).

---

## 4. TRỤC 4 — CROSS-MODAL MATCHING / RETRIEVAL

### Bằng chứng
- **RRF (Cormack et al. 2009)** — vượt Condorcet và rank-learning cá nhân; **scale-free, rank-based** → robust với commensurability. Dùng đúng cho multi-màu. *(PRIMARY.)*
- **Heteroscedastic kernel** σ_A<σ_V — biện minh bằng độ-tin-cậy khác nhau (arousal tin hơn ở **cả** hai phía). Nguyên lý đúng.
- **Vấn đề commensurability** (hai thang V-A khác nguồn: màu vs bài): **Saerens 2002** — calibration ≠ alignment; calibrate **một phía** về thang tuyệt đối **phá vỡ** matching tương đối. Dự án đã hỏng 2 lần (L2 0.65→0.29, L3 4/4→0/4) → bài học khớp lý thuyết. **Rank/quantile/copula matching = scale-invariant** → đường ra đúng để gỡ vĩnh viễn ràng buộc.
- **Iso-Principle (Starcke 2024, Sage 10298649231175029)** — sequencing mood-trajectory có bằng chứng (d≈0.52). Journey waypoint (V23) có cơ sở; nhưng "2 màu = quỹ đạo A→B" là **thiết kế-có-cơ-sở chưa đo trực tiếp** → nhãn chữ + mũi tên gánh nghĩa.
- **Steck 2018 (calibrated recommendations) + Abdollahpouri (popularity bias)** — catalog lệch 47–54% buồn → matching nên **giữ phân bố mood của query**, không sụp về vùng phổ biến. Anti-skew (đã gỡ ở Phase 4) chính là ý này; nên **đóng khung lại như calibrated-recommendation** thay vì heuristic rời.

### ⇒ Phán quyết trục 4
RBF + RRF hợp lý và có nền. Targeting-error (V24 P1) là proxy "relevance" đúng khi không có nhãn. **Quantile/rank matching theo lý thuyết sạch hơn** nhưng bản constant-σ đã FAIL (ED 0.85→0.64) vì catalog cực lệch → cần **adaptive σ ∝ mật-độ-cục-bộ** (bản đúng chưa thử). Đây là nâng cấp tùy chọn, không bắt buộc.

---

## 5. TRỤC 5 — ĐÁNH GIÁ KHÔNG CÓ NGƯỜI DÙNG THẬT (label-free)

### Bằng chứng & ánh xạ vào dự án
- **MTMM (Campbell & Fiske 1959)** — convergent + discriminant validity qua nhiều trait × method. **Structural battery** của dự án (T1 monotonicity, T2 commensurability slope≈1, T3 discriminant) chính là một battery construct-validity kiểu MTMM. ✅ Đúng phương pháp.
- **Distant supervision qua editorial mood playlist** (Laurier 2009, MoodyLyrics, MIREX mood) — proxy end-to-end hợp lệ. Dự án có `color_editorial_grouped`. ⚠️ **Cạm bẫy tautology**: khi scorer = V-A-only thì nó tự trả cùng quadrant → editorial Qprec gần tầm thường (đã flag trong V17 honesty).
- **Dacrema 2019/2021 (aaai.12051)** — phải thắng baseline mạnh (random, popularity, nearest-neighbour). V24 P1 làm đúng: production TE=0.043 vs valence-only 0.233 / arousal-only 0.276 / random — thắng ~5–6×. ✅
- **Beyond-accuracy** (Vargas&Castells 2011 serendipity; Abdollahpouri ARP; coverage/Gini/entropy) — V24 P1E phủ. ✅
- **Circular analysis (Kriegeskorte 2009, Nature Neuroscience nn.2303 "double-dipping")** — cùng model vừa label vừa judge = circular. **Rủi ro Gemini-label-rồi-Gemini-judge** đã được flag đúng (L2 circular). → panel judge phải **decoupled** khỏi model label.
- **CI + FDR** (Benjamini-Hochberg) khắp nơi — V24 P1D. ✅ Fisher-z CI cho L1 (r=0.76 CI rộng vì n=12, đã ghi trung thực).

### ⇒ Phán quyết trục 5
**Khung đánh giá V24 là điểm MẠNH thật sự** và phù hợp ràng buộc no-user-data. Lỗ hổng còn lại:
1. 🔴 **Editorial-GT tautological** sau khi scorer thành V-A-only → cần test end-to-end **khó hơn** (không trùng cơ chế scorer).
2. 🔴 **Rủi ro circular trên valence** (Gemini là cả nguồn nhãn lẫn nền) — Phase 2 decoupled mới chỉ WEAK.
3. **Trần trung thực:** KHÔNG được claim "validated cho người Việt". Claim hợp lệ tối đa: *"có cơ sở khoa học + tự nhất quán + khớp vùng mood người-curate + được model VN độc lập corroborate (yếu)"*.

---

## 6. TRỤC 6 — UX & CẠNH TRANH

- **Manchester Colour Wheel (Carruthers et al. 2010, BMC Med Res Methodol 10:12, PMC2829580; validation học sinh 2012, 12:136)** — màu = công cụ biểu đạt mood **phi-ngôn-ngữ đã validated lâm sàng**: 105 khỏe / 108 lo âu / 110 trầm cảm; **vàng→mood bình thường, xám→lo âu/trầm cảm**; chọn "Yellow 14" giảm có ý nghĩa ở nhóm trầm/lo. → **biện minh mạnh nhất cho cơ chế màu-làm-input** (vượt "gimmick"). *(✅ đã fetch xác nhận 2026-06-08.)*
- **Choice overload** (Iyengar & Lepper 2000; **Scheibehenne 2010 meta-analysis: hiệu ứng mong manh, trung bình ≈ 0**) → 12 ô màu **ổn**, không cần sợ; nhưng giữ đơn giản (cap 2 màu — V23 — hợp lý).
- **WCAG 1.4.1 (Use of Color)** — KHÔNG bao giờ chỉ dựa màu; **bắt buộc** nhãn chữ + trạng thái non-color. Là yêu cầu accessibility, không phải tô điểm. (Dự án đã thêm aria-pressed + nhãn — ✅.)
- **Cạnh tranh:** không app stream lớn nào dùng **màu làm input chính** (Spotify/Apple/YT = text/preset/inferred; Musicovery = pad V-A; Moodagent = sliders; picture-to-playlist = ảnh). → **khoảng trống thị trường thật**, màu-làm-input là điểm khác biệt.

### ⇒ Phán quyết trục 6
Cơ chế màu-làm-input **vững** (Manchester Colour Wheel) + **có khoảng trống TT**. Quyết định UX (12 ICEAS swatch, cap 2 màu, WCAG labels) đều có nền. Không cần đổi.

---

## 7. ĐÁNH GIÁ TOÀN DIỆN THIẾT KẾ HIỆN TẠI (tổng hợp)

### 7.1 Cái gì ĐÚNG (giữ nguyên)
- Cầu V-A emotion-mediation cho bài đầy đủ (Palmer/Whiteford).
- Không gian 2D V-A (Whiteford PARAFAC; GlobalMood cross-culture).
- σ_A < σ_V heteroscedastic (giờ có bằng chứng **cả 2 phía**: màu Springer-2012 + audio Eerola).
- arousal=audio / valence=lời; KHÔNG audio-valence Tây (cross-corpus âm + mode đảo VN).
- RRF multi-màu; targeting-error + structural battery + beats-baseline + CI/FDR (rigor V24).
- Màu-làm-input (Manchester Colour Wheel) + UX (WCAG, cap 2, 12 swatch).

### 7.2 Điểm YẾU thật (xếp theo ROI sửa, no-data)
| Ưu tiên | Vấn đề | Nguồn KH | Hệ quả |
|---|---|---|---|
| 🔴 R1 | `hsl_to_va` HSL fit tay n=12 (không tri-giác-đều) | Ou&Luo 2004; Springer 2012; Wilms&Oberfeld 2018 | vàng/đỏ lệch; nội suy hành trình kém mượt; "rule-based" |
| 🔴 R2 | Valence=Gemini-lời chỉ corroborate YẾU (ρ=0.263); rủi ro circular | Kriegeskorte 2009; Phase 2 | mắt xích yếu nhất của trục valence |
| 🔴 R5 | Editorial-GT **tautological** với scorer V-A-only | Dacrema 2021; double-dipping | gate "đẹp" nhưng mất sức phân biệt |
| 🟠 R4 | Matching tuyệt-đối-khoảng-cách dễ vỡ commensurability; catalog lệch buồn | Saerens 2002; Steck 2018 | quantile-adaptive chưa thử (bản đúng) |
| 🟠 R3 | `−0.19·redness` sai văn hóa VN (đỏ=may) | Jonauskaite 2020 | đỏ bị kéo valence xuống ngược trực giác Việt |
| 🟡 R6 | Claim/ngôn ngữ dễ over-state | Jonauskaite (nation matters); trần no-human | rủi ro học thuật khi bảo vệ |

### 7.3 Cạm bẫy literature đã cảnh báo mà dự án ĐÃ tránh đúng
- Calibrate một phía valence (Saerens) — đã tránh sau 2 lần hỏng.
- Dùng audio-valence Tây (cross-corpus) — đã bỏ.
- Tin point-estimate (Dacrema) — đã thêm CI/FDR.
- Over-fit n=12 weight (selection-on-test) — đã chuyển V-A-only + grouped-CV.

---

## 8. THIẾT KẾ LẠI — HƯỚNG ĐÚNG (no-user-data)

> Nguyên tắc: **mọi thay đổi gate bằng `tools.run_f1_validation` (targeting-error + structural battery), KHÔNG per-piece, KHÔNG calibrate một phía.** Đây là tinh chỉnh, không teardown.

### R1 — Color→V-A: HSL → **CIELAB Lch regression** 🔴 (ROI cao nhất)
- Thay `hsl_to_va` bằng hồi quy trên đặc trưng CIELAB `[L*, C*, cos h, sin h]` (+ Ou&Luo activity/weight/heat nếu muốn). Hệ số: transcribe Ou&Luo 2004 **hoặc** refit Ridge trên 12 ICEAS centroid (đã có `tools/phase3_cielab_experiment.py` để đo trước).
- (Tùy chọn) refit thêm trên **hàng châu Á của ICEAS OSF** (TQ/Nhật/Ấn/Philippines) làm proxy văn hóa gần VN nhất — thích nghi *một phần* không cần data VN.
- **Gate cứng:** KHÔNG regress targeting-error + T1 monotonicity + T2 slope≈1. Regress → giữ HSL. *(Chạy phase3 experiment trước, quyết theo số.)*

### R2 — Củng cố trục valence (decoupled, no-data) 🔴
- Panel valence **độc lập Gemini** (ViSoBERT + PhoBERT-sentiment + 1 LLM khác họ), rubric-anchored tiếng Việt **không dịch EN** (GlobalMood: dịch hại).
- Calibrate Gemini theo panel **CHỈ KHI** cải thiện targeting-error dưới **artist-grouped nested CV** — và **dùng matching scale-invariant** để không phá commensurability.
- Phân tích bài bất đồng (Phase 2 thấy: hip-hop code-switching + nhạc cưới bị label sai) → lọc/xử lý riêng.

### R3 — Sửa term văn hóa redness (rẻ, 🟠)
- Hiện `−0.19·redness` encode "đỏ Tây→giận". Hai lựa chọn (chốt bởi chủ dự án §9): **(a)** giữ thuần-global + ghi rõ giới hạn; **(b)** thêm flag VN-overlay opt-in giảm/đảo term redness cho đỏ no-bão-hòa-cao. *Khuyến nghị: (a) + document*, vì global là quyết định đã chốt và overlay từng bị loại.

### R4 — Matching: quantile-adaptive (tùy chọn, 🟠)
- Giữ heteroscedastic RBF làm mặc định. Thử **quantile-normalization với σ ∝ mật-độ-cục-bộ** (bản đúng của thử-nghiệm constant-σ đã fail) để hấp thụ catalog-skew như **calibrated recommendation (Steck)** mà không phá commensurability. Chỉ giữ nếu thắng targeting-error dưới CV.

### R5 — Test end-to-end khó hơn (chống tautology) 🔴
- Editorial-GT hiện trùng cơ chế scorer → thêm: **cross-corpus** chấm song-V-A của catalog vs **DEAM/PMEmo/GlobalMood** (human-GT thật, non-VN, có culture-penalty); **discriminant pairs** dùng tín hiệu **ngoài** V-A; judge **decoupled** khỏi nguồn nhãn (tránh Kriegeskorte).

### R6 — Ngôn ngữ claim trung thực 🔴 (rẻ)
- Doc cuối liệt kê rõ **validated** (structural, targeting beats-baseline, decoupled-valence-agreement yếu, color-emotion universal r=.88) vs **KHÔNG** (human VN — trần). Câu chuẩn dùng hội đồng: *"scientifically grounded + self-consistent + khớp vùng mood người-curate + corroborated bởi một model VN độc lập (ρ=0.263, yếu)"* — KHÔNG "validated cho người Việt".

### Thứ tự & công sức
```
R6 claim doc        █        rẻ, làm ngay
R5 test khó hơn     ████     chống tautology — giá trị hội đồng cao
R1 CIELAB           █████    ROI cao; chạy phase3 experiment trước rồi quyết
R2 valence decoupled██████   vá mắt xích yếu nhất
R3 redness VN doc   █        rẻ
R4 quantile-adaptive█████    tùy chọn, chỉ nếu R-trên cho thấy cần
```

### DỨT KHOÁT KHÔNG LÀM (giữ từ V24)
❌ Pair-study người · ❌ gold-set mới/208 bài · ❌ audio-valence Tây · ❌ calibrate một phía · ❌ học cross-modal màu↔nhạc end-to-end (cần data cặp người Việt).

---

## 9. CÂU HỎI CHỐT CHO CHỦ DỰ ÁN
1. **Phạm vi lần này:** chỉ ra **tài liệu nền + plan** (đóng băng ở đây) hay **thực thi code** R1/R5? (R1 cần chạy phase3 experiment + có thể đổi `advanced_color_mapping.py`.)
2. **Redness văn hóa (R3):** giữ thuần-global + document, hay mở flag VN-overlay opt-in?
3. **CIELAB (R1):** cho phép thay `hsl_to_va` nếu phase3 experiment cho thấy KHÔNG regress + ≥ tương đương?

---

## Nguồn (primary, peer-reviewed)
Palmer 2013 PNAS 1212562110 · Whiteford 2018 i-Perception (Sage 2041669518808535) · Spence crossmodal (ora.ox r00000226n) · Brill MSR 35(5) · Frontiers 2024 color-timbre (fpsyg.2024.1520131) · PLOS ONE 2025 (pone.0322449) · **Jonauskaite 2020 (PubMed 32900287)** · **Ou & Luo 2004 (Wiley col.20010)** · Wilms & Oberfeld 2018 (Psych Research) · Springer 2012 color-emotion-VA (s11704-012-0154-y) · **GlobalMood 2025 (arXiv 2505.09539)** · Data-gap MER (arXiv 2510.04688) · RRF Cormack 2009 (ResearchGate 221301121) · Iso-Principle Starcke 2024 (Sage 10298649231175029) · Dacrema 2021 (aaai.12051) · Kriegeskorte 2009 (Nature Neuroscience nn.2303) · MTMM Campbell&Fiske 1959 · Carruthers 2010 Manchester Colour Wheel (BMC) · Scheibehenne 2010 choice-overload meta · Hu&Downie 2010 · Delbouys 2018 · MERGE 2024 · Steck 2018 RecSys · Abdollahpouri popularity bias · Vargas&Castells 2011 · Saerens 2002 · Valdez&Mehrabian 1994.

> ⚠️ Lưu ý phương pháp & trạng thái xác minh (cập nhật 2026-06-08):
> - deep-research hoàn tất search/fetch/trích-xuất (29 nguồn primary, 135 claims) nhưng **phase adversarial-verify bị gián đoạn bởi session limit** (vote 0-0 = abstain, KHÔNG phải bị bác thật).
> - **Đã fetch trực tiếp xác nhận TẤT CẢ anchor + phụ trợ (2026-06-08):** ✅ Palmer 2013 (PMC3670360, dải r 0.89–0.99) · ✅ Whiteford 2018 (PMC6240980, PARAFAC V+A) · ✅ Jonauskaite 2020 (4598 người/30 nước/22 ngôn ngữ, r=.88, nation matters) · ✅ Ou&Luo 2004 (DOI col.20010, 3 factors activity/weight/heat, 14 Anh+17 Trung) · ✅ Valdez&Mehrabian 1994 (PubMed 7996122, P=.69B+.22S, A=−.31B+.60S) · ✅ Carruthers 2010 (PMC2829580) · ✅ Steck 2018 (dl.acm 3240323.3240372, KL re-rank) · ✅ Abdollahpouri (arXiv 1901.07555/1907.13286, ARP) · ✅ Frontiers timbre + cross-corpus (verify thủ công).
> - **Đã sửa 1 lỗi over-attribution** (Palmer happy/sad r=.97 → thực ra thuộc thí nghiệm khuôn mặt; nhạc–màu dùng dải 0.89–0.99).
> - **Trạng thái nguồn: ĐẦY ĐỦ** cho trích dẫn luận văn. Khuyến nghị cuối: chỉ cần đọc full-text Ou&Luo Part I (qua ResearchGate/Coventry pureportal) để lấy bảng hệ số CIELAB chính xác khi thực thi R1 CIELAB.
