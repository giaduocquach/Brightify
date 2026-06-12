# Brightify — Immersive Color-First UI Redesign · Plan V1

> Trạng thái: **PLAN — chưa code.** Tác giả: redesign session 2026-06-11.
> Từ khoá chỉ đạo: **ấn tượng · phá cách · thoả mãn · chìm đắm.**
> Quyết định scope đã chốt với chủ dự án:
> 1. **Stack:** giữ kiến trúc static/FastAPI hiện tại, thêm **Three.js + GSAP (+ Meyda)** qua **CDN ES-module import map** — KHÔNG build step, KHÔNG framework mới ⇒ rủi ro regression thấp nhất.
> 2. **Đường cảm xúc:** làm **cả hai** — Phase 1 đường năng lượng **live (Web Audio)**, Phase 2 đường **arousal thật theo segment (MERT)** làm lớp nền.
> 3. **Độ táo bạo:** **Color-first, bỏ template Spotify.** Trang chính = không gian màu/cảm xúc 3D; chọn màu là cách khám phá chính.
> 4. Ràng buộc cứng: **chọn màu vẫn phải dễ + accessible + không lỗi.** Mọi hiệu ứng nặng phải degrade graceful.

---

## 0. Tại sao redesign (vấn đề hiện tại)

| Hiện trạng | Vấn đề với tầm nhìn "chìm đắm, color-first" |
|---|---|
| Layout = clone Spotify (sidebar 240px + topbar + player bar 80px) | Quy chuẩn, không "phá cách"; feature lõi (color) bị chôn trong tab "AI Lab" |
| Color picker = 12 thẻ tĩnh trong panel | Đúng khoa học (ISCC-NBS centroid, mỗi thẻ có `data-va`) nhưng vô hồn, không immersive |
| `#ambient-bg` = 1 radial-gradient tĩnh đổi mỗi 3s | Không phản ứng nhạc, không phản ứng cảm xúc bài đang nghe |
| Visualizer = canvas 80×36px ở góc player | Cảm xúc "lên xuống" của bài hoàn toàn vô hình với người nghe |
| Đường nghe và đường nhìn **rời rạc** | Không có sự "chìm đắm" — mắt và tai không kể cùng một câu chuyện |

**Tài sản đang có (tái dùng 100%, không phá khoa học):**
- 12 màu cảm xúc, mỗi màu có `data-va="valence,arousal"` (ISCC-NBS vivid centroid, Kelly&Judd 1955) + nhãn cảm xúc tiếng Việt.
- API `/api/recommend/color`: 1 màu = mood, 2 màu = **mood journey A→B** (Iso-Principle), trả về per-song `{valence, arousal, label, color_hex}` + `bridge` (color→emotion).
- Per-song VA labels (`emotion_labels_v6b.json`): `{valence, arousal, label}`.
- `MERTEncoder.extract()` đã chunk audio nội bộ; `mert_arousal_probe.py` (Ridge, CV R²≈0.58) map MERT→arousal.
- Audio graph trong `player.js`: AnalyserNode + crossfade decks A/B + RAF loop sẵn sàng.

---

## 1. Nguyên lý nền tảng (research-grounded)

Toàn bộ thiết kế xoay quanh **một mô hình thống nhất**: *màu, chuyển động, và nhạc đều được điều khiển bởi cùng một toạ độ Valence–Arousal (V,A).* Mắt nhìn và tai nghe kể **cùng một câu chuyện cảm xúc** ⇒ đó chính là "chìm đắm".

### 1.1 Color ↔ Emotion ↔ Music (đã có nguồn)
- **Palmer & Schloss, PNAS 2013** — tương ứng nhạc↔màu được **trung gian bởi cảm xúc** (r = 0.89–0.99). Nhanh+major → màu **bão hoà, sáng, ấm/vàng**; chậm+minor → **nhạt, tối, lạnh/xanh**.
- **Valdez & Mehrabian 1994** — hệ số định lượng (B = brightness, S = saturation, chuẩn hoá 0–1):
  - `Pleasure (≈Valence) = 0.69·B + 0.22·S` → **độ sáng là đòn bẩy chính của valence.**
  - `Arousal = −0.31·B + 0.60·S` → **độ bão hoà là đòn bẩy chính của arousal** (sáng làm *giảm* arousal).
- **Russell 1980** — mặt phẳng circumplex V×A (đúng mô hình app đang dùng).

> **Quy tắc kỹ thuật áp dụng (lõi của redesign):**
> Bất kỳ màu hex nào → `(L*, C*, h)` trong CIELAB →
> `arousal ≈ f(C* ↑)`, `valence ≈ f(L* ↑ + hue ấm)`.
> Đây là HÀM MÀU→VA dùng chung cho cả visual lẫn việc neo về recommender hiện có.

### 1.2 Cảm xúc → Chuyển động & Không khí (Laban / affective computing)
- **Fluidity ↓ arousal:** mượt, liên tục, `ease-in-out` = **bình thản**; gắt, giật, staccato = **kích thích cao**.
- **Naturalness ↑ valence:** quỹ đạo tự nhiên, mềm = **tích cực hơn**.

| Trục | Thấp | Cao |
|---|---|---|
| **Arousal** → tốc độ/tần suất/độ sắc | drift chậm, blur lớn, ease mượt, ít hạt | nhanh, hạt bùng, cạnh sắc, ease gắt |
| **Valence** → sáng/ấm/hướng | tối, lạnh/xanh, chuyển động chìm xuống | sáng, ấm/vàng, chuyển động dâng lên/nở ra |

Saturation→motion-energy, Brightness→warmth/lift: **đồng bộ với hệ số Valdez–Mehrabian** ⇒ lớp visual tính từ **cùng một (V,A)** mà recommender dùng.

---

## 2. Ngôn ngữ thiết kế

### 2.1 Bảng màu — *động, không cố định*
Khác mọi app: **không có "accent color" cứng.** Màu chủ đạo của toàn UI = nội suy từ (V,A) hiện hành (màu user chọn HOẶC VA bài đang phát).

- **Nền (hằng số, OLED-friendly):** `--void: #05050B` → `#0A0A18` (gần đen, để màu cảm xúc nổi bật, tiết kiệm pin OLED, tương phản text cao).
- **Lớp màu cảm xúc (biến thiên runtime):** 2–3 stop gradient mesh (style **Aurora UI / Gradient Mesh**) tính từ (V,A):
  - `hue = lerp(lạnh 220° … ấm 35°, valence)`.
  - `saturation = lerp(25% … 95%, arousal)`.
  - `lightness = lerp(35% … 70%, valence)`.
- **Text:** `--ink: #F4F2FB`, phụ `#A6A4C4`. Luôn kiểm 4.5:1 trên lớp màu động (xem §6).
- Giữ accent gradient cũ (`#a78bfa → #67e8f9`) **chỉ cho chrome trung tính** (nav, icon) để không xung đột màu cảm xúc.

### 2.2 Typography
- **Display/Hero:** chữ có "tiếng nói" — `Space Grotesk` hoặc `Clash Display` (qua Google/Fontshare CDN) cho cảm giác phá cách, hiện đại.
- **Body/UI:** **giữ `Inter`** (đã dùng, hỗ trợ tiếng Việt tốt, an toàn).
- **VN diacritics:** verify subset `vietnamese` của mọi font display (tránh dấu vỡ).
- Mood: "music / entertainment / bold" (khớp gợi ý skill ui-ux-pro-max).

### 2.3 Motion language (GSAP)
- Easing chủ đạo: `expo.out` / `power3.out` cho vào, `power2.inOut` cho chuyển cảnh — mượt = valence dương, "chìm đắm".
- Mọi chuyển cảnh màu = **GSAP tween trên uniforms shader** (không đổi DOM đột ngột).
- Thời lượng: micro 150–250ms; chuyển cảnh lớn 600–1000ms; loop môi trường 8–12s (khớp Aurora).
- **`prefers-reduced-motion`**: tắt loop nền, giảm về gradient tĩnh + arc 2D (xem §6).

---

## 3. Kiến trúc kỹ thuật (low-risk, no build)

### 3.1 Phụ thuộc — toàn bộ qua CDN ES-module import map
```html
<script type="importmap">{ "imports": {
  "three": "https://cdn.jsdelivr.net/npm/three@0.169/build/three.module.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.169/examples/jsm/",
  "gsap": "https://cdn.jsdelivr.net/npm/gsap@3.12/index.js",
  "simplex-noise": "https://cdn.jsdelivr.net/npm/simplex-noise@4/dist/esm/simplex-noise.js"
}}</script>
```
- **Three.js** — color field shader + particle cloud. **GSAP (+ScrollTrigger)** — chuyển cảnh/choreography. **simplex-noise** — displacement hữu cơ. **Meyda** (tùy chọn) — de-risk phần tính RMS/centroid. Shader helper: **Lygia** (`lygia.xyz`, include GLSL).
- Tách code mới thành module riêng (`static/js/immersive/`), **không đụng** `player.js`/`api.js` core ⇒ bám Rule 3 (surgical) của CLAUDE.md.

### 3.2 Module mới (nhiều file nhỏ — bám coding-style)
```
static/js/immersive/
  va-engine.js        # nguồn chân lý (V,A) runtime; emit 'va-change'; color↔VA math (CIELAB)
  color-field.js      # Three.js: gradient-mesh blob (vertex simplex displace + fragment gradient)
  particle-cloud.js   # InstancedMesh hạt phản ứng audio band
  audio-features.js   # tap _analyser sẵn có → RMS(arousal) + spectral centroid(valence), EMA smooth
  emotion-arc.js      # vẽ đường cảm xúc (canvas/ribbon), Phase1 live + Phase2 MERT nền
  color-space.js      # picker immersive: raycast mặt phẳng V×A → chọn màu
  quality.js          # đo FPS, cap DPR, reduced-motion, WebGL detect → fallback CSS
static/css/immersive.css
```
`va-engine.js` là **trung tâm**: mọi thứ (field, particle, arc, chrome màu) subscribe vào một state `(V,A)` duy nhất ⇒ đồng bộ tuyệt đối.

### 3.3 Tích hợp đường cảm xúc (đã verify với code thật)
- **Phase 1 — live (Web Audio, 0 backend):** tap **chính `player._analyser`** (đã tồn tại, fftSize cần nâng lên 1024 hoặc thêm 1 analyser tap riêng off gain-chain để có độ phân giải centroid; KHÔNG đổi đồ thị bars cũ).
  - `getFloatTimeDomainData` → `RMS = √(Σx²/N)` → **arousal (trục Y)**.
  - `getByteFrequencyData` → spectral centroid `C = Σ(k·|X|)/Σ|X|` → **brightness ≈ valence (màu nét)**.
  - EMA smooth (`v = 0.9v + 0.1·new`) ⇒ đường cong mượt, không jitter.
- **Phase 2 — arc thật (MERT segment, backend):** giữ `chunk_embs` per-chunk (đã có trong `MERTEncoder.extract`) thay vì mean-pool → chạy **arousal probe có sẵn** mỗi chunk → `arousal[t]`. Valence **giữ mức bài** (cross-corpus valence transfer fail — đã ghi trong probe docstring & memory). ⇒ **arousal arc = thật theo thời gian; valence tô màu arc.** Lưu `data/segment_arousal_v1.json`. Đường live (Phase 1) chạy *trên* đường nền "thật" này.

---

## 4. Information Architecture mới (color-first)

Bỏ sidebar-as-primary. Cấu trúc 3 "thế giới", chuyển cảnh bằng GSAP, KHÔNG reload:

```
┌─────────────────────────────────────────────────────────┐
│  ❶ COLORSCAPE (Home)   ❷ NOW PLAYING   ❸ LIBRARY/Classic │
└─────────────────────────────────────────────────────────┘
```
- Nav tối giản nổi (floating, không phải sidebar 240px). Search vẫn truy cập nhanh (overlay).
- **Classic list view vẫn còn** nhưng là *thứ cấp* (cho lúc cần thao tác nhanh / accessibility / low-end) — không phải mặc định. Đáp ứng "bỏ chuẩn Spotify" mà vẫn không bỏ rơi tác vụ cơ bản.

### ❶ COLORSCAPE — trang chính (thay hero+carousel cũ)
Toàn màn hình là **không gian màu cảm xúc 3D** (color-field shader trôi nhẹ theo `prefers-reduced-motion`).
- **Chọn màu dễ — 2 tầng (progressive disclosure):**
  - *Tầng 1 (mặc định, dễ):* 12 thẻ màu cảm xúc hiện tại **nổi trong không gian 3D như những "viên cảm xúc"** phát sáng. Tap = chọn + chạy ngay (giữ nguyên hành vi `pickColor` cũ). Mỗi viên có **tên màu + nhãn cảm xúc** (a11y: không chỉ dựa màu).
  - *Tầng 2 (nâng cao, mở khi muốn):* **Color Space** — mặt phẳng V×A tương tác (raycast), kéo con trỏ trong vùng "Vui ↔ Buồn" × "Tĩnh ↔ Bùng nổ", màu hiện theo `(V,A)`. Vẫn neo bằng nhãn 4 góc cảm xúc để không lạc.
- Chọn 1 màu → mood tĩnh; **chọn 2 màu → "hành trình tâm trạng" A→B** hiển thị thành **một con đường màu chảy literal trong không gian** (gradient từ màu A sang B), playlist xếp theo Iso-Principle (đã có ở backend).
- Khi có kết quả: không gian màu *đông lại* thành màu (V,A) trung bình của playlist; danh sách bài trượt lên dạng cards tối giản trên nền.

### ❷ NOW PLAYING — "chìm đắm" cao nhất
- Toàn màn: color-field + particle cloud **phản ứng audio realtime** (bass→scale, treble→shimmer), màu = (V,A) bài hiện tại nội suy live theo centroid.
- **Đường cảm xúc (Emotion Arc)** nổi bật giữa/dưới: X = thời gian bài, Y = arousal, **màu nét = valence**. Đầu phát chạy dọc theo arc → người nghe *thấy* "cảm xúc đang lên/xuống". Phase 2: arc nền MERT thật + live overlay.
- Nhãn "câu chuyện": gắn 1 trong 6 cung cảm xúc kinh điển (rise / fall / rise-fall / fall-rise / rise-fall-rise / fall-rise-fall — UVM Story Lab) cho bài & cho playlist.
- Player controls ẩn mờ, hiện khi rê chuột (immersive, không vướng mắt).

### ❸ LIBRARY / Classic
- Yêu thích, Gần đây, Queue — list quen thuộc, nhanh, accessible. Player bar cổ điển vẫn sống ở đây.

---

## 5. Đặc tả Emotion Arc (chi tiết)

```
Y = arousal (0..1)         ╭──╮        ← màu nét = valence (lạnh→ấm)
                       ╭───╯  ╰─╮      ● = đầu phát hiện tại
        ╭──────╮   ╭──╯        ╰────
   ╭────╯      ╰───╯
   └──────────────────────────────▶ X = thời gian (0 … duration)
```
- **Render:** polyline canvas với per-segment gradient (Phase 1, rẻ) → nâng cấp **TubeGeometry ribbon 3D** vertex-color theo valence (Phase 3, đẹp).
- **Dữ liệu:**
  - Phase 1: Y = RMS live (EMA). Màu = centroid live → hue. Chỉ "vẽ tới" theo thời gian thực (như nhồi ức đang hình thành).
  - Phase 2: Y nền = `arousal[t]` MERT (vẽ toàn bộ trước, mờ); live RMS overlay đậm chạy trên nền. Lệch nền↔live = "biến tấu" thực tế bài.
- **Playlist macro-arc:** mỗi bài 1 sparkline nhỏ nối nhau → thấy hành trình cả set; với 2-màu journey, arc tổng phải đi từ vùng (V,A) của A → B.

---

## 6. Accessibility, Performance & Degradation (ràng buộc cứng "không lỗi")

### 6.1 Chọn màu accessible (WCAG 2.2)
- **SC 1.4.1 (Use of Color):** mọi viên màu có **tên + nhãn cảm xúc text**; selected-state = **viền/checkmark + `aria-pressed`** (đã có ở code cũ — giữ), KHÔNG chỉ glow.
- **SC 1.4.11:** viền swatch & vòng focus ≥ **3:1** so với nền.
- **SC 2.4.11/2.4.13 (2.2):** focus rõ, không bị che — grid màu phải duyệt được bằng bàn phím (Tab/Arrow).
- Color Space (tầng 2) **luôn có** lối tắt = 12 thẻ tầng 1 (không bắt buộc dùng manifold). CVD: cặp **xanh↔cam** an toàn cho mọi loại mù màu; cân nhắc preview CVD.

### 6.2 Performance (Three.js)
- `setPixelRatio(min(devicePixelRatio, 2))`; mobile cap 1.5.
- **InstancedMesh** cho particle (1 draw call); mobile < 50 draw calls; tắt shadow map (bake).
- Reuse `Uint8Array/Float32Array` (cấp phát 1 lần ngoài loop).
- Pause RAF khi tab/canvas ẩn (`visibilitychange`, IntersectionObserver).
- **Adaptive quality:** đo FPS ~1s đầu; thấp → giảm particle count / noise octaves / DPR.

### 6.3 Graceful degradation (no-bug priority)
- `prefers-reduced-motion: reduce` → tắt loop shader, dùng **gradient CSS tĩnh** (tính từ cùng (V,A)) + arc 2D đơn giản.
- WebGL không hỗ trợ → fallback CSS-gradient + giữ toàn bộ chức năng chọn màu/nghe (feature parity, chỉ kém lung linh).
- Mọi tính năng cốt lõi (chọn màu, phát nhạc, queue) **phải chạy được khi WebGL tắt** ⇒ immersive là *lớp tăng cường*, không phải điều kiện sống.

---

## 7. Lộ trình theo phase (eval-gated, bám văn hoá dự án)

| Phase | Nội dung | Deliverable | Tiêu chí thành công (đo được) |
|---|---|---|---|
| **P0 — Spike** | Dựng `va-engine.js` (color↔VA CIELAB) + color-field shader tối thiểu trên 1 trang test, CDN import map chạy | `static/js/immersive/*` skeleton + trang `/static/immersive-test.html` | Shader render 60fps desktop / ≥30fps mobile mid; reduced-motion fallback chạy; 0 lỗi console |
| **P1 — Live Arc** | `audio-features.js` tap analyser sẵn có → RMS+centroid; `emotion-arc.js` vẽ live | Now Playing có đường cảm xúc live | Arc phản ứng đúng (im lặng→thấp, drop→cao); không jitter; không đụng visualizer/crossfade cũ |
| **P2 — Colorscape Home** | Trang chính color-first: 12 viên cảm xúc trong không gian 3D + Color Space tầng 2; nối API color sẵn có | Home mới thay hero+carousel | Chọn màu ≤ 1 tap ra nhạc; a11y pass (keyboard+SC1.4.1); journey 2-màu hiển thị path |
| **P3 — Now Playing đắm** | particle cloud audio-reactive + arc ribbon 3D + chrome màu động theo bài | Màn Now Playing hoàn chỉnh | "Đường nghe = đường nhìn" (màu/chuyển động khớp VA bài); FPS đạt; controls auto-hide ổn |
| **P4 — MERT segment arc** | Backend: per-chunk arousal → `data/segment_arousal_v1.json`; arc nền thật | Job + dữ liệu 5138 bài | Arc nền khớp cảm nhận; live overlay chạy trên nền; backtest arousal-arc không vô lý |
| **P5 — Polish** | 6-arc labels, transitions GSAP, QA chéo thiết bị | Bản hoàn chỉnh | test 375/768/1024/1440; reduced-motion & no-WebGL parity |

**Mỗi phase tự đứng được & không phá core.** P1/P2/P3 thuần frontend (rủi ro thấp). P4 là dự án ML nhỏ, độc lập.

---

## 8. Skills sẽ dùng khi build (theo yêu cầu "tận dụng skill")
- **gsap-core / gsap-scrolltrigger / gsap-timeline** — choreography chuyển cảnh & arc.
- **ui-ux-pro-max** (đã chạy: Aurora/Gradient-Mesh + OLED dark) + **high-end-visual-design / frontend-design-direction** — taste & độ hoàn thiện.
- **motion-ui / motion-foundations** — cảm xúc→chuyển động.
- **frontend-a11y / accessibility** — gate WCAG cho color picker.
- **performance-optimizer** + **browser-qa / verify** — đo FPS, QA thiết bị.
- **code-reviewer** sau mỗi phase (bám code-review rule).

---

## 9. Rủi ro & giảm thiểu
| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| WebGL nặng → giật/máy yếu | Cao | Adaptive quality, DPR cap, instancing, reduced-motion + CSS fallback (§6) |
| Đụng audio graph crossfade khi tap analyser | Trung | Tap analyser sẵn có / thêm analyser-only node; KHÔNG sửa gain-chain; test crossfade sau P1 |
| Color Space khó dùng → mất "dễ chọn màu" | Trung | Tầng 1 (12 thẻ) luôn là default; Color Space là tuỳ chọn nâng cao |
| Valence segment không đáng tin | Trung | Phase 2 chỉ làm **arousal** arc theo thời gian; valence giữ mức bài (đã có nguồn fail) |
| Màu động làm text khó đọc | Trung | Lớp scrim tối dưới text; auto-check contrast 4.5:1 theo (V,A) runtime |
| Diacritics tiếng Việt vỡ ở font display | Thấp | Verify subset `vietnamese`; fallback Inter |

---

## 10. Nguồn (research session 2026-06-11)
- Palmer & Schloss, *Music–color associations mediated by emotion*, PNAS 2013 — https://www.pnas.org/doi/10.1073/pnas.1212562110
- Valdez & Mehrabian, *Effects of color on emotions*, JEP:General 1994 — https://pubmed.ncbi.nlm.nih.gov/7996122/
- Russell, circumplex / VA space — https://www.emergentmind.com/topics/valence-arousal-space
- VN color symbolism — https://sungetawaystravel.com/vietnamese-color-symbolism/ · https://vinwonders.com/en/wonderpedia/news/colors-in-vietnamese-insights-into-different-expressions/
- WCAG 1.4.1 Use of Color — https://www.accessibilitychecker.org/wcag-guides/ensure-links-are-distinguished-from-surrounding-text-in-a-way-that-does-not-rely-on-color/
- Designing for color blindness — https://colorblind.io/guides/designing-for-color-blindness
- Laban movement → affect (arXiv 2025) — https://arxiv.org/html/2505.11716v2
- Codrops 3D Audio Visualizer (Three.js+GSAP+Web Audio) — https://tympanus.net/codrops/2025/06/18/coding-a-3d-audio-visualizer-with-three-js-gsap-web-audio-api/
- Codrops Audio-Reactive Shaders / Particles — https://tympanus.net/codrops/2023/02/07/audio-reactive-shaders-with-three-js-and-shader-park/ · https://tympanus.net/codrops/2023/12/19/creating-audio-reactive-visuals-with-dynamic-particles-in-three-js/
- MDN Web Audio Visualizations / AnalyserNode — https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API/Visualizations_with_Web_Audio_API
- Spectral centroid — https://en.wikipedia.org/wiki/Spectral_centroid · Meyda — https://meyda.js.org/audio-features.html
- UVM Story Lab — 6 emotional arcs — https://www.technologyreview.com/2016/07/06/158961/data-mining-reveals-the-six-basic-emotional-arcs-of-storytelling/
- Three.js performance — https://www.utsubo.com/blog/threejs-best-practices-100-tips · https://tympanus.net/codrops/2025/02/11/building-efficient-three-js-scenes-optimize-performance-while-maintaining-quality/
