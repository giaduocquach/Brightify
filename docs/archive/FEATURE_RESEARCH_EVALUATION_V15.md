# Brightify — Đánh giá khoa học từng feature + Roadmap nâng cấp (V15)

> Tổng hợp nghiên cứu đa nguồn (2026-06) đối chiếu với logic gợi ý hiện tại. Mỗi nhận định
> gắn **[STRONG]** (peer-reviewed/định lượng) hoặc **[WEAK]** (preprint/blog/gián tiếp). Mọi
> trích dẫn đều có URL ở §9 — không có trích dẫn bịa.

## 0. Scorecard điều hành

| Feature | Logic hiện tại đúng research chưa? | Offline metrics | "Best" chưa? | Việc cần |
|---|---|---|---|---|
| 🎨 Màu→nhạc | ✅ cầu V-A đúng (Palmer) nhưng **HSL Tây lệch cho VN** (Jonauskaite) | ⚠️ quadrant-match@100% **vòng tròn, không hợp lệ** | Gần tối ưu cho zero-data; learned re-ranker tốt hơn nếu có nhãn | Sửa metric, **localize màu VN**, validate MERT-arousal trên MusAV |
| 📷 Ảnh→nhạc | ✅ CLIP+V-A đúng hướng (Emo-CLIM, IMEMNet) | ⚠️ chưa đo riêng | Backbone ổn; nâng = probe trên ảnh gán nhãn cảm xúc | Đo Recall@K/mAP/MRR; CLIP-affective (không chỉ màu) |
| 🎵 Similar | ✅ late-fusion + tối ưu trọng số **defensible** (2026 paper) | ✅ NDCG+CI tốt **nhưng thiếu beyond-accuracy** | Cạnh tranh; thử MuQ-MuLan vs MERT | **Cap per-artist**, thêm ILD/novelty/serendipity/coverage, stratify theo popularity |
| 🎢 Journey | ✅ Iso-Principle **peer-reviewed** (Starcke 2021/24); Bézier = heuristic | ❌ **chưa đo** | Feature có cơ sở KH NHẤT; chỉ thiếu metric | Thêm **coherence + trajectory-RMSE + monotonic-progress**; demo vs shuffle/jump |
| 🔍 Vibe search | ✅ PhoBERT semantic | ⚠️ GT-1 semi-independent | Nâng = qwen3 parse → V-A+lyric+tempo có cấu trúc | Structured NL retrieval (đánh đúng chỗ Spotify fail) |

**Hai lỗ hổng xuyên suốt:** (1) **Phương pháp đánh giá** — bỏ quadrant-match, dùng Recall@K/mAP/MRR + MusAV + bộ human-rated nhỏ + beyond-accuracy. (2) **Bản địa hóa VN** — màu/cảm xúc đang dùng prior phương Tây.

---

## 1. 🎨 Màu → Nhạc

**Research:** cầu V-A được Palmer/Whiteford (PMC6240980) xác nhận là **cơ chế trung gian thật** [STRONG]. Learned cross-modal (Emo-CLIM arXiv:2308.12610 — P@5 68%, MRR 76%; IMEMNet/CDCML arXiv:2009.05103 — V-A liên tục, metric học thắng hand-crafted) chính xác hơn **nhưng cần nhãn** [STRONG]. → cầu V-A của ta là **baseline không-cần-data hợp lý**, gần IMEMNet/MMVA.

**Lỗi cần sửa:**
- **Màu→cảm xúc phương Tây lệch cho VN** [STRONG]: Jonauskaite 2020 (30 nước) — quốc gia dự báo *vượt* mẫu phổ quát. VN: **trắng=tang** (Tây=thuần khiết → công thức map sai ngược), **đỏ=may/lễ**, **tím=hoài niệm/buồn**. ⇒ override màu loaded-VN (publishable, không ai làm color→nhạc-Việt).
- **quadrant-match@100% không hợp lệ** [STRONG]: GT proxy và query cùng pipeline V-A → đo self-consistency. Thay bằng **Recall@K/P@K/mAP/MRR** (như Emo-CLIM) + **MusAV** (ISMIR 2022, relative-pairwise) validate MERT-arousal + ~200 cặp human-rated.

**UX [STRONG]:** Moodplay (IJHCS 2018) — không gian mood trực quan + **control + transparency** = feature thật. ⇒ giữ chip "màu→cảm xúc→nhạc" + thêm nút "đổi/tinh chỉnh".

---

## 2. 📷 Ảnh → Nhạc
CLIP zero-shot là chuẩn khởi điểm 2023+ [STRONG]. Nâng = **fine-tune/probe trên ảnh gán nhãn cảm xúc** (DeepEmotion, Emo-CLIM) thay vì prompt thô; nhấn **affective** (mood ảnh) chứ không chỉ màu. Đo Recall@K/mAP/MRR. Cùng cầu V-A như màu → kể chung 1 câu chuyện.

---

## 3. 🎵 Bài tương tự
**Logic defensible** [STRONG]: 2026 paper (arXiv:2601.19109) — cosine trên MuQ-MuLan/CLAP **ngang model giám sát**; tối ưu tuyến tính trên human-pref đẩy thêm — đúng kiểu SLSQP của ta. Lyrics nặng (0.50) hợp lý cho VN (chưa có joint VN music-text).

**Thiếu — beyond-accuracy** [STRONG, Kaminskas & Bridge TiiS 2017]: đang có NDCG+CI tốt nhưng **chưa đo** ILD (chỉ enforce qua MMR/DPP), **novelty, serendipity, coverage, popularity-bias (Gini/long-tail)**. Thêm tất cả với bootstrap CI sẵn có.

**GT editorial:** hợp lệ (Berenzweig ISMIR 2003: trùng playlist ↔ tương đồng chủ quan 70-76%) nhưng **lệch** (nguồn đơn, popularity, theo chủ đề). ⇒ **stratify kết quả theo tầng popularity** + thêm bộ human XAB-triplet nhỏ.

**UX [STRONG]:** users **KHÔNG muốn giống tối đa** (ISMIR 2011); 1 bài bất ngờ hay > nhiều bài tầm thường (Spotify 2018); filter-bubble thật (Nature 2024). **Lặp nghệ sĩ = than phiền #1.**

**Nâng cấp (ưu tiên):** ① **cap per-artist** (impact cao, gần như free — đúng pain-point #1 + khớp ghi chú KG-artist-bias) · ② thêm beyond-accuracy metrics · ③ stratify popularity · ④ term **serendipity/novelty** re-rank · ⑤ debias popularity (lift long-tail VN) · ⑥ benchmark **MuQ-MuLan vs MERT**.

---

## 4. 🎢 Emotion Journey
**Cơ sở KH thật [STRONG]:** Iso-Principle (Altshuler 1944; Davis-Thaut). Starcke 2021 (n=59, RCT) + 2024 + bệnh viện 2024 (n=125, p=.001) — chuyển mood dần **hiệu quả** (directional). **Bézier = heuristic** (không có shift-rate thực nghiệm → để #bước là config, A/B sau).

**Metric defensible (không cần người chấm) [STRONG]:**
- **Coherence** `coh = 1 − s²(liên tiếp)/σ²(toàn cục)` (EPJ Data Science 2025) — chuẩn, citable.
- **Monotonic-progress**: % bước giảm khoảng cách-tới-đích.
- **Trajectory-RMSE** so đường Bézier · **step-variance** (mượt) · **start/end fidelity**.
- **Demo = eval**: vẽ V-A của A (journey) vs B (shuffle) vs B' (jump-to-target) → A mượt+đơn điệu tiến đích, B zigzag, B' nhảy. Bảng số đi kèm.

**UX [STRONG]:** demand thật (điều tiết cảm xúc) NHƯNG "khai báo cảm xúc" chấp nhận thấp (CHI 2024: 23% receptive, **69% muốn nút tắt**). ⇒ opt-in, hiện đường cong, cho override/skip; preset relax/energize/focus.

**Verdict:** GIỮ — feature **có cơ sở KH nhất**. Reframe "Iso-Principle-guided V-A trajectory" + thêm metric §4 → từ "chưa đo" thành thesis-grade. Mượn: per-segment V-A, two-stage candidate→re-rank với transition-cost (DJ-MC).

---

## 5. 🔍 Vibe / NL search
Nâng thành **structured NL retrieval**: qwen3 parse "buồn nhưng muốn nhảy" → V-A target + lyric-keywords + tempo/energy → retrieve PhoBERT+MERT+V-A. Đánh đúng chỗ Spotify/PlaylistAI **fail** (nuance/BPM/lyrics) [STRONG].

---

## 6. Đại tu phương pháp đánh giá (xuyên suốt — ưu tiên cao nhất)
1. Bỏ **quadrant-match@100%** (vòng tròn). Thay **Recall@K/P@K/mAP/MRR**.
2. **MusAV** validate MERT-arousal probe (rẻ, uy tín ngay).
3. **Beyond-accuracy** cho similar (ILD/novelty/serendipity/coverage/Gini).
4. **Stratify theo popularity** mọi backtest.
5. Bộ **human-rated nhỏ** (~200 cặp màu/ảnh→bài; XAB-triplet cho similar) = trần thực.

## 7. Feature AI mới đề xuất (xếp theo bằng chứng × khả thi, dùng model sẵn có)

| # | Feature | Model/method | Nhu cầu (nguồn) | Demo case rõ |
|---|---|---|---|---|
| **A** 🟢 | **"Vì sao bài này"** — 1 câu lý do mỗi gợi ý | qwen3 *diễn đạt* delta tín hiệu THẬT (V-A dist, MERT sim, Camelot, lyric-theme) | Transparency trust [STRONG] + **luật DSA 2024** | bật/tắt explanation trên cùng list |
| **B** 🟢 | **NL mood search "đúng"** | qwen3 parse → V-A+lyric+tempo có cấu trúc | Spotify +4% listen-time nhưng **fail nuance** [STRONG] | chạy đúng prompt Spotify fail, ta honor lyric+tempo |
| **C** 🟢 | **Discovery dial** (Quen↔Phiêu lưu) | nới bán kính MERT/V-A + phạt popularity (config) | filter-bubble = pain #1; Spotify thêm steering 2025 [STRONG] | slider 0 vs max → catalog-distance & popularity đo được |
| **D** 🟡 | **Giải nghĩa/Q&A lời** | qwen3 + PhoBERT emotion grounding | emotion-first trend (demand WEAK) | bài ẩn dụ Việt mà hệ Anh-ngữ hiểu sai |
| **E** 🟡 | **Ảnh→nhạc CLIP-affective** (nâng từ chỉ-màu) | CLIP→V-A→MERT+V-A | discover-by-moment [STRONG method] | ảnh: kết quả màu-only vs affective |
| **F** 🟡 | **Visualizer cảm xúc** (màu theo V-A, không chỉ FFT) | per-segment MERT/V-A → palette CIEDE2000 | engagement [STRONG], retention WEAK | ballad buồn giữ palette lạnh vs nhấp nháy |
| **G** 🟡 | **Auto-DJ journey + giải thích chuyển** | journey + crossfade LUFS/Camelot + qwen3 | AI DJ 90M users nhưng **bị chê opacity** [STRONG] → ta *hiện đường + cho sửa* | V-A trajectory + chuyển mượt vs shuffle |
| **H** 🔵 | **Hồ sơ gu chỉnh-được (NL)** | qwen3 tóm centroid liked → prose sửa được | interpretable profile = trust [STRONG] | sửa "upbeat hơn" → list dịch V-A |

**LLM concierge?** CÓ — nhưng làm **front-end NL retrieval grounded + hiện lý do + cho steering**, KHÔNG làm "DJ persona" chatty (chỗ Spotify bị chê). Đây là đòn bẩy cao nhất tận dụng qwen3 + PhoBERT-Việt.

## 8. Roadmap đề xuất (cho bảo vệ + sau đó)
**Trước bảo vệ (rẻ, impact cao, đo được):**
1. **Đại tu metric** (§6.1-6.2): Recall@K/mAP/MRR + MusAV → thay con số 100% gây nghi.
2. **Cap per-artist** trong similar (pain #1, gần free).
3. **Journey metrics** (§4) → biến journey thành "đo được, mượt hơn random" + demo V-A plot.
4. **Feature A "Vì sao bài này"** (LLM verbalize signal thật) — wow + trust + DSA, demo bật/tắt.

**Sau (giá trị cao):** VN-localize màu · beyond-accuracy similar · Feature B/C (NL search + discovery dial).

## 9. Nguồn (chọn lọc)
Emo-CLIM arXiv:2308.12610 · IMEMNet/CDCML arXiv:2009.05103 · MMVA 2501.01094 · Music2Palette/MuCED 2507.04758 · Palmer/Whiteford PMC6240980 · Jonauskaite 2020 (Psych Sci 0956797620948810) · MusAV ISMIR2022 (mtg.github.io/musav-dataset) · Moodplay IJHCS 2018 (S1071581918301654) · Music-similarity 2026 arXiv:2601.19109 · Revisiting CB-MusicRec 2604.20847 · Kaminskas&Bridge TiiS2017 (10.1145/2926720) · Berenzweig ISMIR2003 · "How Similar Is Too Similar" ISMIR2011 · Spotify satisfaction 2018 · Filter-bubble Nature 2024 (s41598-024-75967-0) · Iso-Principle Starcke MDPI 18/23/12486, Sage 10298649231175029 · Playlist coherence EPJ 2025 (PMC11923031) · Mood-Dynamic KNN Springer 2024 · DJ-MC arXiv:1401.1880 · "Would You Tell Spotify How You're Feeling" CHI2024 (10.1145/3726986.3726998) · Spotify AI DJ/prompted (newsroom) · AI-DJ critique Sage 20438869251395753 · MIDiA discovery · Vietnam market Decision Lab Q1-2024.
