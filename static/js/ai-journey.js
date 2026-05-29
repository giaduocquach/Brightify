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
// F2 — Mood Shift: need-based journeys (Home card · Player button · AI Lab)
// User picks only the DESTINATION (the need); the start is auto-detected from the
// now-playing song so the machine plans the path (P7). F2.1: generates then shows
// a PREVIEW (arc + first songs + duration) before committing — "see the mood
// before you press play" — instead of playing blind.
// ══════════════════════════════════════════════════════════════════════════
const MOOD_SHIFTS = {
    lift:  { label: '🌅 Vực dậy',   end: [0.85, 0.65], start: [0.25, 0.35], desc: 'Nâng tâm trạng dần lên vui tươi' },
    calm:  { label: '🧘 Hạ lo âu',  end: [0.62, 0.20], start: [0.40, 0.82], desc: 'Đưa từ căng thẳng về bình yên' },
    sleep: { label: '🌙 Ru ngủ',    end: [0.48, 0.10], start: [0.50, 0.48], desc: 'Hạ năng lượng để dễ ngủ' },
    focus: { label: '🎯 Tập trung', end: [0.60, 0.42], start: [0.50, 0.62], desc: 'Ổn định để tập trung' },
};

let _preparedJourney = null;

async function openMoodPreview(key) {
    const m = MOOD_SHIFTS[key];
    if (!m) return;
    const cur = window.player?.getCurrentSong?.() || null;
    const startTrackId = cur?.track_id || null;
    // With a now-playing song the backend resolves the start V-A from it;
    // otherwise seed with the preset's default start.
    const sv = startTrackId ? null : m.start[0];
    const sa = startTrackId ? null : m.start[1];

    _showJourneyPreviewSheet(`<div class="loading-inline"><div class="loader"></div>${esc(m.label)} — đang dựng hành trình…</div>`);
    try {
        const data = await API.getEmotionJourney(sv, sa, m.end[0], m.end[1], 8, { startTrackId });
        if (!data.success || !data.songs?.length) { app.toast('Không tạo được hành trình', 'error'); closeJourneyPreview(); return; }
        _preparedJourney = { label: m.label, desc: m.desc, data, fromName: (startTrackId && cur) ? cur.track_name : null };
        _renderJourneyPreview();
    } catch (e) {
        app.toast(e.message || 'Lỗi tạo hành trình', 'error');
        closeJourneyPreview();
    }
}

function _showJourneyPreviewSheet(innerHtml) {
    let ov = document.getElementById('journey-preview-overlay');
    if (!ov) {
        ov = document.createElement('div');
        ov.id = 'journey-preview-overlay';
        ov.style.cssText = 'position:fixed;inset:0;z-index:300;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.55);backdrop-filter:blur(4px)';
        ov.addEventListener('click', (e) => { if (e.target === ov) closeJourneyPreview(); });
        document.body.appendChild(ov);
    }
    ov.innerHTML = `<div class="journey-preview-card" style="width:min(440px,92vw);max-height:86vh;overflow:auto;background:var(--surface,#15131f);border:1px solid var(--border);border-radius:16px;padding:18px;box-shadow:0 20px 60px rgba(0,0,0,.5)">${innerHtml}</div>`;
    ov.style.display = 'flex';
}

function closeJourneyPreview() {
    const ov = document.getElementById('journey-preview-overlay');
    if (ov) ov.style.display = 'none';
}

function _renderJourneyPreview() {
    const pj = _preparedJourney;
    if (!pj) return;
    const songs = pj.data.songs, N = songs.length;
    const curMood = songs[0]?.fused_emotion || '—';
    const destMood = songs[N - 1]?.fused_emotion || '—';
    const estMin = Math.round(N * 3.5);
    const first = songs.slice(0, 3).map((s, i) => `
        <div style="display:flex;align-items:center;gap:8px;padding:4px 0">
            <span style="width:18px;color:var(--text-secondary);font-size:.78rem">${i + 1}</span>
            <span style="flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:.85rem">${esc(s.track_name)} <span style="color:var(--text-secondary)">· ${esc(s.artist)}</span></span>
        </div>`).join('');
    _showJourneyPreviewSheet(`
        <div style="font-size:1.05rem;font-weight:700;margin-bottom:2px">${esc(pj.label)}</div>
        <div style="font-size:.8rem;color:var(--text-secondary);margin-bottom:12px">${esc(pj.desc || '')}</div>
        <canvas id="journey-preview-canvas" width="380" height="96" style="width:100%;height:96px;margin-bottom:10px"></canvas>
        <div style="font-size:.8rem;color:var(--text-secondary);margin-bottom:10px">
            ${pj.fromName ? `Từ “${esc(pj.fromName)}” · ` : ''}đang: ${esc(curMood)} → hướng tới: ${esc(destMood)} · ${N} bài · ~${estMin} phút
        </div>
        <div style="border-top:1px solid var(--border);padding-top:8px;margin-bottom:14px">${first}${N > 3 ? `<div style="font-size:.78rem;color:var(--text-secondary);padding-top:4px">…và ${N - 3} bài nữa</div>` : ''}</div>
        <div style="display:flex;gap:8px">
            <button class="btn btn-primary btn-glow" style="flex:1" onclick="playPreparedJourney()">
                <svg viewBox="0 0 24 24" fill="currentColor" style="width:16px;height:16px"><polygon points="5 3 19 12 5 21 5 3"/></svg> Bắt đầu hành trình
            </button>
            <button class="btn btn-ghost" onclick="closeJourneyPreview()">Hủy</button>
        </div>
    `);
    // Reuse the player mini-arc renderer (bigger canvas) for a consistent look.
    _drawJourneyMiniArc(document.getElementById('journey-preview-canvas'), { songs }, -1);
}

function playPreparedJourney() {
    const pj = _preparedJourney;
    if (!pj) return;
    const songs = pj.data.songs.map(s => _normalizeSong(s));
    // Raw API songs keep V-A / step / emotion that _normalizeSong drops.
    window._activeJourney = {
        label: pj.label,
        songs: pj.data.songs,
        waypoints: pj.data.waypoints,
        info: pj.data.journey_info,
        ids: new Set(pj.data.songs.map(s => s.track_id)),
    };
    closeJourneyPreview();
    _checkAudioBatch(songs).then(() => {
        player.loadQueue(songs, 0, 'emotion-journey');
        renderJourneyStrip();
    });
    app.toast(`${pj.label}: bắt đầu hành trình ${songs.length} bài`, 'success');
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
        openMoodPreview(item.dataset.mood);
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

// ── F2.2 Journey Mode: the arc you're being guided along, in the Player ──────
// While an emotion journey plays, a slim strip floats above the player bar and
// shows the emotional arc (energy over the steps) with a "you are here" dot,
// step k/N, and the current → destination mood. Makes the iso-principle felt.
function renderJourneyStrip() {
    const strip = document.getElementById('journey-strip');
    if (!strip) return;
    const j = window._activeJourney;
    const cur = window.player?.getCurrentSong?.() || null;
    const active = j && cur && window.player?._playSource === 'emotion-journey' && j.ids.has(cur.track_id);
    if (!active) { strip.style.display = 'none'; return; }

    const idx = j.songs.findIndex(s => s.track_id === cur.track_id);
    const N = j.songs.length;
    const curMood = j.songs[idx]?.fused_emotion || '';
    const destMood = j.songs[N - 1]?.fused_emotion || '';

    // Anchor just above the player bar regardless of its height.
    const bar = document.getElementById('player-bar');
    const barTop = bar ? bar.getBoundingClientRect().top : window.innerHeight - 90;
    strip.style.cssText = `position:fixed;left:50%;transform:translateX(-50%);bottom:${window.innerHeight - barTop + 6}px;z-index:101;display:flex;align-items:center;gap:12px;padding:8px 12px;border-radius:12px;background:rgba(20,18,32,.93);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border:1px solid var(--border);box-shadow:0 6px 24px rgba(0,0,0,.4);max-width:min(560px,92vw)`;
    strip.innerHTML = `
        <canvas id="journey-mini-canvas" width="200" height="42" style="flex-shrink:0"></canvas>
        <div style="min-width:0;flex:1">
            <div style="font-size:.82rem;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(j.label)} · Bước ${idx + 1}/${N}</div>
            <div style="font-size:.72rem;color:var(--text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">đang: ${esc(curMood || '—')} → hướng tới: ${esc(destMood || '—')}</div>
        </div>
        <button onclick="exitJourneyMode()" title="Thoát chế độ hành trình" style="flex-shrink:0;background:none;border:none;color:var(--text-secondary);cursor:pointer;font-size:1.15rem;line-height:1;padding:2px 4px">×</button>
    `;
    strip.style.display = 'flex';
    _drawJourneyMiniArc(document.getElementById('journey-mini-canvas'), j, idx);
}

function _drawJourneyMiniArc(canvas, j, curIdx) {
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height, pad = 8;
    ctx.clearRect(0, 0, W, H);
    const songs = j.songs, N = songs.length;
    const X = i => pad + (N <= 1 ? 0 : i / (N - 1)) * (W - pad * 2);
    const Y = a => pad + (1 - a) * (H - pad * 2);  // arousal as height: energy rising/falling
    // Gradient path (mood hue progresses start→end)
    ctx.lineWidth = 2;
    for (let i = 0; i < N - 1; i++) {
        const a1 = songs[i].song_arousal ?? 0.5, a2 = songs[i + 1].song_arousal ?? 0.5;
        const t = i / Math.max(1, N - 1);
        const g = ctx.createLinearGradient(X(i), 0, X(i + 1), 0);
        g.addColorStop(0, `hsla(${260 + t * 120},70%,65%,.7)`);
        g.addColorStop(1, `hsla(${260 + (t + 1 / N) * 120},70%,65%,.7)`);
        ctx.strokeStyle = g;
        ctx.beginPath(); ctx.moveTo(X(i), Y(a1)); ctx.lineTo(X(i + 1), Y(a2)); ctx.stroke();
    }
    // Step dots; current step enlarged with a white ring
    songs.forEach((s, i) => {
        const a = s.song_arousal ?? 0.5, isCur = i === curIdx, t = i / Math.max(1, N - 1);
        ctx.beginPath(); ctx.arc(X(i), Y(a), isCur ? 4.5 : 2.5, 0, Math.PI * 2);
        ctx.fillStyle = `hsl(${260 + t * 120},75%,${isCur ? 70 : 52}%)`;
        ctx.fill();
        if (isCur) { ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.stroke(); }
    });
}

function exitJourneyMode() {
    window._activeJourney = null;
    const strip = document.getElementById('journey-strip');
    if (strip) strip.style.display = 'none';
}

window.renderJourneyStrip = renderJourneyStrip;
window.exitJourneyMode = exitJourneyMode;
window.openMoodPreview = openMoodPreview;
window.closeJourneyPreview = closeJourneyPreview;
window.playPreparedJourney = playPreparedJourney;
window.showMoodMenu = showMoodMenu;

