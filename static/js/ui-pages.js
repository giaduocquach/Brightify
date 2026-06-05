// ══════════════════════════════════════════════════════════════════════════
// Pages
// ══════════════════════════════════════════════════════════════════════════
const pages = {
    // ── HOME ────────────────────────────────────────────────────────────
    async home(container) {
        const stats = _getListeningStats();
        const followed = JSON.parse(localStorage.getItem('bf_followed_artists') || '[]');

        container.innerHTML = `
            <div class="hero-banner">
                <div class="hero-content">
                    <div class="hero-greeting">${getGreeting()}</div>
                    <div class="hero-title">Khám phá âm nhạc<br>với trí tuệ nhân tạo</div>
                    <div class="hero-subtitle">Brightify dùng AI để tìm nhạc phù hợp với cảm xúc của bạn — qua màu sắc hoặc hình ảnh.</div>
                    <div class="hero-actions">
                        <button class="btn btn-primary" onclick="router.navigate('ai-lab')">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:18px;height:18px"><path d="M12 2a5 5 0 015 5c0 2-1 3-2 4l-1 1v2h-4v-2l-1-1c-1-1-2-2-2-4a5 5 0 015-5z"/></svg>
                            Thử AI Lab
                        </button>
                    </div>
                </div>
            </div>

            <!-- Listening Stats -->
            <div class="stats-dashboard">
                <div class="stats-card">
                    <div class="stats-icon">🎧</div>
                    <div class="stats-value">${stats.totalPlays}</div>
                    <div class="stats-label">Bài đã nghe</div>
                </div>
                <div class="stats-card">
                    <div class="stats-icon">🎤</div>
                    <div class="stats-value">${stats.uniqueArtists}</div>
                    <div class="stats-label">Nghệ sĩ</div>
                </div>
                <div class="stats-card">
                    <div class="stats-icon">❤️</div>
                    <div class="stats-value">${stats.likedCount}</div>
                    <div class="stats-label">Yêu thích</div>
                </div>
                <div class="stats-card">
                    <div class="stats-icon">📡</div>
                    <div class="stats-value">${followed.length}</div>
                    <div class="stats-label">Theo dõi</div>
                </div>
            </div>

            ${stats.topArtists.length > 0 ? `
            <div class="section-header" style="margin-top:28px">
                <div class="section-title">🏆 Nghệ sĩ nghe nhiều nhất</div>
            </div>
            <div class="top-artists-bar">
                ${stats.topArtists.slice(0, 5).map((a, i) => `
                    <div class="top-artist-chip" onclick="router.navigate('artist/${encodeURIComponent(a.name)}')">
                        <span class="top-artist-rank">#${i + 1}</span>
                        <span class="top-artist-name">${esc(a.name)}</span>
                        <span class="top-artist-plays">${a.count} lần</span>
                    </div>
                `).join('')}
            </div>` : ''}

            <div class="carousel-container">
                <div class="section-header">
                    <div><div class="section-title">Nổi bật</div><div class="section-subtitle">Những bài hát được yêu thích</div></div>

                </div>
                <div class="carousel" id="home-featured"></div>
            </div>

            <div class="carousel-container">
                <div class="section-header">
                    <div><div class="section-title">Gợi ý cho bạn</div><div class="section-subtitle">Chọn ngẫu nhiên từ thư viện</div></div>
                </div>
                <div class="carousel" id="home-random"></div>
            </div>

            <div class="carousel-container">
                <div class="section-header">
                    <div><div class="section-title">Nghệ sĩ phổ biến</div></div>
                    <a href="#/artists" class="section-link">Xem tất cả →</a>
                </div>
                <div class="carousel" id="home-artists" style="gap:14px"></div>
            </div>

            ${followed.length > 0 ? `
            <div class="section-header" style="margin-top:28px">
                <div class="section-title">Nghệ sĩ đang theo dõi</div>
                <span class="section-badge">${followed.length}</span>
            </div>
            <div id="home-followed" class="followed-artists-grid"></div>
            ` : ''}
        `;

        const [featured, random, artists] = await Promise.all([
            API.getFeatured(14).catch(() => ({ songs: [] })),
            API.getRandomSongs(14).catch(() => ({ songs: [] })),
            API.getArtists(20).catch(() => ({ artists: [] })),
        ]);

        // Featured
        const featEl = document.getElementById('home-featured');
        if (featEl) featEl.innerHTML = featured.songs.map(s => songCardHTML(s)).join('');

        // Random
        const randEl = document.getElementById('home-random');
        if (randEl) randEl.innerHTML = random.songs.map(s => songCardHTML(s)).join('');

        // Artists
        const artEl = document.getElementById('home-artists');
        if (artEl) {
            artEl.innerHTML = artists.artists.slice(0, 14).map(a => `
                <div class="artist-card" style="flex-shrink:0;width:140px" onclick="router.navigate('artist/${encodeURIComponent(a.name)}')">
                    <div class="artist-avatar">
                        ${a.has_artist_image ? `<img src="${safeUrl(a.artist_image_url)}" alt="">` : a.has_art ? `<img src="${safeUrl(a.art_url)}" alt="">` : '🎤'}
                    </div>
                    <div class="artist-name">${esc(a.name)}</div>
                    <div class="artist-count">${a.song_count} bài</div>
                </div>
            `).join('');
        }

        // Followed artists
        if (followed.length > 0) {
            const followedEl = document.getElementById('home-followed');
            if (followedEl) {
                // Build lookup from already-loaded artists data
                const artistLookup = {};
                (artists.artists || []).forEach(a => {
                    artistLookup[a.name.toLowerCase()] = a;
                });
                // Fetch full list if some followed artists not in top 20
                const missing = followed.filter(n => !artistLookup[n.toLowerCase()]);
                if (missing.length > 0) {
                    try {
                        const all = await API.getArtists(300);
                        (all.artists || []).forEach(a => {
                            artistLookup[a.name.toLowerCase()] = a;
                        });
                    } catch(e) {}
                }

                const artistCards = followed.map(artistName => {
                    const a = artistLookup[artistName.toLowerCase()];
                    const imgHtml = a?.has_artist_image ? `<img src="${safeUrl(a.artist_image_url)}" alt="">` :
                                    a?.has_art ? `<img src="${safeUrl(a.art_url)}" alt="">` : '🎤';
                    const songCount = a?.song_count || 0;
                    return `
                        <div class="followed-artist-card" onclick="router.navigate('artist/${encodeURIComponent(artistName)}')">
                            <div class="followed-artist-avatar">
                                ${imgHtml}
                            </div>
                            <div class="followed-artist-info">
                                <div class="followed-artist-name">${esc(artistName)}</div>
                                <div class="followed-artist-meta">${songCount} bài hát</div>
                            </div>
                            <div class="followed-artist-actions">
                                <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation(); playArtist('${encodeURIComponent(artistName)}')" title="Phát">▶</button>
                            </div>
                        </div>
                    `;
                });
                followedEl.innerHTML = artistCards.join('');
            }
        }

        this._checkAudio(featured.songs);
    },

    // ── ALL ARTISTS ──────────────────────────────────────────────────────
    async allArtists(container) {
        container.innerHTML = '<div class="loading-screen"><div class="loader"></div>Đang tải...</div>';
        const data = await API.getArtists(9999).catch(() => ({ artists: [] }));
        container.innerHTML = `
            <div class="page-title">Tất cả nghệ sĩ</div>
            <div class="page-subtitle">${data.artists.length} nghệ sĩ</div>
            <div class="artists-full-grid">
                ${data.artists.map(a => `
                    <div class="artist-card" onclick="router.navigate('artist/${encodeURIComponent(a.name)}')">
                        <div class="artist-avatar">
                            ${a.has_artist_image ? `<img src="${safeUrl(a.artist_image_url)}" alt="">` : a.has_art ? `<img src="${safeUrl(a.art_url)}" alt="">` : '🎤'}
                        </div>
                        <div class="artist-name">${esc(a.name)}</div>
                        <div class="artist-count">${a.song_count} bài</div>
                    </div>
                `).join('')}
            </div>
        `;
    },

    // ── AI LAB ──────────────────────────────────────────────────────────
    async aiLab(container) {
        container.innerHTML = `
            <div class="ai-lab-hero">
                <div class="page-title">AI Lab ✨</div>
                <div class="page-subtitle">Khám phá nhạc qua màu sắc hoặc hình ảnh — AI sẽ tìm bài hát phù hợp cho bạn</div>
            </div>

            <!-- V23: "Hành trình" tab merged into colour (2 colours = mood journey A→B,
                 Iso-Principle). Separate journey tab removed — single mood entry point
                 (progressive disclosure: 1 colour = static mood, 2 = journey). -->

            <!-- Color Tab -->
            <div class="ai-panel" id="tab-color">
                <div class="color-picker-v2">
                    <div class="color-picker-header">
                        <div class="color-wheel-title">🎨 Soundtrack cho khoảnh khắc</div>
                        <div class="color-wheel-subtitle">Chọn màu bạn đang cảm thấy — hoặc thả một tấm ảnh — AI bắt "vibe" rồi tìm nhạc phù hợp</div>
                    </div>

                    <!-- Emotion Color Grid V17 — 12 màu ICEAS, hex = CENTROID TRI GIÁC
                         (ISCC-NBS vivid/strong, Kelly&Judd 1955) thay primary thuần — primary
                         (#FF0000…) ghim saturation 100% làm vống arousal & lệch valence (audit
                         V17). data-va + nhãn sinh từ hsl_to_va/color_to_emotion_probs
                         (vietnamese=False). Hiển thị == hex được tính. -->
                    <div class="color-emotion-grid color-emotion-grid-v2">
                        <button class="color-emotion-card-v2" onclick="pickColor('#BE0032')" data-color="#BE0032" data-va="0.56,0.89" aria-pressed="false" aria-label="Đỏ — Đam mê, Mãnh liệt">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:#BE0032"></span>
                                <span class="cev2-check" aria-hidden="true">✓</span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Đỏ</span>
                                <span class="cev2-emotions">Đam mê · Mãnh liệt</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="pickColor('#F38400')" data-color="#F38400" data-va="0.62,0.84" aria-pressed="false" aria-label="Cam — Vui tươi, Năng động">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:#F38400"></span>
                                <span class="cev2-check" aria-hidden="true">✓</span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Cam</span>
                                <span class="cev2-emotions">Vui tươi · Năng động</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="pickColor('#F3C300')" data-color="#F3C300" data-va="0.63,0.81" aria-pressed="false" aria-label="Vàng — Vui vẻ, Lạc quan">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:#F3C300"></span>
                                <span class="cev2-check" aria-hidden="true">✓</span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Vàng</span>
                                <span class="cev2-emotions">Vui vẻ · Lạc quan</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="pickColor('#FFB7C5')" data-color="#FFB7C5" data-va="0.76,0.76" aria-pressed="false" aria-label="Hồng — Ngọt ngào, Phấn khích">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:#FFB7C5"></span>
                                <span class="cev2-check" aria-hidden="true">✓</span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Hồng</span>
                                <span class="cev2-emotions">Ngọt ngào · Phấn khích</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="pickColor('#008856')" data-color="#008856" data-va="0.70,0.57" aria-pressed="false" aria-label="Xanh lá — Tươi mát, Cân bằng">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:#008856"></span>
                                <span class="cev2-check" aria-hidden="true">✓</span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Xanh lá</span>
                                <span class="cev2-emotions">Tươi mát · Cân bằng</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="pickColor('#3AB09E')" data-color="#3AB09E" data-va="0.51,0.33" aria-pressed="false" aria-label="Ngọc — Thư thái, Tươi mát">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:#3AB09E"></span>
                                <span class="cev2-check" aria-hidden="true">✓</span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Ngọc</span>
                                <span class="cev2-emotions">Thư thái · Tươi mát</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="pickColor('#0067A5')" data-color="#0067A5" data-va="0.72,0.56" aria-pressed="false" aria-label="Xanh dương — Phấn chấn, Sâu lắng">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:#0067A5"></span>
                                <span class="cev2-check" aria-hidden="true">✓</span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Xanh dương</span>
                                <span class="cev2-emotions">Phấn chấn · Sâu lắng</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="pickColor('#9C4F96')" data-color="#9C4F96" data-va="0.27,0.55" aria-pressed="false" aria-label="Tím — Trầm tư, Mãnh liệt">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:#9C4F96"></span>
                                <span class="cev2-check" aria-hidden="true">✓</span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Tím</span>
                                <span class="cev2-emotions">Trầm tư · Mãnh liệt</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="pickColor('#F2F3F4')" data-color="#F2F3F4" data-va="0.59,0.17" aria-pressed="false" aria-label="Trắng — Thanh thản, Tinh khôi">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:#F2F3F4;border:1px solid rgba(255,255,255,0.25)"></span>
                                <span class="cev2-check" aria-hidden="true">✓</span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Trắng</span>
                                <span class="cev2-emotions">Thanh thản · Tinh khôi</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="pickColor('#848482')" data-color="#848482" data-va="0.41,0.32" aria-pressed="false" aria-label="Xám — U hoài, Trầm lắng">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:#848482"></span>
                                <span class="cev2-check" aria-hidden="true">✓</span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Xám</span>
                                <span class="cev2-emotions">U hoài · Trầm lắng</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="pickColor('#80461B')" data-color="#80461B" data-va="0.35,0.77" aria-pressed="false" aria-label="Nâu — Trầm mặc, Bất an">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:#80461B"></span>
                                <span class="cev2-check" aria-hidden="true">✓</span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Nâu</span>
                                <span class="cev2-emotions">Trầm mặc · Bất an</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="pickColor('#222222')" data-color="#222222" data-va="0.25,0.45" aria-pressed="false" aria-label="Đen — U tối, Nặng nề">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:#222222;border:1px solid rgba(255,255,255,0.15)"></span>
                                <span class="cev2-check" aria-hidden="true">✓</span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Đen</span>
                                <span class="cev2-emotions">U tối · Nặng nề</span>
                            </div>
                        </button>
                    </div>

                    <!-- Selected Colors -->
                    <div class="color-selected-section">
                        <div class="color-selected-header">
                            <span class="color-selected-label">Màu đã chọn</span>
                            <span class="color-selected-count" id="color-selected-count">0/2</span>
                            <button class="btn-clear-colors" id="btn-clear-colors" onclick="clearSelectedColors()" style="display:none">Xóa hết</button>
                        </div>
                        <div class="color-selected-dots" id="color-selected-dots">
                            <div class="color-add-hint">Nhấp vào màu bên trên để chọn</div>
                        </div>
                    </div>

                    <!-- Palette Presets -->
                    <div class="color-palettes-section">
                        <div class="color-palettes-label">Bảng màu gợi ý</div>
                        <div class="color-palettes" id="color-palettes"></div>
                    </div>

                    <div class="color-action-bar">
                        <div class="color-count-control">
                            <label>Số bài:</label>
                            <div class="color-count-stepper">
                                <button onclick="adjColorCount(-1)">−</button>
                                <span id="color-count-val">10</span>
                                <button onclick="adjColorCount(1)">+</button>
                            </div>
                            <input type="range" id="color-count" min="5" max="25" value="10" class="color-count-slider" oninput="document.getElementById('color-count-val').textContent=this.value">
                        </div>
                        <!-- E8 — "dig deeper"/novelty dial: quen thuộc ↔ khám phá -->
                        <div class="color-novelty-control">
                            <label for="color-novelty">Khám phá: <span id="color-novelty-val">Cân bằng</span></label>
                            <input type="range" id="color-novelty" min="0" max="100" value="50" step="5" class="color-count-slider"
                                   aria-label="Mức khám phá: thấp là bài quen thuộc, cao là bài ít nghe"
                                   oninput="onNoveltyChange(this.value)" onchange="rerunActiveColorQuery()">
                            <div class="color-novelty-ends"><span>Quen thuộc</span><span>Ít nghe</span></div>
                        </div>
                        <button class="btn btn-primary btn-glow" onclick="getColorRecommendations()">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:18px;height:18px"><path d="M12 2a5 5 0 015 5c0 2-1 3-2 4l-1 1v2h-4v-2l-1-1c-1-1-2-2-2-4a5 5 0 015-5z"/><line x1="9" y1="18" x2="15" y2="18"/><line x1="10" y1="22" x2="14" y2="22"/></svg>
                            Tìm nhạc ✨
                        </button>
                    </div>
                </div>
                <div class="ai-results" id="color-results"></div>

                <!-- F5 — same "capture a vibe" screen: an image is just another way
                     to express a mood. Drop one instead of (or after) picking colors. -->
                <div style="display:flex;align-items:center;gap:12px;margin:22px 0 14px;color:var(--text-secondary);font-size:.82rem">
                    <span style="flex:1;height:1px;background:var(--border)"></span>
                    hoặc bắt vibe từ một tấm ảnh 📷
                    <span style="flex:1;height:1px;background:var(--border)"></span>
                </div>
                <div class="image-dropzone" id="image-dropzone">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
                    <div class="image-dropzone-text">Kéo thả hình ảnh vào đây</div>
                    <div class="image-dropzone-hint">hoặc click để chọn file (JPEG, PNG, WebP)</div>
                    <input type="file" id="image-input" accept="image/*" style="display:none">
                </div>
                <div id="image-preview-area"></div>
                <div class="ai-results" id="image-results"></div>
            </div>



        `;


        initImageUpload();
        // V23: initJourneyPickers() removed — journey tab merged into colour.
    },

    // ── LIKED ────────────────────────────────────────────────────────────
    liked(container) {
        const liked = JSON.parse(localStorage.getItem('bf_liked') || '[]');
        container.innerHTML = `
            <div class="liked-header">
                <div class="page-title">❤️ Yêu thích</div>
                <div class="page-subtitle">${liked.length} bài hát</div>
            </div>
            <div style="margin-bottom:16px;display:flex;gap:8px">
                ${liked.length > 0 ? '<button class="btn btn-primary btn-sm" onclick="playLiked()"><svg viewBox="0 0 24 24" fill="currentColor" style="width:14px;height:14px"><polygon points="5 3 19 12 5 21 5 3"/></svg> Phát tất cả</button><button class="btn btn-secondary btn-sm" onclick="shuffleLiked()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><path d="M16 3h5v5"/><path d="M4 20L21 3"/><path d="M21 16v5h-5"/><path d="M15 15l6 6"/><path d="M4 4l5 5"/></svg> Trộn phát</button>' : ''}
            </div>
            <div class="song-list">
                ${liked.length === 0
                    ? '<div class="empty-state"><div class="empty-state-icon">💕</div><div class="empty-state-title">Chưa có bài hát yêu thích</div><div class="empty-state-text">Nhấn vào icon trái tim khi nghe nhạc để thêm vào đây</div></div>'
                    : liked.map((s, i) => songRowHTML(s, i + 1)).join('')}
            </div>
        `;
    },

    // ── HISTORY ──────────────────────────────────────────────────────────
    history(container) {
        const history = JSON.parse(localStorage.getItem('bf_history') || '[]');
        container.innerHTML = `
            <div class="page-title">Nghe gần đây</div>
            <div class="page-subtitle">${history.length} bài hát</div>
            <div style="margin-bottom:16px">
                ${history.length > 0
                    ? '<button class="btn btn-ghost btn-sm" onclick="clearHistory()">Xóa lịch sử</button>'
                    : ''}
            </div>
            <div class="song-list" id="history-songs">
                ${history.length === 0
                    ? '<div class="empty-state"><div class="empty-state-icon">🕐</div><div class="empty-state-title">Chưa nghe bài nào</div><div class="empty-state-text">Bắt đầu nghe nhạc để thấy lịch sử ở đây</div></div>'
                    : history.map((s, i) => songRowHTML(s, i + 1)).join('')}
            </div>
        `;
    },

    // ── ARTIST ──────────────────────────────────────────────────────────
    async artist(container, hash) {
        const name = decodeURIComponent(hash.replace('artist/', ''));
        container.innerHTML = '<div class="loading-screen"><div class="loader"></div></div>';
        try {
            const data = await API.getArtistSongs(name);
            const isFollowing = _isFollowingArtist(name);
            container.innerHTML = `
                <div style="display:flex;align-items:center;gap:20px;margin-bottom:28px">
                    <div class="artist-avatar" style="width:120px;height:120px;font-size:3rem">
                        ${data.songs[0]?.has_artist_image ? `<img src="${safeUrl(data.songs[0].artist_image_url)}" alt="">` : data.songs[0]?.has_album_art ? `<img src="${safeUrl(data.songs[0].album_art_url)}" alt="">` : '🎤'}
                    </div>
                    <div>
                        <div style="font-size:0.8rem;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:0.06em">Nghệ sĩ</div>
                        <div class="page-title">${esc(name)}</div>
                        <div class="page-subtitle">${data.total} bài hát</div>
                        <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">
                            <button class="btn btn-primary btn-sm" onclick="playArtist('${encodeURIComponent(name)}')"><svg viewBox="0 0 24 24" fill="currentColor" style="width:14px;height:14px"><polygon points="5 3 19 12 5 21 5 3"/></svg> Phát tất cả</button>
                            <button class="btn btn-secondary btn-sm" onclick="shuffleArtist('${encodeURIComponent(name)}')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><path d="M16 3h5v5"/><path d="M4 20L21 3"/><path d="M21 16v5h-5"/><path d="M15 15l6 6"/><path d="M4 4l5 5"/></svg> Trộn phát</button>
                            <button class="btn ${isFollowing ? 'btn-following' : 'btn-follow'} btn-sm" id="btn-follow-artist"
                                onclick="toggleFollowArtist('${name.replace(/'/g, "\\'")}')">
                                ${isFollowing
                                    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px"><polyline points="20 6 9 17 4 12"/></svg> Đang theo dõi'
                                    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4-4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg> Theo dõi'}
                            </button>
                        </div>
                    </div>
                </div>
                <div class="song-list">
                    ${data.songs.map((s, i) => songRowHTML(s, i + 1)).join('')}
                </div>
            `;
        } catch (e) {
            container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">😕</div>Không tìm thấy nghệ sĩ</div>';
        }
    },

    // ── SEARCH (F3 — unified full results: khớp-nhất + liên-quan, play-all) ──
    async search(container, hash) {
        const query = decodeURIComponent(hash.replace('search/', '')).trim();
        container.innerHTML = '<div class="loading-screen"><div class="loader"></div></div>';
        if (!query) { container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🔍</div>Nhập từ khoá để tìm</div>'; return; }
        try {
            const data = await API.searchUnified(query, 20, 20);
            const matches = (data.matches || []).map(s => _normalizeSong(s));
            const related = (data.related || []).map(s => _normalizeSong(s));
            await _checkAudioBatch([...matches, ...related]);
            window._searchMatches = matches;
            window._searchRelated = related;

            const section = (title, sub, songs, which) => songs.length ? `
                <div class="section-header" style="margin-top:18px">
                    <div><div class="section-title">${title}</div><div class="section-subtitle">${sub}</div></div>
                    <button class="btn btn-primary btn-sm" onclick="playSearchResults('${which}')"><svg viewBox="0 0 24 24" fill="currentColor" style="width:14px;height:14px"><polygon points="5 3 19 12 5 21 5 3"/></svg> Phát tất cả</button>
                </div>
                <div class="song-list">${songs.map((s, i) => songRowHTML(s, i + 1)).join('')}</div>` : '';

            container.innerHTML = `
                <div class="page-header">
                    <div class="page-title">Kết quả: "${esc(query)}"</div>
                    <div class="page-subtitle">${matches.length + related.length} bài · khớp nhất trước, liên quan ở dưới</div>
                </div>
                ${(!matches.length && !related.length) ? '<div class="empty-state"><div class="empty-state-icon">🔍</div>Không tìm thấy bài nào</div>' : ''}
                ${section('🎯 Khớp nhất', 'Trùng tên, nghệ sĩ hoặc lời bài hát', matches, 'matches')}
                ${section('🔗 Liên quan · cùng vibe', 'AI gợi ý theo cảm xúc/chủ đề', related, 'related')}
            `;
        } catch (e) {
            container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">😕</div>Lỗi tìm kiếm</div>';
        }
    },

    // ── Helper ──────────────────────────────────────────────────────────
    async _checkAudio(songs) {
        if (!songs.length) return;
        const ids = songs.filter(s => s.track_id).map(s => s.track_id);
        if (!ids.length) return;
        try {
            const res = await API.getBatchAudioStatus(ids);
            songs.forEach(s => {
                if (res.status && s.track_id) {
                    s.has_audio = !!res.status[s.track_id];
                    if (s.has_audio) s.audio_url = `/api/audio/stream/${s.track_id}`;
                }
            });
        } catch (e) { /* Silent */ }
    },
};

