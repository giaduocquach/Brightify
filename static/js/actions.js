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
        why: r.why || null,   // E6: colour "why this song" explanation (colour query only)
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

// Cached coordinates — synchronous, instant, no permission prompt. The Home
// shelf reads this so it can render immediately; null until a fix is cached.
function _getCachedGeo() {
    try { return JSON.parse(localStorage.getItem('bf_geo') || 'null'); } catch (e) { return null; }
}

// Best-effort BACKGROUND refresh of the user's coordinates for location-accurate
// weather. May prompt for permission once; the result is cached for the NEXT
// visit, so it NEVER blocks the Home shelf from rendering. No-ops when geolocation
// is unsupported, denied, or a fresh (<6h) fix already exists. Coords rounded to
// ~1km (2 dp) — enough for weather, avoids storing a precise location.
function _refreshGeo() {
    if (!navigator.geolocation) return;
    const cached = _getCachedGeo();
    if (cached && cached.ts && (Date.now() - cached.ts) < 6 * 3600 * 1000) return;
    navigator.geolocation.getCurrentPosition(
        (pos) => {
            const geo = {
                lat: +pos.coords.latitude.toFixed(2),
                lon: +pos.coords.longitude.toFixed(2),
                ts: Date.now(),
            };
            try { localStorage.setItem('bf_geo', JSON.stringify(geo)); } catch (e) {}
        },
        () => {},   // denied / unavailable → keep falling back to the default city
        { timeout: 8000, maximumAge: 6 * 3600 * 1000 }
    );
}

// F1 — "Ngay bây giờ": context shelf that runs automatically on Home (no button).
// Uses the smart context engine (circadian + activity + season) now also wired to
// the VN holiday calendar + live weather via vn_context. Time/day auto-resolve
// server-side; the browser's current coordinates are passed for local weather.
// F3 — play a whole search-result group (matches / related) from the search page.
function playSearchResults(which) {
    const songs = which === 'related' ? window._searchRelated : window._searchMatches;
    if (songs?.length) player.loadQueue([...songs], 0, 'search');
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

