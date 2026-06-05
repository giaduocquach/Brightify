# Hướng tốt nhất NẾU bỏ gold-set bespoke (V18b)

Date: 2026-06-03. Tổng hợp 2 luồng deep-research (validation-không-gold-set · LLM-judge). Trả lời:
nếu muốn bỏ gold-set người tự thu thập thì validate/grounding hệ màu→cảm xúc→nhạc thế nào cho đúng.

---

## Kết luận 1 câu
**"Bỏ gold-set" nên hiểu = bỏ việc THU THẬP THÊM + bỏ tham vọng CALIBRATION (nguồn gây vỡ 2 lần) +
thay gold-set-match đắt đỏ bằng nguồn miễn phí scalable — NHƯNG giữ 208 bài đã có làm "neo người" một
lần.** Khoa học nói rõ: kể cả hướng không-thu-thập vẫn cần một neo người nhỏ (~100-200 item) để
*hợp lệ hóa* các metric scalable — và ta đã có sẵn 208 bài (rẻ, đã xong, chịu lực). Xóa hẳn là phí.

---

## Stack validation KHÔNG cần thu thập mới (xếp theo sức mạnh/công sức)

### Tier 1 — làm trước, rẻ, không cần nhãn người mới
**(1) Battery cấu trúc / self-consistency (label-free).** = construct validity (convergent/discriminant,
truyền thống MTMM Campbell&Fiske). Falsify hành vi hỏng + tái lập khoa học màu-cảm-xúc:
- *Discriminant:* màu đối nghịch (đỏ-cam vs xanh) → phân bố V-A bài tách (AUC/effect size). Neo:
  Jonauskaite 2020/2024 (đỏ/vàng→arousal cao, xanh→calm là directional GT đủ vững).
- *Monotonicity:* màu trượt dọc trục V (hoặc A) → trung tâm V-A bài gợi ý trượt cùng chiều (Spearman).
- *Commensurability:* fit `color_VA ≈ a·song_VA + b` → cầu hợp lệ chỉ khi a≈1, b≈0 *(test bắt được lỗi
  lệch-thang mà Pearson/ICC mù — chính cái đã làm vỡ calibration).*
- *Distribution audit:* định lượng skew 47% sad, coverage/quadrant — chứng minh không phải cứ trả cụm sad.
- *Round-trip:* màu→V-A→bài→ước lượng lại V-A bài → khoảng cách về điểm yêu cầu phải nhỏ, không lệch.

**(2) Distant supervision từ playlist mood (HEADLINE end-to-end).** Dùng **playlist mood người Việt
curate** (YouTube/Spotify "Nhạc Buồn/Vui/Chill/Sôi động") → quadrant Q1-Q4. Tiền lệ MIR vững: Hu&Downie
2007 (MIREX AMC chạy trên nhãn tag), Laurier 2009 (178 tag AllMusic → đúng 4 quadrant Russell),
MoodyLyrics (Çano 2017, 74% acc không cần nhãn người), MTG-Jamendo/MediaEval.
- *De-noise:* yêu cầu **đồng thuận đa nguồn** (bài "buồn" phải vừa ở playlist Nhạc Buồn vừa có tag
  sad), giữ subset agreement cao, map về **quadrant chứ không phải điểm V-A liên tục**.
- *Metric:* **macro-F1 / per-quadrant recall / class-balanced acc** (KHÔNG dùng raw acc — skew 47% sad
  sẽ thổi phồng). Dự án đã có `color_editorial_gt` — đây chính là leg này, cần củng cố + cân bằng.
- *Cấp phép claim:* "bài gợi ý rơi vào vùng mood người-curate mà màu hàm ý" — gần end-to-end nhất có
  thể mà không cần thu thập.

### Tier 2 — kiểm component
**(3) Cross-corpus song→V-A:** đo arousal/valence trên PMEmo + EmoMusic held-out (probe train trên
DEAM), so baseline Ching&Widmer 2025 / Music2Emo. Chỉ cấp phép "probe generalize trong corpora Tây" —
**có culture-penalty Tây→Việt** (GlobalMood: zero-shot r≈0.08; dịch thuật ngữ Anh làm TỆ hơn r≈0.13).
**(4) LLM-valence component check:** LLM-lyrics valence vs quadrant distant-supervised + vs lexicon
(MoodyLyrics-style) làm ý kiến thứ hai.
**(5) Color→V-A ICEAS held-out fit** (L1 đã có, r=0.85).

**Triangulation 4+ tín hiệu độc lập (cấu trúc + distant + cross-corpus + LLM-vs-lexicon) = MTMM
convergent validity** — đúng cách tâm trắc học validate một construct *khi không có single gold standard*.

---

## LLM-judge: có thay người được không?
**Có — CÓ ĐIỀU KIỆN**, làm metric scalable cho dev-loop + report toàn catalog:
- **Decoupled bắt buộc:** judge phải KHÁC họ model với Qwen3-labeler (Qwen-label + Qwen-judge = circular,
  Kriegeskorte 2009 double-dipping; self-preference bias Panickssery 2024, đặc biệt hại đúng ca model sai).
- **Panel 3 họ khác nhau** (PoLL, Verga 2024) — rẻ hơn ~7×, ít bias hơn 1 judge GPT-4.
- **Neo vào bộ người NHỎ** (≥100-200 item) + báo κ/ρ judge-vs-người; dùng **thuật ngữ mood tiếng Việt
  bản ngữ** (đừng dịch từ Anh — GlobalMood: dịch làm tệ hơn). Bias controls: swap order, CoT-trước-verdict, rubric.
- **Trần độ tin có thật:** affect tiếng Việt chỉ moderate (GlobalMood r≈0.34-0.50; đa ngữ κ≈0.3); scale/đa-ngữ
  KHÔNG sửa được. → LLM-judge là *relative dev metric*, không phải trọng tài tuyệt đối.
- **208 bài hiện có = đúng cái neo người** mà LLM-panel cần để hợp lệ → **đừng xóa**.

---

## Hệ quả kiến trúc khi bỏ gold-set (quan trọng)
**Bỏ gold-set ⇒ bỏ luôn tham vọng CALIBRATION về thang người tuyệt đối ⇒ tránh hẳn cái bẫy lệch-thang
đã gây vỡ 2 lần.** → Giữ hệ trên **thang native nhất quán** (vốn pass L2 0.654, L3 4/4), KHÔNG calibrate
một bên. Nâng cấp tập trung vào thứ KHÔNG cần thang người:
- **Heteroscedastic RBF** (σ_arousal hẹp, σ_valence rộng) — justify bằng *literature* (arousal dễ hơn
  valence: Yang&Chen, MERGE) + bài học một-lần của 208 (arousal r=0.83 > valence r=0.70). Không cần
  duy trì gold-set vẫn dùng được kết luận này.
- **Multimodal valence fusion** (audio phụ + lyrics chính) — validate bằng ablation trên cross-corpus
  (PMEmo/EmoMusic), không cần gold-set Việt.
- **Editorial-playlist** làm metric end-to-end chính, anchored/spot-check bằng 208.

---

## CÓ THỂ vs KHÔNG THỂ claim (trung thực)
**CÓ THỂ:** hệ tự-nhất-quán + tái lập khoa học màu-cảm-xúc (Jonauskaite); bài gợi ý rơi đúng vùng mood
người-curate (distant, quadrant, balanced metric); song→V-A generalize trong corpora Tây; mỗi component
khớp một tín hiệu độc lập.
**KHÔNG THỂ:** "đã validate cho cảm nhận màu↔nhạc của người Việt thật" — mọi paper cross-cultural cho
thấy gap Tây→phi-Tây mà KHÔNG dataset public nào đóng được cho tiếng Việt; calibration V-A liên tục;
mức hài lòng/cảm-nhận-match của user.

**Cái mất không thể thay thế:** đo lường *vừa in-culture (Việt) + vừa end-to-end (màu→bài) + vừa về
perceived-correctness*. Thứ duy nhất lấp được là một **nghiên cứu người nhỏ** (~30-50 rater trên vài
trăm cặp màu-bài, thuật ngữ bản ngữ) — và **208 bài hiện có chính là mức tối thiểu đó**, nên giữ.

---

## Khuyến nghị
1. **Giữ 208 bài làm neo một-lần** (đừng mở rộng/đừng phụ thuộc đi tới; đừng dùng để calibrate một bên).
2. **Bỏ gold-set-match đắt đỏ (R5 cũ)** → thay bằng **editorial-playlist distant supervision** làm metric
   end-to-end chính (củng cố `color_editorial_gt`, cân bằng class).
3. **Bỏ tham vọng calibration** → giữ thang native + heteroscedastic RBF (justify bằng literature).
4. **Battery cấu trúc** (commensurability/monotonicity/discriminant/skew-audit) làm gate thường trực.
5. **LLM-judge panel decoupled** (3 họ ≠ Qwen, thuật ngữ Việt) neo bằng 208 — metric scalable dev-loop.
6. Ghi rõ giới hạn: "scientifically grounded + self-consistent + khớp mood-region", KHÔNG over-claim
   "validated cho người Việt".

## Nguồn
GlobalMood/Whitehead 2025 ISMIR · Ching&Widmer 2025 CMMR · Hu&Downie 2007 ISMIR · Laurier 2009 ·
Çano MoodyLyrics 2017 · MTG-Jamendo/MediaEval · Jonauskaite 2020/2024 · Choi 2018 (noisy labels) ·
Niu 2024 (LLM emotion annotation) · Zheng 2023 MT-Bench · Verga 2024 PoLL · Panickssery 2024 ·
Wataoka 2024 · Chen 2025 · Kriegeskorte 2009 · Campbell&Fiske MTMM.
</content>
