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

            <div class="carousel-container" id="time-songs-section">
                <div class="section-header">
                    <div><div class="section-title" id="time-songs-title">🌤️ Ngay bây giờ</div><div class="section-subtitle" id="time-songs-subtitle">Tự động theo thời điểm, lễ Việt & thời tiết</div></div>
                    <div style="display:flex;gap:6px">
                        <button class="btn btn-ghost btn-sm" id="btn-play-time-songs" style="display:none" onclick="playCurrentTimeSongs()"><svg viewBox="0 0 24 24" fill="currentColor" style="width:14px;height:14px"><polygon points="5 3 19 12 5 21 5 3"/></svg> Phát tất cả</button>
                        <button class="btn btn-ghost btn-sm" id="btn-shuffle-time-songs" style="display:none" onclick="shuffleCurrentTimeSongs()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><path d="M16 3h5v5"/><path d="M4 20L21 3"/><path d="M21 16v5h-5"/><path d="M15 15l6 6"/><path d="M4 4l5 5"/></svg> Trộn</button>
                    </div>
                </div>
                <div class="carousel" id="home-time-songs"></div>
            </div>

            <div class="carousel-container">
                <div class="section-header">
                    <div><div class="section-title">🎭 Đổi tâm trạng</div><div class="section-subtitle">Chọn nơi muốn đến — AI dẫn bạn tới đó qua từng bài, bắt đầu từ bài đang nghe (Iso Principle)</div></div>
                </div>
                <div class="journey-presets-grid">
                    <button class="journey-preset" onclick="openMoodPreview('lift')">🌅 Vực dậy</button>
                    <button class="journey-preset" onclick="openMoodPreview('calm')">🧘 Hạ lo âu</button>
                    <button class="journey-preset" onclick="openMoodPreview('sleep')">🌙 Ru ngủ</button>
                    <button class="journey-preset" onclick="openMoodPreview('focus')">🎯 Tập trung</button>
                </div>
            </div>

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

        // "Ngay bây giờ" context shelf — auto by time + VN holiday + live weather (F1)
        _loadContextShelf();

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

            <div class="ai-tabs" id="ai-tabs">
                <div class="ai-tab active" data-tab="color" onclick="switchAiTab('color')">🎨 Bắt vibe từ ảnh/màu</div>
                <div class="ai-tab" data-tab="lyrics" onclick="switchAiTab('lyrics')">✨ Tìm theo cảm xúc</div>
                <div class="ai-tab" data-tab="journey" onclick="switchAiTab('journey')">🎯 Hành trình</div>
            </div>

            <!-- Color Tab -->
            <div class="ai-panel" id="tab-color">
                <div class="color-picker-v2">
                    <div class="color-picker-header">
                        <div class="color-wheel-title">🎨 Soundtrack cho khoảnh khắc</div>
                        <div class="color-wheel-subtitle">Chọn màu bạn đang cảm thấy — hoặc thả một tấm ảnh — AI bắt "vibe" rồi tìm nhạc phù hợp</div>
                    </div>

                    <!-- Emotion Color Grid (Jonauskaite et al. 2020: 12 universal colors) -->
                    <div class="color-emotion-grid color-emotion-grid-v2">
                        <button class="color-emotion-card-v2" onclick="addSelectedColor('#ef4444')" data-color="#ef4444" data-va="0.65,0.85">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:linear-gradient(135deg,#ef4444,#b91c1c)"></span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Đỏ</span>
                                <span class="cev2-emotions">Đam mê · Tức giận · Tình yêu</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="addSelectedColor('#f97316')" data-color="#f97316" data-va="0.80,0.75">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:linear-gradient(135deg,#f97316,#c2410c)"></span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Cam</span>
                                <span class="cev2-emotions">Phấn khích · Vui tươi · Sáng tạo</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="addSelectedColor('#eab308')" data-color="#eab308" data-va="0.90,0.70">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:linear-gradient(135deg,#eab308,#a16207)"></span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Vàng</span>
                                <span class="cev2-emotions">Hạnh phúc · Lạc quan · Niềm vui</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="addSelectedColor('#22c55e')" data-color="#22c55e" data-va="0.65,0.35">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:linear-gradient(135deg,#22c55e,#15803d)"></span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Xanh lá</span>
                                <span class="cev2-emotions">Bình yên · Hy vọng · An lành</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="addSelectedColor('#06b6d4')" data-color="#06b6d4" data-va="0.55,0.25">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:linear-gradient(135deg,#06b6d4,#0e7490)"></span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Cyan</span>
                                <span class="cev2-emotions">Thư thái · Tĩnh lặng · Nhẹ nhàng</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="addSelectedColor('#3b82f6')" data-color="#3b82f6" data-va="0.25,0.25">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:linear-gradient(135deg,#3b82f6,#1d4ed8)"></span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Xanh dương</span>
                                <span class="cev2-emotions">Nỗi buồn · U sầu · Suy tư</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="addSelectedColor('#8b5cf6')" data-color="#8b5cf6" data-va="0.45,0.40">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:linear-gradient(135deg,#8b5cf6,#6d28d9)"></span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Tím</span>
                                <span class="cev2-emotions">Huyền bí · Lãng mạn · Ngưỡng mộ</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="addSelectedColor('#ec4899')" data-color="#ec4899" data-va="0.72,0.45">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:linear-gradient(135deg,#ec4899,#be185d)"></span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Hồng</span>
                                <span class="cev2-emotions">Dịu dàng · Yêu thương · Ngọt ngào</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="addSelectedColor('#a16207')" data-color="#a16207" data-va="0.40,0.30">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:linear-gradient(135deg,#a16207,#78350f)"></span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Nâu</span>
                                <span class="cev2-emotions">Hoài niệm · Vintage · Ấm áp</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="addSelectedColor('#6b7280')" data-color="#6b7280" data-va="0.30,0.20">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:linear-gradient(135deg,#6b7280,#374151)"></span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Xám</span>
                                <span class="cev2-emotions">Cô đơn · Trống rỗng · Trầm lắng</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="addSelectedColor('#f5f5f4')" data-color="#f5f5f4" data-va="0.60,0.15">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:linear-gradient(135deg,#f5f5f4,#d6d3d1);border:1px solid rgba(255,255,255,0.1)"></span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Trắng</span>
                                <span class="cev2-emotions">Thanh thoát · Thuần khiết · Nhẹ nhõm</span>
                            </div>
                        </button>
                        <button class="color-emotion-card-v2" onclick="addSelectedColor('#171717')" data-color="#171717" data-va="0.15,0.55">
                            <div class="cev2-swatch-wrap">
                                <span class="cev2-swatch" style="background:linear-gradient(135deg,#171717,#000000)"></span>
                            </div>
                            <div class="cev2-info">
                                <span class="cev2-name">Đen</span>
                                <span class="cev2-emotions">Sợ hãi · Bí ẩn · Quyền lực</span>
                            </div>
                        </button>
                    </div>

                    <!-- Inline custom color input (optional) -->
                    <div class="color-custom-inline">
                        <span class="color-custom-label">Hoặc nhập mã màu:</span>
                        <div class="color-custom-field">
                            <div class="color-hex-preview" id="hex-preview-swatch" style="background:#a78bfa"></div>
                            <span class="color-hex-hash">#</span>
                            <input type="text" id="color-hex-input" class="color-hex-input" placeholder="a78bfa" maxlength="6" spellcheck="false" autocomplete="off" onkeydown="if(event.key==='Enter')addColorFromHex()">
                            <button class="btn btn-sm btn-secondary" onclick="addColorFromHex()">Thêm</button>
                        </div>
                    </div>

                    <!-- Selected Colors -->
                    <div class="color-selected-section">
                        <div class="color-selected-header">
                            <span class="color-selected-label">Màu đã chọn</span>
                            <span class="color-selected-count" id="color-selected-count">0/5</span>
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

            <!-- Lyrics Tab -->
            <div class="ai-panel" id="tab-lyrics" style="display:none">
                <div class="lyrics-search-section">
                    <div class="lyrics-search-prompt">
                        <div class="lyrics-search-title">Mô tả cảm xúc bằng lời</div>
                        <div class="lyrics-search-subtitle">Hãy viết vài từ về tâm trạng, chủ đề hoặc cảm giác bạn muốn nghe — AI sẽ tìm bài hát phù hợp</div>
                    </div>
                    <div class="lyrics-search-input-wrap">
                        <textarea id="lyrics-search-input" class="lyrics-search-textarea" placeholder="Ví dụ: nhớ người yêu cũ, đêm mưa buồn, muốn quên đi mọi thứ..." rows="3"></textarea>
                        <div class="lyrics-search-suggestions">
                            <button class="lyrics-suggestion" onclick="setLyricQuery('tình yêu đầu tan vỡ, nước mắt')">💔 Thất tình</button>
                            <button class="lyrics-suggestion" onclick="setLyricQuery('đường phố đêm khuya, tự do, bay cao')">🌃 Đêm thành phố</button>
                            <button class="lyrics-suggestion" onclick="setLyricQuery('mẹ ơi, gia đình, quê hương, nhớ nhà')">🏠 Nhớ nhà</button>
                            <button class="lyrics-suggestion" onclick="setLyricQuery('cùng nhau, bên nhau mãi, hạnh phúc')">💍 Hạnh phúc</button>
                            <button class="lyrics-suggestion" onclick="setLyricQuery('tuổi trẻ, ước mơ, thanh xuân')">🌅 Tuổi trẻ</button>
                        </div>
                    </div>
                    <div class="lyrics-search-actions">
                        <label>Số bài: <span id="lyrics-count-val">10</span></label>
                        <input type="range" id="lyrics-count" min="5" max="20" value="10" oninput="document.getElementById('lyrics-count-val').textContent=this.value">
                        <button class="btn btn-primary btn-glow" onclick="getLyricsRecommendations()">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:18px;height:18px"><path d="M12 2a5 5 0 015 5c0 2-1 3-2 4l-1 1v2h-4v-2l-1-1c-1-1-2-2-2-4a5 5 0 015-5z"/></svg>
                            Tìm nhạc ✨
                        </button>
                    </div>
                </div>
                <div class="ai-results" id="lyrics-results"></div>
            </div>


            <!-- Emotion Journey Tab -->
            <div class="ai-panel journey-panel-wide" id="tab-journey" style="display:none">
                <div class="journey-section">
                    <div class="journey-header">
                        <div class="journey-title">Hành Trình Cảm Xúc</div>
                        <div class="journey-subtitle">Chọn nơi bạn muốn đến — AI dẫn từ bài đang nghe qua từng bước (Iso Principle). Xem trước trước khi bắt đầu.</div>
                    </div>

                    <!-- F2.1 — need-presets lead: 1 chạm → xem trước cung → bắt đầu -->
                    <div class="journey-presets" style="margin-bottom:6px">
                        <div class="journey-presets-grid">
                            <button class="journey-preset" onclick="openMoodPreview('lift')">🌅 Vực dậy</button>
                            <button class="journey-preset" onclick="openMoodPreview('calm')">🧘 Hạ lo âu</button>
                            <button class="journey-preset" onclick="openMoodPreview('sleep')">🌙 Ru ngủ</button>
                            <button class="journey-preset" onclick="openMoodPreview('focus')">🎯 Tập trung</button>
                        </div>
                    </div>

                    <details class="journey-advanced">
                        <summary style="cursor:pointer;color:var(--text-secondary);font-size:.85rem;padding:6px 0;user-select:none">⚙️ Tùy chỉnh nâng cao — tự chọn điểm đầu & đích trên biểu đồ cảm xúc</summary>

                    <!-- Quick Mood Cards — Russell's Circumplex × 13 system emotions -->
                    <div class="journey-quick-moods">
                        <div class="jqm-instruction">
                            <span class="jqm-step jqm-step-1">①</span> Chọn cảm xúc <strong>hiện tại</strong> &nbsp;→&nbsp;
                            <span class="jqm-step jqm-step-2">②</span> Chọn cảm xúc <strong>mong muốn</strong>
                        </div>
                        <div class="jqm-grid">
                            <!-- Q1: High Valence, High Arousal -->
                            <button class="jqm-card jqm-q1" data-v="0.95" data-a="0.90" onclick="setJourneyFromQuickMood(this)">
                                <span class="jqm-emoji">🤩</span><span class="jqm-name">Phấn khích</span>
                                <span class="jqm-quadrant">Ecstatic</span>
                            </button>
                            <button class="jqm-card jqm-q1" data-v="0.85" data-a="0.70" onclick="setJourneyFromQuickMood(this)">
                                <span class="jqm-emoji">😊</span><span class="jqm-name">Vui vẻ</span>
                                <span class="jqm-quadrant">Happy</span>
                            </button>
                            <button class="jqm-card jqm-q1" data-v="0.65" data-a="0.85" onclick="setJourneyFromQuickMood(this)">
                                <span class="jqm-emoji">🔥</span><span class="jqm-name">Đam mê</span>
                                <span class="jqm-quadrant">Passionate</span>
                            </button>
                            <button class="jqm-card jqm-q1" data-v="0.75" data-a="0.55" onclick="setJourneyFromQuickMood(this)">
                                <span class="jqm-emoji">🌟</span><span class="jqm-name">Hy vọng</span>
                                <span class="jqm-quadrant">Hopeful</span>
                            </button>
                            <!-- Q4: High Valence, Low Arousal -->
                            <button class="jqm-card jqm-q4" data-v="0.70" data-a="0.15" onclick="setJourneyFromQuickMood(this)">
                                <span class="jqm-emoji">🍃</span><span class="jqm-name">Bình yên</span>
                                <span class="jqm-quadrant">Peaceful</span>
                            </button>
                            <button class="jqm-card jqm-q4" data-v="0.60" data-a="0.20" onclick="setJourneyFromQuickMood(this)">
                                <span class="jqm-emoji">😌</span><span class="jqm-name">Thư thái</span>
                                <span class="jqm-quadrant">Calm</span>
                            </button>
                            <button class="jqm-card jqm-q4" data-v="0.72" data-a="0.30" onclick="setJourneyFromQuickMood(this)">
                                <span class="jqm-emoji">🤗</span><span class="jqm-name">Dịu dàng</span>
                                <span class="jqm-quadrant">Tender</span>
                            </button>
                            <button class="jqm-card jqm-q4" data-v="0.70" data-a="0.45" onclick="setJourneyFromQuickMood(this)">
                                <span class="jqm-emoji">💕</span><span class="jqm-name">Lãng mạn</span>
                                <span class="jqm-quadrant">Romantic</span>
                            </button>
                            <!-- Q3: Low Valence, Low Arousal -->
                            <button class="jqm-card jqm-q3" data-v="0.20" data-a="0.20" onclick="setJourneyFromQuickMood(this)">
                                <span class="jqm-emoji">😢</span><span class="jqm-name">Buồn bã</span>
                                <span class="jqm-quadrant">Sad</span>
                            </button>
                            <button class="jqm-card jqm-q3" data-v="0.30" data-a="0.30" onclick="setJourneyFromQuickMood(this)">
                                <span class="jqm-emoji">🌧️</span><span class="jqm-name">U sầu</span>
                                <span class="jqm-quadrant">Melancholic</span>
                            </button>
                            <button class="jqm-card jqm-q3" data-v="0.45" data-a="0.35" onclick="setJourneyFromQuickMood(this)">
                                <span class="jqm-emoji">📷</span><span class="jqm-name">Hoài niệm</span>
                                <span class="jqm-quadrant">Nostalgic</span>
                            </button>
                            <!-- Q2: Low Valence, High Arousal -->
                            <button class="jqm-card jqm-q2" data-v="0.15" data-a="0.90" onclick="setJourneyFromQuickMood(this)">
                                <span class="jqm-emoji">😤</span><span class="jqm-name">Tức giận</span>
                                <span class="jqm-quadrant">Angry</span>
                            </button>
                            <button class="jqm-card jqm-q2" data-v="0.25" data-a="0.80" onclick="setJourneyFromQuickMood(this)">
                                <span class="jqm-emoji">😰</span><span class="jqm-name">Lo lắng</span>
                                <span class="jqm-quadrant">Anxious</span>
                            </button>
                        </div>
                    </div>

                    <!-- Journey Summary -->
                    <div class="journey-summary-v2" id="journey-summary" style="display:none">
                        <div class="jsv2-from" id="journey-summary-from">
                            <span class="jsv2-dot jsv2-dot-start"></span>
                            <span class="jsv2-label"></span>
                        </div>
                        <div class="jsv2-path">
                            <div class="jsv2-path-line"></div>
                            <div class="jsv2-path-dots">
                                <span></span><span></span><span></span>
                            </div>
                        </div>
                        <div class="jsv2-to" id="journey-summary-to">
                            <span class="jsv2-dot jsv2-dot-end"></span>
                            <span class="jsv2-label"></span>
                        </div>
                    </div>

                    <!-- Journey Presets -->
                    <div class="journey-presets">
                        <div class="journey-presets-label">Hành trình phổ biến (Iso Principle)</div>
                        <div class="journey-presets-grid">
                            <button class="journey-preset" onclick="setJourneyPreset(0.2,0.2, 0.8,0.7)">😢→😊 Buồn → Vui</button>
                            <button class="journey-preset" onclick="setJourneyPreset(0.3,0.8, 0.7,0.2)">😤→😌 Căng thẳng → Bình yên</button>
                            <button class="journey-preset" onclick="setJourneyPreset(0.5,0.3, 0.8,0.9)">😐→🤩 Uể oải → Phấn khích</button>
                            <button class="journey-preset" onclick="setJourneyPreset(0.8,0.8, 0.6,0.2)">🎉→😴 Sôi động → Nghỉ ngơi</button>
                            <button class="journey-preset" onclick="setJourneyPreset(0.2,0.3, 0.65,0.45)">💔→💕 Thất tình → Hy vọng</button>
                            <button class="journey-preset" onclick="setJourneyPreset(0.4,0.7, 0.85,0.85)">🔥→✨ Nổi loạn → Tự do</button>
                        </div>
                    </div>

                    <div class="journey-options">
                        <div class="journey-options-row">
                            <label>Số bước: <span id="journey-steps-val">8</span></label>
                            <input type="range" id="journey-steps" min="6" max="15" value="8" oninput="document.getElementById('journey-steps-val').textContent=this.value">
                            <div class="journey-steps-hint">Saari (2016): 10-15% V-A mỗi bước → tối ưu 7-10 bài</div>
                        </div>
                        <button class="btn btn-primary btn-glow btn-journey-go" onclick="generateEmotionJourney()" id="btn-journey-go">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:18px;height:18px"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>
                            Tạo hành trình ✨
                        </button>
                    </div>
                    </details>
                </div>

                <div id="journey-visualization" style="display:none"></div>
                <div class="ai-results" id="journey-results"></div>
            </div>

        `;

        initColorPicker();
        initImageUpload();
        initJourneyPickers();
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

