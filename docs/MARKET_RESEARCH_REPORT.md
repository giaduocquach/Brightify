# Brightify — Báo Cáo Khảo Sát Thị Trường & Định Hướng Tính Năng

> **Ngày:** 2026-05-29
> **Phạm vi:** Nghiên cứu thị trường streaming nhạc (toàn cầu + Việt Nam), nhu cầu & tâm lý người dùng, pain point, xu hướng tính năng AI; đối chiếu với tính năng hiện có của Brightify; đề xuất tính năng mới có giá trị thực và tạo điểm "wow".
> **Phương pháp:** Tổng hợp từ báo cáo ngành, khảo sát người dùng (Edison, BPI, Decision Lab, NuVoodoo), diễn đàn cộng đồng (Spotify Community, Reddit), paper học thuật (arXiv, ISMIR, Scientific Reports, MDPI), và phân tích đối thủ (Spotify AI DJ, PersonalAIs, Tunee, ElevenMusic, Suno). Mọi nguồn liệt kê ở mục 9.

---

## 1. Tóm Tắt Điều Hành (Executive Summary)

**Brightify đang sở hữu một "động cơ AI" mạnh hơn nhiều so với mặt tiền (UI) mà người dùng nhìn thấy.** Hệ thống có 7-signal multimodal fusion, phân tích cảm xúc tiếng Việt (PhoBERT + lexicon 730+ từ), bản đồ màu→cảm xúc dựa trên nghiên cứu Palmer/Jonauskaite, CLIP cho ảnh, và Smart Crossfade cấp DJ (LUFS + Camelot + cue-point). Đây là tài sản kỹ thuật hiếm có.

Tuy nhiên, nghiên cứu thị trường cho thấy một khoảng cách rõ rệt: **những gì người dùng thực sự đau đớn (pain point) và khao khát lại nằm ở nơi Brightify chưa khai thác — không phải ở chỗ thuật toán mạnh hơn.** Ba phát hiện then chốt:

1. **Pain point #1 toàn cầu là "echo chamber" + mất quyền kiểm soát**, KHÔNG phải thiếu thuật toán. Người dùng Spotify ghét việc bị gợi ý lặp 30 bài giống nhau, không có nút "dislike", không hiểu vì sao được gợi ý. → Brightify có sẵn DPP/MMR (chống lặp) và 7 tín hiệu (có thể giải thích) nhưng **chưa biến thành tính năng người dùng cầm nắm được**.

2. **Gen Z dùng nhạc như công cụ điều tiết cảm xúc, bản sắc và kết nối cộng đồng** — không phải để "khám phá nhạc mới" (việc này họ thấy "khá chán"). 85% nghiên cứu về điều tiết cảm xúc tập trung vào *nghe* nhạc. → Brightify có Emotion Journey (Iso-Principle) và phân tích V-A — đây chính là **lợi thế khác biệt lớn nhất** nhưng đang bị đóng gói như "thí nghiệm AI Lab" thay vì một trải nghiệm wellness hằng ngày.

3. **Thị trường Việt Nam có nhu cầu đặc thù mà đối thủ quốc tế phục vụ kém**: tiếng Việt, lyrics đồng bộ/karaoke, ngữ cảnh văn hóa (Tết, lễ). → Brightify đã có NLP tiếng Việt + ngữ cảnh lễ Việt — **đây là con hào (moat) cạnh tranh** trước Spotify/Apple Music.

**Kết luận chiến lược:** Brightify không cần thuật toán mạnh hơn. Brightify cần **đưa sức mạnh AI sẵn có lên bề mặt** dưới dạng (a) quyền kiểm soát & minh bạch, (b) trải nghiệm cảm xúc/wellness, (c) tính xã hội, và (d) bản sắc Việt — bốn thứ thị trường đang đòi mà đối thủ làm dở.

---

## 2. Tổng Quan Thị Trường

### 2.1. Việt Nam (thị trường mục tiêu)
- **Quy mô:** Doanh thu nhạc số VN ~**$51.95M (2025)**, hơn nửa từ streaming. Thị trường streaming ~$85.24M (2024) → dự báo **$168.84M (2033)**, CAGR **7.89%**.
- **Người dùng:** ~**12.57 triệu** người dùng nhạc số (2025); chỉ ~**31.9%** trả tiền → phần lớn dùng free/ad-supported.
- **Thị phần app (Decision Lab Q4/2025):** YouTube **74%** > Zing MP3 **45%** > TikTok **32%** > Spotify **27%** > Apple Music **9%**.
- **Hành vi:** **75%** người Việt nghe nhạc *hằng ngày*; **93%** nghe qua điện thoại; nhạc là hình thức giải trí chính.
- **Tiêu chí chọn app (khảo sát):** Playlist hợp nhu cầu **64.3%** › Giao diện dễ dùng **59.7%** › Thư viện lớn **58%** › Gợi ý phù hợp **56.7%** › Free/rẻ **54.1%**.

> **Hàm ý:** Người Việt nghe nhạc rất thường xuyên trên mobile, nhưng tiêu chí #1 là *playlist hợp ngữ cảnh/nhu cầu* chứ không phải "gợi ý" thuần. "Gợi ý phù hợp" xếp thứ 4. Giao diện và độ phù hợp playlist quan trọng ngang thuật toán. Đa số dùng free → cần giá trị giữ chân không tốn license đắt.

### 2.2. Toàn cầu — các thị trường liền kề đang tăng nóng
- **Functional/wellness music** (focus, sleep, sound healing): Sleep Sound Music Apps $2.13B (2024) → $5.5B (2035); Sound Healing App CAGR **12.15%**; Wellness apps CAGR **15.11%** (2025–2034). Động lực chính: **cá nhân hóa bằng AI theo dữ liệu hành vi thời gian thực**.
- **AI tạo sinh & agent nhạc:** Suno (tạo bài hát từ prompt), Tunee (AI agent hội thoại), PersonalAIs (gợi ý theo mood bằng ngôn ngữ tự nhiên), ElevenMusic (stations theo mood: Focus/Energy/Relax/Chill).

> **Hàm ý:** Hai làn sóng tăng trưởng nóng nhất — *wellness/functional music* và *AI hội thoại theo mood* — đều ăn khớp trực tiếp với thế mạnh V-A/cảm xúc của Brightify.

---

## 3. Nhu Cầu & Tâm Lý Người Dùng (đặc biệt Gen Z)

Gen Z (18–25) được mô tả là **"musical omnivores"** với 4 trụ cột vai trò của nhạc trong đời sống:
1. **Soundtrack nền** thường trực cho mọi hoạt động.
2. **Hỗ trợ cảm xúc & nâng/điều tiết tâm trạng.**
3. **Công cụ bản sắc & thể hiện bản thân.**
4. **Trải nghiệm gắn kết cộng đồng**, mở rộng thế giới quan.

Đặc điểm hành vi quan trọng:
- **Ưu tiên mood/cảm xúc/sự quen thuộc hơn ranh giới thể loại** — nhiều người "không còn tin vào genre". Họ tìm nhạc theo *vibe*, không theo tên thể loại.
- **Khám phá nhạc mới = "khá chán" (a big meh):** Gen Z ít chủ động săn nghệ sĩ/bài mới hơn thế hệ trước; chỉ 19% người 16–24 nghe thêm sau khi "phát hiện" nghệ sĩ mới. → **Đừng ép "khám phá"; hãy phục vụ tâm trạng & ngữ cảnh hiện tại.**
- **Kết nối là trung tâm:** playlist cộng tác tăng **+41%** ở nhóm <30 tuổi (2025); "nhạc là mạng xã hội của riêng nó". Gen Z khao khát kết nối và trải nghiệm trực tiếp.
- **Điều tiết cảm xúc qua nhạc** là chủ đề nghiên cứu rất nóng (29/47 nghiên cứu 2021–2024): nghe nhạc giúp *down-regulate* cảm xúc tiêu cực, nâng năng lượng. **Cảnh báo khoa học:** có "music use không lành mạnh" — nghe lặp để *rumination* (đắm chìm tiêu cực), né tránh vấn đề, kéo tâm trạng xuống. → Cơ hội cho tính năng *điều hướng cảm xúc lành mạnh* (Iso-Principle: gặp người dùng ở tâm trạng hiện tại rồi dẫn dắt lên).

---

## 4. Pain Point Người Dùng (tổng hợp từ diễn đàn + khảo sát)

| # | Pain point | Bằng chứng | Mức độ |
|---|-----------|-----------|--------|
| 1 | **Echo chamber / lặp bài** — gợi ý cùng ~30 bài, "thuật toán = phòng vọng âm" | Spotify Community (nhiều thread) | 🔴 Rất cao |
| 2 | **Mất quyền kiểm soát & không có "dislike"** — không thể lái thuật toán, skip không được học | Spotify Community; nghiên cứu AI DJ (loss of agency) | 🔴 Rất cao |
| 3 | **Hộp đen — không hiểu "vì sao gợi ý bài này"** | Nghiên cứu explainability/FAccTRec; AI DJ "mismanaged expectations" | 🟠 Cao |
| 4 | **Hiệu năng & bug** — buffering, tính năng hỏng, app crash | Brandwatch (pain point lớn nhất) | 🟠 Cao |
| 5 | **Quảng cáo & chi phí** | Brandwatch | 🟠 Cao (đặc biệt VN free-heavy) |
| 6 | **Nghe offline** kém | Brandwatch | 🟡 Trung bình |
| 7 | **Quản lý playlist** còn yếu | Brandwatch | 🟡 Trung bình |
| 8 | **AI DJ lặp & "vô hồn quy mô lớn"** (scalability bottleneck → repetitive) | Sage 2025 (phân tích 1,400+ comment) | 🟡 Trung bình |

> Ba pain point đầu (#1–#3) đều xoay quanh **kiểm soát + minh bạch + đa dạng** — và đây chính là chỗ Brightify đã có sẵn vũ khí (DPP/MMR, 7 tín hiệu rõ ràng) nhưng chưa "lên kệ".

---

## 5. Bối Cảnh Cạnh Tranh & Xu Hướng Tính Năng AI

| Đối thủ/sản phẩm | Tính năng AI nổi bật | Điểm mạnh | Điểm yếu (cơ hội cho Brightify) |
|---|---|---|---|
| **Spotify AI DJ** | DJ giọng người + voice/text request | Giọng tự nhiên, request bằng lời | Lặp nội dung, mất quyền kiểm soát, không tiếng Việt |
| **PersonalAIs** | Gợi ý hội thoại theo mood ("I'm in a chill mood") | Ngôn ngữ tự nhiên + ngữ cảnh | Không có chiều sâu cảm xúc V-A/lyrics tiếng Việt |
| **Tunee** | AI agent: mô tả mood/upload melody/video clip → nhạc | Đa phương thức input | Thiên về tạo sinh, không phục vụ catalog VN |
| **ElevenMusic** | Stations theo mood (Focus/Energy/Relax/Chill) | Mood-first đơn giản | Mood thô, không cá nhân hóa sâu |
| **Suno** | Tạo bài hát hoàn chỉnh từ prompt | Tạo sinh đỉnh cao | Không phải nghe nhạc thật/khám phá catalog |
| **Zing MP3** (VN) | Lyrics, karaoke, thư viện VN lớn | Bản địa hóa, lyrics/karaoke | AI cảm xúc/đa phương thức yếu |

**Xu hướng AI hội tụ rõ:** (1) *hội thoại/ngôn ngữ tự nhiên* thay cho gõ keyword; (2) *mood-first* thay cho genre-first; (3) *đa phương thức* (ảnh/giọng/clip → nhạc); (4) *minh bạch & công bằng* (FAccTRec, explainable recs).

---

## 6. Phân Tích Giá Trị Tính Năng HIỆN CÓ Của Brightify

Ký hiệu giá trị: 🟢 Giá trị cao (giữ & làm nổi bật) · 🟡 Giá trị tiềm năng (đang bị chôn, cần đưa lên bề mặt) · 🔵 Wow/novelty (ấn tượng nhưng dùng ít hằng ngày — dùng làm "hook" marketing) · ⚪ Hạ tầng (giá trị gián tiếp).

### 6.1. Khám phá / Gợi ý
| Tính năng | Đáp ứng nhu cầu nào | Verdict |
|---|---|---|
| **Emotion Journey (Iso-Principle)** | Điều tiết cảm xúc (trụ cột #2 Gen Z), thị trường wellness | 🟢 **Vũ khí khác biệt mạnh nhất.** Khoa học hậu thuẫn (Altshuler 1948, Davis & Thaut 1989). Hiện đang chôn trong "AI Lab". |
| **Context Mix** (giờ/hoạt động/mùa/thời tiết/lễ Việt) | "Playlist hợp ngữ cảnh" = tiêu chí #1 ở VN (64.3%) | 🟢 **Trúng tiêu chí số 1 của người Việt.** Nên là màn hình chính, không phải lab. |
| **7-signal fusion (similar songs)** | Gợi ý phù hợp (tiêu chí #4 VN) | 🟢 Lõi tốt; cần thêm *kiểm soát & giải thích* (xem mục 7). |
| **Diversity/Serendipity (MMR/DPP)** | Chống echo chamber (pain #1) | 🟡 Đang chạy ngầm — **phải biến thành "núm vặn" cho người dùng.** |
| **Lyrics keyword + semantic (RRF + cross-encoder)** | Tìm theo nội dung/chủ đề tiếng Việt | 🟢 Khác biệt cho VN; nền tảng cho tìm kiếm hội thoại. |
| **Color-based reco** | Novelty | 🔵 Ấn tượng/wow, ít dùng hằng ngày — hook marketing & visualizer. |
| **Image-based reco (CLIP)** | Novelty, đa phương thức | 🔵 Wow ("soundtrack ảnh của bạn") — gắn vào tính năng xã hội. |
| **KG embeddings (cold-start)** | Người dùng/bài mới | ⚪ Hạ tầng tốt; vô hình với user. |

### 6.2. Phát lại & Âm thanh
| Tính năng | Đáp ứng | Verdict |
|---|---|---|
| **Smart Crossfade** (LUFS + Camelot + cue + beat-align) | Trải nghiệm nghe liền mạch (soundtrack nền — trụ cột #1) | 🟢 **Giá trị thực cao, cấp DJ.** Hiếm có ở app VN. Cần "khoe" tinh tế (badge "harmonic mix"). |
| **Radio Mode** (queue liên tục) | Nghe thụ động liên tục | 🟢 Hợp hành vi "nghe nền" của Gen Z. |
| **Visualizer / Now Playing màu** | Bản sắc/thẩm mỹ | 🔵 Wow; nâng cấp thành visualizer phản ánh cảm xúc. |
| **Local streaming + range request** | Hạ tầng phát | ⚪ Cần thiết, vô hình. |

### 6.3. Phân tích AI (backend)
| Tính năng | Verdict |
|---|---|
| **Emotion analysis tiếng Việt** (PhoBERT + lexicon 730+ từ + Gen-Z slang + vùng miền) | 🟢 **Con hào bản địa.** Đối thủ quốc tế không có. Đang chỉ dùng nội bộ — cần phơi ra (nhãn cảm xúc, lyrics tô màu cảm xúc, tìm hội thoại). |
| **Color→emotion mapping** (Palmer/Jonauskaite) | 🔵 Độc đáo về khoa học; làm nền cho visualizer & màu thương hiệu. |
| **CLAP/MERT/timbre** | ⚪ Hạ tầng nâng chất lượng; vô hình. |

### 6.4. Tìm kiếm / Duyệt / Admin
- **Browse + filter mood/sort, Time-of-Day, Featured/New/Random, Artists/Genres**: 🟢 Cơ bản tốt, đúng kỳ vọng. Time-of-Day là điểm cộng (hợp circadian + hành vi VN).
- **GIN trigram search tiếng Việt** (fuzzy, dấu): 🟢 Quan trọng cho UX gõ tiếng Việt — giữ.
- **Health/Stats/Config/Backtest, Cache (Redis), Rate limit**: ⚪ Hạ tầng vận hành tốt (giúp giảm pain #4 hiệu năng/bug).

### 6.5. Những thứ nên cân nhắc cắt/gộp
- **Color picker & Image upload** ở dạng tab riêng trong AI Lab: giữ làm **một** mục "Bắt vibe từ ảnh/màu" (gộp), định vị là *hook* chứ không phải lối vào chính — vì dữ liệu cho thấy người dùng hằng ngày tìm theo **mood + ngữ cảnh**, không phải dán hex code.
- Tránh sa đà thêm tín hiệu thứ 9, 10. Pain point thị trường **không** phải "thuật toán chưa đủ mạnh" mà là **kiểm soát/minh bạch/cảm xúc/xã hội**.

---

## 7. Đề Xuất Tính Năng MỚI (ưu tiên giá trị thực + tạo "wow")

Mỗi đề xuất ghi rõ: *nhu cầu/pain point giải quyết* · *tận dụng tài sản sẵn có* · *độ khó*.

### Nhóm A — Lấy lại quyền kiểm soát & minh bạch (đánh trúng pain #1–#3)

**A1. "Vì sao bài này?" — Gợi ý có thể giải thích** 🟢 *Must-have*
- *Giải quyết:* Pain #3 (hộp đen), tăng tin tưởng; xu hướng explainable recs (FAccTRec).
- *Cách làm:* Mỗi bài gợi ý hiện 1–2 lý do từ 7 tín hiệu đã tính sẵn ("Cùng vibe buồn-nhẹ", "Lyrics cùng chủ đề chia tay", "Hợp gam màu/khoá nhạc"). Dữ liệu đã có — chỉ cần bề mặt hóa.
- *Độ khó:* Thấp–Trung bình. **Đây là quick win ấn tượng nhất.**

**A2. "Núm vặn khám phá" (Discovery Dial) + Anti-repeat** 🟢
- *Giải quyết:* Pain #1 (echo chamber) + #2 (mất kiểm soát). Cho người dùng kéo thanh *Quen thuộc ⟷ Bất ngờ* → ánh xạ thẳng vào λ của MMR / độ mạnh DPP (đã có).
- *Cách làm:* Slider + chế độ "Đừng lặp bài tôi vừa nghe". Tận dụng `core/diversity.py`.
- *Độ khó:* Thấp.

**A3. Phản hồi "Thích/Không hợp lúc này" có học** 🟢
- *Giải quyết:* Pain #2 (không có dislike). "Không hợp lúc này" khác "ghét vĩnh viễn" — điều chỉnh tạm thời theo phiên.
- *Độ khó:* Trung bình (cần lưu profile phiên).

### Nhóm B — Trải nghiệm cảm xúc & Wellness (thị trường nóng + thế mạnh độc nhất)

**B1. "Liệu trình cảm xúc" — nâng Emotion Journey thành chế độ Wellness** 🟢 *Đặc trưng thương hiệu*
- *Giải quyết:* Điều tiết cảm xúc (trụ cột #2 Gen Z), thị trường wellness CAGR 12–15%.
- *Cách làm:* Đóng gói Iso-Principle thành các *liệu trình* có chủ đích: "Vực dậy tâm trạng", "Hạ nhiệt lo âu", "Ru ngủ", "Tập trung sâu". Bắt đầu ở tâm trạng hiện tại → dẫn dắt đến đích. **Tích hợp cảnh báo khoa học:** phát hiện *rumination* (nghe lặp nhạc buồn kéo dài) và *nhẹ nhàng* đề xuất chuyển hướng nâng tâm trạng (dựa trên nghiên cứu "unhealthy music use").
- *Độ khó:* Trung bình (logic đã có ở `emotion-journey`).

**B2. "Tuần cảm xúc của bạn" — Wrapped phiên bản cảm xúc** 🔵🟢
- *Giải quyết:* Bản sắc/tự hiểu mình (trụ cột #3), tính chia sẻ xã hội (Wrapped lan truyền mạnh).
- *Cách làm:* Dùng dữ liệu V-A đã tính để vẽ "bản đồ tâm trạng" tuần/tháng (quadrant Q1–Q4), insight kiểu "Thứ 5 của bạn buồn nhất", thẻ chia sẻ đẹp với gradient màu cảm xúc.
- *Độ khó:* Trung bình.

### Nhóm C — Tìm kiếm hội thoại & đa phương thức (xu hướng AI agent)

**C1. "DJ tiếng Việt" — tìm nhạc bằng lời nói tự nhiên** 🟢 *Wow + đúng xu hướng*
- *Giải quyết:* Genre-less mood search (Gen Z), vượt PersonalAIs/Tunee về *chiều sâu tiếng Việt*.
- *Cách làm:* Người dùng gõ/nói "buồn vì chia tay, cho tôi nhạc để khóc rồi nguôi ngoai" → parse cảm xúc bằng PhoBERT/lexicon → map sang V-A → kích hoạt Emotion Journey + lyrics semantic. **Đây là nơi mọi tài sản backend hội tụ thành một tính năng wow.** Có thể chạy hoàn toàn trên engine sẵn có, hoặc tăng cường bằng một LLM nhỏ để parse ý định.
- *Độ khó:* Trung bình (parse) → khác biệt rất lớn.

**C2. "Soundtrack khoảnh khắc" — ảnh → nhạc, dạng xã hội** 🔵
- *Giải quyết:* Đa phương thức (xu hướng Tunee), tính chia sẻ.
- *Cách làm:* Tái định vị image-reco (CLIP đã có) thành "chụp/chọn ảnh → nhận playlist hợp vibe → chia sẻ kèm ảnh". Biến novelty thành nội dung lan truyền.
- *Độ khó:* Thấp (đã có endpoint).

### Nhóm D — Xã hội & Cộng đồng (nhu cầu tăng mạnh, Brightify đang trống)

**D1. "Blend cảm xúc" — playlist chung dựa trên giao thoa tâm trạng 2 người** 🟢
- *Giải quyết:* Kết nối (trụ cột #4), playlist cộng tác +41%. Khác biệt với Spotify Blend: ghép theo *toạ độ V-A/cảm xúc* chứ không chỉ lịch sử nghe.
- *Độ khó:* Trung bình–Cao (cần tài khoản/đồng bộ).

**D2. "Phòng nghe chung" (Jam) theo vibe** 🟡
- *Giải quyết:* Nghe chung thời gian thực (Gen Z khao khát trải nghiệm chung).
- *Độ khó:* Cao (realtime sync) — để pha sau.

### Nhóm E — Đặc thù Việt Nam (con hào bản địa)

**E1. Lyrics đồng bộ + TÔ MÀU theo cảm xúc** 🟢 *Độc nhất*
- *Giải quyết:* Karaoke/lyrics là kỳ vọng cốt lõi ở VN (Zing MP3); chưa app nào tô màu lyrics theo cảm xúc.
- *Cách làm:* Hiển thị lyrics đồng bộ (đã có lyrics trong DB), tô màu từng đoạn theo cảm xúc/V-A (dùng emotion analysis + color mapping đã có). Vừa thực dụng (hát theo) vừa wow (thẩm mỹ).
- *Độ khó:* Trung bình (cần timestamp lyrics — có thể ước lượng/căn chỉnh dần).

**E2. Chế độ Lễ Việt tự động** 🟡
- *Giải quyết:* Ngữ cảnh văn hóa; Context Mix đã có `vn_context` (Tết, Trung Thu, 30/4...).
- *Cách làm:* Tự động gợi "Playlist Tết", "Trung Thu" đúng dịp ở màn hình chính.
- *Độ khó:* Thấp (logic đã có, chỉ cần lên UI).

---

## 8. Ưu Tiên & Lộ Trình Đề Xuất

| Đợt | Tính năng | Lý do ưu tiên | Độ khó |
|---|---|---|---|
| **Sóng 1 — Quick wins giá trị cao** | A1 (Vì sao bài này), A2 (Discovery Dial), E2 (Lễ Việt lên UI), đưa Context Mix + Emotion Journey ra màn hình chính | Trúng pain #1–#3, tận dụng 100% backend có sẵn, công sức thấp | Thấp |
| **Sóng 2 — Khác biệt thương hiệu** | C1 (DJ tiếng Việt), B1 (Liệu trình cảm xúc/Wellness), E1 (Lyrics tô màu cảm xúc) | Định vị Brightify = "app nhạc cảm xúc tiếng Việt", đánh vào wellness đang tăng nóng | Trung bình |
| **Sóng 3 — Lan truyền & giữ chân** | B2 (Tuần cảm xúc/Wrapped), C2 (Soundtrack ảnh), A3 (Feedback có học) | Tạo nội dung chia sẻ + tăng retention | Trung bình |
| **Sóng 4 — Xã hội** | D1 (Blend cảm xúc), D2 (Phòng nghe chung) | Nhu cầu kết nối lớn nhưng cần hạ tầng tài khoản/realtime | Cao |

**Nguyên tắc xuyên suốt:** *Đưa AI lên bề mặt dưới dạng quyền kiểm soát, minh bạch, cảm xúc và bản sắc Việt — không thêm tín hiệu cho có.* Đồng thời giữ hiệu năng/ổn định (pain #4) làm nền, vì đó là pain point lớn nhất theo Brandwatch.

---

## 9. Nguồn Tham Khảo

**Thị trường & khảo sát**
- Brandwatch — *Biggest Pain Points Consumers Have With Music Streaming*: https://www.brandwatch.com/blog/pain-points-music-streaming-services/
- Edison Research — *The Gen Z Audio Report*: https://www.edisonresearch.com/the-gen-z-audio-report/
- Music Ally — *Gen-Z 'musical omnivores'*: https://musically.com/2025/06/13/gen-z-music-study-hails-18-25-year-olds-as-musical-omnivores/
- NuVoodoo — *Gen Z's Passion for Discovering New Music is a Big "Meh"*: https://nuvoodoo.com/2025/03/05/new-data-gen-zs-passion-for-discovering-new-music-is-a-big-meh/
- BPI — *Seeking Community: Gen Z Music Insights 2025*: https://www.bpi.co.uk/news-analysis/seeking-community-report-on-gen-z-music-insights
- MIDiA Research — *Gen Z social habits & music discovery*: https://www.midiaresearch.com/blog/gen-z-social-habits-spell-trouble-for-music-discovery
- Decision Lab — *Vietnam music streaming Q1 2024 / Connected Consumer*: https://www.decisionlab.co/blog/vietnam-music-streaming-industry-q1-2024
- IMARC — *Vietnam Online Music Streaming Market*: https://www.imarcgroup.com/vietnam-online-music-streaming-market
- Vietnam-Briefing — *Music Streaming in Vietnam: Opportunities & Challenges*: https://www.vietnam-briefing.com/news/music-streaming-services-in-vietnam-opportunities-and-challenges.html/
- Statista — *Vietnam leading music streaming apps (Gen Z) 2024*: https://www.statista.com/statistics/1229596/vietnam-leading-apps-to-stream-music-among-gen-z/

**Pain point & đối thủ**
- Spotify Community — *Recommendations terrible / same songs / echo chamber* (nhiều thread): https://community.spotify.com/t5/Your-Library/Keep-getting-recommended-the-same-songs/td-p/5504758
- Music Ally — *Spotify roundup: AI DJ's evolution*: https://musically.com/2025/10/16/spotify-roundup-ai-djs-evolution-ice-ads-and-songdna-leak/
- Mukherjee, Chang, Wibowo (2025) — *Managing the personalization paradox: Lessons from Spotify's AI DJ*, Sage: https://journals.sagepub.com/doi/10.1177/20438869251395753
- Orfium — *PersonalAIs: Mood-aware AI music recommendation*: https://www.orfium.com/data-science/
- Tunee — *Next-Gen AI Music Agent*: https://www.tunee.ai/en

**Học thuật — đa dạng/filter bubble/explainability/cảm xúc**
- *Against Filter Bubbles: Diversified Music Recommendation via Weighted Hypergraph Embedding* (arXiv 2402.16299): https://arxiv.org/html/2402.16299v1
- *Diversity by Design in Music Recommender Systems* (TISMIR): https://transactions.ismir.net/articles/10.5334/tismir.106
- *Reframing the filter bubble…* (Scientific Reports 2024): https://www.nature.com/articles/s41598-024-75967-0
- Music Tomorrow — *Fairness & Transparency in Music Streaming Algorithms: 2025 Review*: https://www.music-tomorrow.com/blog/fairness-transparency-music-recommender-systems
- *Scoping Review on the Use of Music for Emotion Regulation* (MDPI Behav. Sci. 2024): https://www.mdpi.com/2076-328X/14/9/793
- Tan et al. (2024) — *Music's Dual Role in Emotion Regulation* (Depression & Anxiety): https://onlinelibrary.wiley.com/doi/10.1155/2024/1790168

**Wellness & xã hội**
- Soundverse — *Social Listening Sessions*: https://www.soundverse.ai/blog/article/social-listening-sessions-real-time-shared-music-0024
- Precedence Research — *Wellness Apps Market 2025–2034*: https://www.precedenceresearch.com/wellness-apps-market
- Global Wellness Institute — *Music for Health & Wellbeing Trends 2025*: https://globalwellnessinstitute.org/global-wellness-institute-blog/2025/04/02/music-for-health-and-wellbeing-initiative-trends-for-2025/

---

*Báo cáo này được tổng hợp từ nghiên cứu web (tháng 5/2026) đối chiếu với bản kiểm kê tính năng codebase Brightify. Các con số thị trường là ước tính từ nguồn thứ cấp — nên xác minh lại trước khi dùng trong tài liệu gọi vốn/chiến lược chính thức.*
