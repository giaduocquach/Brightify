# Brightify — Master Upgrade Plan (V10)

> **Ngày:** 2026-05-29
> **Mục tiêu:** Nâng cấp toàn diện — (1) tăng *trí thông minh* của từng tính năng AI, (2) đưa mỗi tính năng về *đúng vị trí UI/UX* để người dùng dễ chạm tới & nhận giá trị cao nhất.
> **Cơ sở:** Ground-truth từ codebase (wiring AI, backtest, KG, UI/UX) + nghiên cứu thị trường/tâm lý người dùng (xem `MARKET_RESEARCH_REPORT.md`) + paper kỹ thuật (liệt kê mục 8).
> **Nguyên tắc nền:** *Đưa AI có sẵn lên bề mặt dưới dạng kiểm soát · minh bạch · cảm xúc · bản sắc Việt.* Không thêm tín hiệu cho có.

---

## 0. BÁO CÁO XÁC MINH (theo yêu cầu)

### 0.1. Pillar B (ViDeBERTa/ViSoBERT/SimCSE) — ✅ Trí nhớ của bạn ĐÚNG
- **Đã xây + đo nghiêm túc.** Có embeddings `data/vietnamese_music_embeddings_pillar_b.npy` + backtest đầy đủ.
- **Kết quả: FAIL.** NDCG@10 baseline 0.09119 → Pillar B 0.09414, **Δ +0.00102 (~0.1%)**, CI95 **[−0.0089, +0.0068]** — *chạm vùng âm*, vượt ngưỡng fail −0.005.
- **Commit `0e977f9` (2026-05-28):** *"re-run flips Pillar B to FAIL … Honest stats reject it; config auto-reverted ENABLE_PILLAR_B=False. Old PASS was a naive-bootstrap artifact."*
- **`docs/BACKTEST_REPORT.md`:** *"B — SimCSE: +0.001, khoảng tin cậy chạm vùng âm ❌ BỎ, quay lại PhoBERT."*
- **Kết luận:** Tắt **có cơ sở thống kê vững**. Giữ tắt. (Lưu ý nhỏ: ViSoBERT *có thể* hữu ích riêng cho slang mạng xã hội/comment nếu sau này có chức năng đó — nhưng chỉ bật lại nếu có ground-truth riêng cho domain đó.)

### 0.2. Cross-Encoder Reranker — ⚠️ Trí nhớ của bạn CHỈ ĐÚNG MỘT NỬA
- **Đã xây** (`core/reranker.py`, model `mmarco-mMiniLMv2-L12-H384`), wired vào `recommend_by_lyrics_keywords()`.
- **NHƯNG chưa bao giờ đo riêng hiệu quả.** Backtest Pillar C chỉ đo **RRF** (RRF có lợi: Δ+0.056 trên color path, SIG). Reranker ON-vs-OFF **không có số liệu nào**.
- **Lý do tắt (theo comment `config.py:249-252`):** *"requires sentence-transformers and extra inference time"* — tức **latency/chi phí**, KHÔNG phải "đã chứng minh vô hiệu".
- **Kết luận:** Khác với Pillar B. Reranker là **ẩn số chưa đo**. → **ĐÃ ĐO trong Phase 0 (2026-05-29):** chi phí gấp đôi latency (+191ms/query) nhưng chỉ reorder top-10 (overlap@10=10/10, không đổi tập bài). **Quyết định: giữ tắt.** Chi tiết & điều kiện xét lại ở mục 6.4.

### 0.3. KG embeddings — ✅ Xác nhận root cause "gợi ý theo tác giả, không theo nhạc"
- `tools/build_kg_embeddings.py` xây **đồ thị lưỡng phân thuần artist/album** (edge: song→artist 1.5, song→album 1.0, song→featured 0.8) rồi SVD 64-dim.
- **Đo thực nghiệm:** cặp **cùng nghệ sĩ** có KG-sim trung bình **0.99** (97.7% cặp > 0.9, nhiều cặp = 1.0); cặp khác nghệ sĩ ≈ **0.0**. → Embedding **gần như 100% là "cùng tác giả/album", ZERO tín hiệu nhạc.**
- **Cách dùng:** `recommend_by_song` cộng thẳng `+0.05 * kg_sim` (dòng 641-644) → **mọi** bài cùng tác giả được +0.05 vô điều kiện, kể cả khác hẳn về nhạc.
- **Nguồn thiên vị KHÁC (cộng hưởng):** PhoBERT lyrics (48% cặp cùng nghệ sĩ >0.9 — cùng phong cách lời), MERT (56% — cùng chất âm/giọng), mood-match (cùng nghệ sĩ → cùng mood → bonus). KG là thủ phạm *hệ thống & vô lý* nhất.
- **Dữ liệu sẵn có để xây lại:** MERT (768-dim audio), `mood_tags` (Essentia), `instrument_tags`, audio features, PhoBERT. **Không có** dữ liệu co-listening/playlist/user-interaction.
- **Kết luận:** KG cần **xây lại theo nội dung nhạc** (mục 6.3) + **bỏ +0.05 bonus thuần-tác-giả**.

---

## 1. NGUYÊN TẮC THIẾT KẾ (rút ra từ nghiên cứu)

| # | Nguyên tắc | Bằng chứng nghiên cứu |
|---|---|---|
| P1 | **Home = ngăn xếp shelf theo ngữ cảnh**, không phải danh mục tĩnh. Daypart/mood/hoạt động quyết định nội dung. | Spotify Home/Daylist: layout đổi theo giờ/mood/hoạt động; "recommendation engine với UI ở trên". |
| P2 | **Minh bạch tạo niềm tin.** Mỗi gợi ý nên giải thích được; cho user *điều khiển* tín hiệu. | EXPLORE/transparent RecSys 2024: explainability ↑ trust & forgiveness; DSA 2024 còn bắt buộc. |
| P3 | **Mood/ngữ cảnh > thể loại.** Gen Z tìm theo *vibe*, không theo genre. | BPI/Music Ally 2025: "musical omnivores", ưu tiên mood. |
| P4 | **Tương tác bằng ngôn ngữ tự nhiên** là hướng đi của RecSys nhạc. | TalkPlay, CHI 2025 conversational RecSys: NL giúp làm rõ nhu cầu ẩn. |
| P5 | **Gợi ý phải dựa trên nội dung nhạc**, không chỉ metadata/tác giả, để chống bias & cold-start. | arXiv 2409.09026 (CLAP audio emb cho graph RecSys); Hybrid GNN (Springer 2024). |
| P6 | **Giảm ma sát.** Tính năng giá trị cao phải ≤1-2 click từ home. | Hiện tại mọi tính năng AI chôn 2+ click trong AI Lab. |
| P7 | **Trao quyền, không tước quyền.** User nắm *ý định* (đích/đầu vào), máy lo *thực thi* (đường đi/xếp hạng). | Spotify AI DJ bị chê "loss of agency"; bài học trực tiếp. |

---

## 2. BẢN ĐỒ "ĐẶT LẠI ĐÚNG CHỖ" (UI/UX)

**Hiện trạng:** Sidebar 5 mục (Home / AI Lab / Liked / History / Artists). Home có 8 section tĩnh. **Toàn bộ 5 tính năng AI** (màu, lyrics, ảnh, journey, context) **nằm trong AI Lab, sâu 2+ click.** Không có "vì sao", không có phản hồi tiêu cực, không có núm điều khiển đa dạng. `app.js` là monolith 2,429 dòng.

**Tầm nhìn đặt lại:**

| Tính năng | Hiện ở đâu | Đưa về đâu | Lý do |
|---|---|---|---|
| **Context Mix** | AI Lab tab 5 | 🏠 **Home — shelf động "Ngay bây giờ"** (auto theo giờ/mood/lễ) | P1, P6. Đây là "playlist hợp ngữ cảnh" = tiêu chí #1 của user Việt (64.3%). |
| **Emotion Journey** | AI Lab tab 4 | 🏠 **Home — thẻ "Tâm trạng"** + 🎵 nút trong Player ("đổi mood") + chế độ Wellness | P3, P7. Khác biệt thương hiệu mạnh nhất. |
| **Search hợp nhất** (gộp Lyrics search) | AI Lab tab 2 | 🔝 **Thanh search toàn cục**: tên · câu lyrics · mô tả vibe → **khớp-nhất-trước, liên-quan-dưới** | P4. Gì cũng tìm ra; biến search thành cửa AI chính. |
| ~~**Similar / Radio**~~ | Context menu | ❌ BỎ (2026-05-29) | F6 đã làm reco thuần "giống về nhạc"; không có logic "cùng nghệ sĩ" để tách (xem nghệ sĩ = điều hướng qua trang artist). |
| **Color + Image** | AI Lab tab 1,3 | 🧪 **Gộp 1 mục "Bắt vibe từ ảnh/màu"** trong khu "Khám phá" (giữ làm hook, không phải cửa chính) | P6. Là novelty/wow, không phải daily-use. |
| ~~**Discovery Dial** (MMR/DPP)~~ | (ẩn ngầm) | ❌ BỎ (2026-05-29) | Loại theo yêu cầu user. MMR vẫn chạy ngầm, λ cố định. |
| ~~**"Vì sao bài này"**~~ | (không có) | ❌ BỎ (2026-05-29) | Loại theo yêu cầu user. |
| **Phản hồi "không hợp lúc này" / dislike** | (chỉ có like) | ⏸️ hoãn — cần lớp cá nhân hóa (xem F10) | Pain #2, nhưng phụ thuộc kiến trúc chưa có. |

> **AI Lab** không biến mất — nó trở thành **"Khám phá / Phòng thí nghiệm"** cho input lạ (màu, ảnh) và người dùng nâng cao; còn *discovery hằng ngày* chuyển hết về Home + Search + Player.
>
> **Trạng thái AI Lab (2026-05-29) — còn 3 tab:** `🎨 Bắt vibe từ ảnh/màu` (gộp F5 ✅) · `✨ Tìm theo cảm xúc` (GIỮ TẠM tới khi F3 đưa lên search) · `🎯 Hành trình` (GIỮ TẠM tới khi F2-REDESIGN xong, sẽ thành cửa "nâng cao"). Tab `🌅 Hôm nay` đã **GỠ** (trùng shelf Home tự động). Markup + JS chết của context tab đã dọn (`context-init.js` chỉ còn app-bootstrap).

---

## 3. PLAN THEO TỪNG FEATURE

> Mỗi feature gồm: **[AI]** nâng trí thông minh · **[UX]** đặt đúng chỗ · **[Effort]** S/M/L.

### F1. Context Mix → "Ngay bây giờ" (shelf động trên Home) — ✅ ĐÃ LÀM (2026-05-29)
- **[AI]** (a) ✅ **Nối `vn_context` vào `smart_context_recommend`** — lễ Việt + thời tiết live OWM nay tác động vào target V-A của Home (trước chỉ color reco dùng). (b) ⏳ *chưa* — tín hiệu MERT/mood_tags theo "chất" hoạt động (để Phase 3 / F7). (c) ⏳ *chưa* — nhiều shelf daypart kiểu Daylist (1 shelf "Ngay bây giờ" trước, mở rộng sau nếu cần).
- **[UX]** ✅ Shelf **đầu Home, tự chạy theo giờ — 0 click, không nút generate** (theo yêu cầu user). Subtitle hiện ngữ cảnh đầy đủ. Chip tinh chỉnh hoạt động/thời tiết ngay tại shelf: *chưa* (auto-mode trước; chip thủ công vẫn ở AI Lab tab "Hôm nay").
- **[Effort]** M — ĐÃ XONG phần lõi (re-wire + shelf Home auto).

### F2. Emotion Journey → "Liệu trình cảm xúc" (Home card + Player + Wellness) — ✅ ĐÃ LÀM (2026-05-29)
- **[AI]** (a) ✅ **Auto-đoán điểm bắt đầu** từ bài đang nghe (`get_song_va` + `start_track_id`, bỏ nhập tọa độ V-A). (b) ⏳ **Rumination HOÃN** — cần theo dõi Q3 kéo dài qua lịch sử; nudge opt-in, ưu tiên thấp. (c) ✅ Preset theo *nhu cầu* (`MOOD_SHIFTS`: Vực dậy / Hạ lo âu / Ru ngủ / Tập trung).
- **[UX]** ✅ Thẻ "🎭 Đổi tâm trạng" trên Home (1 chạm → tạo + phát ngay) + nút 😊 trong Player (popover, hành trình từ bài đang nghe). **P7 giữ:** user chọn *đích*, máy lo *đường*. Wellness mode đầy đủ vẫn ở Phase 4.
- **[Effort]** M — XONG phần lõi (auto-start + need-presets + 2 điểm chạm UI).

#### F2-REDESIGN (2026-05-29) — phản hồi user: "bản Home CHƯA WOW & phí tính năng; nhưng để trong AI Lab lại quá khó dùng"
**Chẩn đoán gốc:** *Giá trị của journey là CUNG CẢM XÚC theo THỜI GIAN, nhưng hiện không gì làm cung đó "thấy được" hay "cảm được".* Bấm xong là thành một hàng đợi như mọi playlist → mất cảm giác "đang được dẫn dắt". Hai lối vào hiện tại đều lệch: thẻ Home = 4 nút phẳng (đích trừu tượng, phát mù), AI Lab = picker V-A (đòi hiểu valence/arousal → dọa người dùng). Khu trung gian — *xem trước cung + thấy mình đang ở đâu trên cung khi nghe* — thì trống.

**Nguyên tắc thiết kế lại** (P1 surface-as-control, P2 minh bạch/EXPLORE, P3 vibe-first, P7 trao quyền):
1. **Cung cảm xúc THẤY ĐƯỢC & CẢM ĐƯỢC khi phát ("Journey Mode" trong Player)** — dải arc mảnh trong player: điểm bắt đầu → đích, *chấm "bạn đang ở đây" bước k/N*, nhãn micro-mood tiếng Việt ("đang: buồn nhẹ → hướng tới: bình yên"). Đây là phần WOW: user *nhìn thấy mình đang được dẫn*. Tái dùng `_drawJourneyVisualization` (canvas đã có) thu nhỏ vào player.
2. **Vào bằng NGÔN NGỮ CẢM XÚC, không bằng V-A** — lối chính = (a) auto-start từ bài đang nghe (✅ đã có) + (b) chọn đích là *kết quả mong muốn*. Picker V-A hạ xuống mục "Nâng cao" gập lại (giữ cho power-user → hết "quá khó"; graph thành opt-in).
3. **XEM TRƯỚC trước khi cam kết** — chạm đích → sheet nhỏ hiện *đường cong cảm xúc* + 2–3 bài đầu + thời lượng ước tính → nút "Bắt đầu hành trình". Bỏ cảm giác "nút mù", tăng tin tưởng (P2).
4. **RE-STEER khi đang nghe (P7)** — điều khiển "ở lại tâm trạng này lâu hơn" / "tới đích nhanh hơn" → sinh lại các bước còn lại. User nắm tốc độ cung.
5. **Preset có BẢN SẮC VIỆT theo khoảnh khắc** (thay nhãn mood trừu tượng) — "Thất tình 3am → ngủ được", "Cày deadline khuya", "Sáng Chủ nhật chữa lành", "Khóc cho xong rồi nguôi". Khác biệt thương hiệu + đúng P3.
6. **Journey là MỘT NƠI, không phải một nút** — arc visualization làm *hero*, tới được từ cả thẻ Home lẫn Player (overlay nhẹ), không chôn trong tab.

**Tiến độ:**
- ✅ **F2.2 (2026-05-29)** — "Journey Mode" trong Player: dải `#journey-strip` nổi trên player bar khi đang phát hành trình (`player._playSource==='emotion-journey'`), mini-arc canvas (arousal=trục dọc/năng lượng, hue theo tiến trình) + chấm "bạn đang ở đây" bước k/N + nhãn "đang → hướng tới" + nút thoát. `window._activeJourney` giữ raw journey songs; hook trong `player._updateUI`; tự ẩn khi đổi queue/stop.
- ✅ **F2.1 (2026-05-29)** — Sheet **xem-trước-cung** + dẫn bằng human-preset: `openMoodPreview(key)` (Home card · nút Player · AI Lab) sinh journey rồi mở overlay preview (mini-arc + start→dest mood + 3 bài đầu + ~thời lượng) → "Bắt đầu hành trình" (`playPreparedJourney` → loadQueue + Journey Mode). Thay luồng phát-mù cũ. **AI Lab journey tab:** 4 need-preset dẫn đầu, toàn bộ picker V-A/quick-mood/preset gập vào `<details>` "⚙️ Tùy chỉnh nâng cao" → hết "quá khó".
- ✅ **F2.7 (2026-05-29)** — Độ dài thích ứng + "tới đích rồi ở lại": preview cho chọn **Ngắn ~6 / Vừa ~8 / Dài ~12** (regenerate qua `_genPreview`, trong khoảng endpoint 6–15) + toggle **🔁 "Tới đích rồi ở lại"**. Dwell = gọi journey `start==end` tại V-A đích (`extendJourneyDwell`) → pre-append nền lúc bắt đầu + top-up khi hết queue (nhánh mới trong `player._onTrackEnd`, mô phỏng radio) → nghe không dừng. Strip hiện "🎯 Đã tới đích · đang giữ \<mood>" ở pha dwell. *Lưu ý:* dwell cụm quanh đích nhưng hơi lệch (engine blend đa tín hiệu, không V-A-thuần) — siết sau bằng endpoint V-A-nearest nếu cần.
- ✅ **F2.6 (2026-05-29)** — Taxonomy theo MMR: thêm họ **"Ở lại · biểu đạt"** (`type:'stay'`) cạnh họ "Đổi" (`type:'shift'`). 3 preset stay: **💧 Buồn cùng mình** (solace, target Q3) · **🔥 Xả** (discharge, high-arousal) · **✨ Giữ vibe vui** (entertainment). Kỹ thuật: stay = journey `start==end==target` + dwell (tái dùng F2.7) → settle & ở lại, KHÔNG ép dịch. Preset gom 2 nhóm có nhãn (helper `moodPresetButtonsHTML` dùng chung Home + AI Lab; Player popover cũng nhóm). Strip/preview hiện "đang ở lại: \<mood>". *Đo:* solace cụm đúng (val .30/aro .33), vibe đúng (.71/.57); **discharge lệch valence (.32→.63)** vì catalog VN ít nhạc giận-dữ → ra nhạc *mạnh/sôi* (chấp nhận; siết sau bằng V-A-nearest). *Cảnh báo rumination (solace/discharge) chờ F2.b.*
- *Còn lại: F2.3 (re-steer) · F2.4 (preset bản-sắc-Việt) · F2.5 (đổi mood nhanh 5 phút).*
- ⏸️ **TẠM GÁC TOÀN BỘ EMOTION JOURNEY (2026-05-29, quyết định user):** đây là feature *khó & quan trọng*, cần **nghiên cứu sâu hơn** (mô hình cảm xúc, đánh giá hiệu quả, UX) trước khi đầu tư tiếp. F2.1/F2.2/F2.6/F2.7 đã code & commit nhưng **CHƯA smoke-test browser** — coi là *bản nháp đặt nền*, không phát triển thêm F2.3/4/5 cho tới khi có nghiên cứu chuyên sâu. Khi quay lại: bắt đầu bằng smoke-test + thiết kế đánh giá (đo hiệu quả điều tiết cảm xúc), rồi mới mở rộng.

**Lộ trình thực hiện (đề xuất, Phase 3):**
- **F2.1** *(M)*: Sheet xem-trước-cung khi chọn đích (Home + AI Lab); dẫn bằng human-preset; V-A picker → "Nâng cao" gập. → *giải quyết "AI Lab quá khó" + "phát mù".*
- **F2.2** *(M)*: "Journey Mode" trong Player — dải arc + chấm bước hiện tại + chip "vì sao bài này hợp bước này". → *phần WOW chính.*
- **F2.3** *(M)*: Re-steer khi đang phát (sinh lại bước còn lại từ bài hiện tại + đích).
- **F2.4** *(S)*: Bộ preset bản-sắc-Việt theo khoảnh khắc.
- **F2.5** *(S)*: bản "đổi mood nhanh 5 phút" (3–4 bài).
- **F2.6** *(M)*: **Taxonomy chế độ theo tâm lý điều tiết cảm xúc** (xem F2-NGHIÊN-CỨU bên dưới).
- **F2.7** *(M)*: **Độ dài thích ứng + "tới đích rồi ở lại"** thay fix cứng 8 bài (xem F2-NGHIÊN-CỨU).

#### F2-NGHIÊN-CỨU (web, 2026-05-29) — phản hồi user: "4 chế độ thế?" + "fix cứng 8 bài, muốn nghe hơn thì sao?"

**(1) 4 chế độ là CHƯA ĐỦ & lệch — căn cứ tâm lý học.** Saarikallio *Music in Mood Regulation* (MMR, 2008/2011) xác định **7 chiến lược** người ta thực sự dùng nhạc để điều tiết cảm xúc: *entertainment* (giữ vibe đang vui), *revival* (hồi sức/thư giãn), *strong sensation* (phiêu/cường độ mạnh), *diversion* (đánh lạc hướng khỏi lo âu), *discharge* (xả — sống cùng cơn giận/buồn qua nhạc hợp tâm trạng), *mental work* (suy ngẫm/tái định khung), *solace* (được an ủi khi buồn). **Vấn đề cốt lõi:** 4 chế độ hiện (Vực dậy/Hạ lo âu/Ru ngủ/Tập trung) đều giả định *"chuyển sang tâm trạng TỐT hơn"* — nhưng **không phải nhu cầu nào cũng là dịch chuyển**: *solace* và *entertainment* là **ở lại** với tâm trạng (được an ủi / giữ vibe), *discharge* là **biểu đạt** chứ không "sửa". Ép buồn→vui có thể **vô hiệu hoá cảm xúc** (invalidating).
- → **Thiết kế lại preset thành 2 họ:**
  - **Đổi sang (iso A→B):** Vực dậy (revival/diversion) · Hạ lo âu (relaxation) · Ru ngủ (deep relax) · Tập trung (mental work).
  - **Ở lại / biểu đạt (dwell tại một vùng V-A, không ép dịch):** **"Buồn cùng mình"** (solace — ở lại Q3, nhạc an ủi) · **"Xả"** (discharge — cường độ/giận) · **"Giữ vibe"** (entertainment — duy trì mood đang tốt) · *(tùy chọn)* "Phiêu hết mình" (strong sensation).
- **Cảnh báo wellness (Sakka & Juslin 2018; trầm cảm):** *solace/discharge* nếu lạm dụng có thể thành **nhai-lại (rumination)** ở người trầm cảm. → các chế độ "ở lại" phải đi kèm **nudge nhẹ opt-in** (chính là **F2.b rumination** đang HOÃN): sau thời gian dài ở Q3 → *gợi ý* (không tự đổi) "thử nhẹ chuyển hướng?". Tôn trọng P7.
- **Không nhồi 7 nút:** giữ ~5–6 preset rõ nghĩa (đủ phủ shift + ít nhất 1 "solace" + 1 "discharge"); phần đuôi dài giao cho **F3 mô tả tự nhiên** ("muốn được an ủi", "cần xả").

**(2) Fix cứng 8 bài — bỏ; cho độ dài thích ứng + "tới đích rồi ở lại".** Bằng chứng: 5–6 bài là khởi điểm tốt, **10–15 bài "vừa tay"**, phiên trị liệu iso ~**30 phút**; *không có con số một-cho-tất-cả*, nhấn mạnh **cá nhân hoá** (It's Complicated; Dynamic Lynks; thử nghiệm iso NCT05442099). 8 bài (~28′) hợp lý làm *mặc định* nhưng phải cho chọn.
- **Chọn độ dài:** Ngắn (~5 bài/15′) · Vừa (~8/28′, mặc định) · Dài (~12/40′) — hoặc theo **phút**. Lộ ngay ở **sheet xem-trước** (F2.1) + truyền `steps` xuống endpoint (đã hỗ trợ 6–15; cần mở trần nếu muốn >15).
- **"Tới đích rồi ở lại" (đòn chính, giải đúng "muốn nghe hơn"):** iso đưa BẠN TỚI tâm trạng đích — **đừng dừng phựt**; khi hết các bước chuyển, **tự phát tiếp các bài quanh V-A đích** (radio neo tại đích = chiến lược *entertainment/maintain*). Nghe bao lâu tùy ý mà vẫn giữ tâm trạng đã đạt. Toggle "🔁 Ở lại tâm trạng đích". Kỹ thuật: sau N bài journey, nối thêm bằng kNN quanh V-A cuối (hoặc `smart_context` neo V-A đích).
- **Endless:** bật từ "ở lại đích" — không bao giờ dừng cho tới khi user đổi.

> **Quyết định tab "🎯 Hành trình" (AI Lab):** GIỮ tạm (chưa xóa) tới khi F2.1+F2.2 xong — lúc đó nó trở thành cửa "nâng cao" với arc-preview dẫn đầu, picker V-A gập lại. Tab "🌅 Hôm nay" (context) đã **GỠ** (2026-05-29) vì trùng hoàn toàn với shelf Home tự động.

**Nghiên cứu bổ sung (web, 2026-05-29) — củng cố hướng trên:**
- **Iso-principle lâm sàng** (PMC8656869; feed.fm; Heartfelt Harmony): hình ảnh chuẩn của kỹ thuật chính là **"music arc"** (match hiện trạng → dịch dần) → xác nhận *arc visualization là đúng metaphor*. Quan trọng: **"phẩm chất nhạc > thể loại"** (chọn theo chất, không theo genre — đúng với fusion V-A/MERT của ta). Mood có thể điều biến **trong ~5 phút** → **thêm bản "Đổi mood nhanh 5 phút"** (3–4 bài) cạnh journey dài; wow & actionable hơn hàng đợi 8 bài.
- **Spotify Daylist UX** (Raw.Studio; UX Magazine): (1) **cover/màu gói tâm trạng TRƯỚC khi bấm play** → arc-preview của ta nên có *ảnh bìa động + dải màu* theo cung cảm xúc (canvas hue-gradient sẵn có tái dùng làm cover). (2) **Title + mô tả nổi bật** cho biết "vì sao/đang ở đâu" → đặt **tên journey thân thuộc, đổi theo ngữ cảnh** ("3am chữa lành", "Sáng cà phê tỉnh dần") thay nhãn V-A. (3) **Palette đổi dần theo tiến trình** → trong Journey Mode, màu player **chuyển dần** theo bước (thấy mình "đang đi"). (4) Nút hành động không-ma-sát + feedback.
- **Tổng hợp → ưu tiên F2.2 (Journey Mode thấy-được-cung) + F2.1 (preview có cover/màu/tên)** là 2 đòn wow chính; thêm **F2.5** *(S)*: bản "đổi mood nhanh 5 phút". Nguồn liệt kê ở §8.

### F3. Search HỢP NHẤT — "gì cũng tìm ra: tên · lyrics · vibe" (thanh search toàn cục) — ✅ LÕI ĐÃ LÀM (2026-05-29)
**Đã làm:** endpoint `/api/songs/search/unified` chạy 3 matcher → trả `{matches, related}`: (1) name/artist/album substring, (2) **lyrics-line substring** trên `plain_lyrics` (sửa bug `/songs/search` không search lời), (3) semantic `recommend_by_lyrics_keywords` cho "liên quan/cùng vibe" (đã trừ matches). FE: dropdown search toàn cục đổi sang `searchUnified` → render **2 nhóm "🎯 Khớp nhất" + "🔗 Liên quan · cùng vibe"** (match theo lời gắn tag "· lời"); placeholder mời cả 3 kiểu. Đo end-to-end: tên/câu-lyrics/mô-tả-vibe đều ra đúng, khớp-nhất nổi đầu. **Còn lại (follow-up):** Enter → *trang kết quả đầy đủ* (play-all) để thật sự thay tab "✨ Tìm theo cảm xúc" (dropdown 5–6 mục chưa thay được trải nghiệm "vibe → cả playlist"); **giữ tab lyrics tới lúc đó.**

> **Cập nhật yêu cầu user (2026-05-29):** KHÔNG còn là "route sang 1 chế độ". Mục tiêu: **gõ gì cũng ra kết quả đúng**, và **kết quả khớp nhất luôn nằm trên cùng, bên dưới là bài tương đồng/liên quan**. Tức search hợp nhất 3 nguồn, xếp lớp — không bắt user chọn "tìm theo tên" hay "theo vibe".
- **[AI]** Một ô search chạy **song song 3 matcher** rồi **trộn + xếp lớp**:
  1. **Tên/metadata** (track_name, artist, album) — khớp chính xác/substring.
  2. **Lyrics-line** (gõ một câu lời → ra đúng bài chứa câu đó) — substring/`pg_trgm` trên `plain_lyrics`/`lyrics_cleaned`.
  3. **Semantic vibe/cảm xúc** (mô tả tâm trạng → PhoBERT/lexicon + RRF, endpoint `recommend_by_lyrics_keywords` đã có).
- **[UX]** Kết quả **xếp lớp, minh bạch (P2):**
  - **"🎯 Khớp nhất"** (trên cùng): bài/nghệ sĩ trùng tên, hoặc bài chứa đúng câu lyrics, hoặc bài hợp nhất mô tả vibe — *thứ user thực sự gõ*.
  - **"🔗 Liên quan / Cùng vibe"** (dưới): láng giềng nội dung (MERT/V-A/lyrics-semantic) của kết quả top — "more like this".
  - Placeholder mời cả ba ("Tìm bài, lời hát, hay tả cảm giác bạn muốn nghe"); header nói rõ đã hiểu gì.
- **[Effort]** M (3 matcher + lớp `searchUnified` trộn-xếp; LLM intent là tùy chọn sau).

#### F3-CƠ-CHẾ — search hợp nhất "khớp-nhất-trước, liên-quan-dưới" (chi tiết)
**Hiện trạng (ground-truth):** (1) `/api/songs/search` thực ra **chỉ tìm tên** track/artist/album — **docstring nói "lyrics keywords" nhưng KHÔNG hề search lyrics** (bug nhẹ). (2) Lyrics chỉ có ở semantic `/api/recommend/lyrics` (PhoBERT). (3) DB có `plain_lyrics`/`lyrics_cleaned` + index `gin_trgm_ops` → **đủ hạ tầng cho lyrics-line search**.

**Thiết kế `searchUnified(query)`:**
1. Chạy song song: `nameMatch` (exact + substring tên), `lyricsMatch` (substring/trgm trên lyrics — **cần bổ sung**, sửa luôn bug docstring), `vibeMatch` (semantic emotion+lyrics).
2. **Chấm độ tin cậy & gộp:** exact-name / lyrics-line khớp nguyên câu = *confidence cao* → nhóm **"Khớp nhất"**. Phần còn lại (semantic neighbors, cùng vibe, cùng chủ đề lời) → nhóm **"Liên quan"**. Khử trùng theo track_id giữ thứ hạng cao nhất.
3. **Vì sao layered (đúng ý user):** *gõ tên* → bài đó top, rồi bài cùng nghệ sĩ/giống nhạc dưới; *gõ câu lyrics* → bài chứa câu đó top, rồi bài cùng chủ đề lời; *gõ mô tả vibe* → bài hợp nhất top, rồi cùng vibe dưới. **Gì cũng ra, đúng nhất luôn nổi lên đầu.**
4. **Free-tier:** name/lyrics matcher là DB/df thuần (không model); chỉ vibe-matcher cần PhoBERT (đã warm sẵn). Không bắt buộc LLM. LLM phân loại intent = nâng cấp tùy chọn (TalkPlay/CHI 2025).
5. **Nối F2:** nếu query là *mô tả mood chuyển dịch* ("buồn… rồi nguôi ngoai") → thêm gợi ý "tạo **hành trình cảm xúc** từ mô tả này".
> Backend chủ yếu **tái dùng** (name search + `/recommend/lyrics`); việc mới = **thêm lyrics-line matcher** (trgm/substring) + lớp `searchUnified` trộn-xếp + UI 2 nhóm kết quả. Khi F3 ship → **gỡ tab "✨ Tìm theo cảm xúc"** khỏi AI Lab (hiện GIỮ tạm tới lúc đó).

### F4. ❌ BỎ HẲN (2026-05-29, quyết định user)
- **Lý do:** sau F6, `recommend_by_song` đã **thuần "giống về nhạc"** (KG content MERT+mood+instrument+audio, bỏ bonus artist). **KHÔNG còn — và không nên có — thuật toán gợi ý "cùng nghệ sĩ"** nào (đó chính là bias mà F6 đã sửa tận gốc). Việc xem nhạc của một nghệ sĩ đã có sẵn qua **điều hướng** (trang artist / `/artists/{name}/songs`), không phải một "ý định gợi ý" cần nút riêng. → Ý tưởng "hai nút Giống-về-nhạc vs Cùng-nghệ-sĩ" là **thừa & mâu thuẫn triết lý F6**. Bỏ.

### F5. Color + Image → gộp "Bắt vibe từ ảnh/màu" (hook) — ✅ ĐÃ LÀM (2026-05-29)
- **[AI]** Giữ nguyên (CIEDE2000 + CLIP đã tốt). Tùy chọn (chưa làm): dùng MERT xếp hạng tinh hơn sau khi map màu→V-A — để Phase 3/F7.
- **[UX]** ✅ Gộp 2 tab thành **1 màn** "🎨 Bắt vibe từ ảnh/màu" (header "Soundtrack cho khoảnh khắc"): chọn màu *hoặc* thả ảnh trong cùng panel, chung luồng kết quả. Định vị novelty/hook, không phải cửa chính.
- **[Effort]** S — XONG (thuần gộp UI, backend không đổi).

### F6. KG — XÂY LẠI theo nội dung nhạc (xem mục 6.3 chi tiết)
- **[AI]** Thay đồ thị thuần-artist bằng **đồ thị tương đồng nhạc** (kNN trên MERT + mood_tags + instrument_tags), giữ artist/album là **một** loại cạnh trọng số thấp chỉ cho cold-start. **Bỏ +0.05 bonus cứng.**
- **[UX]** Vô hình (backend) — nhưng kết quả thấy rõ ở chất lượng "giống về nhạc" của similar-song/radio.
- **[Effort]** L.

### F7. MERT — mở rộng ứng dụng (xem mục 6.2)
- **[AI]** Hiện chỉ dùng ở `recommend_by_song`. Mở sang: (a) KG content rebuild ✅ (F6), (b) **"Audio Radio" thuần chất âm ✅ (2026-05-29)**, (c) bổ sung tín hiệu context/journey/color (chưa), (d) phát hiện duplicate/cover (chưa).
- **[Đã làm — nhánh (b) Audio Radio]:** `recommend_by_audio(song)` = **k-NN thuần MERT** (cosine trên embedding đã L2-norm) → bài *giống âm sắc* bất kể tác giả/lyrics/mood. Endpoint `GET /api/song/{id}/audio-radio`; FE: mục context-menu **"🎧 Radio chất âm"** → `_startAudioRadio` nạp queue [seed + sound-alikes]. Đo: top-8 cosine 0.93–0.94, loại seed. *An toàn — chế độ opt-in mới, KHÔNG đổi trọng số reco mặc định nên không cần backtest gating.* Bổ trợ cho "Phát bài tương tự" (đa-tín-hiệu): radio chất âm là *thuần production/timbre*.
- **[Effort]** M-L theo từng nhánh — (b) XONG; (c)/(d) còn lại (cần backtest nếu đổi default).

### F8. Discovery Dial (MMR/DPP) — ❌ BỎ (2026-05-29, quyết định user)
- ~~map slider "Quen thuộc ⟷ Bất ngờ" → `DIVERSITY_LAMBDA`~~. Đã loại khỏi roadmap; plumbing dở đã revert. MMR vẫn chạy ngầm với `DIVERSITY_LAMBDA` cố định trong config.

### F9. Explainability "Vì sao bài này" — ❌ BỎ (2026-05-29, quyết định user)
- ~~chip lý do dưới mỗi thẻ kết quả~~. Đã implement rồi revert toàn bộ (engine/api/FE). Loại khỏi roadmap.

### F10. Phản hồi tiêu cực có học — ⏸️ HOÃN (cần lớp cá nhân hóa trước)
- **Phụ thuộc kiến trúc chưa có:** "dislike có học" / taste profile chỉ có nghĩa khi có lớp cá nhân hóa người dùng. Hệ thống hiện *chưa* có (chỉ liked/history ở localStorage). → Không thuộc Phase 1.
- **Điều kiện kích hoạt:** sau khi có một **initiative Cá nhân hóa** riêng quyết định mô hình (tài khoản đăng nhập? client-only? hồ sơ server + taste vector?). Khi đó dislike/not-now mới gắn vào được.
- *(Ghi chú: mục này ban đầu suy ra từ pain point thị trường "Spotify thiếu dislike", không phải yêu cầu trực tiếp.)*

### F11. Smart Crossfade — đảm bảo "chạy thật"
- **[AI/Data]** Code live nhưng phụ thuộc cột DB `loudness_lufs/fade_*_cue_s/downbeat_times_json` — **CSV không có**. **Phải xác minh `backfill_lufs.py` + `backfill_cue_points.py` đã chạy vào DB.** Nếu chưa → crossfade thoái hóa về fade tuyến tính (mất Camelot/LUFS/beat-align).
- **[UX]** Đã có toggle ◈. Thêm badge tinh tế "harmonic mix" khi điều kiện đủ.
- **[Effort]** S (chạy backfill) — nhưng **chặn**: phải làm sớm để biết tính năng có thật không.

### F12. Lyrics tô màu cảm xúc + đồng bộ (đặc thù VN)
- **[AI]** Chạy emotion analysis theo *đoạn* → map sang màu (color mapper). Timestamp: MVP ước lượng tuyến tính → V2 forced alignment.
- **[UX]** Mở rộng nút ♪ Lyrics đã có trong Player.
- **[Effort]** M-L.

---

## 4. CROSS-CUTTING: nền tảng kỹ thuật trước khi đại tu UI

- **Refactor `app.js` (2,429 dòng monolith) → modules** (`js/pages/*`, `js/ai/*`) trước khi di chuyển feature, để tránh regression. `player.js` (1,599 dòng) tách `crossfade`/`queue`/`ui`.
- **Cá nhân hóa = initiative riêng (chưa thuộc lộ trình này):** hệ thống hiện KHÔNG có lớp cá nhân hóa thật (chỉ liked/history ở localStorage). Mọi tính năng cần hồ sơ người dùng (dislike có học/F10, taste vector, gợi ý cá nhân hóa) phải chờ một quyết định kiến trúc riêng: tài khoản đăng nhập? client-only? hồ sơ server-side? Cho tới lúc đó, các tính năng Phase 1-3 được thiết kế **per-request / per-session**, không phụ thuộc hồ sơ người dùng.
- **Backtest harness** đã tốt (Bonferroni, CI) — tái dùng để đo mọi thay đổi AI (KG, MERT, reranker) trước khi bật mặc định.

---

## 5. THỨ TỰ IMPLEMENT (roadmap có phụ thuộc)

> Triết lý sắp xếp: **Sửa cái sai & lấy lại niềm tin trước → đặt đúng chỗ → mở rộng trí thông minh → khác biệt hóa.** Mỗi đổi-AI phải qua backtest trước khi bật mặc định.

### 🔵 PHASE 0 — Nền tảng & xác minh ✅ HOÀN TẤT (2026-05-29)
1. **F11**: ✅ Crossfade data **đã đầy đủ trong DB** (5548 LUFS/cue, 159 downbeat = đúng toàn bộ bài danceable); `app._hydrate_crossfade_columns()` merge DB→df lúc khởi động (log xác nhận). **Crossfade chạy thật, không cần backfill.** Lo ngại ban đầu là báo động giả (CSV thiếu cột nhưng có bước hydration).
2. **Reranker**: ✅ ĐÃ ĐO → **giữ tắt** (chi tiết mục 6.4). +191ms/query (~gấp đôi), chỉ reorder top-10 (overlap@10=10/10), accuracy không đo được nếu không dựng GT chủ đề-lời.
3. **Refactor frontend**: ✅ Tách theo hướng "file-split giữ global" (user chọn). `app.js` (2429) → 7 file (ui-core, ui-pages, actions, ai-discovery, ai-journey, features, context-init); tách `crossfade.js` (184) khỏi `player.js`. **Kiểm chứng nối lại == bản gốc từng byte**, syntax-check toàn bundle (4215 dòng) hợp lệ, index.html cập nhật đúng thứ tự. *Khuyến nghị: smoke-test trên trình duyệt lần chạy app kế tiếp (môi trường refactor không có browser).* True ES-module decoupling để dành làm dần theo từng feature ở Phase 2-3.
- **Kết quả:** nền tảng sẵn sàng cho Phase 1. Hai "ẩn số" (crossfade, reranker) đã chốt bằng dữ liệu; monolith FE đã chia nhỏ an toàn.

### 🟢 PHASE 1 — Sửa correctness & niềm tin (giá trị cao nhất / pain #1-3)
4. **F6** ✅: Xây lại KG content-based + bỏ +0.05 artist bonus + artist-cap → đã đo backtest (mục 6.3.1). *(L)*
5. **F9** ❌ BỎ (2026-05-29, theo quyết định user — "không cần thiết"): lớp "Vì sao bài này" đã từng implement (helper `_top_reasons`, wired vào `recommend_by_song`/`recommend_by_colors`, serialize `_song_to_dict`, chip FE) nhưng đã **revert toàn bộ**. Engine/api/FE trở lại trạng thái không explainability.
6. **F8** ❌ BỎ (2026-05-29, theo quyết định user — "không cần thiết"): Discovery Dial. Phần plumbing `diversity=` đã thêm dở (param API + `_diversity_to_lambda` + λ override trong `_fast_rank`) cũng đã **revert toàn bộ**.
7. ~~**F4**~~ ❌ BỎ — sau F6, reco đã thuần "giống về nhạc"; không có logic "cùng nghệ sĩ" để tách (xem nghệ sĩ = điều hướng). Mâu thuẫn triết lý F6.
- **Vì sao:** nhóm này đánh trúng pain echo-chamber + hộp đen và sửa bug KG, **đều hoạt động ở mức per-request, KHÔNG cần lớp cá nhân hóa**. *(F4, F8, F9 đã loại theo yêu cầu user — Phase 1 chỉ còn F6 ✅.)*
- **❌ F10 (dislike/feedback có học) GỠ KHỎI Phase 1:** giả định một lớp cá nhân hóa/người dùng mà hệ thống *chưa có* (hiện chỉ có liked/history ở localStorage, không có hồ sơ server/mô hình cá nhân hóa). Cá nhân hóa là **một quyết định kiến trúc riêng** (tài khoản? client-only? hồ sơ server?) → tách thành initiative riêng, không thuộc Phase 1. (Ban đầu thêm F10 từ pain point thị trường, không phải yêu cầu thực tế.)

### 🟡 PHASE 2 — Đặt đúng chỗ (giảm ma sát, tăng chạm)
9. **F1** ✅ (2026-05-29): Context Mix → shelf "Ngay bây giờ" **tự chạy trên Home, không nút generate**. Nối `vn_context` (lễ Việt + thời tiết live OWM) vào `smart_context_recommend` — bổ tín hiệu địa phương mà circadian/activity/season chưa có; bỏ qua time-of-day vì circadian đã model giờ; thời tiết live chỉ fetch khi không có weather string thủ công. Engine trả thêm `vn_context_label`/`is_holiday`; FE `_loadContextShelf()` thay `_loadTimePeriodSongs`, subtitle hiện ngữ cảnh ("🌆 Buổi tối · 18:00 · 🎊 Tết · Thời tiết: mây cụm"). **Vị trí thực:** browser geolocation (cache 6h, làm tròn 2dp ~1km) → lat/lon qua `/context-mix` → OWM lấy thời tiết đúng nơi user; từ chối/không hỗ trợ → fallback config city (Hà Nội). **Shelf render TỨC THÌ** (giờ+lễ không cần quyền): dùng `_getCachedGeo()` (đồng bộ) + `_refreshGeo()` (xin quyền ở chế độ nền, cache cho lần sau) — KHÔNG `await` popup vị trí trên đường tới hiển thị. `OWM_API_KEY` đã có trong `.env` (app load qua `load_dotenv`); thiếu key thì degrade an toàn. OWM thêm `lang=vi` (mô tả thời tiết tiếng Việt). *(M)*
10. **F2** ✅ (2026-05-29): Emotion Journey → Home card + nút Player + need-presets. (a) ✅ **Auto-đoán điểm bắt đầu** từ bài đang nghe: `get_song_va(track_id)` engine + endpoint nhận `start_track_id` (precedence: V-A tường minh → now-playing → neutral 0.5). Bỏ bắt user nhập tọa độ V-A. (c) ✅ **4 need-preset** (`MOOD_SHIFTS`: 🌅 Vực dậy / 🧘 Hạ lo âu / 🌙 Ru ngủ / 🎯 Tập trung) — user chọn *đích*, máy lo *đường* (P7). UX: thẻ "🎭 Đổi tâm trạng" trên Home (1 chạm → tạo + phát) + nút 😊 `btn-mood` trong Player (popover từ bài đang nghe). (b) ⏳ **Rumination detection HOÃN** — cần theo dõi Q3 kéo dài qua lịch sử nghe (nudge opt-in), ưu tiên thấp; tách sau. *(M)*
11. **F5** ✅ (2026-05-29): Gộp Color+Image thành **1 màn "🎨 Bắt vibe từ ảnh/màu"** (header "Soundtrack cho khoảnh khắc"). Bỏ tab "📷 Hình ảnh" riêng; dropzone ảnh + preview + `#image-results` chuyển vào panel color, dưới divider "hoặc bắt vibe từ một tấm ảnh"; `switchAiTab` bỏ 'image' (còn 4 tab). Backend color/image **giữ nguyên** (CIEDE2000 + CLIP); ID `#image-dropzone`/`#image-input`/`#image-results` giữ nguyên nên `initImageUpload()` + handlers chạy y cũ. *(S)*
- **Vì sao:** sau khi gợi ý đáng tin (Phase 1), đưa chúng ra chỗ dễ chạm để phát huy. **→ PHASE 2 HOÀN TẤT** (F1 ✅ + F2 ✅ + F5 ✅).

### 🟠 PHASE 3 — Mở rộng trí thông minh
12. **F2-REDESIGN** (xem chi tiết §3/F2): biến Emotion Journey thành "wow & dễ dùng". ✅ **F2.2** Journey Mode · ✅ **F2.1** preview + human-preset + V-A→nâng cao · ✅ **F2.7** độ dài thích ứng + "tới đích rồi ở lại" · ✅ **F2.6** taxonomy MMR (thêm họ "ở lại/biểu đạt": solace/discharge/entertainment). Còn: **F2.5** đổi-mood-nhanh-5′ *(S)* · **F2.3** re-steer *(M)* · **F2.4** preset bản-sắc-Việt *(S)*.
13. **F3** ✅ LÕI: Search HỢP NHẤT trên thanh search toàn cục — gõ **tên / câu lyrics / mô tả vibe** đều ra, **khớp-nhất-trước + liên-quan-dưới** (endpoint `/songs/search/unified` 3 matcher; đã sửa bug `/songs/search` không search lyrics). *Follow-up:* trang kết quả đầy đủ (Enter→play-all) rồi gỡ tab "Tìm theo cảm xúc".
14. **F7** ✅ phần chính: MERT vào KG (F6) + **Audio Radio thuần MERT (2026-05-29)** — context-menu "🎧 Radio chất âm". Còn (c) bổ sung tín hiệu context/journey/color + (d) cover/dup-detection *(cần backtest nếu đổi default)*.
- **Vì sao:** nâng "chất" AI sau khi cấu trúc đã đúng. F2-REDESIGN ưu tiên đầu Phase 3 vì user đã thử & thấy bản hiện tại chưa đạt.

### 🟣 PHASE 4 — Khác biệt hóa & giữ chân
14. **F12**: Lyrics tô màu cảm xúc + đồng bộ. *(M-L)*
15. **B2 (báo cáo thị trường)**: "Tuần cảm xúc" (Wrapped cảm xúc). *(M)*
16. **Wellness mode** hoàn chỉnh (từ F2) + (sau cùng) tính năng xã hội "Blend cảm xúc". *(L)*
- **Vì sao:** các tính năng "wow"/lan truyền/giữ chân, xây trên nền đã vững.

---

## 6. CHI TIẾT KỸ THUẬT TRỌNG ĐIỂM

### 6.1. Tóm tắt trạng thái AI hiện tại (ground-truth)
- **LIVE & dùng rộng:** emotion analysis (PhoBERT+lexicon+CLAP), diversity MMR/DPP, color/image, 5 endpoint reco.
- **LIVE nhưng hẹp/sai chỗ:** MERT & KG (chỉ similar-song), VN context (chỉ color reco), RRF (chỉ color path).
- **OFF:** reranker (chưa đo), Pillar B (đã đo, FAIL).
- **Rủi ro dữ liệu:** crossfade phụ thuộc cột DB chưa chắc đã backfill.

### 6.2. MERT — có thể áp dụng thêm vào đâu
MERT (768-dim, đã có file 16M, là *biểu diễn nội dung nhạc thật*) hiện lãng phí. Đề xuất:
1. **KG content rebuild** (mục 6.3) — dùng MERT làm xương sống tương đồng nhạc.
2. **"Audio Radio" / "Giống về nhạc"** — kNN thuần trên MERT, độc lập tác giả/lyrics → đúng "tính nhạc" bạn muốn.
3. **Bổ sung tín hiệu cho color/image/journey/context** (hiện không dùng MERT) — vd. sau khi map màu→V-A, dùng MERT để chọn bài hợp *chất âm*.
4. **Phát hiện cover/duplicate & lọc trùng** trong kết quả (MERT-sim rất cao = gần như cùng bản).
5. *(Nghiên cứu)* CrossMuSim/CLAP-style: kết hợp MERT (audio) + text mô tả để retrieval đa phương thức.
> Mọi nhánh phải đo backtest trước khi tăng trọng số mặc định (MERT cũng cluster theo nghệ sĩ 56% — cần kết hợp, không thay thế mù quáng).

### 6.3.1. KG rebuild — ĐÃ TRIỂN KHAI & VALIDATE (Phase 1, 2026-05-29) ✅
- **Builder mới** (`tools/build_kg_embeddings.py` v2): đồ thị k-NN tương đồng nội dung trên `[MERT 0.5 ⊕ mood_tags 0.2 ⊕ instrument_tags 0.2 ⊕ audio 0.1]` (fused 5548×802) → SVD 64-dim. **Bỏ hoàn toàn cạnh artist/album.**
- **Engine**: bỏ `+0.05*kg_sim` artist bonus → `KG_SIM_WEIGHT` (config, content-based). `_cap_per_artist` được thêm nhưng **TẮT mặc định** (`MAX_PER_ARTIST_SIMILAR=0`) — xem ghi chú triết lý bên dưới.
- **Triết lý (theo phản hồi user):** *sửa NGUYÊN NHÂN (tín hiệu thiên vị nghệ sĩ) chứ không chặn TRIỆU CHỨNG (số bài cùng nghệ sĩ).* Cap cứng = "thông minh áp đặt": nó vứt bỏ bài cùng nghệ sĩ *thực sự* giống về nhạc. Đa dạng (nếu muốn) là **lựa chọn user qua Discovery Dial F8**, không phải luật cứng. Cap chỉ còn là override tùy chọn cho operator.
- **Kết quả đo trực tiếp:** % láng giềng top-10 cùng nghệ sĩ **89.6% → 7.2%**; cosine cùng-nghệ-sĩ 0.982 → 0.152. `recommend_by_song` **không cap**: median same-artist trong top-10 = **0**, mean 0.5, 24/25 seed ≤2 *một cách tự nhiên*. Trường hợp nhiều (Mr. Siro 6 bài) là đúng — nghệ sĩ có style nhất quán nên các bài thật sự giống nhất; MMR (đa dạng theo *nhạc*) vẫn giữ chúng vì chúng khác nhau đủ.
- **Backtest `pillar-f-xartist`:** "CIRCULARITY LIKELY" (delta −0.0099) → **"INCONCLUSIVE/neutral" (delta −0.0041, CI chạm 0)** = không còn khai thác danh tính nghệ sĩ, không regression. Marginal value của term KG gần 0 trên editorial GT (genre-playlist) — để tinh chỉnh sau bằng `optimize-weights`. Bản KG cũ backup ở `data/kg_embeddings_v1_artist.bak.npy`.

### 6.3. KG — kế hoạch xây lại (cốt lõi sửa "gợi ý theo tác giả")
**Root cause:** đồ thị thuần artist/album → 99% same-artist sim + bonus +0.05 cứng.

**Thiết kế mới — đồ thị tương đồng *nội dung nhạc*:**
- **Cách A (nhanh, khuyến nghị MVP):** Bỏ artist-KG. Xây **kNN graph trên hợp nhất nội dung**: `MERT (chất âm) ⊕ mood_tags ⊕ instrument_tags ⊕ audio features` → mỗi bài nối k láng giềng *giống về nhạc*. Embedding = node2vec/SVD trên graph này, hoặc đơn giản dùng trực tiếp kNN-sim. **Không** chứa tín hiệu tác giả.
- **Cách B (đầy đủ, paper-grounded):** **Đồ thị dị thể (heterogeneous)**: cạnh "music-similarity" (MERT/mood, trọng số cao) + cạnh "artist/album" (trọng số *thấp*, chỉ để cold-start), nhúng bằng GNN/metapath (HAN-style; theo Hybrid GNN Springer 2024 & arXiv 2409.09026). 
- **Bỏ `+0.05 * kg_sim` thuần-tác-giả** trong `recommend_by_song`; thay bằng tín hiệu KG-nội-dung (hoặc gộp vào trọng số fusion qua config, có thể ablation).
- **Xử lý same-artist bias còn lại** (PhoBERT 48%, MERT 56%, mood): artist-diversity cap tùy chọn trong `_fast_rank` (mặc định TẮT — sửa nguyên nhân, không chặn triệu chứng; không có khái niệm "chọn cùng nghệ sĩ" vì F4 đã bỏ).
- **Đo:** backtest NDCG + một metric mới *"% same-artist trong top-K"* (mục tiêu giảm mạnh mà không hại relevance).
- **Dữ liệu cần:** đã đủ (MERT, mood_tags, instrument_tags). Không cần co-listening.

### 6.4. Reranker — ĐÃ ĐO (Phase 0, 2026-05-29) → KẾT LUẬN: GIỮ TẮT
**Đo thực nghiệm trên `recommend_by_lyrics_keywords` (6 truy vấn chủ đề lời, máy dev MPS):**
- **Latency:** OFF median **~195 ms/query** → ON (warm) median **~386 ms/query** = **+191 ms (~gấp đôi)**. Cold-load model lần đầu **~25 s** (tải ~120MB + init), mỗi worker tốn thêm RAM.
- **Hành vi reorder:** **overlap@10 = 10/10 ở MỌI truy vấn** — reranker **KHÔNG đổi tập bài** trong top-10, chỉ **xếp lại thứ tự trong tập đó** (top-1 đổi ở 5/6 query). → Trần lợi ích bị chặn: nó *không thể* cải thiện recall/đưa bài tốt hơn vào, chỉ đổi thứ tự.
- **GT không đo được accuracy:** editorial GT chỉ có intent **cấp thể loại** ("nhạc indie việt", "rap việt") — sai domain cho reranker (chấm theo lyrics); GT weak-annotation (bài chứa keyword trong lyrics) thì *vòng lặp* với baseline keyword-match. → Không có cách đo nDCG công bằng nếu không dựng GT chủ đề-lời riêng.

**Quyết định:** Chi phí **cao & chắc chắn** (gấp đôi latency mỗi lần search, RAM model, cold-start), lợi ích **bị chặn trần & không đo được** (chỉ reorder top-10). Với user VN chủ yếu free-tier, gấp đôi latency search là cái giá khó biện minh cho một thay đổi reorder-only. → **Giữ `ENABLE_RERANKER=False`.**

**Điều kiện xét lại (nếu muốn):** dựng GT chủ đề-lời ~100-150 cặp `query→bài-có-lyrics-thật-khớp` (gán nhãn thủ công, KHÔNG weak-annotation), thêm lệnh `run-reranker` (theo mẫu `run-pillar-c`, dùng `Catalog.build_isolated` + `_pinned_recommend_flags`), đo nDCG/MRR ON-vs-OFF. Chỉ bật nếu reorder cho lợi nDCG *rõ rệt & có ý nghĩa thống kê* đủ bù +191ms.

### 6.5. UI/UX — điểm sửa code chính (từ map ground-truth)
- Sidebar/nav: `static/index.html:100-124`, router `app.js:10-61,135-142`.
- Home sections: `app.js:483-663` (chèn shelf "Ngay bây giờ" lên đầu, sau hero).
- AI Lab tabs: `app.js:687-1126`, switch `:1431` (rút còn "Khám phá"; di chuyển context/journey ra ngoài).
- Player extra controls: `index.html:204-237` + `player.js` (thêm nút "đổi mood", "không hợp lúc này", chip "vì sao").
- ⚠️ **Refactor monolith trước** (Phase 0) để các thao tác trên không gây regression.

---

## 7. RỦI RO & LƯU Ý
- **Mọi thay đổi AI phải qua backtest** (harness đã có Bonferroni/CI) trước khi bật mặc định — tránh lặp lại bài học Pillar B "PASS giả do naive bootstrap".
- **MERT/KG cluster theo nghệ sĩ một phần là tự nhiên** (giọng/phong cách) — mục tiêu là *giảm* bias vô lý, không phải triệt tiêu mọi tương đồng cùng nghệ sĩ.
- **Conversational search + LLM** làm tăng chi phí/latency; cần fallback không-LLM (lexicon/PhoBERT) cho free-tier (đa số user VN dùng free).
- **Refactor frontend** là việc "không thấy được" nhưng là điều kiện tiên quyết để đại tu UI an toàn — đừng bỏ qua.

---

## 8. NGUỒN THAM KHẢO BỔ SUNG (kỹ thuật & UX, ngoài MARKET_RESEARCH_REPORT.md)

**Content-based / Graph music recommendation**
- *Towards Leveraging Contrastively Pretrained Neural Audio Embeddings for Recommender Tasks* (arXiv 2409.09026): https://arxiv.org/abs/2409.09026v1
- *Hybrid music recommendation with graph neural networks* (Springer UMUAI 2024): https://link.springer.com/article/10.1007/s11257-024-09410-4
- *Content-based Music Similarity with Triplet Networks* (arXiv 2008.04938): https://arxiv.org/pdf/2008.04938

**MERT / music representation**
- *MERT: Acoustic Music Understanding Model* (ICLR 2024, arXiv 2306.00107): https://arxiv.org/html/2306.00107v3
- *CrossMuSim: Cross-Modal Music Similarity Retrieval* (arXiv 2503.23128): https://arxiv.org/html/2503.23128v1

**Conversational / LLM music recommendation**
- *TalkPlay: Multimodal Music Recommendation with LLMs* (arXiv 2502.13713): https://arxiv.org/html/2502.13713v3
- *User Experience with LLM-powered Conversational RecSys* (CHI 2025): https://dl.acm.org/doi/10.1145/3706598.3713347
- *Music Recommendation with LLMs: Challenges, Opportunities, Evaluation* (arXiv 2511.16478): https://arxiv.org/html/2511.16478

**Explainability / Transparency / UX**
- *EXPLORE — Explainable Song Recommendation* (arXiv 2401.00353): https://arxiv.org/pdf/2401.00353
- *Explainability in Music Recommender Systems* (Afchar et al.): https://karapostk.github.io/assets/pdf/afchar2022explainability.pdf
- *Transparent & Controllable Music RecSys with Multi-relational Layers* (Springer 2024): https://link.springer.com/chapter/10.1007/978-981-95-6950-2_20
- Spotify Engineering — *Personalizing Spotify Home with ML*: https://engineering.atspotify.com/2020/1/for-your-ears-only-personalizing-spotify-home-with-machine-learning
- Spotify Design — *Three Principles for Designing ML-Powered Products*: https://spotify.design/article/three-principles-for-designing-ml-powered-products

**Emotion Journey / mood-arc UX (bổ sung 2026-05-29, cho F2-REDESIGN)**
- *Emotion Modulation through Music after Sadness Induction — The Iso Principle* (PMC8656869): https://pmc.ncbi.nlm.nih.gov/articles/PMC8656869/
- feed.fm — *Mood Music: How the Iso Principle Can Help You Shift Your Mood* (music-arc): https://blog.feed.fm/mood-music-how-the-iso-principle-can-help-you-shift-your-mood
- Heartfelt Harmony — *Making a mood-management playlist with the iso principle*: https://heartfeltharmonymusictherapy.com/2019/05/21/mood-and-music-how-to-make-a-playlist-for-mood-management-using-the-iso-principle/
- Raw.Studio — *Spotify Daylists: the UI, UX, and ML* (mood-arc, cover/title, palette-by-time): https://raw.studio/blog/spotify-daylists-unveiling-the-ui-ux-and-ml-magic-behind-personalized-music/
- UX Magazine — *Analyzing Spotify's Daylist: UI, UX, and ML*: https://uxmag.com/articles/analyzing-spotifys-new-day-list-feature-ui-ux-and-great-ml

**Tâm lý điều tiết cảm xúc & độ dài phiên (bổ sung 2026-05-29, cho F2.6/F2.7)**
- Saarikallio — *Music in Mood Regulation: Initial Scale Development* (MMR, 7 chiến lược): https://journals.sagepub.com/doi/10.1177/102986490801200206
- Saarikallio — *Music as emotional self-regulation throughout adulthood* (2011): https://journals.sagepub.com/doi/10.1177/0305735610374894
- Sakka & Juslin — *Emotion regulation with music in depressed and non-depressed individuals* (2018, rủi ro rumination): https://journals.sagepub.com/doi/10.1177/2059204318755023
- *Iso-Principle Based Music Playlists on Anxiety* (clinical trial, phiên ~30′): https://clinicaltrials.gov/study/NCT05442099
- It's Complicated — *Emotional Regulation Playlist* (độ dài 5–6 khởi điểm, cá nhân hoá): https://complicated.life/blog/the-emotional-regulation-playlist-using-music-to-shift-your-mood/

---

*Plan này dựa trên ground-truth codebase (truy vết file:line) + nghiên cứu công khai đã kiểm chứng. Các đổi-AI (KG, MERT, reranker) cần đo bằng backtest harness sẵn có trước khi bật mặc định. Roadmap có thể song song hóa trong từng phase, nhưng nên giữ thứ tự phase vì có phụ thuộc (Phase 0 mở khóa phần còn lại).*
