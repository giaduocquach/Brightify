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
| ~~**Audio Radio**~~ (`recommend_by_audio`) | "Giống chất âm thuần?" | MERT thuần | ❌ **ĐÃ GỠ** (2026-05-30) — trùng Similar chỉ 1.1/10 nhưng *khác ≠ tốt hơn* + niche + rối UX; code giữ dormant |
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

### F-AUDIO. Audio Radio `recommend_by_audio` — ❌ ĐÃ GỠ surface (2026-05-30)
- MERT thuần — đúng modality về lý thuyết. **NHƯNG đã gỡ feature** sau kiểm chứng: top-10 của Audio Radio **chỉ trùng ~1.1/10** với Similar Song (≈89% khác) → *không trùng*, nhưng **"khác ≠ chứng minh được tốt hơn"** + nhu cầu **niche** (pure sound-alike, bỏ qua cảm xúc/lời → dễ ghép lạ) + **rối UX** (2 cửa "tìm tương tự" + chôn trong chuột phải).
- **Quyết định:** gỡ context-menu + endpoint + `getAudioRadio`. **Giữ `recommend_by_audio` DORMANT** (code) — để dành cho **phương án núm trượt "Tổng thể ⟷ Thuần chất âm"** trong Similar Song (option B) *nếu* sau này đo được nhu cầu. Đúng triết lý "đừng giữ feature chưa chứng minh giá trị".

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

## 3.6. AUDIT SÂU THEO TỪNG FEATURE — thừa / thiếu (nghiên cứu đa nguồn, 2026-05-30)

> Kết quả 4 nhánh nghiên cứu song song. Mỗi tín hiệu: **GIỮ / THỪA / YẾU-CƠ-SỞ / THIẾU**. Độ tin: **(M)** mạnh-xác thực · **(v)** vừa · **(w)** yếu/suy luận.

### 🎵 Similar Song — đang **THỪA cảm xúc (đếm 3 lần)** + thủ công trùng MERT
- **THỪA — tonal (key/mode)** (M): MERT pretrain có *CQT "musical teacher"* riêng cho cao độ/điệu thức, SOTA key/pitch → tự làm key/mode là **trùng** (mạnh nhất nên cắt). [MERT ICLR2024](https://arxiv.org/html/2306.00107v4)
- **THỪA — timbral, rhythmic** (M): deep embedding "đã làm lu mờ feature thủ công" cho similarity. [arXiv 2601.19109], [MARBLE NeurIPS2023](https://arxiv.org/html/2306.10548)
- **THỪA — V-A *đứng riêng* + mood-quadrant** (M): cảm xúc đang bị mã hoá **3 lần** (V-A + emotion-vector + mood-quadrant). Feature tương quan/dư thừa **làm giảm** fusion. → giữ **1** (emotion-vector 13-cat), bỏ V-A-riêng + mood-quadrant. [Oxford Bioinformatics 2011](https://academic.oup.com/bioinformatics/article/27/14/1986/194387)
- **GIỮ — lyrics(PhoBERT)** (M): modality khác, fusion lyrics+audio > từng cái. [arXiv 2110.01001](https://arxiv.org/pdf/2110.01001)
- **GIỮ — MERT (anchor, trọng số lớn nhất)** (M).
- **GIỮ-THẬN-TRỌNG — KG** (w): xây *từ* MERT+audio+mood → **một phần vòng lặp** (re-inject), là lớp graph-smoothing, không phải modality độc lập.
- **THIẾU — tương đồng giọng/nhạc cụ (stem)** (v): catalog VN thiên giọng → tín hiệu vocal-vs-accompaniment đáng thêm. [arXiv 2404.06682], [arXiv 2503.17281]
- ⚠️ **Cảnh báo phương pháp (M):** lợi ích fusion trong literature đến từ **học trọng số**; **tổng đều tay (equal-weight) là chế độ dư-thừa-hại-nhất**. → nếu giữ nhiều tín hiệu thì **học/tune trọng số**, đừng cộng đều. [DFS-WR ScienceDirect 2023]
- *Lưu ý:* feature thủ công **không phải luôn vô dụng** — nếu là *embedding học chuyên* cho pitch/timbre + fusion học, có thể lợi ([arXiv 2309.08751]); nhưng các *scalar rẻ* (energy/tempo/loudness) hiện dùng thì lập luận dư thừa vẫn đúng.

### 🎨 Color → music — **CIEDE2000-tới-1-màu yếu cơ sở**
- **GIỮ (M) — color→V-A (Jonauskaite/Palmer):** liên kết màu↔nhạc **qua CẢM XÚC**, không qua màu thô. Palmer PNAS 2013: tương quan cảm xúc nhạc↔màu **0.89–0.99**. [PNAS 2013](https://www.pnas.org/doi/10.1073/pnas.1212562110), [i-Perception 2018](https://journals.sagepub.com/doi/10.1177/2041669518808535)
- **YẾU-CƠ-SỞ (v) — CIEDE2000 tới 1 màu đại diện:** không nghiên cứu nào ủng hộ match nhạc bằng *khoảng cách màu thô tới 1 hex*; literature đi qua cảm xúc; 1 hex vứt bỏ cấu trúc đa-màu (hue×chroma×lightness). → hạ thành tie-break yếu hoặc bỏ; dùng **đa-màu→V-A**.
- **GIỮ — RRF** (đã đo SIG color-path); **VN context shift** = heuristic nhỏ.
- **MERT:** không phải cầu nối — chỉ thuộc **thượng nguồn** (ước lượng V-A của bài chính xác hơn).

### 📷 Image → music — **thiếu 2 kênh có bằng chứng**
- **GIỮ (M) — V-A là cầu nối** (ACM MM2020 [2009.05103], Multisensory Research 2022).
- **GIỮ-nhưng-nhiễu (v) — CLIP→emotion:** chỉ hơi trên ngẫu nhiên với ảnh trừu tượng → coi V-A từ CLIP là *mềm*. [arXiv 2405.06319]
- **THỪA (v) — image-dominant-color→V-A:** trùng ước lượng cảm xúc CLIP đã cho → gộp 1.
- **THIẾU (v) — embedding học emotion-aligned** (Won ICASSP2024 [2308.12610]) **+ semantic scene tags** (MMVA [2501.01094]) → nâng cấp có bằng chứng.

### 🌤️ Context — **thiếu session/sequence; weather marginal**
- **GIỮ (M) — time→arousal:** nhịp ngày-đêm về *cường độ/arousal* rất vững (Park 2019 *Nature HB* 765M plays; Heshmat 2021). *Nhưng biên độ nhỏ* → trọng số khiêm tốn, **arousal > valence**. [Nature HB 2019](https://www.nature.com/articles/s41562-018-0508-z), [RSOS 2021](https://royalsocietypublishing.org/doi/10.1098/rsos.210885)
- **GIỮ + SỬA (M) — activity:** đúng, nhưng phải khớp qua **thuộc tính diễn giải (tempo/energy/instrumentalness)**, không chỉ V-A (workout=BPM theo nhịp chân; North&Hargreaves 1998). V-A under-determine activity.
- **GIẢM cho VN (M) — season:** hiệu ứng tỉ lệ với biên độ ngày-dài → **yếu ở vĩ độ thấp** (VN).
- **MARGINAL — cân nhắc BỎ (M) — weather:** chỉ ~**6% variance**, chỉ top-chart, một nghiên cứu thấy weather **làm hại** hiệu quả → cap nhỏ/arousal-only, **ứng viên ablate đầu tiên**. [RSOS 2023](https://royalsocietypublishing.org/doi/10.1098/rsos.221443)
- **HEURISTIC — VN holiday:** editorial override, không phải V-A fitted.
- **THIẾU — session/sequence + repeat/skip** (M, **đòn cao nhất**): scorer hiện *pointwise*; literature đã chuyển sang *sequential/session* (Deezer RecSys'24 [2408.16578]). **+ day-of-week**.
- **MERT: KHÔNG** đưa vào lớp luật (giết explainability); activity-fit dùng thuộc tính diễn giải. [Audio Prototypical Net 2508.00194]

### ✨ Lyrics/Vibe Search — **thiếu emotion; centroid thừa**
- **GIỮ (M) — semantic(PhoBERT) + keyword:** keyword **KHÔNG dư thừa** — dense bỏ lỡ exact-term/tên riêng; đặc biệt quan trọng cho **tiếng Việt có dấu**. Hybrid > từng cái.
- **THỪA (w) — centroid-γ:** không cơ sở độc lập; là bản làm-mượt của semantic → bỏ/gộp trừ khi A/B cho lợi.
- **THIẾU (M cho valence) — emotion/V-A cho query *vibe*:** valence bắt tốt từ *lời/text* hơn audio; query "đêm mưa buồn" là biểu đạt cảm xúc → thêm term V-A/emotion (gate khi nhận diện query mood). [Hu & Downie], [arXiv 2302.13321](https://arxiv.org/abs/2302.13321)

### 🎯 Emotion Journey *(gác)* — **sửa trích dẫn + nâng smoothness**
- **GIỮ (M/v) — iso-principle:** RCT n=107 có ý nghĩa (η²≈0.17, *caveat:* có ở nữ, không ở nam). [PMC8656869](https://pmc.ncbi.nlm.nih.gov/articles/PMC8656869/)
- **GIỮ (M) — V-A Bézier waypoint.**
- ⚠️ **SỬA TRÍCH DẪN (w):** **"Saari 2016 ~10–15%/bước" KHÔNG xác minh được** — Saari là về *gán nhãn mood* (ACT), không phải tốc-độ-bước. → đổi nhãn thành **heuristic**, gỡ trích dẫn Saari (đang nằm ở hint UI journey + plan V10).
- **THỪA (w) — emotion-profile interpolation:** trùng V-A trừ khi mang nuance categorical.
- **GIỮ — lyrics-zone** (bổ valence), **no-repeat/artist diversity.**
- **NÂNG CẤP (v) — smoothness:** đổi cosine audio-feature → **cosine MERT** cho liền mạch tri giác (giữ key/LUFS cho ràng buộc cứng).

### 🔑 4 phát hiện xuyên suốt
1. **Dư thừa rõ nhất cần cắt:** mood-quadrant + V-A-riêng (similar) · CIEDE2000-1-màu (color) · centroid-γ (search) · image-color-V-A · emotion-interpolation (journey).
2. **Thiếu giá trị cao nhất:** session/sequence (context) · emotion/V-A term (vibe search) · semantic-tags + learned-embedding (image) · vocal/instrument (similar).
3. **Equal-weight sum hại nhất với dư thừa** → chuyển sang **học/tune trọng số fusion**.
4. **Sửa trích dẫn Saari** (chưa xác thực).

## 4. MERT — TỔNG KẾT "DÙNG / KHÔNG DÙNG"

**✅ Nên dùng MERT (câu hỏi về chất âm):**
- Similar songs (chính) · ~~Audio Radio~~ (đã gỡ surface 2026-05-30, code dormant) · KG content (xương sống) · *Journey-smoothness* (thử).

**❌ Không nên dùng MERT làm tín hiệu chính (sai câu hỏi):**
- Color→music · Image→music · Lyrics/Vibe search (text) · Context activity-fit (dùng thuộc tính diễn giải).
- *(Chỉ cân nhắc MERT như re-rank phụ ở color/image, và phải qua backtest.)*

**Lý do gốc:** MERT trả lời *"nghe như thế nào"*. Color/image/mood hỏi *"cảm xúc gì"* (→ V-A), lyrics hỏi *"về cái gì"* (→ text), context hỏi *"hợp lúc nào/làm gì"* (→ context-map). Nhồi MERT vào sai câu hỏi = thêm nhiễu, vi phạm S1/S4 (1.7).

---

## 5. ROADMAP THÍ NGHIỆM (ưu tiên, đều backtest-gated)

> Mọi thay đổi trọng số mặc định phải qua harness backtest (Bonferroni/CI) trước khi bật.

**Nhóm A — Cắt dư thừa (rủi ro thấp, củng cố triết lý; đo bằng backtest):**
1. **E1 — `recommend_by_song`: cắt dư thừa + học trọng số** *(M, CAO NHẤT)*: (a) **gộp cảm xúc về 1**; (b) **bỏ tonal/timbral/rhythmic**, tăng MERT; (c) **học trọng số** (SLSQP, ràng buộc sàn diversity).
   - ✅ **ĐÃ ĐO — drop-one-signal ablation (2026-05-30, editorial GT, baseline NDCG@10=0.0930):** ΔNDCG khi bỏ: **lyrics −0.0164** (quan trọng nhất, GIỮ) · **va +0.0072** (V-A *hơi hại* relevance) · tonal +0.0010 · emotion +0.0006 · timbral −0.0002 · mood +0.0001 · rhythmic +0.0001. → **Xác nhận:** lyrics áp đảo; cảm xúc-3-lần + thủ công-3 **không cải thiện relevance** (V-A hơi hại). *Caveat:* GT editorial (genre-playlist) thiên lyrics/topic; bỏ các tín hiệu này **giảm ILD/diversity** + V-A giữ mood-coherence (ΔMood −0.05) → có trade-off. (c) ✅ **`optimize-weights` XONG (SLSQP, sàn ILD≥95%):** trọng số tối ưu = lyrics **0.28→0.49**, va **0.17→0.013**, emotion 0.15→0.078, mood 0.10→0.056, rhythmic 0.10→0.19. **Kết quả CONFIRMED:** NDCG@10 Δ**+0.0128, CI95 [+0.0082, +0.0162]** (>0, SIG) · ILD **+0.043** · coverage **+0.026** · MoodCoherence −0.05. → *vừa tăng relevance VỪA tăng diversity* — đúng kỳ vọng V11.
   - ⚠️ **Áp dụng MỚI cho config 7-signal** (`RECO_SONG_WEIGHTS`, dùng khi ENABLE_MERT=False). **PRODUCTION dùng MERT 8-signal** (`RECO_SONG_WEIGHTS_MERT`) → **CHƯA** nhận cải thiện này. (Bug: optimizer ghi đè nhầm dict MERT thành 7 giá trị → đã sửa + khôi phục + vá writer.)
   - ✅ **E1b — config 8-signal MERT (PRODUCTION) ĐÃ TỐI ƯU & ÁP DỤNG (2026-05-30):** mở rộng `optimize-weights --mert` (x0=`RECO_SONG_WEIGHTS_MERT` 8-dim, ENABLE_MERT=True). **CONFIRMED:** NDCG@10 Δ**+0.0097, CI95 [+0.0063, +0.0155]** (>0) · ILD **+0.053** · coverage **+0.027** · MoodCoherence −0.021 (nhẹ). Trọng số mới: lyrics 0.25→**0.356**, **MERT 0.17→0.270**, V-A 0.15→0.058, emotion 0.13→0.075, tonal/rhythmic cắt mạnh → **xác nhận V11: lyrics+MERT gánh chính, cắt dư thừa**. ✅ **Đã vào production** (config sum=1.0, recommend_by_song chạy OK). Writer đã neo `\b`+count=1 (không phá dict kia).
   - **Kiểm chứng đa-metric (1050 queries, cũ vs mới):** NDCG +0.0082 · Precision@10 +0.0079 · Recall@10 +0.0008 (+18% rel) · MRR +0.0136 — **cả 4 đều dương** → win không phải artifact của NDCG. *(Bài học: gate nên report cả họ metric — NDCG + Recall@k + MRR — chứ không chỉ NDCG; Recall tuyệt đối nhỏ do GT editorial có tập-liên-quan lớn.)*
2. **E2 — KG bỏ thành phần `audio 0.1`** *(S)*: giữ MERT+mood+instrument; đo chất lượng + %same-artist (KG vốn một phần vòng lặp).
3. **E7 — Color bỏ/hạ CIEDE2000-1-màu** *(M)*: chuyển sang **đa-màu→V-A** (saturation→arousal, lightness→valence); đo color-path.
4. **E8 — Vibe search: bỏ centroid-γ** *(S)* + **thêm term emotion/V-A** cho query mood (gate); đo (cần GT chủ đề-lời).

**Nhóm B — Thêm tín hiệu THIẾU có bằng chứng (giá trị cao):**
5. **E9 — Context: session/sequence + repeat/skip + day-of-week** *(L, giá trị cao nhất mảng context)*: chuyển scorer pointwise → có ngữ cảnh phiên (Deezer RecSys'24). Hạ weather (ứng viên ablate) + giảm season cho VN.
6. **E10 — Image: thêm semantic scene tags** *(M)* (+ về sau learned emotion-aligned embedding Won 2024); gộp color-V-A trùng.
7. **E11 — Similar: tín hiệu vocal/instrument (stem)** *(M-L)*: cho catalog VN thiên giọng.

**Nhóm C — Đảm bảo nền + journey (khi mở lại):**
8. **E3 — Xác minh nguồn valence**: đã kiểm code (`val=0.6·audio+0.4·lyrics` ✓); coi như đạt, theo dõi.
9. **E5 — Journey: smoothness MERT** *(M)* + bỏ emotion-interpolation nếu trùng + **sửa trích dẫn Saari** (heuristic, không cited) ở hint UI + plan V10.
10. **E6 — Context KHÔNG thêm MERT** (giữ thuộc tính diễn giải cho explainability).

> Ưu tiên: **E1** (kiểm chứng triết lý "đừng dồn hết" + tăng tốc reco chính) → **E9** (đòn context giá trị cao nhất) → E7/E2/E8 (cắt dư thừa nhẹ) → E10/E11/E5 (thêm/ nâng cấp).

---

## 5.5. BACKTEST + VÒNG LẶP CẢI THIỆN THEO TỪNG FEATURE

> **Vì sao mỗi feature một cách đo riêng:** mỗi feature có *ground-truth (GT)* và *mục tiêu* khác nhau → dùng chung 1 metric là sai. Nguyên tắc xuyên suốt:
> - Dùng **harness sẵn có** (Bonferroni đa-biến · CI bootstrap cụm · auto-revert khi FAIL) — tránh lặp bài học **Pillar B "PASS giả do naive bootstrap"**. [Widespread Flaws in Offline Eval, arXiv 2307.14951](https://arxiv.org/pdf/2307.14951)
> - Đo **cả accuracy LẪN beyond-accuracy** (diversity/novelty/coverage) — đừng tối ưu mù 1 số. [Towards Unified Accuracy+Diversity, ACM 2021]
> - **Chống rò rỉ thời gian:** khi có log, dùng **global temporal split**, không leave-one-out. [Time to Split, arXiv 2507.16289](https://arxiv.org/abs/2507.16289)
> - **Offline là proxy** (offline-online gap có thật; novelty cao có thể *hại* online) → coi kết quả offline là *điều kiện cần*, không phải đủ; nơi nào cần cảm nhận người thì ghi rõ là *cần A/B/human* (hiện hệ thống thiếu log người dùng — đây là giới hạn).
> - **Vòng lặp chuẩn mỗi feature:** `đo metric → so gate (CI/Bonferroni) → nếu FAIL: chỉnh tín hiệu/trọng số theo chẩn đoán → re-test → chỉ bật mặc định khi PASS bền`.

| Feature | Ground-truth (GT) | Metric offline phù hợp | Gate (PASS khi) | Vòng lặp cải thiện |
|---|---|---|---|---|
| **Similar song** | editorial playlist / đồng-xuất-hiện genre-tag (đã có) + cặp cùng-playlist giữ lại | **nDCG@10, MAP, Recall@k** + beyond: **intra-list diversity, %same-artist (bias), coverage** | ΔnDCG ≥ baseline, CI không chạm ngưỡng fail, Bonferroni qua các biến thể; diversity không giảm | E1: cắt tín hiệu/gộp cảm xúc/học trọng số → nếu nDCG giữ & diversity ↑ → giữ; nếu tụt → khôi phục, thử *học trọng số* thay cộng đều → re-test |
| **Audio Radio** (MERT thuần) | *không có nhãn "nghe giống"* → **proxy:** (a) truy hồi **cover/bản trùng** (MERT phải xếp top); (b) **độ thuần nhãn** (instrument/mood/genre) của k láng giềng vs ngẫu nhiên | **tag/instrument neighbor-purity@k** vs random (bootstrap CI); cover-retrieval **MRR** (nếu có cover) | purity@k *cao hơn ngẫu nhiên có ý nghĩa* (CI) | nếu purity thấp → đổi *layer/pooling* MERT → re-test; (xa hơn) thu nhãn A/B người nghe |
| **KG content** | như similar + **%same-artist** (pillar-f-xartist đã có) | nDCG (không regress) + **%same-artist (mục tiêu thấp)** + genre-purity láng giềng | nDCG không tụt SIG **và** %same-artist không tăng | E2: bỏ `audio 0.1` → nếu relevance/bias giữ → bỏ cho gọn |
| **Color → music** | xác thực **color→V-A** bằng dataset color-emotion (Palmer/Jonauskaite); **proxy match:** V-A bài gợi ý ↔ V-A-của-màu | **V-A target proximity** (khoảng cách trung bình) + **emotion-match@k** + diversity | proximity tốt hơn ngẫu nhiên; **bỏ CIEDE2000-1-màu KHÔNG làm xấu** proximity | E7: thay bằng **đa-màu→V-A** → đo proximity+emotion-match → giữ nếu ≥ |
| **Image → music** | **IMEMNet (~140K cặp ảnh-nhạc gán V-A)** hoặc IAPS/NAPS/EMOTIC (ảnh có nhãn V-A) | **Recall@K** theo GT; khoảng cách V-A (ảnh↔bài) | R@K ≥ baseline emotion-bridge | E10: thêm **semantic scene tags** (+ sau: embedding học emotion-aligned) → đo R@K → giữ nếu ↑ |
| **Context** | *thiếu log* → **proxy:** thoả ràng buộc context (V-A đích + thuộc tính activity: focus→instrumental cao/speech thấp). *Khi có log:* **global temporal split**, dự đoán bài-nghe-tiếp trong ngữ cảnh đó | nay: **target-V-A proximity + activity-attribute-fit rate** + diversity. sau: **nDCG/Recall next-item** | nay: fit-rate cao + bỏ/hạ weather không giảm fit; sau: nDCG next-item ≥ | E9: thêm session/sequence + day-of-week (cần log); hạ weather/season VN → đo fit-rate giữ |
| **Emotion Journey** *(gác)* | *generative path — không cần GT người cho cấu trúc:* đo chất lượng quỹ đạo | **path-straightness, độ lệch chuẩn bước V-A, endpoint V-A error, start-match**; smoothness = **khoảng cách MERT liên-bài** (thấp=mượt) | quỹ đạo mượt & tới đúng đích; *hiệu quả điều tiết cảm xúc cần A/B người* (ghi rõ) | E5: smoothness→MERT, bỏ emotion-interpolation nếu trùng → đo step-distance + (nếu được) A/B nhỏ |
| **Vibe/Lyrics search** | **~100–150 cặp `query→bài-liên-quan` gán nhãn THỦ CÔNG** (không weak-annotation — theo ghi chú reranker); lyric-line: bài chứa đúng câu | **nDCG/MRR/Recall** + **lyric-line P@1** + (vibe) emotion/V-A match | nDCG/MRR ≥ baseline; P@1 lyric-line cao | E8: bỏ centroid-γ + thêm term emotion/V-A (gate query mood) → đo nDCG/MRR → giữ nếu ↑ |

**Việc nền bắt buộc (mở khoá nhiều backtest trên):**
- **GT-1:** dựng **GT chủ đề-lời thủ công ~100–150 cặp** (mở khoá Vibe-search + reranker).
- **GT-2:** nhúng **bộ ảnh có nhãn V-A** (IMEMNet/IAPS) vào harness (mở khoá Image→music R@K).
- **GT-3:** thêm **metric beyond-accuracy** (intra-list diversity, coverage, %same-artist) vào harness — hiện chủ yếu đo nDCG.
- **GT-4:** *(dài hạn)* thu **log nghe có ngữ cảnh** → mới đánh giá Context/Session đúng nghĩa (global temporal split). Tới đó Context chỉ đo *proxy fit-rate*.

> **Lưu ý trung thực:** các feature cảm xúc/cross-modal/context **chỉ đo được PROXY offline** khi chưa có log + nhãn người. Proxy (V-A proximity, attribute-fit, trajectory smoothness) là *điều kiện cần*, không thay được đánh giá người. Đừng coi proxy-PASS là "đã tối ưu cho người dùng".

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

**Bổ sung audit sâu 2026-05-30 (theo từng feature)**
- Palmer et al. — *Music–color associations mediated by emotion* (PNAS 2013): https://www.pnas.org/doi/10.1073/pnas.1212562110
- Whiteford et al. — *Color, Music, and Emotion: Bach to the Blues* (i-Perception 2018): https://journals.sagepub.com/doi/10.1177/2041669518808535
- Park et al. — *Global music streaming reveals diurnal & seasonal patterns of affective preference* (Nature Human Behaviour 2019): https://www.nature.com/articles/s41562-018-0508-z
- Heshmat et al. — *Diurnal fluctuations in musical preference* (RSOS 2021): https://royalsocietypublishing.org/doi/10.1098/rsos.210885
- Baltzersen et al. — *"Here comes the sun": weather & music* (RSOS 2023, weather marginal): https://royalsocietypublishing.org/doi/10.1098/rsos.221443
- North, Hargreaves & Heath — *Musical Tempo in a Gymnasium* (1998, activity↔tempo): https://journals.sagepub.com/doi/10.1177/0305735698261007
- Park & Hennequin (Deezer) — *Transformers Meet ACT-R: Repeat-Aware Sequential Listening Sessions* (RecSys'24): https://arxiv.org/abs/2408.16578
- Won et al. — *Emotion-Aligned Contrastive Learning Between Images and Music* (ICASSP 2024): https://arxiv.org/abs/2308.12610
- Choi et al. — *MMVA: V-A + musical-caption semantics for image↔music* (2025): https://arxiv.org/pdf/2501.01094
- Hu & Downie — *When Lyrics Outperform Audio for Music Mood Classification*: https://www.semanticscholar.org/paper/ab4e037b3edd362dbbde86f0c6a054dba572c90a
- *Comparative analysis of redundant/correlated features degrading fusion* (Oxford Bioinformatics 2011): https://academic.oup.com/bioinformatics/article/27/14/1986/194387
- MARBLE benchmark (NeurIPS 2023, deep emb > handcrafted MIR): https://arxiv.org/html/2306.10548
- *Disentangled / separated instrument-similarity representations*: https://arxiv.org/html/2404.06682 · https://arxiv.org/html/2503.17281
- *Audio Prototypical Network for Controllable Music Recommendation* (interpretable layer over embeddings): https://arxiv.org/html/2508.00194
- Iso-principle RCT (PMC8656869): https://pmc.ncbi.nlm.nih.gov/articles/PMC8656869/
**Phương pháp backtest/đánh giá offline (bổ sung §5.5)**
- *Widespread Flaws in Offline Evaluation of Recommender Systems* (arXiv 2307.14951): https://arxiv.org/pdf/2307.14951
- *Time to Split: Data Splitting Strategies for Offline Eval of Sequential Recommenders* (RecSys'25, arXiv 2507.16289): https://arxiv.org/abs/2507.16289
- *A Revisiting Study of Appropriate Offline Evaluation for Top-N Recommendation* (ACM TOIS): https://dl.acm.org/doi/full/10.1145/3545796
- *Towards Unified Metrics for Accuracy and Diversity* (RecSys 2021): https://dl.acm.org/doi/fullHtml/10.1145/3460231.3474234
- IMEMNet / cross-modal V-A retrieval eval (Recall@K): https://arxiv.org/abs/2009.05103 · https://arxiv.org/html/2501.01094
- ⚠️ *Saari "10–15%/bước"* — **không xác minh được nguồn**; Saari (JYU thesis) là về gán nhãn mood, không phải tốc-độ-bước → coi là heuristic: https://jyx.jyu.fi/bitstream/handle/123456789/45096/978-951-39-6074-2.pdf

---

*Plan này dựa trên bằng chứng công khai đã kiểm chứng + ground-truth codebase. Nguyên tắc cốt lõi: **khớp tín hiệu với câu hỏi, thêm có chọn lọc, đo bằng backtest** — không "dồn hết cho mạnh". Mọi mục §5 phải qua harness backtest trước khi bật mặc định.*
