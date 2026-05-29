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

// ══════════════════════════════════════════════════════════════════════════
// F2 — Mood Shift: 1-tap need-based journeys (Home card + Player button)
// User picks only the DESTINATION (the need); the start point is auto-detected
// from the now-playing song so the machine plans the path (P7). Falls back to a
// sensible default start when nothing is playing. No V-A picker, no extra screen.
// ══════════════════════════════════════════════════════════════════════════
const MOOD_SHIFTS = {
    lift:  { label: '🌅 Vực dậy',   end: [0.85, 0.65], start: [0.25, 0.35], desc: 'Nâng tâm trạng dần lên vui tươi' },
    calm:  { label: '🧘 Hạ lo âu',  end: [0.62, 0.20], start: [0.40, 0.82], desc: 'Đưa từ căng thẳng về bình yên' },
    sleep: { label: '🌙 Ru ngủ',    end: [0.48, 0.10], start: [0.50, 0.48], desc: 'Hạ năng lượng để dễ ngủ' },
    focus: { label: '🎯 Tập trung', end: [0.60, 0.42], start: [0.50, 0.62], desc: 'Ổn định để tập trung' },
};

async function startMoodShift(key) {
    const m = MOOD_SHIFTS[key];
    if (!m) return;
    const cur = window.player?.getCurrentSong?.() || null;
    const startTrackId = cur?.track_id || null;
    // With a now-playing song, let the backend resolve the start V-A from it;
    // otherwise seed the journey with the preset's default start.
    const sv = startTrackId ? null : m.start[0];
    const sa = startTrackId ? null : m.start[1];

    app.toast(`${m.label} — đang tạo hành trình…`, 'info');
    try {
        const data = await API.getEmotionJourney(sv, sa, m.end[0], m.end[1], 8, { startTrackId });
        if (!data.success || !data.songs?.length) { app.toast('Không tạo được hành trình', 'error'); return; }
        const songs = data.songs.map(s => _normalizeSong(s));
        await _checkAudioBatch(songs);
        player.loadQueue(songs, 0, 'emotion-journey');
        const from = startTrackId && cur ? `“${cur.track_name}”` : 'tâm trạng hiện tại';
        app.toast(`${m.label}: dẫn bạn từ ${from} qua ${songs.length} bài`, 'success');
    } catch (e) {
        app.toast(e.message || 'Lỗi tạo hành trình', 'error');
    }
}

// Player "đổi mood" button → popover of mood-shift destinations.
function showMoodMenu() {
    document.querySelectorAll('.speed-picker-popup').forEach(m => m.remove());
    const btn = document.getElementById('btn-mood');
    if (!btn) return;
    const rect = btn.getBoundingClientRect();

    const popup = document.createElement('div');
    popup.className = 'speed-picker-popup';
    popup.style.left = `${rect.left + rect.width / 2}px`;
    popup.style.bottom = `${window.innerHeight - rect.top + 8}px`;
    popup.innerHTML = `
        <div class="speed-picker-title">Đổi tâm trạng</div>
        ${Object.entries(MOOD_SHIFTS).map(([k, m]) => `
            <div class="speed-picker-item" data-mood="${k}" title="${esc(m.desc)}">${m.label}</div>
        `).join('')}
    `;
    document.body.appendChild(popup);

    popup.addEventListener('click', (e) => {
        const item = e.target.closest('[data-mood]');
        if (!item) return;
        startMoodShift(item.dataset.mood);
        popup.remove();
        document.removeEventListener('click', dismiss);
    });
    const dismiss = (e) => {
        if (!popup.contains(e.target) && e.target !== btn) {
            popup.remove();
            document.removeEventListener('click', dismiss);
        }
    };
    setTimeout(() => document.addEventListener('click', dismiss), 0);
}

