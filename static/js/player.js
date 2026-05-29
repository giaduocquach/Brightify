class MusicPlayer {
    constructor() {
        // Dual audio elements for seamless crossfade
        this._audioA = new Audio();
        this._audioB = new Audio();
        this.audio = this._audioA;
        this._audioInactive = this._audioB;
        this.queue = [];
        this.currentIndex = -1;
        this.isPlaying = false;
        this.shuffleOn = false;
        this.repeatMode = 'off'; // off, all, one
        this.radioMode = false;
        this.volume = 0.8;
        this.isMuted = false;
        this._prevVolume = 0.8;
        this._shuffleOrder = [];
        this._seekDragging = false;
        this._volDragging = false;
        this._crossfading = false;
        this._crossfadeNextIdx = -1;
        this._crossfadeInterval = null;
        this._crossfadeRaf = null;

        // Radio queue save/restore
        this._savedQueue = null;
        this._savedIndex = -1;
        this._radioSeedId = null; // track_id of the seed track for current radio queue

        // Audio visualizer
        this._audioCtx = null;
        this._analyser = null;
        this._sourceA = null;
        this._sourceB = null;
        this._dataArray = null;
        this._visualizerRunning = false;

        this.audio.volume = this.volume;

        // Audio events — delegated to both elements
        this._setupAudioEvents(this._audioA);
        this._setupAudioEvents(this._audioB);

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => this._onKeydown(e));

        // Restore volume
        const saved = localStorage.getItem('bf_volume');
        if (saved !== null) {
            this.volume = parseFloat(saved);
            this.audio.volume = this.volume;
        }

        // Radio mode starts OFF — no auto-restore from localStorage
        localStorage.setItem('bf_radio', false);

        this._initProgressBar();
        this._initVolumeBar();
    }

    _setupAudioEvents(el) {
        el.addEventListener('timeupdate', () => { if (this.audio === el) this._onTimeUpdate(); });
        el.addEventListener('ended', () => { if (this.audio === el) this._onTrackEnd(); });
        el.addEventListener('play', () => { if (this.audio === el) this._onPlay(); });
        el.addEventListener('pause', () => { if (this.audio === el) this._onPause(); });
        el.addEventListener('error', (e) => { if (this.audio === el) this._onError(e); });
        el.addEventListener('loadedmetadata', () => { if (this.audio === el) this._onLoaded(); });
    }

    // ── Public API ──────────────────────────────────────────────────────

    loadQueue(songs, startIndex = 0, source = 'browse') {
        // Reset radio mode when loading a new queue externally
        if (this.radioMode) {
            this.radioMode = false;
            localStorage.setItem('bf_radio', false);
            this._savedQueue = null;
            this._savedIndex = -1;
            this._radioSeedId = null;
            const btn = document.getElementById('btn-radio');
            if (btn) btn.classList.remove('radio-active');
        }
        this._playSource = source;
        // Leaving a journey queue exits Journey Mode (F2.2).
        if (source !== 'emotion-journey' && window.exitJourneyMode) window.exitJourneyMode();
        this.queue = songs.filter(s => s);
        this.currentIndex = -1;
        this._shuffleOrder = [];
        if (this.shuffleOn) this._generateShuffleOrder();
        if (this.queue.length > 0) {
            this.playIndex(startIndex);
        }
        this._updateQueuePanel();
        this._showPlayerBar();
    }

    addToQueue(song) {
        this.queue.push(song);
        if (this.shuffleOn) this._shuffleOrder.push(this.queue.length - 1);
        this._updateQueuePanel();
        if (this.queue.length === 1) {
            this.playIndex(0);
            this._showPlayerBar();
        }
        window.app?.toast(`Đã thêm "${song.track_name}" vào hàng đợi`, 'success');
    }

    playNext(song) {
        const insertAt = this.currentIndex + 1;
        this.queue.splice(insertAt, 0, song);
        if (this.shuffleOn) this._shuffleOrder.push(insertAt);
        this._updateQueuePanel();
        if (this.queue.length === 1) {
            this.playIndex(0);
            this._showPlayerBar();
        }
        window.app?.toast(`"${song.track_name}" sẽ phát tiếp theo`, 'success');
    }

    removeFromQueue(index) {
        if (index < 0 || index >= this.queue.length) return;
        if (index === this.currentIndex) return; // Can't remove currently playing
        this.queue.splice(index, 1);
        if (index < this.currentIndex) this.currentIndex--;
        this._updateQueuePanel();
    }

    playIndex(idx) {
        if (idx < 0 || idx >= this.queue.length) return;
        this._cancelCrossfade();

        // Track listen duration of the previous song before switching
        this._sendPlayComplete();

        this.currentIndex = idx;
        const song = this.queue[idx];

        // Initialize visualizer on first play (requires user gesture)
        this._initVisualizer();

        if (!song.has_audio || !song.audio_url) {
            this._updateUI(song);
            this._updatePlayBtn(false);
            window.app?.toast('Bài hát chưa có file audio', 'info');
            setTimeout(() => this.next(), 1500);
            return;
        }

        this.audio.src = song.audio_url;
        this.audio.load();
        // Apply current playback speed
        if (window.playbackSpeed) this.audio.playbackRate = window.playbackSpeed.current;
        this.audio.play().catch(() => {});
        this._songStartTime = Date.now();
        this._songStartTrackId = song.track_id;
        this._updateUI(song);
        this._updateQueuePanel();
        this._addToHistory(song);
        this._updateAmbientBg(song);
    }

    togglePlay() {
        if (this.queue.length === 0) return;
        if (this.currentIndex < 0) { this.playIndex(0); return; }
        if (this.isPlaying) {
            this.audio.pause();
        } else {
            this.audio.play().catch(() => {});
        }
    }

    next() {
        if (this.queue.length === 0) return;
        let nextIdx;
        if (this.repeatMode === 'one') {
            nextIdx = this.currentIndex;
        } else if (this.shuffleOn) {
            const pos = this._shuffleOrder.indexOf(this.currentIndex);
            nextIdx = this._shuffleOrder[(pos + 1) % this._shuffleOrder.length];
        } else {
            nextIdx = (this.currentIndex + 1) % this.queue.length;
        }
        this.playIndex(nextIdx);
    }

    prev() {
        if (this.queue.length === 0) return;
        if (this.audio.currentTime > 3) {
            this.audio.currentTime = 0;
            return;
        }
        let prevIdx;
        if (this.shuffleOn) {
            const pos = this._shuffleOrder.indexOf(this.currentIndex);
            prevIdx = this._shuffleOrder[(pos - 1 + this._shuffleOrder.length) % this._shuffleOrder.length];
        } else {
            prevIdx = (this.currentIndex - 1 + this.queue.length) % this.queue.length;
        }
        this.playIndex(prevIdx);
    }

    toggleShuffle() {
        this.shuffleOn = !this.shuffleOn;
        const btn = document.getElementById('btn-shuffle');
        if (btn) btn.classList.toggle('active', this.shuffleOn);
        if (this.shuffleOn) this._generateShuffleOrder();
        this._updateQueuePanel();
    }

    toggleRepeat() {
        const modes = ['off', 'all', 'one'];
        const idx = (modes.indexOf(this.repeatMode) + 1) % modes.length;
        this.repeatMode = modes[idx];
        const btn = document.getElementById('btn-repeat');
        const badge = document.getElementById('repeat-one-badge');
        if (btn) {
            btn.classList.toggle('active', this.repeatMode !== 'off');
            btn.title = this.repeatMode === 'one' ? 'Lặp 1 bài' :
                         this.repeatMode === 'all' ? 'Lặp tất cả' : 'Không lặp';
        }
        if (badge) {
            badge.style.display = this.repeatMode === 'one' ? 'flex' : 'none';
        }
    }

    async toggleRadio() {
        const btn = document.getElementById('btn-radio');
        if (!this.radioMode) {
            // Turning ON — build radio queue from currently playing song
            const song = this.getCurrentSong();
            if (!song) {
                window.app?.toast('📻 Chưa có bài hát đang phát', 'info');
                return;
            }
            // Save current queue for restore
            this._savedQueue = [...this.queue];
            this._savedIndex = this.currentIndex;
            // Show loading state
            if (btn) btn.classList.add('radio-active');
            window.app?.toast('📻 Đang tạo Radio...', 'info');
            // Build radio queue without restarting the current song
            const ok = await this._buildRadioQueue(song, true);
            if (ok) {
                this.radioMode = true;
                this._playSource = 'radio';
                localStorage.setItem('bf_radio', true);
            } else {
                if (btn) btn.classList.remove('radio-active');
            }
        } else {
            // Turning OFF
            this.radioMode = false;
            localStorage.setItem('bf_radio', false);
            if (btn) btn.classList.remove('radio-active');

            // Restore original queue only if still on the seed track
            const current = this.getCurrentSong();
            if (this._savedQueue && current && current.track_id === this._radioSeedId) {
                this.queue = this._savedQueue;
                this.currentIndex = this._savedIndex;
                this._shuffleOrder = [];
                if (this.shuffleOn) this._generateShuffleOrder();
                this._updateQueuePanel();
                window.app?.toast('📻 Radio tắt — Đã khôi phục hàng đợi', 'info');
            } else {
                // User switched tracks — keep current queue as-is
                this._updateQueuePanel();
                window.app?.toast('📻 Radio tắt — Hàng đợi giữ nguyên', 'info');
            }
            this._savedQueue = null;
            this._savedIndex = -1;
            this._radioSeedId = null;
        }
    }

    async _buildRadioQueue(song, keepPlaying = false) {
        try {
            const res = await API.getSimilarSongs(song.track_id, 30);
            if (!res.songs?.length) {
                window.app?.toast('📻 Không tìm được bài tương tự', 'info');
                return false;
            }

            let radioSongs = res.songs.filter(s => s.track_id !== song.track_id);

            // Deduplicate by track_id
            const seen = new Set();
            radioSongs = radioSongs.filter(s => {
                if (seen.has(s.track_id)) return false;
                seen.add(s.track_id);
                return true;
            });

            // Batch check audio availability
            const ids = radioSongs.filter(s => s.track_id).map(s => s.track_id);
            if (ids.length) {
                try {
                    const batch = await API.getBatchAudioStatus(ids);
                    radioSongs.forEach(s => {
                        if (batch.status?.[s.track_id]) {
                            s.has_audio = true;
                            s.audio_url = `/api/audio/stream/${s.track_id}`;
                        }
                    });
                } catch(e) {}
            }

            // Prioritize songs with audio
            radioSongs.sort((a, b) => (b.has_audio ? 1 : 0) - (a.has_audio ? 1 : 0));

            const newQueue = [song, ...radioSongs.slice(0, 30)];
            this.queue = newQueue;
            this.currentIndex = 0;
            this._radioSeedId = song.track_id;
            this._shuffleOrder = [];
            if (this.shuffleOn) this._generateShuffleOrder();
            this._updateQueuePanel();

            if (!keepPlaying) {
                // Only start playback for fresh radio (e.g., startSongRadio)
                window.app?.toast(`📻 Radio đang phát — ${newQueue.length} bài tương tự`, 'success');
            } else {
                // Toggle-on: just update the queue, don't restart audio
                window.app?.toast(`📻 Radio đang phát — ${newQueue.length} bài tương tự`, 'success');
            }
            return true;
        } catch(e) {
            console.warn('Radio build failed:', e);
            window.app?.toast('Lỗi tạo Radio', 'error');
            return false;
        }
    }

    async startSongRadio(song) {
        if (!song) return;
        // Save current queue for restore
        this._savedQueue = [...this.queue];
        this._savedIndex = this.currentIndex;
        const btn = document.getElementById('btn-radio');
        if (btn) btn.classList.add('radio-active');
        window.app?.toast('📻 Đang tạo Radio...', 'info');
        const ok = await this._buildRadioQueue(song);
        if (ok) {
            this.radioMode = true;
            localStorage.setItem('bf_radio', true);
            this.playIndex(0);
        } else {
            if (btn) btn.classList.remove('radio-active');
            this._savedQueue = null;
            this._savedIndex = -1;
        }
    }

    toggleMute() {
        this.isMuted = !this.isMuted;
        if (this.isMuted) {
            this._prevVolume = this.volume;
            if (this._gainNodeA && this._gainNodeB) {
                this._gainNodeA.gain.value = 0;
                this._gainNodeB.gain.value = 0;
            } else {
                this.audio.volume = 0;
            }
        } else {
            this.volume = this._prevVolume;
            if (this._gainNodeA && this._gainNodeB) {
                // Re-apply LUFS gain via _applyLufsGain (handles both paths)
                const song = this.queue[this.currentIndex];
                if (song) this._applyLufsGain(song);
            } else {
                this.audio.volume = this._prevVolume;
            }
        }
        this._updateVolumeUI();
    }

    setVolume(v) {
        this.volume = Math.max(0, Math.min(1, v));
        this.isMuted = false;
        // Smart Crossfade Phase 2: route through GainNode (LUFS-aware) when available
        if (this._gainNodeA && this._gainNodeB) {
            const song = this.queue[this.currentIndex];
            if (song) this._applyLufsGain(song);
            else {
                const active = (this.audio === this._audioA) ? this._gainNodeA : this._gainNodeB;
                if (active) active.gain.value = this.volume;
            }
        } else {
            this.audio.volume = this.volume;
        }
        localStorage.setItem('bf_volume', this.volume);
        this._updateVolumeUI();
    }

    toggleLike() {
        if (this.currentIndex < 0) return;
        const song = this.queue[this.currentIndex];
        if (!song) return;
        const liked = JSON.parse(localStorage.getItem('bf_liked') || '[]');
        const idx = liked.findIndex(s => s.track_id === song.track_id);
        const wasLiked = idx >= 0;
        if (wasLiked) {
            liked.splice(idx, 1);
            window.app?.toast('Đã bỏ thích', 'info');
        } else {
            liked.push({ ...song, liked_at: Date.now() });
            window.app?.toast('Đã thêm vào yêu thích ❤️', 'success');
        }
        localStorage.setItem('bf_liked', JSON.stringify(liked));
        this._updateLikeBtn();
        const isNowLiked = !wasLiked;
        // Update all heart buttons on the page for this song
        document.querySelectorAll(`[data-song-index="${song.track_id}"] .btn-song-like`).forEach(btn => {
            btn.classList.toggle('liked', isNowLiked);
            const svg = btn.querySelector('svg');
            if (svg) {
                svg.setAttribute('fill', isNowLiked ? 'var(--danger)' : 'none');
                svg.setAttribute('stroke', isNowLiked ? 'var(--danger)' : 'currentColor');
            }
        });
    }

    toggleQueue() {
        const panel = document.getElementById('queue-panel');
        if (panel) {
            panel.classList.toggle('queue-visible');
            const btn = document.getElementById('btn-queue');
            if (btn) btn.classList.toggle('active', panel.classList.contains('queue-visible'));
        }
    }

    getCurrentSong() {
        return this.currentIndex >= 0 ? this.queue[this.currentIndex] : null;
    }

    stop() {
        this._sendPlayComplete();
        this.audio.pause();
        this.audio.src = '';
        this._audioInactive.pause();
        this._audioInactive.src = '';
        this._cancelCrossfade();
        this.queue = [];
        this.currentIndex = -1;
        this.isPlaying = false;
        this.radioMode = false;
        this._savedQueue = null;
        this._savedIndex = -1;
        localStorage.setItem('bf_radio', false);
        const btn = document.getElementById('btn-radio');
        if (btn) btn.classList.remove('radio-active');
        const bar = document.getElementById('player-bar');
        if (bar) bar.classList.add('player-hidden');
        const queuePanel = document.getElementById('queue-panel');
        if (queuePanel) queuePanel.classList.remove('queue-visible');
        if (window.exitJourneyMode) window.exitJourneyMode();  // F2.2
        this._updateQueuePanel();
    }

    // ── Audio Visualizer ────────────────────────────────────────────────

    _initVisualizer() {
        if (this._audioCtx) return;
        try {
            this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            this._analyser = this._audioCtx.createAnalyser();
            this._analyser.fftSize = 128;
            this._analyser.smoothingTimeConstant = 0.82;
            this._sourceA = this._audioCtx.createMediaElementSource(this._audioA);
            this._sourceB = this._audioCtx.createMediaElementSource(this._audioB);
            // Smart Crossfade Phase 2: GainNodes between source and analyser
            // Chain: source → gainNode → analyser → destination
            // Allows LUFS-normalized per-track gain that survives crossfades cleanly.
            this._gainNodeA = this._audioCtx.createGain();
            this._gainNodeB = this._audioCtx.createGain();
            this._gainNodeA.gain.value = this.volume;
            this._gainNodeB.gain.value = this.volume;
            this._sourceA.connect(this._gainNodeA).connect(this._analyser);
            this._sourceB.connect(this._gainNodeB).connect(this._analyser);
            this._analyser.connect(this._audioCtx.destination);
            // HTMLAudio elements should now be at 1.0 (gain handled downstream)
            this._audioA.volume = 1.0;
            this._audioB.volume = 1.0;
            // Apply LUFS to currently playing song, if any
            const curSong = this.queue[this.currentIndex];
            if (curSong) this._applyLufsGain(curSong);
            this._dataArray = new Uint8Array(this._analyser.frequencyBinCount);
            // Smooth bar heights for lerping
            this._barSmooth = new Float32Array(16).fill(0);
            // Current visualizer colors (for smooth transitions)
            this._vizColor1 = { r: 167, g: 139, b: 250 }; // #a78bfa
            this._vizColor2 = { r: 103, g: 232, b: 249 }; // #67e8f9
            this._vizTargetColor1 = { ...this._vizColor1 };
            this._vizTargetColor2 = { ...this._vizColor2 };
            this._vizTime = 0;
            if (!this._visualizerRunning) {
                this._visualizerRunning = true;
                this._drawVisualizer();
            }
        } catch (e) {
            console.warn('Visualizer init failed:', e);
        }
    }

    _hexToRgb(hex) {
        const r = parseInt(hex.slice(1, 3), 16) || 0;
        const g = parseInt(hex.slice(3, 5), 16) || 0;
        const b = parseInt(hex.slice(5, 7), 16) || 0;
        return { r, g, b };
    }

    _lerpColor(current, target, t) {
        return {
            r: current.r + (target.r - current.r) * t,
            g: current.g + (target.g - current.g) * t,
            b: current.b + (target.b - current.b) * t,
        };
    }

    _rgbStr(c, a = 1) {
        return `rgba(${Math.round(c.r)},${Math.round(c.g)},${Math.round(c.b)},${a})`;
    }

    _updateVisualizerColors(song) {
        if (!song) return;
        const hex = song.color_hex || '#a78bfa';
        const base = this._hexToRgb(hex);
        // Primary color: song's color, brightened
        this._vizTargetColor1 = {
            r: Math.min(255, base.r + 50),
            g: Math.min(255, base.g + 50),
            b: Math.min(255, base.b + 50),
        };
        // Secondary: complementary-ish lighter color
        this._vizTargetColor2 = {
            r: Math.min(255, 255 - base.r * 0.3 + 80),
            g: Math.min(255, 255 - base.g * 0.3 + 80),
            b: Math.min(255, 255 - base.b * 0.3 + 80),
        };
    }

    _drawVisualizer() {
        const canvas = document.getElementById('visualizer-canvas');
        if (!canvas) {
            requestAnimationFrame(() => this._drawVisualizer());
            return;
        }
        const ctx = canvas.getContext('2d');
        const W = canvas.width;
        const H = canvas.height;
        const barCount = 16;
        const gap = 1.5;
        const barWidth = (W / barCount) - gap;
        const lerpSpeed = 0.18;
        const colorLerp = 0.03;

        const draw = () => {
            // Skip rendering when tab is hidden to save CPU
            if (document.hidden) {
                requestAnimationFrame(draw);
                return;
            }
            requestAnimationFrame(draw);
            this._vizTime += 0.02;

            // Smoothly transition colors
            this._vizColor1 = this._lerpColor(this._vizColor1, this._vizTargetColor1, colorLerp);
            this._vizColor2 = this._lerpColor(this._vizColor2, this._vizTargetColor2, colorLerp);

            ctx.clearRect(0, 0, W, H);

            if (!this.isPlaying || !this._analyser) {
                // Idle: gentle breathing wave
                for (let i = 0; i < barCount; i++) {
                    const breath = 2 + Math.sin(this._vizTime * 1.5 + i * 0.4) * 1.5;
                    this._barSmooth[i] += (breath - this._barSmooth[i]) * 0.08;
                    const barH = Math.max(1.5, this._barSmooth[i]);
                    const x = i * (barWidth + gap);
                    ctx.fillStyle = this._rgbStr(this._vizColor1, 0.25);
                    ctx.beginPath();
                    ctx.roundRect(x, H - barH, barWidth, barH, 1.5);
                    ctx.fill();
                }
                return;
            }

            this._analyser.getByteFrequencyData(this._dataArray);

            for (let i = 0; i < barCount; i++) {
                // Map frequency bins with slight weighting toward bass
                const binIdx = Math.floor(i * (this._dataArray.length * 0.6) / barCount);
                const raw = (this._dataArray[binIdx] || 0) / 255;
                // Add subtle organic movement
                const organic = Math.sin(this._vizTime * 2.5 + i * 0.7) * 0.04;
                const target = Math.max(0.06, raw + organic);
                // Smooth lerp — faster attack, slower decay
                const speed = target > this._barSmooth[i] ? lerpSpeed * 2.2 : lerpSpeed * 0.7;
                this._barSmooth[i] += (target - this._barSmooth[i]) * speed;
                const barH = Math.max(2, this._barSmooth[i] * H);

                const x = i * (barWidth + gap);
                const gradient = ctx.createLinearGradient(0, H, 0, H - barH);
                gradient.addColorStop(0, this._rgbStr(this._vizColor1, 0.95));
                gradient.addColorStop(0.5, this._rgbStr(this._vizColor1, 0.7));
                gradient.addColorStop(1, this._rgbStr(this._vizColor2, 0.55));
                ctx.fillStyle = gradient;

                // Rounded bar
                ctx.beginPath();
                ctx.roundRect(x, H - barH, barWidth, barH, Math.min(barWidth / 2, 2));
                ctx.fill();

                // Glow on tall bars
                if (raw > 0.6) {
                    ctx.fillStyle = this._rgbStr(this._vizColor1, (raw - 0.6) * 0.3);
                    ctx.beginPath();
                    ctx.roundRect(x - 0.5, H - barH - 1, barWidth + 1, barH + 2, 3);
                    ctx.fill();
                }
            }
        };
        draw();
    }

    // ── Ambient Background ──────────────────────────────────────────────

    _updateAmbientBg(song) {
        const el = document.getElementById('ambient-bg');
        if (!el || !song) return;
        const color = song.color_hex || '#a78bfa';
        const rgb = this._hexToRgb(color);
        // Richer multi-point gradient with smooth CSS transition
        el.style.background = `
            radial-gradient(ellipse at 10% 50%, rgba(${rgb.r},${rgb.g},${rgb.b},0.12) 0%, transparent 55%),
            radial-gradient(ellipse at 90% 25%, rgba(${rgb.r},${rgb.g},${rgb.b},0.07) 0%, transparent 50%),
            radial-gradient(ellipse at 50% 90%, rgba(${rgb.r},${rgb.g},${rgb.b},0.05) 0%, transparent 45%)
        `;
        // Also update visualizer colors for this song
        this._updateVisualizerColors(song);
    }

    // ── Private ─────────────────────────────────────────────────────────

    _showPlayerBar() {
        const bar = document.getElementById('player-bar');
        if (bar) bar.classList.remove('player-hidden');
    }

    _updateUI(song) {
        const title = document.getElementById('player-title');
        const artist = document.getElementById('player-artist');
        const art = document.getElementById('player-art');

        if (title) title.textContent = song.track_name || 'Unknown';
        if (artist) artist.textContent = song.artist || '—';

        if (art) {
            const artUrl = song.album_art_url || '';
            const isValidUrl = artUrl && (artUrl.startsWith('/') || artUrl.startsWith('http://') || artUrl.startsWith('https://'));
            if (song.has_album_art && isValidUrl) {
                const hue = this._colorToHue(song.color_hex || '#a78bfa');
                art.innerHTML = `<img src="${artUrl}" alt="Album Art" onerror="this.parentElement.innerHTML='<div class=\\'player-art-placeholder\\' style=\\'background:hsl(${hue},30%,15%)\\'><svg viewBox=\\'0 0 24 24\\' fill=\\'none\\' stroke=\\'hsl(${hue},50%,55%)\\' stroke-width=\\'1.5\\'><circle cx=\\'12\\' cy=\\'12\\' r=\\'10\\'/><circle cx=\\'12\\' cy=\\'12\\' r=\\'3\\'/></svg></div>'">`;
            } else {
                const hue = this._colorToHue(song.color_hex || '#a78bfa');
                art.innerHTML = `<div class="player-art-placeholder" style="background: hsl(${hue}, 30%, 15%)">
                    <svg viewBox="0 0 24 24" fill="none" stroke="hsl(${hue},50%,55%)" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>
                </div>`;
            }
        }

        this._updateLikeBtn();
        document.title = `${song.track_name} — Brightify`;
        if (window.renderJourneyStrip) window.renderJourneyStrip();  // F2.2 Journey Mode
    }

    _updatePlayBtn(playing) {
        const btn = document.getElementById('play-icon');
        if (btn) {
            btn.innerHTML = playing
                ? '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>'
                : '<polygon points="5 3 19 12 5 21 5 3"/>';
        }
    }

    _updateLikeBtn() {
        const btn = document.getElementById('btn-like');
        if (!btn) return;
        const song = this.getCurrentSong();
        if (!song) return;
        const liked = JSON.parse(localStorage.getItem('bf_liked') || '[]');
        const isLiked = liked.some(s => s.track_id === song.track_id);
        btn.classList.toggle('liked', isLiked);
    }

    _updateVolumeUI() {
        const filled = document.getElementById('volume-filled');
        const v = this.isMuted ? 0 : this.volume;
        if (filled) filled.style.width = `${v * 100}%`;

        // Update volume icon
        const btn = document.getElementById('btn-volume');
        if (btn) {
            let icon;
            if (this.isMuted || this.volume === 0) {
                icon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>';
            } else if (this.volume < 0.5) {
                icon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 010 7.07"/></svg>';
            } else {
                icon = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07"/></svg>';
            }
            btn.innerHTML = icon;
        }
    }

    _onTimeUpdate() {
        if (this._seekDragging) return;
        const { currentTime, duration } = this.audio;
        if (!duration) return;

        const pct = (currentTime / duration) * 100;
        const filled = document.getElementById('progress-filled');
        const thumb = document.getElementById('progress-thumb');
        const cur = document.getElementById('time-current');

        if (filled) filled.style.width = `${pct}%`;
        if (thumb) thumb.style.left = `${pct}%`;
        if (cur) cur.textContent = this._formatTime(currentTime);

        // Crossfade trigger: in smart mode we peek the next track to compute
        // the plan and trigger fade exactly when the planned window starts.
        // Legacy mode (smart=false) keeps fixed `duration + 5s` heuristic.
        if (window.crossfade?.enabled && duration > 15 && !this._crossfading) {
            const remaining = duration - currentTime;
            const smart = window.crossfade?.smart !== false;
            let triggerAt;
            if (smart) {
                const nextIdx = this._getNextIndex();
                const nextSong = (nextIdx >= 0 && nextIdx !== this.currentIndex)
                    ? this.queue[nextIdx] : null;
                const currentSong = this.queue[this.currentIndex];
                if (nextSong && currentSong) {
                    const plan = planCrossfade(currentSong, nextSong, this.volume);
                    triggerAt = plan.duration_s + 0.5;   // 0.5s safety margin
                } else {
                    triggerAt = 6.5;   // no next song info → default 6s + 0.5s
                }
            } else {
                const crossfadeDuration = window.crossfade.duration || 15;
                triggerAt = crossfadeDuration + 5;
            }
            if (remaining <= triggerAt && remaining > 0.3) {
                this._startCrossfade();
            }
        }
    }

    _onLoaded() {
        const total = document.getElementById('time-total');
        if (total) total.textContent = this._formatTime(this.audio.duration);
        // Smart Crossfade Phase 2: re-apply LUFS-matched gain when track metadata
        // becomes available (track switch path that doesn't go through crossfade).
        const song = this.queue[this.currentIndex];
        if (song) this._applyLufsGain(song);
    }

    /**
     * Smart Crossfade Phase 2: pre-scale active track to match -14 LUFS target.
     * Falls back to plain `this.volume` if LUFS data isn't available for the song
     * or if Web Audio GainNodes haven't been initialised yet (no-op).
     */
    _applyLufsGain(song) {
        if (!this._gainNodeA || !this._gainNodeB) return;
        const activeGain = (this.audio === this._audioA) ? this._gainNodeA : this._gainNodeB;
        if (!activeGain) return;

        const lufs = (song && Number.isFinite(song.loudness_lufs))
            ? song.loudness_lufs : null;
        let gainVal;
        if (lufs === null) {
            gainVal = this.volume;   // no LUFS data → behave like before
        } else {
            const TARGET = -14;   // Spotify reference
            // gain_lin = 10^((TARGET - measured) / 20)
            gainVal = this.volume * Math.pow(10, (TARGET - lufs) / 20);
            // Clamp to [0, 1.0] — never amplify above unity (would risk clipping)
            gainVal = Math.min(1.0, Math.max(0, gainVal));
        }
        activeGain.gain.value = gainVal;
    }

    _onPlay() {
        this.isPlaying = true;
        this._updatePlayBtn(true);
        // Resume AudioContext if suspended
        if (this._audioCtx && this._audioCtx.state === 'suspended') {
            this._audioCtx.resume();
        }
    }

    _onPause() {
        // Ignore pause events from the old audio during crossfade transition
        if (this._crossfading) return;
        this.isPlaying = false;
        this._updatePlayBtn(false);
    }

    _onTrackEnd() {
        // Crossfade: next track already playing on inactive audio
        if (this._crossfading && this._crossfadeNextIdx >= 0) {
            // Cancel the ongoing fade animation since we're completing now
            if (this._crossfadeRaf) {
                cancelAnimationFrame(this._crossfadeRaf);
                this._crossfadeRaf = null;
            }
            this._completeCrossfade();
            return;
        }
        if (this.repeatMode === 'one') {
            this.audio.currentTime = 0;
            this.audio.play().catch(() => {});
        } else if (this.repeatMode === 'all' || this.currentIndex < this.queue.length - 1) {
            this.next();
        } else if (this.radioMode) {
            this._startRadio();
        } else if (this._playSource === 'emotion-journey' && window._activeJourney?.dwell && window.extendJourneyDwell) {
            // F2.7 — arrived at destination: top up with more songs at the target
            // mood so the journey keeps playing instead of stopping abruptly.
            window.extendJourneyDwell().then(() => {
                if (this.currentIndex < this.queue.length - 1) this.next();
                else { this.isPlaying = false; this._updatePlayBtn(false); }
            });
        } else {
            this.isPlaying = false;
            this._updatePlayBtn(false);
        }
    }

    async _startRadio() {
        const currentSong = this.getCurrentSong();
        if (!currentSong) return;
        try {
            window.app?.toast('📻 Radio đang tìm bài tiếp...', 'info');
            
            // Use the last 3 played songs for diverse recommendations
            const recentSongs = this.queue.slice(Math.max(0, this.currentIndex - 2), this.currentIndex + 1);
            const seedSong = recentSongs[recentSongs.length - 1] || currentSong;
            
            const data = await API.getSimilarSongs(seedSong.track_id, 20);
            if (data.songs?.length) {
                const queueIds = new Set(this.queue.map(s => s.track_id));
                const historyIds = new Set(JSON.parse(localStorage.getItem('bf_history') || '[]').slice(0, 30).map(s => s.track_id));
                
                // Filter out songs already in queue and recently played
                let newSongs = data.songs.filter(s => !queueIds.has(s.track_id) && !historyIds.has(s.track_id));
                
                // If strict filter yields too few, relax to just queue filter
                if (newSongs.length < 3) {
                    newSongs = data.songs.filter(s => !queueIds.has(s.track_id));
                }
                
                if (newSongs.length > 0) {
                    // Check audio availability
                    const ids = newSongs.filter(s => s.track_id).map(s => s.track_id);
                    if (ids.length) {
                        try {
                            const batch = await API.getBatchAudioStatus(ids);
                            newSongs.forEach(s => {
                                if (batch.status?.[s.track_id]) {
                                    s.has_audio = true;
                                    s.audio_url = `/api/audio/stream/${s.track_id}`;
                                }
                            });
                        } catch(e) {}
                    }
                    
                    // Prioritize songs with audio
                    newSongs.sort((a, b) => (b.has_audio ? 1 : 0) - (a.has_audio ? 1 : 0));
                    
                    this.queue.push(...newSongs.slice(0, 10));
                    this._updateQueuePanel();
                    this.next();
                    return;
                }
            }
            // Fallback: random songs
            const random = await API.getRandomSongs(10).catch(() => ({ songs: [] }));
            if (random.songs?.length) {
                const queueIds = new Set(this.queue.map(s => s.track_id));
                const freshSongs = random.songs.filter(s => !queueIds.has(s.track_id));
                if (freshSongs.length > 0) {
                    this.queue.push(...freshSongs);
                    this._updateQueuePanel();
                    this.next();
                }
            }
        } catch(e) {
            console.warn('Radio failed:', e);
        }
    }

    _onError(e) {
        console.warn('Audio error:', e);
        if (typeof app !== 'undefined' && app.toast) {
            app.toast('Không thể phát bài này — đang chuyển bài tiếp theo', 'error');
        }
        setTimeout(() => this.next(), 2000);
    }

    _onKeydown(e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        switch (e.code) {
            case 'Space':
                e.preventDefault();
                this.togglePlay();
                break;
            case 'ArrowRight':
                if (e.shiftKey) this.next();
                else if (this.audio.duration) this.audio.currentTime = Math.min(this.audio.duration, this.audio.currentTime + 10);
                break;
            case 'ArrowLeft':
                if (e.shiftKey) this.prev();
                else this.audio.currentTime = Math.max(0, this.audio.currentTime - 10);
                break;
            case 'KeyM':
                this.toggleMute();
                break;
            case 'KeyS':
                if (!e.metaKey && !e.ctrlKey) this.toggleShuffle();
                break;
            case 'KeyR':
                if (!e.metaKey && !e.ctrlKey) this.toggleRepeat();
                break;
            case 'KeyQ':
                if (!e.metaKey && !e.ctrlKey) this.toggleQueue();
                break;
            case 'Slash':
                if (e.shiftKey) { // ? key
                    e.preventDefault();
                    window.app?.showShortcuts();
                }
                break;
            case 'KeyI':
                if (!e.metaKey && !e.ctrlKey) window.showLyrics?.();
                break;
            case 'KeyP':
                if (!e.metaKey && !e.ctrlKey) window.playbackSpeed?.showPicker();
                break;
            case 'ArrowUp':
                e.preventDefault();
                this.setVolume(Math.min(1, this.audio.volume + 0.05));
                break;
            case 'ArrowDown':
                e.preventDefault();
                this.setVolume(Math.max(0, this.audio.volume - 0.05));
                break;
            case 'Equal': // + key
            case 'NumpadAdd':
                if (!e.metaKey && !e.ctrlKey) this.setVolume(Math.min(1, this.audio.volume + 0.05));
                break;
            case 'Minus': // - key
            case 'NumpadSubtract':
                if (!e.metaKey && !e.ctrlKey) this.setVolume(Math.max(0, this.audio.volume - 0.05));
                break;
        }
    }

    _initProgressBar() {
        const bar = document.getElementById('progress-bar');
        if (!bar) return;

        const seek = (e) => {
            const rect = bar.getBoundingClientRect();
            const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            if (this.audio.duration) {
                this.audio.currentTime = pct * this.audio.duration;
            }
            const filled = document.getElementById('progress-filled');
            const thumb = document.getElementById('progress-thumb');
            if (filled) filled.style.width = `${pct * 100}%`;
            if (thumb) thumb.style.left = `${pct * 100}%`;
        };

        bar.addEventListener('mousedown', (e) => {
            this._seekDragging = true;
            seek(e);
            const onMove = (e) => seek(e);
            const onUp = () => {
                this._seekDragging = false;
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    }

    _initVolumeBar() {
        const bar = document.getElementById('volume-bar');
        if (!bar) return;

        const setVol = (e) => {
            const rect = bar.getBoundingClientRect();
            const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            this.setVolume(pct);
        };

        bar.addEventListener('mousedown', (e) => {
            this._volDragging = true;
            setVol(e);
            const onMove = (e) => setVol(e);
            const onUp = () => {
                this._volDragging = false;
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    }

    _getDisplayOrder() {
        // Returns array of queue indices in the order they will play.
        // Current song first, then upcoming songs in play order.
        if (this.queue.length === 0) return [];
        const order = [];
        if (this.shuffleOn && this._shuffleOrder.length === this.queue.length) {
            // Find current position in shuffle order
            const pos = this._shuffleOrder.indexOf(this.currentIndex);
            if (pos >= 0) {
                // Current song first, then rest in shuffle order
                for (let i = 0; i < this._shuffleOrder.length; i++) {
                    order.push(this._shuffleOrder[(pos + i) % this._shuffleOrder.length]);
                }
            } else {
                // Fallback: current first, then shuffle order
                order.push(this.currentIndex);
                this._shuffleOrder.forEach(idx => {
                    if (idx !== this.currentIndex) order.push(idx);
                });
            }
        } else {
            // Normal order: current song first, then sequential
            for (let i = 0; i < this.queue.length; i++) {
                order.push((this.currentIndex + i) % this.queue.length);
            }
        }
        return order;
    }

    _updateQueuePanel() {
        const list = document.getElementById('queue-list');
        if (!list) return;

        const displayOrder = this._getDisplayOrder();

        list.innerHTML = displayOrder.map((queueIdx, displayPos) => {
            const song = this.queue[queueIdx];
            if (!song) return '';
            const isCurrent = queueIdx === this.currentIndex;
            const songJson = JSON.stringify(song).replace(/"/g, '&quot;');
            return `
            <div class="queue-item ${isCurrent ? 'current' : ''}"
                 draggable="${!isCurrent}" data-queue-idx="${queueIdx}" onclick="player.playIndex(${queueIdx})"
                 oncontextmenu="app.showContextMenu(event, ${songJson})">
                ${!isCurrent ? `<div class="queue-item-handle" title="Kéo để sắp xếp">
                    <svg viewBox="0 0 24 24" fill="currentColor" opacity="0.3"><circle cx="8" cy="6" r="1.5"/><circle cx="16" cy="6" r="1.5"/><circle cx="8" cy="12" r="1.5"/><circle cx="16" cy="12" r="1.5"/><circle cx="8" cy="18" r="1.5"/><circle cx="16" cy="18" r="1.5"/></svg>
                </div>` : '<div class="queue-item-playing-icon"><span></span><span></span><span></span></div>'}
                <div class="queue-item-num">${isCurrent ? '▶' : displayPos}</div>
                <div class="queue-item-art" style="background:${song.color_hex || '#333'}30">
                    ${song.has_album_art ? `<img src="${song.album_art_url}" alt="">` : '🎵'}
                </div>
                <div class="queue-item-info">
                    <div class="queue-item-title">${this._esc(song.track_name)}</div>
                    <div class="queue-item-artist">${this._esc(song.artist)}</div>
                </div>
                ${!isCurrent ? `
                    <button class="queue-item-remove" onclick="event.stopPropagation(); player.removeFromQueue(${queueIdx})" title="Xóa khỏi hàng đợi">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>
                ` : ''}
            </div>`;
        }).join('');

        // Drag-to-reorder
        this._initQueueDrag();
    }

    _initQueueDrag() {
        const list = document.getElementById('queue-list');
        if (!list) return;
        let draggedIdx = null;

        list.querySelectorAll('.queue-item').forEach(item => {
            item.addEventListener('dragstart', (e) => {
                draggedIdx = parseInt(item.dataset.queueIdx);
                item.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
            });
            item.addEventListener('dragend', () => {
                item.classList.remove('dragging');
                list.querySelectorAll('.queue-item').forEach(el => el.classList.remove('drag-over'));
            });
            item.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                item.classList.add('drag-over');
            });
            item.addEventListener('dragleave', () => {
                item.classList.remove('drag-over');
            });
            item.addEventListener('drop', (e) => {
                e.preventDefault();
                item.classList.remove('drag-over');
                const targetIdx = parseInt(item.dataset.queueIdx);
                if (draggedIdx === null || draggedIdx === targetIdx) return;
                this.moveInQueue(draggedIdx, targetIdx);
            });
        });
    }

    moveInQueue(fromIdx, toIdx) {
        if (fromIdx === toIdx) return;
        const [song] = this.queue.splice(fromIdx, 1);
        this.queue.splice(toIdx, 0, song);
        // Update currentIndex
        if (this.currentIndex === fromIdx) {
            this.currentIndex = toIdx;
        } else if (fromIdx < this.currentIndex && toIdx >= this.currentIndex) {
            this.currentIndex--;
        } else if (fromIdx > this.currentIndex && toIdx <= this.currentIndex) {
            this.currentIndex++;
        }
        this._updateQueuePanel();
    }

    _generateShuffleOrder() {
        this._shuffleOrder = Array.from({ length: this.queue.length }, (_, i) => i);
        for (let i = this._shuffleOrder.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [this._shuffleOrder[i], this._shuffleOrder[j]] = [this._shuffleOrder[j], this._shuffleOrder[i]];
        }
    }

    // ── Crossfade helpers ────────────────────────────────────────────────

    _getNextIndex() {
        if (this.queue.length === 0) return -1;
        if (this.repeatMode === 'one') return this.currentIndex;
        if (this.shuffleOn && this._shuffleOrder.length === this.queue.length) {
            const pos = this._shuffleOrder.indexOf(this.currentIndex);
            return this._shuffleOrder[(pos + 1) % this._shuffleOrder.length];
        }
        return (this.currentIndex + 1) % this.queue.length;
    }

    _startCrossfade() {
        const nextIdx = this._getNextIndex();
        if (nextIdx < 0 || nextIdx === this.currentIndex) return;
        const nextSong = this.queue[nextIdx];
        const currentSong = this.queue[this.currentIndex];
        if (!nextSong?.has_audio || !nextSong?.audio_url) return;

        // ── SMART POLICY: decide all crossfade params ──
        // Falls back to legacy 15s fixed equal-power when smart=false
        const smart = window.crossfade?.smart !== false;
        const plan = smart
            ? planCrossfade(currentSong, nextSong, this.volume)
            : {
                duration_s: window.crossfade?.duration || 15,
                fadeOutStartAt_s: null,
                fadeInStartAt_s: 10,   // legacy SKIP_INTRO
                gainA: this.volume,
                gainB: this.volume,
                curve: 'equal-power',
                debug: { legacy: true },
            };

        this._crossfading = true;
        this._crossfadeNextIdx = nextIdx;
        this._currentCrossfadePlan = plan;   // for completeCrossfade reset

        // Load next track on inactive audio element
        this._audioInactive.src = nextSong.audio_url;
        // Reset inactive element's HTMLAudio volume to neutral
        // (real volume controlled by gainB below — or GainNode in Phase 2)
        this._audioInactive.volume = 0;

        // Wait for metadata so we can safely seek past the intro / to cue point
        const onReady = () => {
            this._audioInactive.removeEventListener('loadedmetadata', onReady);
            const skipTo = Number.isFinite(plan.fadeInStartAt_s) ? plan.fadeInStartAt_s : 0;
            // Only seek if track is long enough to skip safely
            if (this._audioInactive.duration > skipTo + 10) {
                try {
                    this._audioInactive.currentTime = skipTo;
                } catch (_e) {
                    // some browsers throw if seek > duration; ignore
                }
            }
        };
        this._audioInactive.addEventListener('loadedmetadata', onReady);
        // Apply current playback speed to the next track
        if (window.playbackSpeed) this._audioInactive.playbackRate = window.playbackSpeed.current;
        this._audioInactive.play().catch(() => {});

        // RAF fade loop — supports linear AND equal-power curves
        const duration_ms = Math.max(100, plan.duration_s * 1000);
        const startTime = performance.now();
        const halfPi = Math.PI / 2;

        if (this._crossfadeRaf) cancelAnimationFrame(this._crossfadeRaf);

        // Pick the right gain control:
        // - If Web Audio GainNodes available (Phase 2 path) → use those for cleaner gain
        // - Otherwise fall back to HTMLAudioElement.volume
        const useGainNodes = !!(this._gainNodeA && this._gainNodeB);
        const gainNodeActive = useGainNodes
            ? (this.audio === this._audioA ? this._gainNodeA : this._gainNodeB)
            : null;
        const gainNodeInactive = useGainNodes
            ? (this._audioInactive === this._audioA ? this._gainNodeA : this._gainNodeB)
            : null;

        // Make sure the HTMLAudio elements are at 1.0 if using GainNode (gain happens downstream)
        if (useGainNodes) {
            this.audio.volume = 1.0;
            this._audioInactive.volume = 1.0;
        }

        const fadeStep = (now) => {
            const elapsed = now - startTime;
            const p = Math.min(1, elapsed / duration_ms);

            let fadeOutMult, fadeInMult;
            if (plan.curve === 'linear') {
                fadeOutMult = 1 - p;
                fadeInMult  = p;
            } else {
                // Equal-power cos/sin (constant total perceived loudness)
                fadeOutMult = Math.cos(p * halfPi);
                fadeInMult  = Math.sin(p * halfPi);
            }

            const valOut = Math.max(0, Math.min(1, plan.gainA * fadeOutMult));
            const valIn  = Math.max(0, Math.min(1, plan.gainB * fadeInMult));

            if (useGainNodes) {
                gainNodeActive.gain.value   = valOut;
                gainNodeInactive.gain.value = valIn;
            } else {
                this.audio.volume          = valOut;
                this._audioInactive.volume = valIn;
            }

            if (p < 1 && this._crossfading) {
                this._crossfadeRaf = requestAnimationFrame(fadeStep);
            } else {
                this._crossfadeRaf = null;
                if (this._crossfading) {
                    this._completeCrossfade();
                }
            }
        };

        this._crossfadeRaf = requestAnimationFrame(fadeStep);
    }

    _completeCrossfade() {
        // Cancel any ongoing RAF fade
        if (this._crossfadeRaf) {
            cancelAnimationFrame(this._crossfadeRaf);
            this._crossfadeRaf = null;
        }

        // Save next index before clearing state
        const nextIdx = this._crossfadeNextIdx;

        // Swap audio elements
        const oldAudio = this.audio;
        this.audio = this._audioInactive;
        this._audioInactive = oldAudio;

        // Mark crossfade done BEFORE pausing old audio
        // so _onPause guard catches the old audio's pause event
        this._crossfading = false;
        this._crossfadeNextIdx = -1;

        // Stop old audio (may fire pause event — harmless since
        // this.audio now points to the new element)
        oldAudio.pause();
        oldAudio.src = '';

        // Update state
        this.currentIndex = nextIdx;

        // Apply LUFS-normalized gain to the now-active track
        // (uses GainNode if available, falls back to HTMLAudio volume)
        const newSong = this.queue[nextIdx];
        if (this._gainNodeA && this._gainNodeB) {
            // Reset old (inactive) gain to a clean state for next crossfade
            const oldGainNode = (oldAudio === this._audioA) ? this._gainNodeA : this._gainNodeB;
            if (oldGainNode) oldGainNode.gain.value = this.volume;
            // Apply LUFS to active
            this._applyLufsGain(newSong);
            // HTMLAudio volumes stay at 1.0 when using GainNodes
            this.audio.volume = 1.0;
        } else {
            this.audio.volume = this.volume;
        }
        this._currentCrossfadePlan = null;

        // CRITICAL: Restore play state & time display
        // These events were missed because they fired while audio was _audioInactive
        this.isPlaying = true;
        this._updatePlayBtn(true);

        // Update total time for the new track
        const totalEl = document.getElementById('time-total');
        if (totalEl && this.audio.duration) {
            totalEl.textContent = this._formatTime(this.audio.duration);
        }

        // Update progress bar to reflect new track position
        if (this.audio.duration) {
            const pct = (this.audio.currentTime / this.audio.duration) * 100;
            const filled = document.getElementById('progress-filled');
            const thumb = document.getElementById('progress-thumb');
            const cur = document.getElementById('time-current');
            if (filled) filled.style.width = `${pct}%`;
            if (thumb) thumb.style.left = `${pct}%`;
            if (cur) cur.textContent = this._formatTime(this.audio.currentTime);
        }

        // Resume AudioContext if suspended
        if (this._audioCtx && this._audioCtx.state === 'suspended') {
            this._audioCtx.resume();
        }

        // Update song info UI
        const song = this.queue[this.currentIndex];
        if (song) {
            this._updateUI(song);
            this._updateQueuePanel();
            this._addToHistory(song);
            this._updateAmbientBg(song);
        }
    }

    _cancelCrossfade() {
        if (!this._crossfading) return;
        this._crossfading = false;
        this._crossfadeNextIdx = -1;
        this._currentCrossfadePlan = null;
        if (this._crossfadeInterval) {
            clearInterval(this._crossfadeInterval);
            this._crossfadeInterval = null;
        }
        if (this._crossfadeRaf) {
            cancelAnimationFrame(this._crossfadeRaf);
            this._crossfadeRaf = null;
        }
        this._audioInactive.pause();
        this._audioInactive.src = '';
        // Reset gain on the inactive element so a future crossfade starts clean
        if (this._gainNodeA && this._gainNodeB) {
            const inactiveGain = (this._audioInactive === this._audioA) ? this._gainNodeA : this._gainNodeB;
            if (inactiveGain) inactiveGain.gain.value = this.volume;
            // Active gain unchanged — current track keeps its LUFS-normalized level
            this.audio.volume = 1.0;
        } else {
            this.audio.volume = this.volume;
        }
    }

    _addToHistory(song) {
        let history = JSON.parse(localStorage.getItem('bf_history') || '[]');
        // Avoid duplicate DW tracking for same song if already most recent
        const isDuplicate = history.length > 0 && history[0].track_id === song.track_id;
        history = history.filter(s => s.track_id !== song.track_id);
        history.unshift({ ...song, played_at: Date.now() });
        history = history.slice(0, 100);
        localStorage.setItem('bf_history', JSON.stringify(history));
    }

    _sendPlayComplete() {
        // Reset tracking state
        this._songStartTime = null;
        this._songStartTrackId = undefined;
    }

    _formatTime(sec) {
        if (!sec || isNaN(sec)) return '0:00';
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    }

    _colorToHue(hex) {
        try {
            const r = parseInt(hex.slice(1,3), 16) / 255;
            const g = parseInt(hex.slice(3,5), 16) / 255;
            const b = parseInt(hex.slice(5,7), 16) / 255;
            const max = Math.max(r, g, b), min = Math.min(r, g, b);
            let h = 0;
            if (max !== min) {
                const d = max - min;
                if (max === r) h = ((g - b) / d + 6) % 6;
                else if (max === g) h = (b - r) / d + 2;
                else h = (r - g) / d + 4;
                h *= 60;
            }
            return Math.round(h);
        } catch {
            return 0;
        }
    }

    _esc(str) {
        const d = document.createElement('div');
        d.textContent = str || '';
        return d.innerHTML;
    }
}

window.player = new MusicPlayer();
