/**
 * Brightify — Main Application v6.0
 * SPA Router, Page Rendering, State Management
 * Features: Color & Image AI, Sleep Timer, Radio Mode, Keyboard Shortcuts
 */

// ══════════════════════════════════════════════════════════════════════════
// Router
// ══════════════════════════════════════════════════════════════════════════
const router = {
    routes: {},
    currentPage: null,

    register(path, handler) { this.routes[path] = handler; },

    navigate(path) {
        window.location.hash = `#/${path}`;
    },

    init() {
        window.addEventListener('hashchange', () => this._resolve());
        this._resolve();
    },

    _resolve() {
        const hash = window.location.hash.replace('#/', '') || 'home';
        const page = hash.split('/')[0];

        if (this.routes[page]) {
            // Cleanup previous page resources (canvas listeners, etc.)
            this._cleanupPrevious();
            this.currentPage = page;
            this._setActiveNav(page);
            const container = document.getElementById('page-content');
            if (container) {
                container.scrollTop = 0;
                // Page transition
                container.classList.remove('page-enter');
                void container.offsetWidth;
                container.classList.add('page-enter');
                this.routes[page](container, hash);
            }
        }
    },

    _cleanupPrevious() {
        // Run cleanup on any canvas with a _cleanup handler (e.g. color picker)
        const container = document.getElementById('page-content');
        if (!container) return;
        container.querySelectorAll('canvas').forEach(c => {
            if (typeof c._cleanup === 'function') c._cleanup();
        });
    },

    _setActiveNav(page) {
        document.querySelectorAll('.nav-item:not(.nav-playlist-item)').forEach(el => {
            el.classList.toggle('active', el.dataset.page === page);
        });

    },
};

// ══════════════════════════════════════════════════════════════════════════
// App State & Helpers
// ══════════════════════════════════════════════════════════════════════════
const app = {
    stats: null,
    _sleepTimeout: null,
    _sleepTimerEnd: null,

    async init() {

        // Global search — inline dropdown results
        const searchInput = document.getElementById('global-search');
        let searchDebounce;
        if (searchInput) {
            // Create dropdown
            const dropdown = document.createElement('div');
            dropdown.id = 'search-dropdown';
            dropdown.className = 'search-dropdown';
            searchInput.parentElement.style.position = 'relative';
            searchInput.parentElement.appendChild(dropdown);

            const showResults = async (query) => {
                if (!query || query.length < 2) { dropdown.classList.remove('visible'); return; }
                try {
                    const data = await API.searchSongs(query, 8);

                    if (!data.songs || data.songs.length === 0) {
                        dropdown.innerHTML = '<div class="search-dropdown-empty">Không tìm thấy kết quả</div>';
                    } else {
                        dropdown.innerHTML = data.songs.map(s => {
                            const art = s.has_album_art ? `<img src="${safeUrl(s.album_art_url)}" alt="">` : `<span style="color:${safeColor(s.color_hex)}">🎵</span>`;
                            return `<div class="search-dropdown-item" data-song='${JSON.stringify(s).replace(/'/g,"&#39;")}'>
                                <div class="search-dropdown-art">${art}</div>
                                <div class="search-dropdown-info">
                                    <div class="search-dropdown-title">${esc(s.track_name)}</div>
                                    <div class="search-dropdown-artist">${esc(s.artist)}</div>
                                </div>
                            </div>`;
                        }).join('');
                    }
                    dropdown.classList.add('visible');
                } catch(e) { dropdown.classList.remove('visible'); }
            };

            searchInput.addEventListener('input', (e) => {
                clearTimeout(searchDebounce);
                searchDebounce = setTimeout(() => showResults(e.target.value.trim()), 350);
            });
            searchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') { dropdown.classList.remove('visible'); searchInput.blur(); }
            });

            dropdown.addEventListener('click', (e) => {
                const item = e.target.closest('[data-song]');
                if (item) {
                    try {
                        const song = JSON.parse(item.dataset.song);
                        playSong(song, null);
                        dropdown.classList.remove('visible');
                        searchInput.value = '';
                    } catch(err) {}
                }
            });

            // Dismiss dropdown on outside click
            document.addEventListener('click', (e) => {
                if (!searchInput.contains(e.target) && !dropdown.contains(e.target)) {
                    dropdown.classList.remove('visible');
                }
            });
        }

        // Register pages
        router.register('home', (c) => pages.home(c));
        router.register('ai-lab', (c) => pages.aiLab(c));
        router.register('liked', (c) => pages.liked(c));
        router.register('history', (c) => pages.history(c));
        router.register('artist', (c, h) => pages.artist(c, h));
        router.register('artists', (c) => pages.allArtists(c));

        router.init();

        // Dismiss popups on outside click
        document.addEventListener('click', (e) => {
            const sleepPopup = document.getElementById('sleep-timer-popup');
            const sleepBtn = document.getElementById('btn-sleep');
            if (sleepPopup && sleepPopup.style.display !== 'none' && 
                !sleepPopup.contains(e.target) && !sleepBtn?.contains(e.target)) {
                sleepPopup.style.display = 'none';
            }
        });
    },

    promptModal(title, placeholder) {
        return new Promise((resolve) => {
            const overlay = document.createElement('div');
            overlay.className = 'modal-overlay';
            const box = document.createElement('div');
            box.className = 'modal-box';
            const titleEl = document.createElement('div');
            titleEl.className = 'modal-title';
            titleEl.textContent = title;
            const input = document.createElement('input');
            input.className = 'modal-input';
            input.type = 'text';
            input.placeholder = placeholder;
            input.autofocus = true;
            const actions = document.createElement('div');
            actions.className = 'modal-actions';
            const cancelBtn = document.createElement('button');
            cancelBtn.className = 'btn btn-ghost btn-sm';
            cancelBtn.textContent = 'Hủy';
            const confirmBtn = document.createElement('button');
            confirmBtn.className = 'btn btn-primary btn-sm';
            confirmBtn.textContent = 'Tạo';
            actions.appendChild(cancelBtn);
            actions.appendChild(confirmBtn);
            box.appendChild(titleEl);
            box.appendChild(input);
            box.appendChild(actions);
            overlay.appendChild(box);
            document.body.appendChild(overlay);
            input.focus();
            const confirm = () => { resolve(input.value.trim()); overlay.remove(); };
            const cancel = () => { resolve(null); overlay.remove(); };
            confirmBtn.onclick = confirm;
            cancelBtn.onclick = cancel;
            overlay.addEventListener('click', (e) => { if (e.target === overlay) cancel(); });
            input.addEventListener('keydown', (e) => { if (e.key === 'Enter') confirm(); if (e.key === 'Escape') cancel(); });
        });
    },

    toast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;
        const el = document.createElement('div');
        el.className = `toast toast-${type}`;
        el.textContent = message;
        container.appendChild(el);
        setTimeout(() => {
            el.style.animation = 'toastOut 0.3s forwards';
            setTimeout(() => el.remove(), 300);
        }, 3000);
    },

    // ── Sleep Timer ─────────────────────────────────────────────────────
    toggleSleepTimer() {
        const popup = document.getElementById('sleep-timer-popup');
        if (!popup) return;
        if (popup.style.display !== 'none') {
            popup.style.display = 'none';
            return;
        }
        const btn = document.getElementById('btn-sleep');
        if (btn) {
            const rect = btn.getBoundingClientRect();
            popup.style.left = `${rect.left - 60}px`;
            popup.style.bottom = `${window.innerHeight - rect.top + 8}px`;
            popup.style.top = 'auto';
        }
        // Show/hide cancel option
        const cancelOpt = document.getElementById('sleep-cancel-option');
        if (cancelOpt) cancelOpt.style.display = this._sleepTimeout ? 'block' : 'none';
        popup.style.display = 'block';
    },

    setSleepTimer(minutes) {
        if (this._sleepTimeout) clearTimeout(this._sleepTimeout);
        this._sleepTimerEnd = Date.now() + minutes * 60 * 1000;
        this._sleepTimeout = setTimeout(() => {
            player.audio.pause();
            this._sleepTimeout = null;
            this._sleepTimerEnd = null;
            const btn = document.getElementById('btn-sleep');
            if (btn) btn.classList.remove('sleep-active');
            this.toast('💤 Hẹn giờ ngủ — Đã tạm dừng nhạc', 'info');
        }, minutes * 60 * 1000);

        const btn = document.getElementById('btn-sleep');
        if (btn) btn.classList.add('sleep-active');
        document.getElementById('sleep-timer-popup').style.display = 'none';
        this.toast(`⏰ Hẹn giờ: ${minutes} phút`, 'success');
    },

    cancelSleepTimer() {
        if (this._sleepTimeout) {
            clearTimeout(this._sleepTimeout);
            this._sleepTimeout = null;
            this._sleepTimerEnd = null;
        }
        const btn = document.getElementById('btn-sleep');
        if (btn) btn.classList.remove('sleep-active');
        document.getElementById('sleep-timer-popup').style.display = 'none';
        this.toast('Đã hủy hẹn giờ', 'info');
    },

    // ── Keyboard Shortcuts ──────────────────────────────────────────────
    showShortcuts() {
        const modal = document.getElementById('shortcuts-modal');
        if (modal) modal.style.display = 'flex';
    },

    hideShortcuts() {
        const modal = document.getElementById('shortcuts-modal');
        if (modal) modal.style.display = 'none';
    },

    // ── Context Menu ──
    showContextMenu(e, song) {
        e.preventDefault();
        document.querySelectorAll('.context-menu').forEach(m => m.remove());

        const menu = document.createElement('div');
        menu.className = 'context-menu';
        menu.style.left = `${e.clientX}px`;
        menu.style.top = `${e.clientY}px`;

        const liked = JSON.parse(localStorage.getItem('bf_liked') || '[]');
        const isLiked = liked.some(s => s.track_id === song.track_id);



        menu.innerHTML = `
            <div class="context-menu-item" data-action="play">
                <svg viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                <span>Phát ngay</span>
            </div>
            <div class="context-menu-item" data-action="play-next">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 4 15 12 5 20z" fill="currentColor"/><line x1="19" y1="5" x2="19" y2="19"/></svg>
                <span>Phát tiếp theo</span>
            </div>
            <div class="context-menu-item" data-action="queue">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
                <span>Thêm vào hàng đợi</span>
            </div>
            <div class="context-menu-divider"></div>
            <div class="context-menu-item" data-action="radio">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.4"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.4"/><path d="M19.1 4.9C23 8.8 23 15.2 19.1 19.1"/><circle cx="12" cy="12" r="2" fill="currentColor"/></svg>
                <span>Phát bài tương tự</span>
            </div>
            <div class="context-menu-divider"></div>
            <div class="context-menu-item" data-action="like">
                <svg viewBox="0 0 24 24" fill="${isLiked ? 'var(--danger)' : 'none'}" stroke="${isLiked ? 'var(--danger)' : 'currentColor'}" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/></svg>
                <span>${isLiked ? 'Bỏ yêu thích' : 'Yêu thích'}</span>
            </div>
            <div class="context-menu-divider"></div>
            <div class="context-menu-item" data-action="artist">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                <span>Xem nghệ sĩ</span>
            </div>
        `;

        document.body.appendChild(menu);

        const rect = menu.getBoundingClientRect();
        if (rect.right > window.innerWidth) menu.style.left = `${window.innerWidth - rect.width - 8}px`;
        if (rect.bottom > window.innerHeight) menu.style.top = `${window.innerHeight - rect.height - 8}px`;

        menu.addEventListener('click', async (ev) => {
            const action = ev.target.closest('[data-action]')?.dataset.action;
            if (!action) return;

            switch (action) {
                case 'play':
                    menu.remove();
                    player.loadQueue([song], 0, 'context-menu');
                    break;
                case 'play-next':
                    menu.remove();
                    player.playNext(song);
                    break;
                case 'queue':
                    menu.remove();
                    player.addToQueue(song);
                    break;
                case 'radio':
                    menu.remove();
                    this._startSongRadio(song);
                    break;
                case 'like':
                    menu.remove();
                    toggleSongLike(song);
                    break;

                case 'artist':
                    menu.remove();
                    if (song.artist) router.navigate(`artist/${encodeURIComponent(song.artist)}`);
                    break;

            }
        });

        const dismiss = (e) => {
            if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', dismiss); }
        };
        setTimeout(() => document.addEventListener('click', dismiss), 0);
    },

    async _startSongRadio(song) {
        await player.startSongRadio(song);
    },

};

// ── Helpers ──────────────────────────────────────────────────────────────
function esc(str) {
    const d = document.createElement('div');
    d.textContent = str || '';
    return d.innerHTML;
}

function safeColor(hex) {
    return /^#[0-9a-fA-F]{3,8}$/.test(hex) ? hex : '#a78bfa';
}

function safeUrl(url) {
    if (!url || typeof url !== 'string') return '';
    // Allow only relative paths and http(s) URLs
    if (url.startsWith('/') || url.startsWith('http://') || url.startsWith('https://')) return url;
    return '';
}

function getGreeting() {
    const h = new Date().getHours();
    if (h < 12) return 'Chào buổi sáng ☀️';
    if (h < 18) return 'Chào buổi chiều 🌤️';
    return 'Chào buổi tối 🌙';
}

function songCardHTML(song) {
    const artBg = safeColor(song.color_hex);
    const artUrl = safeUrl(song.album_art_url);
    const artContent = song.has_album_art && artUrl
        ? `<img src="${artUrl}" alt="" loading="lazy" onerror="this.parentElement.innerHTML='<div style=\\'width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:${artBg}20;font-size:2.5rem\\'>🎵</div>'">`
        : `<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:${artBg}20;font-size:2.5rem">🎵</div>`;

    return `
        <div class="song-card" data-idx="${song.track_id}" data-song-index="${song.track_id}" data-song-json="${JSON.stringify(song).replace(/"/g, '&quot;')}" onclick="playSong(${JSON.stringify(song).replace(/"/g, '&quot;')}, event)"
             oncontextmenu="app.showContextMenu(event, ${JSON.stringify(song).replace(/"/g, '&quot;')})">
            <div class="song-card-art" style="border: 1px solid ${artBg}20">
                <div class="song-card-art-inner">${artContent}</div>
                <div class="song-card-play">
                    <svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                </div>
            </div>
            <div class="song-card-title">${esc(song.track_name)}</div>
            <div class="song-card-artist">${esc(song.artist)}</div>
        </div>
    `;
}

function songRowHTML(song, num, _likedSet) {
    const artBg = safeColor(song.color_hex);
    const artUrl = safeUrl(song.album_art_url);
    const art = song.has_album_art && artUrl
        ? `<img src="${artUrl}" alt="" loading="lazy" onerror="this.outerHTML='<span style=\\'color:${artBg}\\'>🎵</span>'">`
        : `<span style="color:${artBg}">🎵</span>`;

    if (!_likedSet) {
        const liked = JSON.parse(localStorage.getItem('bf_liked') || '[]');
        _likedSet = new Set(liked.map(s => s.track_id));
    }
    const isLiked = _likedSet.has(song.track_id);

    return `
        <div class="song-row" data-idx="${song.track_id}" data-song-index="${song.track_id}" data-song-json="${JSON.stringify(song).replace(/"/g, '&quot;')}" onclick="playSong(${JSON.stringify(song).replace(/"/g, '&quot;')}, event)"
             oncontextmenu="app.showContextMenu(event, ${JSON.stringify(song).replace(/"/g, '&quot;')})">
            <div class="song-row-num">${num}</div>
            <div class="song-row-art">${art}</div>
            <div class="song-row-info">
                <div class="song-row-title">${esc(song.track_name)}</div>
                <div class="song-row-artist">${esc(song.artist)}</div>
            </div>

            <div class="song-row-actions">
                <button class="btn-song-like ${isLiked ? 'liked' : ''}" onclick="event.stopPropagation(); toggleSongLike(${JSON.stringify(song).replace(/"/g, '&quot;')}, this)" title="${isLiked ? 'Bỏ thích' : 'Yêu thích'}">
                    <svg viewBox="0 0 24 24" fill="${isLiked ? 'var(--danger)' : 'none'}" stroke="${isLiked ? 'var(--danger)' : 'currentColor'}" stroke-width="2"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/></svg>
                </button>
            </div>
        </div>
    `;
}

function playSong(song, event) {
    if (event && event.target.closest('.btn-song-like')) return;
    const container = document.getElementById('page-content');
    const cards = container?.querySelectorAll('[data-idx]');
    if (cards && cards.length > 1) {
        const allSongs = [];
        let startIdx = 0;
        cards.forEach((card) => {
            try {
                // Extract song data from data-song-json attribute (safe) or onclick fallback
                const jsonAttr = card.getAttribute('data-song-json');
                let s;
                if (jsonAttr) {
                    s = JSON.parse(jsonAttr);
                } else {
                    s = JSON.parse(card.getAttribute('onclick')
                        ?.match(/playSong\((.+?),\s*event\)/)?.[1]?.replace(/&quot;/g, '"') || '{}');
                }
                if (s.track_id !== undefined) {
                    if (s.track_id === song.track_id) startIdx = allSongs.length;
                    allSongs.push(s);
                }
            } catch(e) {}
        });
        if (allSongs.length > 0) {
            player.loadQueue(allSongs, startIdx, 'browse');
            return;
        }
    }
    player.loadQueue([song], 0, 'browse');
}

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
                    <div><div class="section-title" id="time-songs-title">🎵 Phù hợp lúc này</div><div class="section-subtitle" id="time-songs-subtitle"></div></div>
                    <div style="display:flex;gap:6px">
                        <button class="btn btn-ghost btn-sm" id="btn-play-time-songs" style="display:none" onclick="playCurrentTimeSongs()"><svg viewBox="0 0 24 24" fill="currentColor" style="width:14px;height:14px"><polygon points="5 3 19 12 5 21 5 3"/></svg> Phát tất cả</button>
                        <button class="btn btn-ghost btn-sm" id="btn-shuffle-time-songs" style="display:none" onclick="shuffleCurrentTimeSongs()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><path d="M16 3h5v5"/><path d="M4 20L21 3"/><path d="M21 16v5h-5"/><path d="M15 15l6 6"/><path d="M4 4l5 5"/></svg> Trộn</button>
                    </div>
                </div>
                <div class="carousel" id="home-time-songs"></div>
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

        // Load songs for current time of day
        const h = new Date().getHours();
        const currentPeriod = h >= 5 && h < 8 ? 'early_morning' : h >= 8 && h < 11 ? 'morning' : h >= 11 && h < 13 ? 'midday' : h >= 13 && h < 17 ? 'afternoon' : h >= 17 && h < 21 ? 'evening' : 'night';
        const periodNames = { early_morning: 'Sáng sớm', morning: 'Buổi sáng', midday: 'Buổi trưa', afternoon: 'Buổi chiều', evening: 'Buổi tối', night: 'Đêm khuya' };
        const periodDescs = { early_morning: 'Nhẹ nhàng, acoustic, khởi đầu ngày mới', morning: 'Tích cực, tràn đầy năng lượng', midday: 'Thư giãn, dịu dàng', afternoon: 'Sôi động, năng lượng cao', evening: 'Chill, lãng mạn, thả lỏng', night: 'Sâu lắng, trầm tư, ballad' };
        _loadTimePeriodSongs(currentPeriod, periodNames[currentPeriod], periodDescs[currentPeriod]);

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
                <div class="ai-tab active" data-tab="color" onclick="switchAiTab('color')">🎨 Màu sắc</div>
                <!-- <div class="ai-tab" data-tab="lyrics" onclick="switchAiTab('lyrics')">✍️ Lời nhạc</div> -->
                <div class="ai-tab" data-tab="image" onclick="switchAiTab('image')">📷 Hình ảnh</div>
                <div class="ai-tab" data-tab="journey" onclick="switchAiTab('journey')">🎯 Hành trình</div>
                <!-- <div class="ai-tab" data-tab="context" onclick="switchAiTab('context')">🌤️ Ngữ cảnh</div> -->
            </div>

            <!-- Color Tab -->
            <div class="ai-panel" id="tab-color">
                <div class="color-picker-v2">
                    <div class="color-picker-header">
                        <div class="color-wheel-title">🎨 Khám Phá Nhạc Qua Màu Sắc</div>
                        <div class="color-wheel-subtitle">Chọn màu bạn cảm thấy — AI sẽ tìm nhạc phù hợp dựa trên nghiên cứu cảm xúc-màu sắc</div>
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

            <!-- Image Tab -->
            <div class="ai-panel" id="tab-image" style="display:none">
                <div class="image-dropzone" id="image-dropzone">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
                    <div class="image-dropzone-text">Kéo thả hình ảnh vào đây</div>
                    <div class="image-dropzone-hint">hoặc click để chọn file (JPEG, PNG, WebP)</div>
                    <input type="file" id="image-input" accept="image/*" style="display:none">
                </div>
                <div id="image-preview-area"></div>
                <div class="ai-results" id="image-results"></div>
            </div>

            <!-- Emotion Journey Tab -->
            <div class="ai-panel journey-panel-wide" id="tab-journey" style="display:none">
                <div class="journey-section">
                    <div class="journey-header">
                        <div class="journey-title">Hành Trình Cảm Xúc</div>
                        <div class="journey-subtitle">Chọn tâm trạng hiện tại & đích đến — AI dẫn dắt bạn qua từng bước mượt mà (Iso Principle)</div>
                    </div>

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
                </div>

                <div id="journey-visualization" style="display:none"></div>
                <div class="ai-results" id="journey-results"></div>
            </div>

            <!-- Context Tab -->
            <div class="ai-panel" id="tab-context" style="display:none">
                <div class="context-engine">
                    <div class="context-header">
                        <div class="context-title">🌤️ Gợi ý nhạc theo ngữ cảnh</div>
                        <div class="context-subtitle">AI phân tích thời gian, hoạt động, thời tiết & sở thích của bạn — tạo playlist tối ưu cho khoảnh khắc hiện tại</div>
                    </div>

                    <div class="context-controls">
                        <div class="context-row">
                            <div class="context-group">
                                <label class="context-label">🕐 Thời điểm</label>
                                <select id="context-hour" class="context-select">
                                    <option value="auto">Tự động (giờ hiện tại)</option>
                                    ${Array.from({length:24}, (_,i) => `<option value="${i}">${i.toString().padStart(2,'0')}:00</option>`).join('')}
                                </select>
                            </div>
                            <div class="context-group">
                                <label class="context-label">🗓️ Ngày</label>
                                <select id="context-day" class="context-select">
                                    <option value="auto">Tự động</option>
                                    <option value="0">Thứ Hai</option>
                                    <option value="1">Thứ Ba</option>
                                    <option value="2">Thứ Tư</option>
                                    <option value="3">Thứ Năm</option>
                                    <option value="4">Thứ Sáu</option>
                                    <option value="5">Thứ Bảy</option>
                                    <option value="6">Chủ Nhật</option>
                                </select>
                            </div>
                        </div>

                        <div class="context-row">
                            <div class="context-group">
                                <label class="context-label">🏃 Hoạt động</label>
                                <div class="context-chips" id="context-activity-chips">
                                    <button class="context-chip" data-value="relax" onclick="selectContextChip(this,'activity')">😌 Thư giãn</button>
                                    <button class="context-chip" data-value="study" onclick="selectContextChip(this,'activity')">📚 Học tập</button>
                                    <button class="context-chip" data-value="focus" onclick="selectContextChip(this,'activity')">🎯 Tập trung</button>
                                    <button class="context-chip" data-value="workout" onclick="selectContextChip(this,'activity')">💪 Tập luyện</button>
                                    <button class="context-chip" data-value="party" onclick="selectContextChip(this,'activity')">🎉 Tiệc tùng</button>
                                    <button class="context-chip" data-value="commute" onclick="selectContextChip(this,'activity')">🚗 Di chuyển</button>
                                    <button class="context-chip" data-value="cooking" onclick="selectContextChip(this,'activity')">🍳 Nấu ăn</button>
                                    <button class="context-chip" data-value="sleep" onclick="selectContextChip(this,'activity')">😴 Ngủ</button>
                                    <button class="context-chip" data-value="morning_routine" onclick="selectContextChip(this,'activity')">🌅 Buổi sáng</button>
                                </div>
                            </div>
                        </div>

                        <div class="context-row">
                            <div class="context-group">
                                <label class="context-label">🌦️ Thời tiết</label>
                                <div class="context-chips" id="context-weather-chips">
                                    <button class="context-chip" data-value="sunny" onclick="selectContextChip(this,'weather')">☀️ Nắng</button>
                                    <button class="context-chip" data-value="cloudy" onclick="selectContextChip(this,'weather')">☁️ Mây</button>
                                    <button class="context-chip" data-value="rainy" onclick="selectContextChip(this,'weather')">🌧️ Mưa</button>
                                    <button class="context-chip" data-value="stormy" onclick="selectContextChip(this,'weather')">⛈️ Bão</button>
                                </div>
                            </div>
                            <div class="context-group">
                                <label class="context-label">🍂 Mùa</label>
                                <div class="context-chips" id="context-season-chips">
                                    <button class="context-chip" data-value="spring" onclick="selectContextChip(this,'season')">🌸 Xuân</button>
                                    <button class="context-chip" data-value="summer" onclick="selectContextChip(this,'season')">☀️ Hạ</button>
                                    <button class="context-chip" data-value="autumn" onclick="selectContextChip(this,'season')">🍂 Thu</button>
                                    <button class="context-chip" data-value="winter" onclick="selectContextChip(this,'season')">❄️ Đông</button>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div class="context-persona-toggle">
                        <label class="context-toggle-label">
                            <input type="checkbox" id="context-use-profile" checked>
                            <span>Sử dụng sở thích cá nhân (từ bài hát đã thích & lịch sử nghe)</span>
                        </label>
                    </div>

                    <div class="context-info" id="context-info" style="display:none"></div>

                    <button class="btn btn-primary btn-glow context-go-btn" onclick="generateContextMix()" id="btn-context-go">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:18px;height:18px"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/></svg>
                        Tạo nhạc theo ngữ cảnh ✨
                    </button>

                    <div class="ai-results" id="context-results"></div>
                </div>
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

// ══════════════════════════════════════════════════════════════════════════
// Global Functions
// ══════════════════════════════════════════════════════════════════════════

function _normalizeSong(r) {
    // Upgrade Google CDN thumbnail resolution for retina displays
    let artUrl = r.album_art_url || r.thumbnail_url || null;
    if (artUrl && typeof artUrl === 'string') {
        artUrl = artUrl.replace(/=w\d+-h\d+-/, '=w226-h226-');
    }
    return {
        song_index: r.song_index ?? r.original_index ?? 0,
        track_id: r.track_id || '',
        track_name: r.track_name || 'Unknown',
        artist: r.artist || r.primary_artist || r.artists || 'Unknown',
        album_name: r.album_name || '',
        color_hex: safeColor(r.color_hex),
        valence: r.valence ?? 0.5,
        energy: r.energy ?? 0.5,
        danceability: r.danceability ?? 0.5,
        tempo: r.tempo ?? null,
        mood_quadrant: r.mood_quadrant || '',
        has_audio: r.has_audio || false,
        audio_url: r.audio_url || null,
        has_album_art: r.has_album_art || !!r.thumbnail_url,
        album_art_url: artUrl,
        thumbnail_url: r.thumbnail_url || null,
        has_artist_image: r.has_artist_image || false,
        artist_image_url: r.artist_image_url || null,
    };
}

function _renumberRows(container) {
    if (!container) return;
    container.querySelectorAll('.song-row').forEach((row, i) => {
        const num = row.querySelector('.song-row-num');
        if (num) num.textContent = i + 1;
    });
}

async function _checkAudioBatch(songs) {
    const ids = songs.filter(s => s.track_id).map(s => s.track_id);
    if (!ids.length) return;
    try {
        const batch = await API.getBatchAudioStatus(ids).catch(() => ({ status: {} }));
        songs.forEach(s => {
            if (batch.status?.[s.track_id]) {
                s.has_audio = true;
                s.audio_url = `/api/audio/stream/${s.track_id}`;
            }
        });
    } catch(e) {}
}

async function playMood(mood) {
    try {
        app.toast('Đang tìm nhạc...', 'info');
        const data = await API.recommendByMood(mood, 15);
        if (data.results?.length) {
            const songs = data.results.map(_normalizeSong);
            await _checkAudioBatch(songs);
            player.loadQueue(songs, 0, 'recommend');
        }
    } catch(e) { app.toast('Lỗi: ' + e.message, 'error'); }
}

async function playGenre(genreId, genreName) {
    try {
        app.toast(`Đang tải ${genreName}...`, 'info');
        let songs;
        if (genreId.startsWith('Q')) {
            const mood = genreId === 'Q1' ? 'happy' : genreId === 'Q2' ? 'energetic' : genreId === 'Q3' ? 'sad' : 'calm';
            const data = await API.getSongsByMood(mood, 20);
            songs = data.songs;
        } else if (genreId.startsWith('emotion_')) {
            const mood = genreId.replace('emotion_', '');
            const data = await API.recommendByMood(mood, 20);
            songs = (data.results || []).map(_normalizeSong);
        } else {
            const data = await API.getRandomSongs(20);
            songs = data.songs;
        }
        if (songs?.length) {
            await _checkAudioBatch(songs);
            player.loadQueue(songs, 0, 'genre');
        }
    } catch(e) { app.toast('Lỗi', 'error'); }
}

async function playTimePeriod(period, name) {
    try {
        app.toast(`Đang tải nhạc ${name}...`, 'info');
        const data = await API.getTimeOfDaySongs(period, 20);
        if (data.songs?.length) {
            await _checkAudioBatch(data.songs);
            player.loadQueue(data.songs, 0, 'time-of-day');
        }
    } catch(e) { app.toast('Lỗi tải nhạc', 'error'); }
}

async function _loadTimePeriodSongs(period, name, desc) {
    const section = document.getElementById('time-songs-section');
    const carousel = document.getElementById('home-time-songs');
    const titleEl = document.getElementById('time-songs-title');
    const subEl = document.getElementById('time-songs-subtitle');
    const playBtn = document.getElementById('btn-play-time-songs');
    const shuffleBtn = document.getElementById('btn-shuffle-time-songs');
    if (!section || !carousel) return;

    try {
        const data = await API.getTimeOfDaySongs(period, 14);
        if (data.songs?.length) {
            if (titleEl) titleEl.textContent = `🎵 ${name}`;
            if (subEl) subEl.textContent = desc || 'Gợi ý dựa trên thời điểm hiện tại';
            carousel.innerHTML = data.songs.map(s => songCardHTML(s)).join('');
            section.style.display = '';
            if (playBtn) playBtn.style.display = '';
            if (shuffleBtn) shuffleBtn.style.display = '';
            window._currentTimeSongs = data.songs;
            app._checkAudio(data.songs);
        }
    } catch(e) {}
}

function playCurrentTimeSongs() {
    if (window._currentTimeSongs?.length) player.loadQueue(window._currentTimeSongs, 0, 'time-of-day');
}

function shuffleCurrentTimeSongs() {
    if (window._currentTimeSongs?.length) {
        const shuffled = [...window._currentTimeSongs].sort(() => Math.random() - 0.5);
        player.loadQueue(shuffled, 0, 'time-of-day');
    }
}

async function playArtist(name) {
    try {
        const data = await API.getArtistSongs(decodeURIComponent(name));
        if (data.songs?.length) player.loadQueue(data.songs, 0, 'artist');
    } catch(e) { app.toast('Lỗi', 'error'); }
}

async function shuffleArtist(name) {
    try {
        const data = await API.getArtistSongs(decodeURIComponent(name));
        if (data.songs?.length) {
            const shuffled = [...data.songs].sort(() => Math.random() - 0.5);
            player.loadQueue(shuffled, 0, 'artist');
        }
    } catch(e) { app.toast('Lỗi', 'error'); }
}

function playLiked() {
    const liked = JSON.parse(localStorage.getItem('bf_liked') || '[]');
    if (liked.length) player.loadQueue(liked, 0, 'liked');
}

function shuffleLiked() {
    const liked = JSON.parse(localStorage.getItem('bf_liked') || '[]');
    if (liked.length) {
        const shuffled = [...liked].sort(() => Math.random() - 0.5);
        player.loadQueue(shuffled, 0, 'liked');
    }
}

function clearHistory() {
    localStorage.removeItem('bf_history');
    const list = document.getElementById('history-songs');
    if (list) {
        list.style.transition = 'opacity 0.3s';
        list.style.opacity = '0';
        setTimeout(() => {
            list.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🕐</div><div class="empty-state-title">Chưa nghe bài nào</div><div class="empty-state-text">Bắt đầu nghe nhạc để thấy lịch sử ở đây</div></div>';
            list.style.opacity = '1';
            const subtitle = document.querySelector('.page-subtitle');
            if (subtitle) subtitle.textContent = '0 bài hát';
        }, 300);
    }
    app.toast('Đã xóa lịch sử nghe', 'success');
}

function toggleSongLike(song, btnEl) {
    const liked = JSON.parse(localStorage.getItem('bf_liked') || '[]');
    const idx = liked.findIndex(s => s.track_id === song.track_id);
    const wasLiked = idx >= 0;
    
    if (wasLiked) {
        liked.splice(idx, 1);
        app.toast('Đã bỏ thích', 'info');
    } else {
        liked.push({ ...song, liked_at: Date.now() });
        app.toast('Đã thêm vào yêu thích ❤️', 'success');
    }
    localStorage.setItem('bf_liked', JSON.stringify(liked));
    
    const isNowLiked = !wasLiked;

    // Update ALL heart buttons for this song on the page
    document.querySelectorAll(`[data-song-index=\"${song.track_id}\"] .btn-song-like`).forEach(btn => {
        btn.classList.toggle('liked', isNowLiked);
        const svg = btn.querySelector('svg');
        if (svg) {
            svg.setAttribute('fill', isNowLiked ? 'var(--danger)' : 'none');
            svg.setAttribute('stroke', isNowLiked ? 'var(--danger)' : 'currentColor');
        }
    });
    
    // Also update the specific button if passed (fallback)
    if (btnEl) {
        btnEl.classList.toggle('liked', isNowLiked);
        const svg = btnEl.querySelector('svg');
        if (svg) {
            svg.setAttribute('fill', isNowLiked ? 'var(--danger)' : 'none');
            svg.setAttribute('stroke', isNowLiked ? 'var(--danger)' : 'currentColor');
        }
    }
    
    // Update player like button if same song
    const current = player.getCurrentSong();
    if (current && current.track_id === song.track_id) {
        player._updateLikeBtn();
    }
    
    // If on liked page, remove the song row immediately
    if (wasLiked && router.currentPage === 'liked') {
        const row = document.querySelector(`#page-content [data-song-index=\"${song.track_id}\"]`);
        if (row) {
            row.style.transition = 'opacity 0.3s, transform 0.3s';
            row.style.opacity = '0';
            row.style.transform = 'translateX(-20px)';
            setTimeout(() => {
                row.remove();
                // Update count
                const subtitle = document.querySelector('.page-subtitle');
                if (subtitle) subtitle.textContent = `${liked.length} bài hát`;
            }, 300);
        }
    }
}

// ══════════════════════════════════════════════════════════════════════════
// AI Lab — Color & Image
// ══════════════════════════════════════════════════════════════════════════

let _selectedColors = [];

function switchAiTab(tab) {
    document.querySelectorAll('.ai-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    ['color', 'image', 'lyrics', 'journey', 'context'].forEach(t => {
        const el = document.getElementById(`tab-${t}`);
        if (el) el.style.display = t === tab ? 'block' : 'none';
    });
}

function adjColorCount(d) {
    const el = document.getElementById('color-count');
    if (!el) return;
    el.value = Math.max(5, Math.min(25, parseInt(el.value) + d));
    document.getElementById('color-count-val').textContent = el.value;
}

// ══════════════════════════════════════════════════════════════════════════
// Color Picker — Emotion Cards + Hex Input
// ══════════════════════════════════════════════════════════════════════════

function addColorFromHex() {
    const input = document.getElementById('color-hex-input');
    let hex = (input?.value || '').trim().replace(/^#/, '');
    if (!/^[0-9a-fA-F]{6}$/.test(hex)) {
        app.toast('Mã màu không hợp lệ (cần 6 ký tự hex)', 'info');
        return;
    }
    hex = '#' + hex.toLowerCase();
    addSelectedColor(hex);
    input.value = '';
    const preview = document.getElementById('hex-preview-swatch');
    if (preview) preview.style.background = '#a78bfa';
}


// ══════════════════════════════════════════════════════════════════════════
// Emotion Journey — Quick Mood Cards (v2)
// ══════════════════════════════════════════════════════════════════════════

function setJourneyFromQuickMood(btn) {
    const v = parseFloat(btn.dataset.v);
    const a = parseFloat(btn.dataset.a);

    // Determine: if no start yet, set start; if start set but no end, set end
    // If both set, reset and set as new start
    if (!_journeyStart) {
        _journeyStart = { v, a };
        btn.classList.add('jqm-selected-start');
    } else if (!_journeyEnd) {
        _journeyEnd = { v, a };
        btn.classList.add('jqm-selected-end');
    } else {
        // Reset both
        document.querySelectorAll('.jqm-card').forEach(c => c.classList.remove('jqm-selected-start', 'jqm-selected-end'));
        _journeyStart = { v, a };
        _journeyEnd = null;
        btn.classList.add('jqm-selected-start');
    }
    _updateJourneySummary();
}

function _updateJourneySummary() {
    const summary = document.getElementById('journey-summary');
    if (!summary) return;
    if (_journeyStart && _journeyEnd) {
        summary.style.display = 'flex';
        const fromEl = document.getElementById('journey-summary-from');
        const toEl = document.getElementById('journey-summary-to');
        if (fromEl) {
            const lbl = fromEl.querySelector('.jsv2-label');
            if (lbl) lbl.textContent = `${_vaToLabel(_journeyStart.v, _journeyStart.a)} (${_journeyStart.v.toFixed(2)}, ${_journeyStart.a.toFixed(2)})`;
        }
        if (toEl) {
            const lbl = toEl.querySelector('.jsv2-label');
            if (lbl) lbl.textContent = `${_vaToLabel(_journeyEnd.v, _journeyEnd.a)} (${_journeyEnd.v.toFixed(2)}, ${_journeyEnd.a.toFixed(2)})`;
        }
    } else {
        summary.style.display = 'none';
    }
}

function initColorPicker() {
    // Reset color state on every page render
    _selectedColors = [];

    // Render palette presets
    const palettes = [
        { name: '🌅 Hoàng hôn', colors: ['#ff6b35','#f7c59f','#ef5350','#ff9800','#ffc107'] },
        { name: '🌊 Đại dương', colors: ['#0077b6','#00b4d8','#90e0ef','#023e8a','#48cae4'] },
        { name: '🌿 Rừng xanh', colors: ['#2d6a4f','#52b788','#95d5b2','#1b4332','#40916c'] },
        { name: '🌌 Thiên hà', colors: ['#7b2cbf','#9d4edd','#c77dff','#3c096c','#e0aaff'] },
        { name: '🌸 Lãng mạn', colors: ['#ff758f','#ff7eb3','#ff85a1','#fbb1bd','#f9bec7'] },
        { name: '🔥 Rực cháy', colors: ['#ef4444','#f97316','#eab308','#dc2626','#fb923c'] },
        { name: '❄️ Băng giá', colors: ['#e0f2fe','#bae6fd','#7dd3fc','#38bdf8','#0ea5e9'] },
        { name: '🎭 Vintage', colors: ['#bc6c25','#dda15e','#606c38','#283618','#fefae0'] },
    ];
    window._colorPalettes = palettes;

    const palettesEl = document.getElementById('color-palettes');
    if (palettesEl) {
        palettesEl.innerHTML = palettes.map((p, i) => `
            <button class="color-palette-btn" onclick="selectPalette(${i})" data-palette-idx="${i}">
                <div class="color-palette-swatches">${p.colors.map(c => `<span style="background:${c}"></span>`).join('')}</div>
                <div class="color-palette-name">${p.name}</div>
            </button>
        `).join('');
    }

    _updateColorPickerUI();

    // Hex input: live preview on typing
    const hexInput = document.getElementById('color-hex-input');
    if (hexInput) {
        hexInput.addEventListener('input', () => {
            let val = hexInput.value.replace(/[^0-9a-fA-F]/g, '').slice(0, 6);
            hexInput.value = val;
            if (val.length === 6) {
                const hex = '#' + val.toLowerCase();
                const preview = document.getElementById('hex-preview-swatch');
                if (preview) preview.style.background = hex;
            }
        });
    }
}

// ── Color helpers ──
function _rgbToHex(r, g, b) { return '#' + [r,g,b].map(c => c.toString(16).padStart(2,'0')).join(''); }

function addSelectedColor(hex) {
    if (_selectedColors.length >= 5) { app.toast('Tối đa 5 màu', 'info'); return; }
    if (_selectedColors.includes(hex)) return;
    _selectedColors.push(hex);
    _updateColorPickerUI();
}

function removeSelectedColor(idx) {
    _selectedColors.splice(idx, 1);
    _updateColorPickerUI();
}

function clearSelectedColors() {
    _selectedColors = [];
    _updateColorPickerUI();
    document.querySelectorAll('.color-palette-btn').forEach(b => b.classList.remove('active'));
}

function selectPalette(paletteIdx) {
    const p = window._colorPalettes?.[paletteIdx];
    if (!p) return;
    _selectedColors = [...p.colors];
    _updateColorPickerUI();
    document.querySelectorAll('.color-palette-btn').forEach((b, i) => b.classList.toggle('active', i === paletteIdx));
}

function _updateColorPickerUI() {
    const dotsEl = document.getElementById('color-selected-dots');
    const countEl = document.getElementById('color-selected-count');
    const clearBtn = document.getElementById('btn-clear-colors');
    if (countEl) countEl.textContent = `${_selectedColors.length}/5`;
    if (clearBtn) clearBtn.style.display = _selectedColors.length > 0 ? 'inline' : 'none';
    if (dotsEl) {
        dotsEl.innerHTML = _selectedColors.length === 0
            ? '<div class="color-add-hint">Nhấp vào màu bên trên để chọn</div>'
            : _selectedColors.map((c, i) => `
                <div class="color-selected-dot" style="background:${c}" onclick="event.stopPropagation(); removeSelectedColor(${i})" title="${c} — Nhấp để xóa">
                    <span class="color-dot-x">×</span>
                </div>`).join('');
    }
}

async function getColorRecommendations() {
    if (_selectedColors.length === 0) {
        app.toast('Hãy chọn ít nhất 1 màu', 'info');
        return;
    }
    const count = parseInt(document.getElementById('color-count')?.value || 10);
    const results = document.getElementById('color-results');
    results.innerHTML = '<div class="loading-inline"><div class="loader"></div>AI đang phân tích màu sắc...</div>';

    try {
        const data = await API.recommendByColor(_selectedColors, count);
        renderAiResults(results, data.results, `Nhạc phù hợp với ${_selectedColors.join(', ')}`, 'color');
    } catch (e) {
        results.innerHTML = '<div class="empty-state"><div class="empty-state-icon">😕</div><div class="empty-state-title">Lỗi</div></div>';
        app.toast(e.message, 'error');
    }
}

function initImageUpload() {
    const dropzone = document.getElementById('image-dropzone');
    const input = document.getElementById('image-input');
    if (!dropzone || !input) return;

    dropzone.addEventListener('click', () => input.click());
    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files[0]) processImage(e.dataTransfer.files[0]);
    });
    input.addEventListener('change', () => {
        if (input.files[0]) processImage(input.files[0]);
    });

    document.addEventListener('paste', (e) => {
        if (router.currentPage !== 'ai-lab') return;
        const items = e.clipboardData?.items;
        if (!items) return;
        for (let item of items) {
            if (item.type.startsWith('image/')) {
                processImage(item.getAsFile());
                break;
            }
        }
    });
}

async function processImage(file) {
    const preview = document.getElementById('image-preview-area');
    const results = document.getElementById('image-results');
    if (!preview || !results) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        preview.innerHTML = `
            <div class="image-preview-container">
                <div class="image-preview"><img src="${e.target.result}" alt="Preview"></div>
                <div class="image-analysis" id="img-analysis">
                    <div class="loading-inline"><div class="loader"></div>AI đang phân tích...</div>
                </div>
            </div>
        `;
    };
    reader.readAsDataURL(file);

    results.innerHTML = '<div class="loading-inline"><div class="loader"></div>Đang tìm nhạc phù hợp...</div>';

    try {
        const data = await API.recommendByImage(file, 12);
        const analysisEl = document.getElementById('img-analysis');
        if (analysisEl && data.image_analysis) {
            const a = data.image_analysis;
            const contentLabels = {
                portrait:'Chân dung', group_photo:'Ảnh nhóm', selfie:'Selfie',
                landscape:'Phong cảnh', urban:'Thành phố', indoor:'Nội thất',
                food_drink:'Ẩm thực', animal:'Động vật', object:'Vật thể',
                art_abstract:'Nghệ thuật', event:'Sự kiện', nature_close:'Thiên nhiên cận cảnh',
            };
            const exprLabels = {
                joy:'Vui sướng', gentle_smile:'Mỉm cười dịu dàng', neutral:'Bình thản',
                thoughtful:'Trầm tư', sadness:'Buồn bã', surprise:'Ngỡ ngàng',
                determination:'Quyết tâm', dreamy:'Mơ màng', laughter:'Cười sảng khoái',
                serenity:'An nhiên', passion:'Đam mê', tenderness:'Dịu dàng',
            };
            const lightLabels = {
                golden_hour:'Hoàng hôn vàng', blue_hour:'Chiều tím',
                bright_daylight:'Nắng chan hòa', overcast:'Trời âm u',
                neon:'Đèn neon', candlelight:'Ánh nến', moonlight:'Ánh trăng',
                dramatic:'Kịch tính',
            };

            let extraHtml = '';
            // Content type
            if (a.content_type) {
                extraHtml += `
                <div class="analysis-item">
                    <div class="analysis-label">Loại nội dung</div>
                    <div class="analysis-value">${contentLabels[a.content_type] || esc(a.content_type)}${a.has_person ? ' 👤' : ''}</div>
                </div>`;
            }
            // Expression (when person detected)
            if (a.has_person && a.expression) {
                extraHtml += `
                <div class="analysis-item">
                    <div class="analysis-label">Biểu cảm</div>
                    <div class="analysis-value">${exprLabels[a.expression] || esc(a.expression)}</div>
                </div>`;
            }
            // Lighting
            if (a.lighting) {
                extraHtml += `
                <div class="analysis-item">
                    <div class="analysis-label">Ánh sáng</div>
                    <div class="analysis-value">${lightLabels[a.lighting] || esc(a.lighting)}</div>
                </div>`;
            }

            analysisEl.innerHTML = `
                <div class="analysis-item">
                    <div class="analysis-label">Mô tả</div>
                    <div class="analysis-value">${esc(a.mood_description) || '—'}</div>
                </div>
                <div class="analysis-item">
                    <div class="analysis-label">Màu chủ đạo</div>
                    <div class="analysis-colors">
                        ${(a.dominant_colors || []).map(c => `<div class="analysis-color-dot" style="background:${safeColor(c)}"></div>`).join('')}
                    </div>
                </div>
                ${extraHtml}
                <div class="analysis-item">
                    <div class="analysis-label">Valence / Arousal</div>
                    <div class="analysis-value">${(a.valence ?? 0).toFixed(2)} / ${(a.arousal ?? 0).toFixed(2)}</div>
                </div>
            `;
        }
        renderAiResults(results, data.results, data.message || 'Nhạc phù hợp với hình ảnh', 'image');
    } catch (e) {
        results.innerHTML = '<div class="empty-state"><div class="empty-state-icon">😕</div><div class="empty-state-title">Lỗi phân tích ảnh</div></div>';
        app.toast(e.message, 'error');
    }
}

async function renderAiResults(container, results, title, recType) {
    if (!results || results.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🤔</div><div class="empty-state-title">Không tìm thấy kết quả</div></div>';
        return;
    }

    const songs = results.map(_normalizeSong);
    await _checkAudioBatch(songs);

    container.innerHTML = `
        <div class="ai-results-header">
            <div class="section-title" style="font-size:1.1rem">${esc(title)}</div>
            <div class="ai-results-count">${songs.length} bài</div>
        </div>
        <div class="ai-results-actions">
            <button class="btn btn-primary btn-sm" onclick="playAiResults()">
                <svg viewBox="0 0 24 24" fill="currentColor" style="width:14px;height:14px"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                Phát tất cả
            </button>
            <button class="btn btn-secondary btn-sm" onclick="shuffleAiResults()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/><line x1="4" y1="4" x2="9" y2="9"/></svg>
                Trộn phát
            </button>
            <button class="btn btn-ghost btn-sm" onclick="addAiResultsToQueue()">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                Thêm vào hàng đợi
            </button>
        </div>
        <div class="song-list">${songs.map((s, i) => songRowHTML(s, i + 1)).join('')}</div>
    `;

    window._lastAiResults = songs;
}

function playAiResults() {
    if (window._lastAiResults?.length) {
        player.loadQueue(window._lastAiResults, 0, 'recommend');
    }
}

function shuffleAiResults() {
    if (window._lastAiResults?.length) {
        const shuffled = [...window._lastAiResults].sort(() => Math.random() - 0.5);
        player.loadQueue(shuffled, 0, 'recommend');
    }
}

function addAiResultsToQueue() {
    if (window._lastAiResults?.length) {
        window._lastAiResults.forEach(s => player.addToQueue(s));
        app.toast(`Đã thêm ${window._lastAiResults.length} bài vào hàng đợi`, 'success');
    }
}

// ── Lyrics Mood Search ──
function setLyricQuery(text) {
    const el = document.getElementById('lyrics-search-input');
    if (el) el.value = text;
}

async function getLyricsRecommendations() {
    const input = document.getElementById('lyrics-search-input');
    const keywords = input?.value?.trim();
    if (!keywords) { app.toast('Hãy mô tả cảm xúc của bạn', 'info'); return; }
    const count = parseInt(document.getElementById('lyrics-count')?.value || 10);
    const results = document.getElementById('lyrics-results');
    results.innerHTML = '<div class="loading-inline"><div class="loader"></div>AI đang phân tích lời bạn viết...</div>';
    try {
        const data = await API.recommendByLyrics(keywords, count);
        renderAiResults(results, data.results, `Nhạc phù hợp: "${keywords}"`, 'lyrics');
    } catch (e) {
        results.innerHTML = '<div class="empty-state"><div class="empty-state-icon">😕</div><div class="empty-state-title">Lỗi</div></div>';
        app.toast(e.message, 'error');
    }
}

// ══════════════════════════════════════════════════════════════════════════
// Emotion Journey — V-A Pickers + Journey Generation
// ══════════════════════════════════════════════════════════════════════════
let _journeyStart = null; // {v, a}
let _journeyEnd = null;

const _VA_LABELS = {
    topRight: 'Vui vẻ\nPhấn khích', topLeft: 'Tức giận\nCăng thẳng',
    bottomLeft: 'Buồn\nU sầu', bottomRight: 'Bình yên\nThư thái',
};

function initJourneyPickers() {
    _journeyStart = null;
    _journeyEnd = null;
}

function _vaToLabel(v, a) {
    if (v >= 0.5 && a >= 0.5) return v > 0.7 ? 'Vui vẻ' : 'Phấn khích';
    if (v < 0.5 && a >= 0.5) return a > 0.7 ? 'Tức giận' : 'Căng thẳng';
    if (v < 0.5 && a < 0.5) return v < 0.3 ? 'Buồn bã' : 'U sầu';
    return v > 0.7 ? 'Bình yên' : 'Thư thái';
}

function setJourneyPreset(sv, sa, ev, ea) {
    _journeyStart = { v: sv, a: sa };
    _journeyEnd = { v: ev, a: ea };

    // Highlight closest quick mood cards
    _highlightClosestQuickMood(sv, sa, ev, ea);
    _updateJourneySummary();
}

function _highlightClosestQuickMood(sv, sa, ev, ea) {
    const cards = document.querySelectorAll('.jqm-card');
    cards.forEach(c => c.classList.remove('jqm-selected-start', 'jqm-selected-end'));
    let bestStart = null, bestStartDist = Infinity;
    let bestEnd = null, bestEndDist = Infinity;
    cards.forEach(c => {
        const cv = parseFloat(c.dataset.v), ca = parseFloat(c.dataset.a);
        const ds = Math.sqrt((cv - sv) ** 2 + (ca - sa) ** 2);
        const de = Math.sqrt((cv - ev) ** 2 + (ca - ea) ** 2);
        if (ds < bestStartDist) { bestStartDist = ds; bestStart = c; }
        if (de < bestEndDist) { bestEndDist = de; bestEnd = c; }
    });
    if (bestStart && bestStartDist < 0.3) bestStart.classList.add('jqm-selected-start');
    if (bestEnd && bestEndDist < 0.3) bestEnd.classList.add('jqm-selected-end');
}

async function generateEmotionJourney() {
    if (!_journeyStart || !_journeyEnd) {
        app.toast('Hãy chọn cả điểm bắt đầu và điểm đích trên biểu đồ', 'info');
        return;
    }
    const steps = parseInt(document.getElementById('journey-steps')?.value || 10);
    const results = document.getElementById('journey-results');
    const viz = document.getElementById('journey-visualization');
    results.innerHTML = '<div class="loading-inline"><div class="loader"></div>AI đang tạo hành trình cảm xúc...</div>';
    if (viz) viz.style.display = 'none';

    try {
        const data = await API.getEmotionJourney(
            _journeyStart.v, _journeyStart.a,
            _journeyEnd.v, _journeyEnd.a, steps
        );
        if (!data.success || !data.songs?.length) {
            results.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🤔</div><div class="empty-state-title">Không tạo được hành trình</div></div>';
            return;
        }

        // Draw journey visualization (V-A path)
        _drawJourneyVisualization(data.waypoints, data.songs, data.journey_info);

        // Build songs for playback
        const songs = data.songs.map(s => _normalizeSong(s));
        await _checkAudioBatch(songs);

        results.innerHTML = `
            <div class="ai-results-header">
                <div class="section-title" style="font-size:1.1rem">🎯 Hành trình ${data.songs.length} bước</div>
                <div class="ai-results-count">V-A distance: ${data.journey_info.total_va_distance.toFixed(2)}</div>
            </div>
            <div class="ai-results-actions">
                <button class="btn btn-primary btn-sm" onclick="playAiResults()">
                    <svg viewBox="0 0 24 24" fill="currentColor" style="width:14px;height:14px"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    Phát hành trình
                </button>
                <button class="btn btn-ghost btn-sm" onclick="addAiResultsToQueue()">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    Thêm vào hàng đợi
                </button>
            </div>
            <div class="song-list journey-song-list">
                ${songs.map((s, i) => {
                    const step = data.songs[i];
                    const emotion = step.fused_emotion || '';
                    const vaDist = step.va_distance;
                    return `
                    <div class="journey-step-wrapper">
                        <div class="journey-step-badge">
                            <span class="journey-step-num">${i + 1}</span>
                            <span class="journey-step-emotion">${esc(emotion)}</span>
                        </div>
                        ${songRowHTML(s, i + 1)}
                    </div>`;
                }).join('')}
            </div>
        `;

        window._lastAiResults = songs;
    } catch (e) {
        results.innerHTML = '<div class="empty-state"><div class="empty-state-icon">😕</div><div class="empty-state-title">Lỗi tạo hành trình</div></div>';
        app.toast(e.message, 'error');
    }
}

function _drawJourneyVisualization(waypoints, songs, info) {
    const viz = document.getElementById('journey-visualization');
    if (!viz) return;
    viz.style.display = 'block';
    viz.innerHTML = '<canvas id="journey-path-canvas" width="600" height="280"></canvas>';
    const canvas = document.getElementById('journey-path-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    const pad = 40;
    const areaW = W - pad * 2, areaH = H - pad * 2;

    // Clear
    ctx.fillStyle = 'rgba(6,6,18,0.6)';
    ctx.fillRect(0, 0, W, H);

    // Quadrant backgrounds
    ctx.fillStyle = 'rgba(248,113,113,0.06)'; ctx.fillRect(pad, pad, areaW / 2, areaH / 2);
    ctx.fillStyle = 'rgba(251,191,36,0.06)'; ctx.fillRect(pad + areaW / 2, pad, areaW / 2, areaH / 2);
    ctx.fillStyle = 'rgba(96,165,250,0.06)'; ctx.fillRect(pad, pad + areaH / 2, areaW / 2, areaH / 2);
    ctx.fillStyle = 'rgba(52,211,153,0.06)'; ctx.fillRect(pad + areaW / 2, pad + areaH / 2, areaW / 2, areaH / 2);

    // Axes
    ctx.strokeStyle = 'rgba(167,139,250,0.2)';
    ctx.lineWidth = 0.5;
    ctx.beginPath(); ctx.moveTo(pad + areaW / 2, pad); ctx.lineTo(pad + areaW / 2, pad + areaH); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(pad, pad + areaH / 2); ctx.lineTo(pad + areaW, pad + areaH / 2); ctx.stroke();

    // Labels
    ctx.fillStyle = 'rgba(152,150,184,0.5)';
    ctx.font = '10px Inter';
    ctx.textAlign = 'center';
    ctx.fillText('Tức giận', pad + areaW * 0.25, pad + 15);
    ctx.fillText('Phấn khích', pad + areaW * 0.75, pad + 15);
    ctx.fillText('Buồn bã', pad + areaW * 0.25, pad + areaH - 8);
    ctx.fillText('Bình yên', pad + areaW * 0.75, pad + areaH - 8);
    ctx.fillText('Valence →', pad + areaW / 2, pad + areaH + 20);
    ctx.save(); ctx.translate(pad - 20, pad + areaH / 2); ctx.rotate(-Math.PI / 2);
    ctx.fillText('Arousal →', 0, 0); ctx.restore();

    // Helper: V,A → canvas coords
    const toX = v => pad + v * areaW;
    const toY = a => pad + (1 - a) * areaH;

    // Draw waypoint path (dotted)
    ctx.strokeStyle = 'rgba(167,139,250,0.3)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    waypoints.forEach((wp, i) => {
        const x = toX(wp.valence), y = toY(wp.arousal);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw actual song path (solid gradient)
    if (songs.length > 1) {
        ctx.lineWidth = 2.5;
        for (let i = 0; i < songs.length - 1; i++) {
            const s1 = songs[i], s2 = songs[i + 1];
            const x1 = toX(s1.song_valence), y1 = toY(s1.song_arousal);
            const x2 = toX(s2.song_valence), y2 = toY(s2.song_arousal);
            const grad = ctx.createLinearGradient(x1, y1, x2, y2);
            const t = i / (songs.length - 1);
            grad.addColorStop(0, `hsla(${260 + t * 120}, 80%, 70%, 0.8)`);
            grad.addColorStop(1, `hsla(${260 + (t + 1 / songs.length) * 120}, 80%, 70%, 0.8)`);
            ctx.strokeStyle = grad;
            ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        }
    }

    // Draw song dots with step numbers
    songs.forEach((s, i) => {
        const x = toX(s.song_valence), y = toY(s.song_arousal);
        const t = i / Math.max(1, songs.length - 1);
        const hue = 260 + t * 120;
        // Glow
        const glow = ctx.createRadialGradient(x, y, 0, x, y, 14);
        glow.addColorStop(0, `hsla(${hue}, 80%, 70%, 0.3)`);
        glow.addColorStop(1, 'transparent');
        ctx.fillStyle = glow;
        ctx.fillRect(x - 14, y - 14, 28, 28);
        // Dot
        ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fillStyle = `hsl(${hue}, 80%, 70%)`; ctx.fill();
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.stroke();
        // Number
        ctx.fillStyle = '#fff'; ctx.font = 'bold 8px Inter'; ctx.textAlign = 'center';
        ctx.fillText(i + 1, x, y + 3);
    });

    // Start & End labels
    if (songs.length > 0) {
        const first = songs[0], last = songs[songs.length - 1];
        ctx.font = 'bold 10px Inter'; ctx.fillStyle = '#a78bfa';
        ctx.fillText('BẮT ĐẦU', toX(first.song_valence), toY(first.song_arousal) - 12);
        ctx.fillStyle = '#34d399';
        ctx.fillText('ĐÍCH', toX(last.song_valence), toY(last.song_arousal) - 12);
    }
}

// ── Follow Artist ──
function _isFollowingArtist(name) {
    const followed = JSON.parse(localStorage.getItem('bf_followed_artists') || '[]');
    return followed.includes(name);
}

function followArtist(name) {
    const followed = JSON.parse(localStorage.getItem('bf_followed_artists') || '[]');
    if (!followed.includes(name)) {
        followed.push(name);
        localStorage.setItem('bf_followed_artists', JSON.stringify(followed));
        app.toast(`Đã theo dõi ${name} ✨`, 'success');
    }
}

function unfollowArtist(name) {
    let followed = JSON.parse(localStorage.getItem('bf_followed_artists') || '[]');
    followed = followed.filter(n => n !== name);
    localStorage.setItem('bf_followed_artists', JSON.stringify(followed));
    app.toast(`Đã bỏ theo dõi ${name}`, 'info');
}

function toggleFollowArtist(name) {
    if (_isFollowingArtist(name)) {
        unfollowArtist(name);
    } else {
        followArtist(name);
    }
    // Update the follow button UI without full page reload
    const btn = document.getElementById('btn-follow-artist');
    if (btn) {
        const isNowFollowing = _isFollowingArtist(name);
        btn.className = `btn ${isNowFollowing ? 'btn-following' : 'btn-follow'} btn-sm`;
        btn.innerHTML = isNowFollowing
            ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px"><polyline points="20 6 9 17 4 12"/></svg> Đang theo dõi'
            : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:16px;height:16px"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4-4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg> Theo dõi';
    }
}

// ── Listening Stats ──
function _getListeningStats() {
    const history = JSON.parse(localStorage.getItem('bf_history') || '[]');
    const liked = JSON.parse(localStorage.getItem('bf_liked') || '[]');

    // Count unique artists and artist play counts
    const artistCounts = {};
    history.forEach(s => {
        const artist = s.artist || s.primary_artist || 'Unknown';
        artistCounts[artist] = (artistCounts[artist] || 0) + 1;
    });

    const topArtists = Object.entries(artistCounts)
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count);

    return {
        totalPlays: history.length,
        uniqueArtists: Object.keys(artistCounts).length,
        likedCount: liked.length,
        topArtists,
    };
}

// ── Playback Speed ──
const playbackSpeed = {
    speeds: [0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
    current: 1.0,

    showPicker() {
        // Remove existing popup
        document.querySelectorAll('.speed-picker-popup').forEach(m => m.remove());
        const btn = document.getElementById('btn-speed');
        if (!btn) return;
        const rect = btn.getBoundingClientRect();

        const popup = document.createElement('div');
        popup.className = 'speed-picker-popup';
        popup.style.left = `${rect.left + rect.width / 2}px`;
        popup.style.bottom = `${window.innerHeight - rect.top + 8}px`;
        popup.innerHTML = `
            <div class="speed-picker-title">Tốc độ phát</div>
            ${this.speeds.map(s => `
                <div class="speed-picker-item ${s === this.current ? 'active' : ''}" data-speed="${s}">
                    ${s === 1.0 ? 'Bình thường' : s + 'x'}
                    ${s === this.current ? '<svg viewBox="0 0 24 24" fill="currentColor" style="width:14px;height:14px"><polyline points="20 6 9 17 4 12" fill="none" stroke="currentColor" stroke-width="3"/></svg>' : ''}
                </div>
            `).join('')}
        `;
        document.body.appendChild(popup);

        popup.addEventListener('click', (e) => {
            const item = e.target.closest('[data-speed]');
            if (!item) return;
            this.current = parseFloat(item.dataset.speed);
            this.apply();
            const label = document.getElementById('btn-speed');
            if (label) {
                label.textContent = this.current === 1.0 ? '1x' : `${this.current}x`;
                label.classList.toggle('active', this.current !== 1.0);
            }
            app.toast(`Tốc độ phát: ${this.current}x`, 'info');
            popup.remove();
        });

        const dismiss = (e) => {
            if (!popup.contains(e.target) && e.target !== btn) {
                popup.remove();
                document.removeEventListener('click', dismiss);
            }
        };
        setTimeout(() => document.addEventListener('click', dismiss), 0);
    },

    apply() {
        if (player?._audioA) player._audioA.playbackRate = this.current;
        if (player?._audioB) player._audioB.playbackRate = this.current;
    },

    reset() {
        this.current = 1.0;
        this.apply();
        const btn = document.getElementById('btn-speed');
        if (btn) { btn.textContent = '1x'; btn.classList.remove('active'); }
    }
};
window.playbackSpeed = playbackSpeed;

// ── Lyrics Panel ──
function showLyrics() {
    const song = player?.getCurrentSong?.();
    if (!song) { app.toast('Chưa có bài hát nào đang phát', 'info'); return; }

    // Toggle existing panel
    const existing = document.getElementById('lyrics-panel');
    if (existing) {
        existing.remove();
        const lBtn = document.getElementById('btn-lyrics');
        if (lBtn) lBtn.classList.remove('lyrics-active');
        return;
    }

    const panel = document.createElement('div');
    panel.id = 'lyrics-panel';
    panel.className = 'lyrics-panel';
    panel.innerHTML = `
        <div class="lyrics-header">
            <span class="lyrics-header-title">Lời bài hát</span>
            <button class="btn-close-info" onclick="document.getElementById('lyrics-panel')?.remove(); document.getElementById('btn-lyrics')?.classList.remove('lyrics-active')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
        </div>
        <div class="lyrics-song-info">
            <div class="lyrics-song-name">${esc(song.track_name)}</div>
            <div class="lyrics-song-artist">${esc(song.artist)}</div>
        </div>
        <div class="lyrics-body"><div class="lyrics-loading">Đang tải lời bài hát...</div></div>
    `;
    document.body.appendChild(panel);
    requestAnimationFrame(() => panel.classList.add('visible'));
    const lBtn = document.getElementById('btn-lyrics');
    if (lBtn) lBtn.classList.add('lyrics-active');
    _lyricsTrackId = song.track_id;
    _startLyricsWatcher();

    // Fetch lyrics
    (async () => {
        const body = panel.querySelector('.lyrics-body');
        try {
            const res = await API.getSongDetails(song.track_id);
            const lyrics = res.song?.lyrics;
            if (lyrics && lyrics.trim()) {
                body.innerHTML = `<div class="lyrics-text">${esc(lyrics).replace(/\n/g, '<br>')}</div>`;
            } else {
                body.innerHTML = `<div class="lyrics-empty">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="width:40px;height:40px;margin-bottom:8px;opacity:0.4"><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v2a7 7 0 01-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
                    <span>Chưa có lời bài hát</span>
                </div>`;
            }
        } catch(e) {
            body.innerHTML = `<div class="lyrics-empty"><span>Không thể tải lời bài hát</span></div>`;
        }
    })();
}
window.showLyrics = showLyrics;

// Auto-refresh lyrics panel when song changes
let _lyricsTrackId = null;
let _lyricsInterval = null;
function _startLyricsWatcher() {
    if (_lyricsInterval) return;
    _lyricsInterval = setInterval(() => {
        const panel = document.getElementById('lyrics-panel');
        if (!panel) {
            _lyricsTrackId = null;
            clearInterval(_lyricsInterval);
            _lyricsInterval = null;
            return;
        }
        const song = player?.getCurrentSong?.();
        if (song && song.track_id !== _lyricsTrackId) {
            _lyricsTrackId = song.track_id;
            panel.remove();
            showLyrics();
        }
    }, 1000);
}

// ── Crossfade ──
const crossfade = {
    enabled: false,
    duration: 15, // seconds — dual fade handled by player.js

    toggle() {
        this.enabled = !this.enabled;
        localStorage.setItem('bf_crossfade', this.enabled);
        const btn = document.getElementById('btn-crossfade');
        if (btn) btn.classList.toggle('active', this.enabled);
        app.toast(this.enabled ? '🔀 Crossfade bật (15s)' : '🔀 Crossfade tắt', 'info');
    },
};
window.crossfade = crossfade;

// Restore crossfade
if (localStorage.getItem('bf_crossfade') === 'true') {
    crossfade.enabled = true;
    setTimeout(() => {
        const btn = document.getElementById('btn-crossfade');
        if (btn) btn.classList.add('active');
    }, 200);
}

// ══════════════════════════════════════════════════════════════════════════
// Smart Context Engine
// ══════════════════════════════════════════════════════════════════════════

let _contextActivity = null;
let _contextWeather = null;
let _contextSeason = null;

function selectContextChip(btn, group) {
    const container = btn.parentElement;
    const wasActive = btn.classList.contains('active');

    container.querySelectorAll('.context-chip').forEach(c => c.classList.remove('active'));

    if (!wasActive) {
        btn.classList.add('active');
        const val = btn.dataset.value;
        if (group === 'activity') _contextActivity = val;
        else if (group === 'weather') _contextWeather = val;
        else if (group === 'season') _contextSeason = val;
    } else {
        if (group === 'activity') _contextActivity = null;
        else if (group === 'weather') _contextWeather = null;
        else if (group === 'season') _contextSeason = null;
    }
}

async function generateContextMix() {
    const resultsEl = document.getElementById('context-results');
    const infoEl = document.getElementById('context-info');
    resultsEl.innerHTML = '<div class="loading-inline"><div class="loader"></div>AI đang phân tích ngữ cảnh & tạo playlist...</div>';
    if (infoEl) infoEl.style.display = 'none';

    const hourSelect = document.getElementById('context-hour');
    const daySelect = document.getElementById('context-day');
    const useProfile = document.getElementById('context-use-profile')?.checked;

    const hour = hourSelect?.value === 'auto' ? null : parseInt(hourSelect?.value);
    const dayOfWeek = daySelect?.value === 'auto' ? null : parseInt(daySelect?.value);

    let userLiked = null;
    let userHistory = null;
    if (useProfile) {
        const liked = JSON.parse(localStorage.getItem('bf_liked') || '[]');
        userLiked = liked.map(s => ({ track_id: s.track_id, liked_at: s.liked_at }));
        const history = JSON.parse(localStorage.getItem('bf_history') || '[]');
        userHistory = history.map(s => ({ track_id: s.track_id, played_at: s.played_at }));
    }

    try {
        const data = await API.getContextMix({
            hour,
            dayOfWeek,
            activity: _contextActivity,
            season: _contextSeason,
            weather: _contextWeather,
            userLiked,
            userHistory,
        });

        if (!data.success || !data.songs?.length) {
            resultsEl.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🤔</div><div class="empty-state-title">Không tạo được gợi ý</div></div>';
            return;
        }

        const ctx = data.context || {};

        // Show context info card
        if (infoEl) {
            const periodLabels = {
                early_morning: '🌅 Sáng sớm', morning: '☀️ Buổi sáng',
                midday: '🌞 Giữa trưa', afternoon: '🌤️ Chiều',
                evening: '🌆 Chiều tối', night: '🌙 Đêm', late_night: '🌌 Khuya',
            };
            const activityLabels = {
                workout: '💪 Tập luyện', study: '📚 Học tập',
                relax: '😌 Thư giãn', commute: '🚗 Di chuyển',
                party: '🎉 Tiệc tùng', sleep: '😴 Ngủ',
                focus: '🎯 Tập trung', cooking: '🍳 Nấu ăn',
                morning_routine: '🌅 Buổi sáng',
            };

            infoEl.style.display = 'block';
            infoEl.innerHTML = `
                <div class="context-info-grid">
                    <div class="context-info-item">
                        <span class="context-info-label">Thời điểm</span>
                        <span class="context-info-value">${periodLabels[ctx.period] || esc(ctx.period)} (${String(ctx.hour).padStart(2,'0')}:00)</span>
                    </div>
                    ${ctx.activity ? `<div class="context-info-item">
                        <span class="context-info-label">Hoạt động</span>
                        <span class="context-info-value">${activityLabels[ctx.activity] || esc(ctx.activity)}</span>
                    </div>` : ''}
                    ${ctx.weather ? `<div class="context-info-item">
                        <span class="context-info-label">Thời tiết</span>
                        <span class="context-info-value">${esc(ctx.weather)}</span>
                    </div>` : ''}
                    <div class="context-info-item">
                        <span class="context-info-label">Mục tiêu V-A</span>
                        <span class="context-info-value">Valence ${ctx.target_valence} · Arousal ${ctx.target_arousal}</span>
                    </div>
                    <div class="context-info-item">
                        <span class="context-info-label">Hồ sơ cá nhân</span>
                        <span class="context-info-value">${ctx.has_user_profile ? '✅ Đã áp dụng' : '⚪ Chưa có'}</span>
                    </div>
                </div>
            `;
        }

        const songs = data.songs.map(s => _normalizeSong(s));
        await _checkAudioBatch(songs);

        resultsEl.innerHTML = `
            <div class="ai-results-header">
                <div class="section-title" style="font-size:1.1rem">🌤️ Nhạc phù hợp ngữ cảnh</div>
                <div class="ai-results-count">${data.count} bài hát</div>
            </div>
            <div class="ai-results-actions">
                <button class="btn btn-primary btn-sm" onclick="playAiResults()">
                    <svg viewBox="0 0 24 24" fill="currentColor" style="width:14px;height:14px"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    Phát tất cả
                </button>
                <button class="btn btn-ghost btn-sm" onclick="addAiResultsToQueue()">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    Thêm vào hàng đợi
                </button>
            </div>
            <div class="song-list">
                ${songs.map((s, i) => songRowHTML(s, i + 1)).join('')}
            </div>
        `;

        window._lastAiResults = songs;
    } catch (e) {
        resultsEl.innerHTML = '<div class="empty-state"><div class="empty-state-icon">😕</div><div class="empty-state-title">Lỗi tạo gợi ý</div></div>';
        app.toast(e.message, 'error');
    }
}

// ══════════════════════════════════════════════════════════════════════════
// Musical DNA
// ══════════════════════════════════════════════════════════════════════════

// ══════════════════════════════════════════════════════════════════════════
// Init
// ══════════════════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => app.init());

window.app = app;
window.router = router;
