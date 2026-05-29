// ══════════════════════════════════════════════════════════════════════════
// AI Lab — Color & Image
// ══════════════════════════════════════════════════════════════════════════

let _selectedColors = [];

function switchAiTab(tab) {
    document.querySelectorAll('.ai-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    ['color', 'journey'].forEach(t => {
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

// (Lyrics Mood Search tab removed — F3 unified search now covers vibe/lyrics
//  queries from the global search bar.)

