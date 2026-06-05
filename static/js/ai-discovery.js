// ══════════════════════════════════════════════════════════════════════════
// AI Lab — Color & Image
// ══════════════════════════════════════════════════════════════════════════

let _selectedColors = [];

// V23: journey tab merged into colour (2-colour journey). Only 'color' remains.
function switchAiTab(tab) {
    document.querySelectorAll('.ai-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    const el = document.getElementById('tab-color');
    if (el) el.style.display = 'block';
}

function adjColorCount(d) {
    const el = document.getElementById('color-count');
    if (!el) return;
    el.value = Math.max(5, Math.min(25, parseInt(el.value) + d));
    document.getElementById('color-count-val').textContent = el.value;
}

// ══════════════════════════════════════════════════════════════════════════
// Color Picker — Emotion Cards
// ══════════════════════════════════════════════════════════════════════════

function initColorPicker() {
    // Reset color state on every page render
    _selectedColors = [];

    // Render palette presets
    // V12: 3-colour "mood blends" (union aggregation gives a rich mixed-mood playlist)
    const palettes = [
        { name: '🌅 Hoàng hôn',   colors: ['#F38400','#BE0032','#F3C300'] },
        { name: '🌊 Trầm lặng',   colors: ['#0067A5','#3AB09E','#848482'] },
        { name: '🌿 An yên',      colors: ['#008856','#3AB09E','#848482'] },
        { name: '🔥 Bùng cháy',   colors: ['#BE0032','#F38400','#9C4F96'] },
        { name: '🌸 Ngọt ngào',   colors: ['#FFB7C5','#F3C300','#F2F3F4'] },
        { name: '🌙 Cô đơn',      colors: ['#222222','#848482','#80461B'] },
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
}

// ── Color helpers ──
function _rgbToHex(r, g, b) { return '#' + [r,g,b].map(c => c.toString(16).padStart(2,'0')).join(''); }

function addSelectedColor(hex) {
    // V23: cap 2. 1 màu = mood tĩnh; 2 màu = hành trình A→B (Iso-Principle).
    if (_selectedColors.length >= 2) { app.toast('Tối đa 2 màu (1 màu = tâm trạng, 2 màu = hành trình)', 'info'); return; }
    if (_selectedColors.includes(hex)) return;
    _selectedColors.push(hex);
    _updateColorPickerUI();
}

// V12: tap a colour card → select AND run immediately ("chạy ngay", friendly).
// Tapping a colour already selected toggles it off. Adding more re-runs.
function pickColor(hex) {
    if (_selectedColors.includes(hex)) {
        removeSelectedColor(_selectedColors.indexOf(hex));
    } else if (_selectedColors.length < 2) {   // V23: cap 2 (mood journey)
        _selectedColors.push(hex);
        _updateColorPickerUI();
    } else {
        app.toast('Tối đa 2 màu (1 màu = tâm trạng, 2 màu = hành trình)', 'info');
        return;
    }
    if (_selectedColors.length > 0) getColorRecommendations();
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
    _selectedColors = [...p.colors].slice(0, 2);   // V23: cap 2 (mood journey)
    _updateColorPickerUI();
    document.querySelectorAll('.color-palette-btn').forEach((b, i) => b.classList.toggle('active', i === paletteIdx));
    getColorRecommendations();   // run immediately
}

function _updateColorPickerUI() {
    const dotsEl = document.getElementById('color-selected-dots');
    const countEl = document.getElementById('color-selected-count');
    const clearBtn = document.getElementById('btn-clear-colors');
    // WCAG 1.4.1: non-colour selected-state on each swatch (border/check + aria-pressed),
    // so selection is conveyed without relying on colour alone.
    const sel = new Set(_selectedColors.map(c => c.toUpperCase()));
    document.querySelectorAll('.color-emotion-card-v2').forEach(card => {
        const on = sel.has((card.dataset.color || '').toUpperCase());
        card.classList.toggle('selected', on);
        card.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    if (countEl) countEl.textContent = `${_selectedColors.length}/2`;
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
        const data = await API.recommendByColor(_selectedColors, count, 0.15);
        const journey = data.query?.journey;
        const modeLabel = journey ? ' (hành trình)' : '';
        renderAiResults(results, data.results, `Nhạc phù hợp với ${_selectedColors.join(', ')}${modeLabel}`, 'color');
        // V23: 2 colours = mood JOURNEY → show "Từ [mood A] → [mood B]" banner + gradient.
        // The playlist is ordered to flow smoothly from A's mood to B's (Iso-Principle).
        if (journey && journey.from && journey.to) {
            results.insertAdjacentHTML('afterbegin', `
                <div class="color-journey-banner" role="note"
                     style="--c-from:${safeColor(journey.from.hex)};--c-to:${safeColor(journey.to.hex)}">
                    <span class="cjb-grad" aria-hidden="true"></span>
                    <span class="cjb-text">🎯 Hành trình tâm trạng:
                        <strong>${esc(journey.from.mood || '')}</strong>
                        <span class="cjb-arrow">→</span>
                        <strong>${esc(journey.to.mood || '')}</strong>
                    </span>
                    <span class="cjb-hint">playlist chuyển dần, nghe theo thứ tự</span>
                </div>`);
        }
        // V12: emotion bridge chip — make the colour→emotion→music link visible
        // (Palmer/PLOS: emotion mediates the colour↔music correspondence).
        const bridge = data.query?.bridge;
        if (!journey && Array.isArray(bridge) && bridge.length) {
            const items = bridge.map(b => `
                <span class="color-bridge-item" title="Valence ${b.valence} · Arousal ${b.arousal}">
                    <span class="color-bridge-dot" style="background:${b.hex}"></span>
                    ${b.emotion_vi}
                </span>`).join('<span class="color-bridge-sep">·</span>');
            results.insertAdjacentHTML('afterbegin', `
                <div class="color-bridge">
                    <span class="color-bridge-label">🎨 AI cảm nhận màu của bạn là</span>
                    ${items}
                    <span class="color-bridge-arrow">→ nhạc bên dưới</span>
                </div>`);
        }
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

// (Lyrics Mood Search tab removed — F3 unified search now covers vibe/lyrics
//  queries from the global search bar.)

