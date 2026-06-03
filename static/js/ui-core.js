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

            // F3 — layered unified search: literal matches (name/artist/lyrics)
            // on top, semantically-related / same-vibe songs below.
            const _searchItem = (s) => {
                const art = s.has_album_art ? `<img src="${safeUrl(s.album_art_url)}" alt="">` : `<span style="color:${safeColor(s.color_hex)}">🎵</span>`;
                const tag = s.match_kind === 'lyrics' ? ' <span style="font-size:.62rem;color:var(--text-secondary)">· lời</span>' : '';
                return `<div class="search-dropdown-item" data-song='${JSON.stringify(s).replace(/'/g,"&#39;")}'>
                    <div class="search-dropdown-art">${art}</div>
                    <div class="search-dropdown-info">
                        <div class="search-dropdown-title">${esc(s.track_name)}${tag}</div>
                        <div class="search-dropdown-artist">${esc(s.artist)}</div>
                    </div>
                </div>`;
            };
            const _group = (label, songs) => songs && songs.length
                ? `<div class="search-dropdown-group" style="padding:6px 12px 2px;font-size:.68rem;text-transform:uppercase;letter-spacing:.04em;color:var(--text-secondary)">${label}</div>${songs.map(_searchItem).join('')}`
                : '';

            const showResults = async (query) => {
                if (!query || query.length < 2) { dropdown.classList.remove('visible'); return; }
                try {
                    const data = await API.searchUnified(query, 6, 5);
                    const matches = data.matches || [], related = data.related || [];
                    if (!matches.length && !related.length) {
                        dropdown.innerHTML = '<div class="search-dropdown-empty">Không tìm thấy kết quả</div>';
                    } else {
                        dropdown.innerHTML =
                            _group('🎯 Khớp nhất', matches) +
                            _group('🔗 Liên quan · cùng vibe', related);
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
                else if (e.key === 'Enter') {
                    const q = searchInput.value.trim();
                    if (q.length >= 2) {
                        dropdown.classList.remove('visible');
                        searchInput.blur();
                        router.navigate(`search/${encodeURIComponent(q)}`);  // F3 — full results page
                    }
                }
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
        router.register('search', (c, h) => pages.search(c, h));

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

    // E6 — "why this song" chip (colour query only). Keep `why` out of the embedded
    // JSON so play/context-menu payloads stay lean; render it as a small caption.
    const why = song.why;
    const songData = why ? (({ why, ...rest }) => rest)(song) : song;
    const songJson = JSON.stringify(songData).replace(/"/g, '&quot;');
    let whyHTML = '';
    if (why && why.reason) {
        const pct = Math.round((why.mood_match ?? 0) * 100);
        const dot = why.color_hex ? `<span class="why-dot" style="background:${safeColor(why.color_hex)}"></span>` : '';
        const detail = `Bài: V ${why.song_va?.[0]} · A ${why.song_va?.[1]} | Màu: V ${why.color_va?.[0]} · A ${why.color_va?.[1]}`;
        whyHTML = `<div class="song-row-why" title="${esc(detail)}">${dot}${esc(why.reason)} · khớp ${pct}%</div>`;
    }

    return `
        <div class="song-row" data-idx="${song.track_id}" data-song-index="${song.track_id}" data-song-json="${songJson}" onclick="playSong(${songJson}, event)"
             oncontextmenu="app.showContextMenu(event, ${songJson})">
            <div class="song-row-num">${num}</div>
            <div class="song-row-art">${art}</div>
            <div class="song-row-info">
                <div class="song-row-title">${esc(song.track_name)}</div>
                <div class="song-row-artist">${esc(song.artist)}</div>
                ${whyHTML}
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

