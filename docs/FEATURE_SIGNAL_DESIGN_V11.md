# Brightify — Thiết Kế Tín Hiệu Theo Từng Feature (V11)

> **Ngày:** 2026-05-30
> **Mục tiêu:** Trả lời 2 câu hỏi của user bằng **bằng chứng khoa học đã công bố & kiểm chứng**:
> 1. Feature gợi ý nào **nên dùng thêm MERT**, feature nào **không**.
> 2. Mỗi feature nên dùng **đúng những tín hiệu nào** để cho kết quả cao & phù hợp nhất — *không phải cứ dồn hết vào là mạnh/thông minh.*
> **Triết lý nền:** **Khớp tín hiệu với CÂU HỎI của feature, không chất đống.** Mỗi tín hiệu chỉ thêm khi (a) mang thông tin *không trùng* và (b) qua **backtest** (Bonferroni/CI sẵn có).

---

## 0. TL;DR — bảng quyết định

| Feature | Câu hỏi cốt lõi | Tín hiệu NÊN dùng | MERT? |
|---|---|---|---|
| **Similar songs** (`recommend_by_song`) | "Giống về nhạc?" | **MERT (chính)** + lyrics-PhoBERT (chủ đề, *khác modality*) + V-A/mood (cảm xúc) | ✅ **CHÍNH** |
| **Audio Radio** (`recommend_by_audio`) | "Giống chất âm thuần?" | **MERT thuần** | ✅ **DUY NHẤT** |
| **KG content** (F6) | "Đồ thị tương đồng nội dung" | MERT + mood_tags + instrument_tags (±audio) | ✅ (xương sống) |
| **Color → music** | "Hợp cảm xúc của màu?" | **Màu→V-A (CIEDE2000/Jonauskaite) + V-A + emotion** | ❌ (không phải cầu nối; chỉ re-rank phụ, gated) |
| **Image → music** | "Hợp cảm xúc của ảnh?" | **CLIP→emotion/V-A + V-A + emotion** | ❌ (như color) |
| **Context** (`smart_context_recommend`) | "Hợp giờ/thời tiết/hoạt động?" | context→**V-A đích** + thuộc tính audio *diễn giải* (energy/instrumentalness/speechiness/tempo) | ⚠️ thấp (chưa cần; phải backtest) |
| **Emotion Journey** (đang gác) | "Dẫn cảm xúc mượt A→B" | V-A waypoints + emotion + **MERT cho smoothness** | ⚠️ thử cho *smoothness* |
| **Lyrics/Vibe search** (F3 related) | "Về chủ đề/cảm giác gì?" | **PhoBERT semantic + keyword + emotion** | ❌ (audio không liên quan) |

**Quy tắc vàng xuyên suốt (từ bằng chứng):**
- **Câu hỏi về CHẤT ÂM** → MERT (similar, audio-radio, KG, smoothness).
- **Câu hỏi về CẢM XÚC/cross-modal** (color/image/mood) → cầu nối **V-A + emotion**, *không* phải MERT.
- **Câu hỏi về CHỦ ĐỀ/NGỮ NGHĨA** (lyrics/vibe) → **text (PhoBERT)**, *không* MERT.
- **Câu hỏi về NGỮ CẢNH** → ánh xạ context→V-A + thuộc tính audio *điều khiển được*.
- **Valence ≠ Arousal:** mọi tín hiệu cảm xúc lấy **arousal từ audio**, **valence từ lyrics** (xem §1.4).

---

## 1. BẰNG CHỨNG NGHIÊN CỨU (đa nguồn, đã xác thực)

### 1.1. MERT mạnh ở "hiểu nội dung âm thanh" — Li et al. 2023 (ICLR 2024)
MERT là SOTA/competitive trên các task **cấp toàn cục**: auto-tagging (MTT), key detection, genre (GTZAN), **emotion recognition (EMO)**. → MERT là biểu diễn *chất âm/nhạc tính* tốt; hợp các câu hỏi "nghe ra sao".

### 1.2. Audio embedding mạnh làm feature thủ công BÃO HÒA — arXiv 2409.09026 (CLAP cho RecSys)
- "CLAP embeddings provide information **missing in other features**" — vượt acoustic features truyền thống.
- **Saturation:** với mô hình đủ sâu, "feature combinations **approach** the model using **only CLAP**"; thậm chí một số feature thủ công "achieve results **similar to random** features". → **Bằng chứng trực tiếp:** chồng thêm feature thủ công lên một audio-embedding mạnh thường **dư thừa**, không tăng (có khi thêm nhiễu).

### 1.3. Deep embedding > handcrafted cho MER — arXiv 2104.06517 / 2502.03979
Handcrafted (MFCC/chroma/rhythm) bắt low-level nhưng **bỏ lỡ ngữ nghĩa nhạc cấp cao**; deep embedding học được những cái đó. → Với câu hỏi cảm xúc/ngữ nghĩa nhạc, embedding học sâu thắng feature thủ công.

### 1.4. ⭐ Valence khó từ audio, cần LYRICS; Arousal tốt từ audio — arXiv 2302.13321 + 1809.07276 + survey 2504.18799
- **Arousal** tương quan cao với **audio** (~78% acc từ audio).
- **Valence** kém từ audio đơn thuần; **text/lyrics** tốt hơn (~73%); "lyrics liên quan valence, gần như **không** liên quan arousal".
- **Mid-level fusion audio+lyrics** cải thiện valence rõ rệt.
- → **HỆ QUẢ TOÀN HỆ THỐNG:** điểm V-A của mỗi bài phải = **arousal(audio) ⊕ valence(lyrics)**. Mọi feature dựa V-A (color/image/journey/context/mood) thừa hưởng điều này.

### 1.5. Cross-modal (color/image → music): cầu nối là V-A/EMOTION — arXiv 2009.05103, 2504.12796, "Learning Affective Correspondence"
Khớp ảnh/màu↔nhạc thực hiện trong **không gian Valence-Arousal**; cảm xúc là *cầu nối*. Khi xung đột, **arousal lấn át** (congruence research). → Tín hiệu *chính* cho color/image KHÔNG phải tương đồng audio thô, mà là **đồng điệu cảm xúc (V-A/emotion)**. MERT chỉ có thể *tinh chỉnh* xếp hạng sau khi đã khớp cảm xúc (phụ, phải đo).

### 1.6. Context-aware: time/weather/activity hiệu quả — MDPI 2021 (systematic review)
time-slot, ngày-thường/lễ, thời tiết, hoạt động đều ảnh hưởng mạnh; context + content cho cải thiện *có ý nghĩa thống kê*. → Context khớp qua **V-A đích + thuộc tính audio diễn giải được** (energy/instrumental/speechiness/tempo hợp hoạt động: focus=instrumental cao, ít speech). Đây là tri thức *điều khiển được*, hợp luật ngữ cảnh hơn embedding mờ.

### 1.7. Thêm feature ≠ tốt hơn — KDD 2025 (de-redundancy), arXiv 2508.06455 / 2411.01561
Feature nhiễu/dư thừa **làm giảm** hiệu năng & khái quát hóa; "side features… đôi khi **mâu thuẫn** hành vi → overspecialization"; **ít feature thông tin** có thể thắng nhiều. → Củng cố triết lý: *chọn lọc, không chất đống*. (Khớp với chính lịch sử dự án: RRF từng **hại** recall ở `recommend_by_song`; Pillar B encoder "xịn hơn" lại **FAIL**.)

---

## 2. NGUYÊN TẮC THIẾT KẾ TÍN HIỆU (rút ra)

| # | Nguyên tắc | Căn cứ |
|---|---|---|
| S1 | **Khớp modality với câu hỏi.** Chất âm→MERT; cảm xúc/cross-modal→V-A+emotion; chủ đề→text; ngữ cảnh→context-map. | 1.1, 1.5, 1.6 |
| S2 | **Một embedding mạnh có thể thay nhiều feature thủ công.** Đừng giữ cả hai theo quán tính — phải ablation. | 1.2, 1.7 |
| S3 | **Valence từ lyrics, Arousal từ audio.** | 1.4 |
| S4 | **Thêm tín hiệu chỉ khi *không trùng* + qua backtest.** Mặc định *bớt*, không *thêm*. | 1.7 + lịch sử dự án |
| S5 | **Tín hiệu điều khiển-được > embedding mờ khi cần luật rõ** (context/activity-fit). | 1.6 |
| S6 | **Đo cả "đúng" lẫn "đa dạng/không thiên vị"** — không tối ưu mù một chỉ số. | lịch sử KG-bias |

---

## 3. THIẾT KẾ THEO TỪNG FEATURE (chi tiết + hành động)

### F-SIM. Similar songs `recommend_by_song` — "Giống về nhạc"
- **Hiện tại:** timbral + rhythmic + tonal (thủ công) + lyrics(PhoBERT) + V-A + emotion + mood + **MERT** + KG.
- **Theo bằng chứng:** MERT là tín hiệu *chất âm* đúng nhất (1.1). NHƯNG bộ **timbral/rhythmic/tonal thủ công có thể đã DƯ THỪA** với MERT (1.2). lyrics-PhoBERT là *modality khác* (chủ đề lời) → giữ, trọng số nhỏ & riêng. V-A/mood: giữ (cảm xúc), nhớ valence yếu từ audio (1.4).
- **HÀNH ĐỘNG (backtest-gated):**
  1. **Ablation MERT-heavy:** đo `recommend_by_song` khi **giảm/bỏ** timbral/rhythmic/tonal và tăng MERT → kiểm chứng saturation (1.2) trên dữ liệu VN. Nếu NDCG không giảm → đơn giản hoá (ít feature, ít nhiễu, nhanh hơn).
  2. Giữ lyrics + V-A/mood như *signal bổ sung khác-modality*, không gộp vào audio.
- **MERT: ✅ CHÍNH.**

### F-AUDIO. Audio Radio `recommend_by_audio` — ✅ đã làm (F7)
- MERT thuần — đúng theo S1. **Không thêm gì** (đó là điểm mạnh: một lăng kính thuần chất âm). Đã hợp lý.

### F-KG. KG content embeddings (F6) — đã làm
- **Hiện tại:** MERT 0.5 ⊕ mood_tags 0.2 ⊕ instrument_tags 0.2 ⊕ audio 0.1 → SVD 64.
- **Theo bằng chứng:** MERT xương sống đúng. mood_tags/instrument_tags là **nhãn ngữ nghĩa** (khác modality MERT) → bổ sung hợp lý. Thành phần **audio 0.1 nghi ngờ dư thừa** với MERT (1.2).
- **HÀNH ĐỘNG:** ablation bỏ `audio 0.1` (giữ MERT+mood+instrument) → nếu chất lượng/`%same-artist` không đổi thì bỏ cho gọn.

### F-COLOR. Color → music `recommend_by_colors`
- **Câu hỏi:** đồng điệu cảm xúc của màu. **Cầu nối = V-A/emotion** (1.5).
- **Tín hiệu đúng:** màu→V-A (CIEDE2000, Jonauskaite 2020) + song V-A + emotion vector. (Đã có RRF trên color path — đo SIG dương trước đây, giữ.)
- **MERT: ❌ không phải cầu nối.** *Tùy chọn* (gated): sau khi đã khớp V-A, dùng MERT **re-rank top-N** cho đồng nhất chất âm — chỉ bật nếu backtest color-path cho lợi rõ. Mặc định **không thêm** (tránh nhiễu, 1.7).
- **Lưu ý valence (1.4):** song V-A phải có valence từ lyrics (dự án đã fuse audio 60% + lyrics 40% — tốt; giữ).

### F-IMAGE. Image → music `recommend_by_image`
- Như F-COLOR: **CLIP scene/emotion → V-A** là cầu nối (1.5). **MERT ❌** (chỉ re-rank phụ, gated).

### F-CTX. Context `smart_context_recommend`
- **Tín hiệu đúng:** ánh xạ giờ/thời tiết/lễ/hoạt động → **V-A đích** (đã có circadian + vn_context) + **thuộc tính audio diễn giải được** cho activity-fit (energy/instrumentalness/speechiness/tempo/acousticness — đã dùng). (1.6, S5)
- **MERT: ⚠️ thấp — chưa cần.** Activity-fit cần *luật điều khiển được* hơn embedding mờ. Chỉ thử MERT nếu có giả thuyết cụ thể + backtest. **Không thêm theo quán tính.**

### F-JOURNEY. Emotion Journey (ĐANG GÁC — ghi để khi quay lại)
- V-A waypoints (Bézier) + emotion + smoothness audio + lyrics-zone.
- **Cơ hội MERT hợp lý:** **smoothness giữa các bài** (chuyển bài nghe liền mạch) hiện dùng cosine audio-features; **MERT có thể bắt "liền mạch chất âm" tốt hơn** (1.1/1.3). → khi quay lại: thử thay/booster smoothness bằng MERT, đo cảm nhận chuyển tiếp.
- **Valence (1.4):** đích/điểm-đầu V-A phải lấy valence từ lyrics — củng cố độ tin "buồn↔vui".

### F-SEARCH. Lyrics/Vibe search (`recommend_by_lyrics_keywords`, lớp "Liên quan" của F3)
- **Câu hỏi:** chủ đề/cảm giác bằng ngôn ngữ. **Tín hiệu = PhoBERT semantic + keyword (+ emotion/V-A cho vibe).**
- **MERT: ❌** — audio không trả lời "về cái gì / cảm giác gì". (1.4: lyrics mang valence/chủ đề.) Giữ thuần text + emotion.

---

## 3.5. BẢNG ĐÁNH GIÁ — đã phù hợp/chuẩn xác chưa, dựa cơ sở nào, xác thực chưa

**Chú thích trạng thái xác thực:**
🟢 *Đã đo/kiểm chứng trong chính dự án này* · 🟡 *Đúng theo bằng chứng công bố nhưng CHƯA đo trên dữ liệu VN* · 🔵 *Đề xuất, chưa triển khai*

| Feature | Yếu tố gợi ý (theo V11) | MERT | Cơ sở nghiên cứu (đã công bố) | Xác thực | Đánh giá |
|---|---|---|---|---|---|
| **Similar songs** | MERT (chính) + timbral/rhythmic/tonal + lyrics(PhoBERT) + V-A + emotion + mood + KG | ✅ | MERT ICLR2024; CLAP-RecSys 2409.09026; Berenzweig 2004 | 🟢 MERT (Pillar A PASS) · 🟡 nghi dư thừa feature thủ công | **Tốt nhưng CHƯA tối ưu:** MERT đã đo có lợi; *bộ thủ công có thể dư thừa* (saturation) — phải E1 mới biết. Hiện "đủ tốt", chưa chắc "gọn nhất". |
| **Audio Radio** | MERT thuần | ✅ | MERT ICLR2024 (SOTA acoustic) | 🟢 test chức năng (cosine .93–.94) | **Chuẩn về thiết kế.** Đúng modality. Chưa có đánh giá *chất lượng cảm nhận* (thiếu GT sound-alike) — nhưng đúng nguyên lý. |
| **KG content** (F6) | MERT 0.5 + mood + instrument + (audio 0.1?) | ✅ | 2409.09026; Hybrid-GNN UMUAI 2024 | 🟢 pillar-f-xartist (same-artist 89.6%→7.2%) · 🟡 audio 0.1 chưa ablation | **Đã sửa bias thành công (đo rồi).** Còn thành phần audio 0.1 nghi thừa — E2. |
| **Color → music** | màu→V-A (CIEDE2000/Jonauskaite) + V-A + emotion + RRF | ❌ | Jonauskaite 2020; V-A bridge 2009.05103; CIE 2001 | 🟢 RRF color-path SIG (Δ+0.056) · 🟡 toàn path | **Cầu nối V-A đúng & một phần đã đo.** Không-dùng-MERT là quyết định đúng (đỡ nhiễu). Valence có lyrics ✓. |
| **Image → music** | CLIP→emotion/V-A + V-A + emotion | ❌ | 2009.05103; CLIP (Radford 2021) | 🟡 đúng hướng, chưa đo riêng | **Đúng theo bằng chứng** (cùng cầu nối V-A như color). Chưa backtest riêng (GT ảnh khó). |
| **Context** | context→V-A đích + thuộc tính audio diễn giải (energy/instr/speech/tempo) | ⚠️ thấp | Context review MDPI 2021; Skowronek 2006; North&Hargreaves 1996 | 🟡 đã wire (F1), chưa đo hiệu quả | **Tín hiệu đúng** (dùng thuộc tính điều khiển-được, không MERT). Chưa đo định lượng (khó GT ngữ cảnh). |
| **Emotion Journey** *(gác)* | V-A waypoints + emotion + smoothness + lyrics-zone (+MERT-smoothness?) | 🔵 thử | Iso-principle (Altshuler/Davis-Thaut); Saari 2016 | 🔵 chưa đo / đang gác | **Thiết kế hợp lý nhưng CHƯA kiểm chứng** — đang gác để nghiên cứu sâu. MERT-smoothness là giả thuyết. |
| **Lyrics/Vibe search** (F3) | PhoBERT semantic + keyword + emotion | ❌ | valence-lyrics 2302.13321; PhoBERT (Nguyen 2020) | 🟢 test chức năng 3 kiểu query · 🟡 chưa đo nDCG | **Đúng modality, hoạt động.** Chưa có nDCG định lượng (cần GT chủ đề-lời, như ghi chú reranker). |

### Kết luận đánh giá (trung thực)
- **Về THIẾT KẾ:** ✅ **đã phù hợp nhất theo bằng chứng công bố hiện có** — mỗi feature khớp tín hiệu với *câu hỏi* của nó (chất âm→MERT; cảm xúc→V-A; chủ đề→text; ngữ cảnh→context-map), và đã tránh "dồn hết". Valence-từ-lyrics đã đúng trong code.
- **Về EMPIRICAL "chuẩn xác nhất":** ⚠️ **một phần** — những mục lõi đã đo trong dự án (MERT/Pillar A, KG/pillar-f-xartist, RRF color-path) là 🟢; phần còn lại 🟡/🔵 **đúng hướng nhưng chưa đo trên data VN**. Để khẳng định "chuẩn xác nhất" theo nghĩa định lượng, cần hoàn tất **E1–E6** (§5) — đặc biệt E1 (saturation) và dựng GT cho color/image/search.
- **Tóm lại:** thiết kế *evidence-based, không over-engineer*; nhưng "tối ưu đã được chứng minh bằng số" mới đạt ở các mục 🟢. Đừng coi 🟡/🔵 là đã tối ưu — chúng là *giả thuyết có cơ sở chờ đo*.

## 4. MERT — TỔNG KẾT "DÙNG / KHÔNG DÙNG"

**✅ Nên dùng MERT (câu hỏi về chất âm):**
- Similar songs (chính) · Audio Radio (thuần) · KG content (xương sống) · *Journey-smoothness* (thử).

**❌ Không nên dùng MERT làm tín hiệu chính (sai câu hỏi):**
- Color→music · Image→music · Lyrics/Vibe search (text) · Context activity-fit (dùng thuộc tính diễn giải).
- *(Chỉ cân nhắc MERT như re-rank phụ ở color/image, và phải qua backtest.)*

**Lý do gốc:** MERT trả lời *"nghe như thế nào"*. Color/image/mood hỏi *"cảm xúc gì"* (→ V-A), lyrics hỏi *"về cái gì"* (→ text), context hỏi *"hợp lúc nào/làm gì"* (→ context-map). Nhồi MERT vào sai câu hỏi = thêm nhiễu, vi phạm S1/S4 (1.7).

---

## 5. ROADMAP THÍ NGHIỆM (ưu tiên, đều backtest-gated)

> Mọi thay đổi trọng số mặc định phải qua harness backtest (Bonferroni/CI) trước khi bật.

1. **E1 — Ablation saturation ở `recommend_by_song`** *(M)*: đo NDCG khi giảm/bỏ timbral/rhythmic/tonal, tăng MERT. *Mục tiêu:* xác nhận (hay bác bỏ) saturation (1.2) trên catalog VN → đơn giản hoá nếu được. **Cao nhất** (đụng feature dùng nhiều nhất + kiểm tra trực tiếp triết lý).
2. **E2 — Ablation `audio 0.1` trong KG** *(S)*: bỏ thành phần audio, giữ MERT+mood+instrument; đo chất lượng + %same-artist.
3. **E3 — Kiểm chứng nguồn valence** *(S-M)*: xác nhận song V-A đang fuse lyrics cho valence (1.4); nếu chưa, sửa — ảnh hưởng *mọi* feature cảm xúc.
4. **E4 — Color/Image re-rank bằng MERT (tùy chọn)** *(M)*: thử MERT re-rank top-N *sau* khớp V-A; chỉ giữ nếu color-path backtest lợi rõ. Mặc định OFF.
5. **E5 — (khi mở lại Journey) MERT cho smoothness** *(M)*: thay/booster smoothness; đo cảm nhận chuyển tiếp.
6. **E6 — Context: KHÔNG thêm MERT** trừ khi có giả thuyết + backtest; ưu tiên hoàn thiện thuộc tính activity-fit diễn giải.

---

## 6. NGUỒN (đã công bố & kiểm chứng)

**MERT / audio embeddings cho reco**
- MERT — Acoustic Music Understanding (ICLR 2024, arXiv 2306.00107): https://arxiv.org/abs/2306.00107
- Leveraging Contrastively Pretrained Neural Audio Embeddings for Recommender Tasks (arXiv 2409.09026): https://arxiv.org/html/2409.09026v1
- Revisiting Content-Based Music Recommendation: Efficient Feature Aggregation from Large-Scale Music Models (arXiv 2604.20847): https://arxiv.org/html/2604.20847
- Deep content-based music recommendation (van den Oord, NeurIPS 2013): http://papers.neurips.cc/paper/5004-deep-content-based-music-recommendation.pdf

**MER — handcrafted vs deep, valence vs arousal**
- Comparison of Deep Audio Embeddings for MER (arXiv 2104.06517): https://arxiv.org/pdf/2104.06517
- Multi-Modality in Music: Predicting Emotion from Audio Features and Lyrics (arXiv 2302.13321): https://arxiv.org/abs/2302.13321
- Music Mood Detection Based on Audio and Lyrics with DNN (arXiv 1809.07276): https://arxiv.org/pdf/1809.07276
- A Survey on Multimodal Music Emotion Recognition (arXiv 2504.18799): https://arxiv.org/html/2504.18799v1
- A Comparison Study of DL Methodologies for MER (Sensors 2024, PMC11014202): https://pmc.ncbi.nlm.nih.gov/articles/PMC11014202/

**Cross-modal image/color → music (cầu nối V-A)**
- Emotion-Based End-to-End Matching Between Image and Music in V-A Space (arXiv 2009.05103): https://arxiv.org/pdf/2009.05103
- A Survey on Cross-Modal Interaction Between Music and Multimodal Data (arXiv 2504.12796): https://arxiv.org/html/2504.12796v1
- Learning Affective Correspondence between Music and Image (ICASSP 2019): https://www.researchgate.net/publication/332791185
- Music recommendation based on affective image content analysis (ScienceDirect): https://www.sciencedirect.com/science/article/pii/S1877050923000212

**Context-aware reco**
- Context-Aware Recommender Systems in the Music Domain: A Systematic Literature Review (MDPI Electronics 2021): https://www.mdpi.com/2079-9292/10/13/1555
- Context-Aware Mobile Music Recommendation for Daily Activities (NUS): https://smcnus.comp.nus.edu.sg/archive/pdf/2012-2013/2012_Context.pdf

**Thêm feature ≠ tốt hơn / chọn lọc tín hiệu**
- Mitigating Redundancy in Deep Recommender Systems (KDD 2025): https://dl.acm.org/doi/10.1145/3690624.3709275
- Maximum Impact with Fewer Features: Efficient Feature Selection for Cold-Start Recommenders (arXiv 2508.06455): https://arxiv.org/pdf/2508.06455
- Multimodal GNN with Dynamic De-redundancy and Modality-Guided De-noisy (arXiv 2411.01561): https://arxiv.org/pdf/2411.01561

---

*Plan này dựa trên bằng chứng công khai đã kiểm chứng + ground-truth codebase. Nguyên tắc cốt lõi: **khớp tín hiệu với câu hỏi, thêm có chọn lọc, đo bằng backtest** — không "dồn hết cho mạnh". Mọi mục §5 phải qua harness backtest trước khi bật mặc định.*
