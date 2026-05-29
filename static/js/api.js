/**
 * Brightify — API Client Module
 * Handles all backend communication
 */

const API = {
    // ── Music Browse ─────────────────────────────────────────────────────
    async getSongs(params = {}) {
        const q = new URLSearchParams(params).toString();
        return this._get(`/api/songs?${q}`);
    },

    async getFeatured(count = 12) {
        return this._get(`/api/songs/featured?count=${count}`);
    },

    async getNewReleases(count = 12) {
        return this._get(`/api/songs/new-releases?count=${count}`);
    },

async getRandomSongs(count = 10) {
        return this._get(`/api/songs/random?count=${count}`);
    },

    async getTimeOfDaySongs(period, count = 14) {
        return this._get(`/api/songs/time-of-day?period=${encodeURIComponent(period)}&count=${count}`);
    },

    async searchSongs(query, limit = 20) {
        return this._get(`/api/songs/search?q=${encodeURIComponent(query)}&limit=${limit}`);
    },

    async getSongDetails(songId) {
        return this._get(`/api/song/${songId}`);
    },

    async getSimilarSongs(songId, count = 10) {
        return this._get(`/api/song/${songId}/similar?count=${count}`);
    },

    async getTrackInfo(songIndex) {
        return this._get(`/api/track/info/${songIndex}`);
    },

    // ── Artists ──────────────────────────────────────────────────────────
    async getArtists(limit = 50) {
        return this._get(`/api/artists?limit=${limit}`);
    },

    async getArtistSongs(artistName) {
        return this._get(`/api/artists/${encodeURIComponent(artistName)}/songs`);
    },

    // ── Genres ──────────────────────────────────────────────────────────
    async getGenres() {
        return this._get('/api/genres');
    },

    // ── AI Recommendations ──────────────────────────────────────────────
    async recommendByColor(colors, topK = 10, diversityPenalty = 0.15) {
        return this._post('/api/recommend/color', {
            colors, top_k: topK, diversity_penalty: diversityPenalty,
        });
    },

    async recommendByLyrics(keywords, topK = 10) {
        return this._post('/api/recommend/lyrics', {
            keywords, top_k: topK,
        });
    },

    async recommendByImage(file, topK = 10) {
        const form = new FormData();
        form.append('file', file);
        form.append('top_k', topK);
        const res = await fetch('/api/recommend/image', { method: 'POST', body: form });
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        return res.json();
    },

    // ── Audio ────────────────────────────────────────────────────────────
    async getBatchAudioStatus(trackIds) {
        if (!trackIds.length) return { status: {} };
        return this._get(`/api/audio/batch-status?track_ids=${trackIds.join(',')}`);
    },

    async getAudioStats() {
        return this._get('/api/audio/stats');
    },

    getStreamUrl(trackId) {
        return `/api/audio/stream/${trackId}`;
    },

    getAlbumArtUrl(trackId) {
        return `/api/album-art/${trackId}`;
    },

    // ── System ──────────────────────────────────────────────────────────
    async getStatistics() {
        return this._get('/api/statistics');
    },

    async getMoods() {
        return this._get('/api/moods');
    },

    async getImageStatus() {
        return this._get('/api/image/status');
    },

    // ── Emotion Journey ─────────────────────────────────────────────────
    async getEmotionJourney(startValence, startArousal, endValence, endArousal, steps = 10) {
        return this._post('/api/recommend/emotion-journey', {
            start_valence: startValence,
            start_arousal: startArousal,
            end_valence: endValence,
            end_arousal: endArousal,
            steps,
        });
    },

    // ── Smart Context Engine ────────────────────────────────────────────
    async getContextMix({ hour, dayOfWeek, activity, season, weather,
                          userHistory, userLiked, count } = {}) {
        return this._post('/api/recommend/context-mix', {
            hour: hour ?? null,
            day_of_week: dayOfWeek ?? null,
            activity: activity || null,
            season: season || null,
            weather: weather || null,
            user_history: userHistory || null,
            user_liked: userLiked || null,
            count: count || 15,
        });
    },

    // ── Internal ─────────────────────────────────────────────────────────
    async _get(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`API ${res.status}: ${url}`);
        return res.json();
    },

    async _post(url, body) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `API ${res.status}`);
        }
        return res.json();
    },

    async _put(url, body) {
        const res = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error(`API ${res.status}`);
        return res.json();
    },

    async _delete(url) {
        const res = await fetch(url, { method: 'DELETE' });
        if (!res.ok) throw new Error(`API ${res.status}`);
        return res.json();
    },

    /** Fire-and-forget POST — swallows errors so tracking never breaks the UI. */
    async _postSilent(url, body) {
        try {
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            return res.ok ? await res.json() : null;
        } catch { return null; }
    },
};

window.API = API;
