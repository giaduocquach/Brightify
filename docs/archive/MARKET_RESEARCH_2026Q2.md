# 📊 BÁO CÁO KHẢO SÁT THỊ TRƯỜNG — Brightify Q2/2026

**Ngày lập:** 29/05/2026
**Phạm vi:** Nghiên cứu pain point người dùng music streaming, đánh giá tính năng Brightify hiện tại, đề xuất tính năng mới
**Phương pháp:** Tổng hợp 29 nguồn được kiểm chứng (IFPI, RMIT VN, Decision Lab, Edison Research, MIDiA, Spotify Research, cộng đồng người dùng); đối chiếu với codebase Brightify hậu cleanup (đã loại bỏ `recommend_by_mood` và `compute_musical_dna`)

---

## 🎯 TL;DR — 5 phát hiện quan trọng nhất

1. **Spotify Wrapped 2024–2025 bị tẩy chay "AI slop"** (Rolling Stone, Headphonesty). User chán algorithm bias — Brightify content-based **không có cold-start bias** là lợi thế lớn chưa được tận dụng marketing.
2. **Thị trường VN siêu nội địa**: 75% lượng nghe là nhạc Việt, 8/10 bảng xếp hạng IFPI VN là nghệ sĩ Việt. **Brightify với 4,348 bài Việt 100% đi đúng hướng** — không cần catalog quốc tế.
3. **YouTube 77% > Zing 52% > NhacCuaTui 32% > Spotify 28%** (Decision Lab Q1/2024). YouTube là đối thủ #1, không phải Spotify. Nỗi đau lớn nhất ở Zing/NCT là **reliability + lag**.
4. **Gen Z VN dùng audio như therapy**: 63% nói audio giúp vượt khủng hoảng, 86% boost mood (Edison Gen Z Audio Report 2025, n=2,010). **Emotion Journey của Brightify đúng tâm điểm**.
5. **AI music penetration ở VN cao**: 2/10 bài hot 2025 là AI-generated; 60% nhạc sĩ dùng AI (RMIT). User VN **không sợ AI** — Brightify có thể "khoe" AI mạnh hơn nữa.

---

## PHẦN I — PHƯƠNG PHÁP & PHẠM VI

**Phương pháp**: Tổng hợp định tính + định lượng từ:
- Survey-grade: IFPI 2025/2026, Decision Lab VN Q1/2024, Edison Gen Z 2025 (n=2,010), MIDiA Research, RMIT VN Digital Music Landscape 2024–2025
- Industry analysis: Music Tomorrow, Spotify Research, Digital Music News, TechCrunch
- User voice: Reddit, Tinhte, GigLifePro, Spotify Community, PissedConsumer
- VN local: NhacCuaTui/Zing user complaints, Vietnam.vn, Taylor & Francis VN indie paper

**Phạm vi đối thủ**: Spotify, Apple Music, YouTube Music, Amazon Music, Deezer, ZingMP3, NhacCuaTui, TikTok (discovery), Endel (mood/biometrics), Mixtape Social.

---

## PHẦN II — PAIN POINTS NGƯỜI DÙNG (TOÀN CẦU)

| # | Pain Point | Bằng chứng | Mức độ |
|---|---|---|---|
| **P1** | "AI slop" trong Wrapped 2024 — Spotify trả nghệ sĩ user chưa từng nghe | Rolling Stone, Headphonesty, u/Normal-Earth-9700 | ⭐⭐⭐⭐⭐ Viral |
| **P2** | Echo chamber — mọi playlist nghe giống nhau | Music Tomorrow 2025 ("favors repetition over discovery") | ⭐⭐⭐⭐⭐ Industry |
| **P3** | Distrust algorithm → đòi manual control (Flow Tuner ra đời) | EU DSA 2024 + Deezer Flow Tuner Feb 2026 | ⭐⭐⭐⭐ Industry |
| **P4** | AI Playlist chất lượng chưa đạt (Spotify tự nhận trong paper Text2Tracks) | Spotify Research 2025 | ⭐⭐⭐⭐ Self-admit |
| **P5** | Gemini hallucinates — recommend "9 bài không tồn tại" | Android Authority review | ⭐⭐⭐ Anecdotal |
| **P6** | Hum-search fail — không tìm được bài đang ngân nga | Quora threads | ⭐⭐⭐ Anecdotal |
| **P7** | "Sad spiral" — high-rumination user nghe nhạc buồn ↑ trầm cảm | Frontiers/NCBI PMC6542982 | ⭐⭐⭐⭐⭐ Academic |
| **P8** | Mất social listening (mixtape, forum) | TechBuzz Mixtape Social | ⭐⭐⭐ Anecdotal |
| **P9** | TikTok discovery → app conversion thấp: 75% Gen Z dùng TikTok hàng tuần, chỉ 31% click "add to music app", 19% explore artist | MIDiA Research | ⭐⭐⭐⭐⭐ Survey |

---

## PHẦN III — THỊ TRƯỜNG VIỆT NAM (40% trọng số)

### 3.1 Thị phần và behavior

| Platform | Share (Decision Lab Q1/2024) | Điểm yếu |
|---|---:|---|
| **YouTube** | 77% | Quảng cáo, không curate cảm xúc |
| **Zing MP3** | 52% | Crash khi tắt màn hình, quality "thuộc loại tệ hại nhất" (Tinhte) |
| **NhacCuaTui** | 32% | "Lag tung đít" (GigLifePro), geo restriction |
| **Spotify** | 28% | Catalog VN thiếu, không hiểu lyrics Việt |

→ **Insight**: User VN **nghe nhiều platform song song** (Gen Z spreads across platforms — Decision Lab). Cơ hội cho Brightify là **bù đắp điểm yếu** của Zing/NCT (reliability + AI hiểu lyrics Việt), không cạnh tranh trực tiếp catalog.

### 3.2 Đặc thù Việt Nam

| # | Phát hiện | Bằng chứng | Hệ quả cho Brightify |
|---|---|---|---|
| **VN1** | 75% lượng nghe = nhạc Việt, 8/10 top chart IFPI là VN artists | IFPI VN Chart 2025 | ✅ Brightify đi đúng: 100% catalog Việt |
| **VN2** | Gen Z VN "internet-native" — indie scene khởi đầu từ SoundCloud 2015 | Taylor & Francis paper | 💡 Cơ hội cho **indie discovery radar** |
| **VN3** | Superfans Gen Z drive idol cycles, mua vé, push top chart | Vietnam.vn | 💡 Cơ hội **fan community features** |
| **VN4** | AI music accepted: 2/10 hot songs 2025 là AI-gen, 60% nhạc sĩ dùng AI | RMIT 2026 | ✅ User VN không sợ AI |
| **VN5** | Karaoke = cultural bonding ritual | KissTour | 💡 Cơ hội **karaoke mode** — chưa platform nào tích hợp tốt |
| **VN6** | Decision Lab top-3 driver chọn platform: intuitive UI (93%) + catalog (93%) + price (92%) | Decision Lab | ⚠️ UI Brightify phải simple — đang quá nhiều tab AI |
| **VN7** | Vinahouse trending mạnh cho party/dance | TikTok trending | 💡 Curated playlist "party mode" |
| **VN8** | Thị trường VN tăng $85M (2024) → $169M (2033), CAGR 7.89% | IMARC | ✅ Đủ runway cho startup |

### 3.3 Cross-platform: TikTok là engine discovery

RMIT 2024–2025: 3 platform top được dùng là **YouTube + TikTok + Spotify** chứ không phải Zing/NCT cho Gen Z. TikTok dẫn dắt 30%+ discovery nhưng MIDiA cho thấy **chỉ 31% Gen Z chuyển sang music app sau khi nghe trên TikTok** — đây là gap khổng lồ.

---

## PHẦN IV — XU HƯỚNG MỚI 2024–2026

| # | Xu hướng | Người dẫn đầu | Trạng thái Brightify |
|---|---|---|---|
| **T1** | Vibe-based natural-language search | Spotify Prompted, Amazon Maestro, Deezer | ⚠️ Có engine (lyrics keyword) nhưng UI ẨN |
| **T2** | Mood Check-In khi mở app | Spotify Smart Filters (10/2025) | ❌ Chưa có |
| **T3** | Biometrics + music (heart rate, weather) | Endel + Apple Watch | ⚠️ Có context-mix (engine) nhưng UI ẨN |
| **T4** | Co-listening (Jam, SharePlay, Messages) | Spotify Jam DAU 2x YoY, 40M Messages users | ❌ Chưa có |
| **T5** | AI transparency — "tại sao bài này?" | Spotify AI credit beta 4/2026 | ❌ Chưa có |
| **T6** | Manual algorithm tuner (sliders) | Deezer Flow Tuner Feb/2026 | ❌ Chưa có |
| **T7** | Daily personality playlist (Daylist) | Spotify Daylist viral 20,000% search ↑ | ⚠️ Có engine context-mix |

---

## PHẦN V — ĐÁNH GIÁ TỪNG TÍNH NĂNG BRIGHTIFY (đối chiếu với research)

### Bảng đánh giá đa chiều

| Feature | Trạng thái UI | Pain point address | User value | Wow factor | USP | Đánh giá |
|---|---|---|---|---|---|---|
| 🎨 **Color** | ✅ Live (AI Lab default) | P2 (echo), P9 (discovery) | Cao | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | **GIỮ — flagship** |
| 📷 **Image** | ✅ Live (AI Lab) | P9, T3 | Vừa | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | **GIỮ — demo magnet** |
| 🎯 **Emotion Journey** | ✅ Live (AI Lab) | **P7 (sad spiral)** | Cao | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | **GIỮ — therapy USP** |
| 📻 **Radio/Auto-queue** | ✅ Live (player) | Daily driver | Rất cao | ⭐⭐⭐ | ⭐⭐ | **GIỮ — daily essential** |
| ✍️ **Lyrics keyword** | ❌ DEAD UI | T1, **VN4 (AI Việt)** | Cao | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | **BẬT LẠI** — match xu hướng T1 |
| 🌤️ **Smart Context** | ❌ DEAD UI | T7 (Daylist), T2 (mood check-in) | **Rất cao** (daily) | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | **BẬT LẠI** — match T7 viral |
| 🔍 Search lexical | ✅ Live | Cơ bản | Cao | ⭐ | ⭐ | Giữ, thêm lyrics field (Apple-style) |
| 📊 Mood Q1-Q4 browse | ✅ Live | Cơ bản | Vừa | ⭐⭐ | ⭐ | Giữ, nhưng overlap với Color |

### Chi tiết đánh giá

**🎨 Color (FLAGSHIP)** — Đáp ứng P2/P9. Content-based fusion lyrics + audio + V-A + emotion (theo memory: CORE feature). Khoa học rõ (Jonauskaite 2020, CIEDE2000). **Wow factor cao nhất** vì không đối thủ nào làm. Hiện đang là default tab — đúng quyết định.

**📷 Image** — Đáp ứng P9. Demo magnet, "wow" cho first-time user (upload selfie → playlist). Tận dụng pipeline Color → marginal cost thấp. **Retention thấp**: user rare upload ảnh lần 2. → Định vị là **"awareness driver"** chứ không phải daily feature.

**🎯 Emotion Journey** — Trúng P7 (sad spiral) với evidence academic-grade. **USP duy nhất** trên thị trường music therapy. Edison Gen Z: 86% nói music boost mood → đây là feature target Gen Z VN trực tiếp.

**📻 Radio/Auto-queue** — Engine mạnh nhất (7-signal), nhưng **chỉ render trong player** — thiếu UI "Bài tương tự" trên trang song detail. Cần expose hơn nữa.

**✍️ Lyrics keyword — DEAD UI** — Đáng tiếc nhất. Theo research:
- T1 vibe-search là xu hướng số 1 toàn cầu (Spotify/Amazon/YouTube đầu tư mạnh)
- VN4: user VN chấp nhận AI cao
- PhoBERT 768-d đã sunk cost
- → **Bật lại 1 dòng comment** = giải phóng giá trị to lớn.

**🌤️ Smart Context — DEAD UI** — Đáng tiếc thứ 2.
- T7: Daylist viral 20,000% search ↑ — Brightify có engine TƯƠNG ĐƯƠNG (circadian + activity + weather + season + user taste) nhưng không ai biết
- T2: Spotify Community demand mood check-in
- Engine sâu nhất hệ thống (~300 dòng)
- → **Bật lại + repackage thành "Daily Vibe"** = match xu hướng viral

---

## PHẦN VI — GỢI Ý 12 TÍNH NĂNG MỚI (xếp theo độ wow × giá trị)

### 🏆 Top tier — Triển khai ngay (effort thấp, impact cao)

#### F1. **Daily Vibe Card** 🌅 (Daylist-killer, VN-localized)
- **Inspired by**: Spotify Daylist viral (T7, D1)
- **Mô tả**: Mở app sáng → card lớn: "Hôm nay là 1 ngày **mưa nhẹ chill lofi** của bạn" với 15 bài curate. Tự update 4 lần/ngày theo circadian + weather + history. Title sinh động: "Cà phê chiều mưa thứ Tư" / "Đêm khuya hoài niệm cuối tuần".
- **Tái sử dụng**: `smart_context_recommend` (đã có) + LLM (hoặc template) generate title
- **Effort**: Thấp (engine có sẵn, chỉ cần UI card + title generator)
- **Wow**: ⭐⭐⭐⭐⭐ — share lên Insta Stories như Daylist
- **VN angle**: title bằng tiếng Việt giàu cảm xúc — Spotify không làm được

#### F2. **Mood Check-In khi mở app** 😊
- **Inspired by**: T2 (Spotify Community demand), A9 (Gen Z dùng audio như therapy)
- **Mô tả**: 1 lần/ngày khi mở app, prompt nhẹ: "Hôm nay bạn thế nào?" với 7 emoji (🥰😢😡😌🤩😴😶) + skip. Tap → tự curate trang chủ + queue đầu tiên. Save mood log để build "emotional timeline" của user.
- **Effort**: Thấp (mapping emoji → V-A coordinate sẵn)
- **Wow**: ⭐⭐⭐⭐ — feel-cared-for moment
- **Long-term**: data cho Wrapped/insight

#### F3. **"Tại sao bài này?" — Explanation card** 💡
- **Inspired by**: T5 (Spotify AI credit 4/2026), market demand transparency
- **Mô tả**: Mỗi recommend kèm dòng giải thích: "🎵 Cùng *cảm xúc nhớ nhung* và *giai điệu acoustic chậm* với bài bạn vừa nghe" hoặc "🎨 Khớp 87% với màu tím bạn chọn — *valence thấp, năng lượng dịu*".
- **Tái sử dụng**: Engine đã trả `similarity_score` + component scores → chỉ cần format
- **Effort**: Trung bình (cần collect breakdown từ engine)
- **Wow**: ⭐⭐⭐⭐⭐ — anti-black-box, builds trust
- **VN angle**: explain bằng tiếng Việt cảm xúc, không phải số khô khan

#### F4. **TikTok Bridge** 🎬
- **Inspired by**: P9 MIDiA (75% Gen Z TikTok, chỉ 31% chuyển sang app); RMIT VN top platform TikTok
- **Mô tả**: Paste link TikTok hoặc tên đoạn hot → Brightify identify bài + 1-click add to library + recommend 10 bài cùng mood. Bonus: nhúng QR code "Save to Brightify" cho TikTok creator dùng.
- **Effort**: Trung bình (cần TikTok URL parser + audio fingerprint hoặc API)
- **Wow**: ⭐⭐⭐⭐ — bridge to dominant Gen Z platform
- **VN angle**: chính nguồn discovery #1 của Gen Z VN

### 🥈 Mid tier — Quý 2/2026

#### F5. **Karaoke Mode** 🎤
- **Inspired by**: VN5 (karaoke = bonding ritual), Apple Music lyrics highlight (D3)
- **Mô tả**: Tab "Karaoke" trong song detail. Lyrics highlight theo time (đã có lyrics column). Bonus tier-2: mic input → pitch matching score; share score lên TikTok.
- **Effort**: Trung bình (cần timestamp lyrics — hiện chưa có)
- **Wow**: ⭐⭐⭐⭐⭐ — **VN killer feature**, không platform quốc tế nào làm tốt cho nhạc Việt
- **Note**: cần thêm phase trong pipeline để align lyrics + audio (forced alignment)

#### F6. **Anti-Sad-Spiral Guard** 🛡️
- **Inspired by**: P7 (rumination + sad music ↑ depression — academic), Emotion Journey vibe
- **Mô tả**: Detect khi user nghe ≥ 5 bài V<0.3 liên tiếp → tooltip nhẹ: "Đã 30 phút bạn nghe nhạc buồn. Thử **Hành trình** kéo mood lên?" (1-click → Emotion Journey từ current V-A → 0.7/0.6). Không ép, dễ dismiss.
- **Effort**: Thấp (đã có Emotion Journey + V-A của mọi bài)
- **Wow**: ⭐⭐⭐⭐ — *caring* feature, social impact
- **Marketing**: "music wellness" branding — chưa ai làm

#### F7. **Vibe Tuner (Brightify Tuner)** 🎛️
- **Inspired by**: P3, T6 (Deezer Flow Tuner Feb/2026), D4 (polarized but loud)
- **Mô tả**: Trong queue/radio, sliders real-time cho: 🌡 Năng lượng / 😊 Vui-Buồn / 🎶 Acoustic-Điện tử / ⚡ Tempo. Kéo slider → next song trong queue update real-time.
- **Effort**: Trung bình (cần re-rank queue mỗi khi slider thay đổi)
- **Wow**: ⭐⭐⭐⭐ — control freaks love this
- **Caveat**: D4 cho thấy polarized — phải làm OPT-IN, không default

#### F8. **Indie VN Discovery Radar** 🌟
- **Inspired by**: VN2/VN3 (Gen Z VN indie internet-native), P2 (anti-echo)
- **Mô tả**: Section "Mới nổi" curate nghệ sĩ < 1000 plays, sắp xếp theo recent activity + audio quality. Mỗi tuần highlight 5 nghệ sĩ indie.
- **Effort**: Thấp (filter SQL + cron)
- **Wow**: ⭐⭐⭐ — chậm nhưng builds long-term loyalty từ indie community

### 🥉 Lower tier — Nếu có thời gian

#### F9. **Brightify Wrapped — Honest Edition** 📅
- **Inspired by**: A1 (Spotify Wrapped 2024 AI-slop backlash), D2 (Wrapped viral)
- **Mô tả**: Cuối năm + cuối tháng: data report có thật (top emotion, top color, mood timeline, longest sad streak, "most journey'd from sad to happy"). KHÔNG có AI slop. Share-friendly cards cho IG/TikTok.
- **Effort**: Trung bình (cần persist listen log + design template)
- **Wow**: ⭐⭐⭐⭐ — counter-positioning vs Spotify failure

#### F10. **Co-Listening Room (Brightify Together)** 👯
- **Inspired by**: T4 (Spotify Jam DAU 2x), P8 (social listening loss)
- **Mô tả**: Phòng nghe chung 2–8 người, sync playback, chat reactions, voting next song. Phù hợp couple long-distance / friend hangout.
- **Effort**: Cao (cần WebSocket infra)
- **Wow**: ⭐⭐⭐⭐
- **Risk**: cần realtime infrastructure, có thể beyond scope

#### F11. **Lyrics Story Mode** 📖
- **Inspired by**: từ MARKET_ANALYSIS_REPORT.md cũ, tận dụng PhoBERT
- **Mô tả**: Chọn theme ("yêu xa", "tuổi học trò") → PhoBERT tìm bài tạo narrative arc (gặp → yêu → xa → nhớ → hàn gắn). Mỗi bài kèm lyric snippet hay nhất.
- **Effort**: Trung bình (PhoBERT đã có)
- **Wow**: ⭐⭐⭐⭐ — storytelling unique

#### F12. **Friend Vibe Match** 🤝
- **Inspired by**: VN3 (VN superfans community), P8
- **Mô tả**: Connect bạn bè → so vibe-fingerprint (V-A center, top emotion, color profile). "Bạn và Linh khớp 78% — cùng yêu *bình yên buổi sáng*". Compatibility report.
- **Effort**: Trung bình (cần auth + user data persist)
- **Wow**: ⭐⭐⭐⭐ — viral potential
- **VN angle**: fandom culture mạnh

### Ma trận ưu tiên

```
                  CAO ↑
              │  F1 Daily Vibe          F5 Karaoke
              │  F2 Mood Check-In       F4 TikTok Bridge
   GIÁ TRỊ    │  F3 Explanation         F10 Co-Listening
   USER       │
              │  F6 Anti-Spiral         F11 Lyrics Story
              │  F8 Indie Radar         F12 Friend Match
              │
              │  F7 Vibe Tuner          F9 Honest Wrapped
              │
                  THẤP ───────────────→ CAO
                              EFFORT
```

**Khuyến nghị triển khai theo wave**:
- **Wave 1 (tuần 1–2, low-hanging)**: F2 Mood Check-In + F3 Explanation + bật lại Lyrics/Context (2 dòng uncomment) + F1 Daily Vibe (repackage Context)
- **Wave 2 (tháng 1–2)**: F6 Anti-Spiral + F5 Karaoke (đầu tư lyric timestamping) + F4 TikTok Bridge
- **Wave 3 (tháng 3+)**: F9 Wrapped + F8 Indie Radar + F11 Lyrics Story + F7 Tuner

---

## PHẦN VII — STRATEGIC POSITIONING

### Brightify's "Unfair Advantages" (dựa trên research)

1. **Content-based, không AI slop** (vs P1 Spotify Wrapped backlash) — tuyệt đối không có popularity bias hay astroturf. Đáng marketing mạnh.
2. **PhoBERT hiểu lyrics Việt** — Spotify/YT/Apple đều thua. Match VN4 (60% nhạc sĩ dùng AI).
3. **Emotion Journey music therapy** — duy nhất trên thị trường. Match P7 + A8 academic.
4. **Color synesthesia** — visual differentiation, demo magnet.
5. **100% catalog Việt** — match VN1 (75% lượng nghe = nhạc Việt).

### "Tagline" candidates (từ insight)

- *"Brightify — Hiểu cảm xúc bạn, không chỉ tên bài"* (chống AI slop)
- *"Music as therapy. Made in Vietnam."* (Gen Z mental health hook)
- *"Khi nhạc của bạn không lặp lại."* (anti-echo-chamber)

### Risks (research-grade)

- **VN6**: 93% user VN ưu tiên UI intuitive → đang có **6 AI feature** = nguy cơ choice paralysis. Phải **streamline navigation**.
- **D4**: Flow Tuner polarized — manual control features dễ split user base. Phải opt-in.
- **P5**: AI hallucination risk — đặc biệt với Lyrics keyword (PhoBERT có thể trả bài không liên quan). Cần guardrail "không tìm thấy thì im lặng" thay vì cố gắng.

### KPIs đề xuất theo dõi

| Metric | Target Q3/2026 | Lý do |
|---|---|---|
| Daily Vibe card open rate | > 60% | F1 success indicator |
| Mood Check-In opt-in rate | > 40% | F2 stickiness |
| Emotion Journey usage / DAU | > 8% | USP penetration |
| Lyrics search → play conversion | > 25% | Bật lại có value |
| Wrapped share rate (year-end) | > 15% | F9 viral test |
| 7-day retention | > 45% | overall health |

---

## PHẦN VIII — KẾT LUẬN & NEXT STEPS

### Tóm tắt 1 câu
**Brightify có engine xuất sắc nhưng đang underutilize: 2 feature ẩn UI (Lyrics, Context) đúng tâm điểm 2 xu hướng nóng nhất ngành (vibe-search T1 + Daylist T7). Bật lại + thêm 4 feature wave-1 (Daily Vibe, Mood Check-In, Explanation, TikTok Bridge) sẽ chuyển Brightify từ "AI demo" thành "daily companion".**

### Hành động tức thì (effort < 1 ngày)
1. ☐ Uncomment 2 dòng `app.js:696` và `app.js:699` để bật lại Lyrics + Context tab
2. ☐ Đổi tên tab Context → **"🌅 Hôm nay"** (Daylist positioning)
3. ☐ Đổi tên Lyrics → **"✨ Tìm theo cảm xúc"**
4. ☐ Thêm "Tại sao bài này?" tooltip ngắn vào mỗi recommendation card

### Hành động tuần này (effort 2–5 ngày)
5. ☐ Implement F2 Mood Check-In (modal khi mở app)
6. ☐ Implement F1 Daily Vibe Card cho homepage hero
7. ☐ Implement F6 Anti-Sad-Spiral Guard (passive monitoring)

### Hành động tháng này (effort 1–3 tuần)
8. ☐ F5 Karaoke Mode (cần thêm phase lyric-timestamp trong pipeline)
9. ☐ F4 TikTok Bridge
10. ☐ F3 Explanation cards với breakdown thực

---

## NGUỒN THAM KHẢO

**Survey-grade**:
- [IFPI Global Music Report 2025 SOTI](https://www.ifpi.org/wp-content/uploads/2024/03/GMR2025_SOTI.pdf)
- [IFPI Global Music Report 2026 SOTI](https://www.ifpi.org/wp-content/uploads/2026/03/GMR2026_SOTI.pdf)
- [Decision Lab Vietnam Music Streaming Q1 2024](https://www.decisionlab.co/blog/vietnam-music-streaming-industry-q1-2024)
- [RMIT Vietnam Digital Music Landscape 2024–2025](https://www.rmit.edu.vn/content/dam/rmit/vn/en/assets-for-production/documents/pdfs/scd/2024/EN-vietnam-digital-music-landscape-2024.pdf)
- [Edison Research Gen Z Audio Report 2025](https://www.edisonresearch.com/the-gen-z-audio-report/)
- [MIDiA Research Gen Z Social Habits](https://www.midiaresearch.com/blog/gen-z-social-habits-spell-trouble-for-music-discovery)
- [IMARC Vietnam Online Music Streaming Market](https://www.imarcgroup.com/vietnam-online-music-streaming-market)
- [IFPI Official Vietnam Chart launch](https://www.ifpi.org/ifpi-launches-official-southeast-asia-charts-hub-with-creation-of-new-charts-in-philippines-and-vietnam/)

**Industry analysis**:
- [Music Tomorrow — Fairness & Transparency 2025](https://www.music-tomorrow.com/blog/fairness-transparency-music-recommender-systems)
- [Spotify Research — Text2Tracks](https://research.atspotify.com/2025/04/text2tracks-improving-prompt-based-music-recommendations-with-generative-retrieval)
- [Spotify Research — Agentic Query Understanding](https://research.atspotify.com/2025/9/you-say-search-i-say-recs-a-scalable-agentic-approach-to-query-understanding)
- [Deezer Newsroom — Flow Tuner](https://newsroom-deezer.com/2026/02/deezer-launches-flow-tuner-personalized-recommendations/)
- [Deezer + Ipsos — AI fools 97%](https://newsroom-deezer.com/2025/11/deezer-ipsos-survey-ai-music/)
- [TechCrunch — Amazon Music Maestro](https://techcrunch.com/2024/04/16/amazon-music-follows-spotify-with-an-ai-playlist-generator-of-its-own-maestro/)
- [Spotify Newsroom — New Spotify Features Oct 2025](https://newsroom.spotify.com/2025-10-08/new-spotify-features-to-use/)

**Wrapped 2024 controversy**:
- [Rolling Stone — Spotify Wrapped 2024: Why It Was Disappointing](https://www.rollingstone.com/music/music-news/spotify-wrapped-2024-disappointing-1235192170/)
- [Headphonesty — Fans Slam Spotify Wrapped as AI Slop](https://www.headphonesty.com/2025/12/fans-slam-spotify-wrapped-ai-slop-stats/)

**Mental health & music**:
- [NCBI PMC6542982 — Music Use for Mood Regulation in Young People with Depression](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6542982/)
- [ArXiv — Music Listening as Depression Risk Indicators](https://arxiv.org/pdf/2009.13685)
- [Inside Radio — Gen Z Music as Coping Toolkit](https://www.insideradio.com/free/for-gen-z-music-and-audio-is-part-of-their-coping-toolkit/article_a88b0950-fc1b-4330-8699-7ef130fbca34.html)

**Vietnam-specific**:
- [Tinhte — Spotify vs ZingMP3 vs NhacCuaTui](https://tinhte.vn/thread/spotify-vs-zingmp3-vs-nhaccuatui-3-ung-dung-nhac-pho-bien-dau-nhau-ra-sao.3164637/)
- [GigLifePro — Music Streaming Platforms of Vietnam](https://giglifepro.com/articles/music-streaming-platforms-of-vietnam)
- [RMIT — AI and Music: Digital Symphony](https://www.rmit.edu.vn/news/all-news/2026/jan/ai-and-music-digital-symphony-or-the-end-of-human-creativity)
- [Taylor & Francis — Vietnamese indie music in the age of digital streaming](https://www.tandfonline.com/doi/full/10.1080/10304312.2023.2286204)
- [Vietnam.vn — Shaping new standards of success for Vietnamese music](https://www.vietnam.vn/en/dinh-hinh-tieu-chuan-thanh-cong-moi-cua-nhac-viet)
- [KissTour — Vietnam Karaoke Culture](https://kisstour.com/travel-guide/vietnam-karaoke-culture-more-than-just-singing/)

**Trends 2024–2026**:
- [Melod.ie — Natural Language Search](https://blog.melod.ie/2025/05/12/introducing-natural-language-search/)
- [Endel Technology](https://endel.io/technology)
- [TechCrunch — Spotify Real-Time Sharing](https://techcrunch.com/2026/01/07/spotify-now-lets-you-share-what-youre-streaming-in-real-time-with-friends/)
- [Spotify Community — Mood-based listening request](https://community.spotify.com/t5/Live-Ideas/listening-to-music-based-on-your-mood/idi-p/5640839)

---

*Báo cáo này được sinh ra như công cụ ra quyết định product, không thay thế research định tính sâu (user interview, usability test). Để verify các giả thuyết về user VN, khuyến nghị bổ sung 10–15 buổi user interview Gen Z + 1 survey n≥300 trước khi quyết định Wave 2/3.*
