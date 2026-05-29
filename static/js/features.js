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
// Smart Crossfade engine: feature-aware (tempo / key / mood / energy / LUFS / cue points)
// See docs/PLAN_SMART_CROSSFADE.md and core in player.js::planCrossfade
const crossfade = {
    enabled: false,
    smart: true,     // policy engine (planCrossfade) decides duration / curve / gains
    duration: 6,     // legacy fallback duration when smart=false (was 15)

    toggle() {
        this.enabled = !this.enabled;
        localStorage.setItem('bf_crossfade', this.enabled);
        const btn = document.getElementById('btn-crossfade');
        if (btn) btn.classList.toggle('active', this.enabled);
        const label = this.smart ? '🧠 Smart Crossfade' : `🔀 Crossfade (${this.duration}s)`;
        app.toast(this.enabled ? `${label} bật` : '🔀 Crossfade tắt', 'info');
    },

    toggleSmart() {
        this.smart = !this.smart;
        localStorage.setItem('bf_crossfade_smart', this.smart);
        app.toast(this.smart ? '🧠 Smart mode on' : `🔀 Legacy ${this.duration}s fixed mode`, 'info');
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
if (localStorage.getItem('bf_crossfade_smart') === 'false') {
    crossfade.smart = false;
}

