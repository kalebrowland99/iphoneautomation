const FARM_SLOTS = window.__FARM__.slots;
const BRAND_ID = window.__FARM__.brand;
        let slotProfiles = {};
        let deviceId = null;
        let selectedSlot = null;
        let farmDevices = [];
        let slotToDevice = {};
        let ws = null;
        let activityEntries = [];
        let activityAutoScroll = true;
        let activityPaused = false;
        const DEBUG_STORAGE = {
            open: 'farmDebugPanelOpen',
            test: 'farmDebugTestId',
        };
        let debugFlowStepIds = [];
        let postTextSaveTimers = {};
        let cachedPostTexts = [];
        let batchSelectedSlots = new Set();
        let accountHandleEditing = false;
let slideshowJobId = null;
let slideshowPollTimer = null;
let runLogEntries = [];
let lastRunMessage = '';
let runConsoleTimer = null;
let currentSlideshowJob = null;
let currentBatchStatus = { status: 'idle' };
let slideshowConfig = { use_embedded_runner: true };
let slideshowEmbedUrl = '';

const RUN_STEPS = ['slideshow', 'ingest', 'captions', 'batch'];

function appendRunLog(message, level = 'info', source = 'system') {
    const text = String(message || '').trim();
    if (!text) return;
    runLogEntries.unshift({
        ts: new Date().toISOString(),
        level,
        source,
        message: text,
    });
    if (runLogEntries.length > 400) runLogEntries.length = 400;
    renderUnifiedLog();
}

function renderUnifiedLog() {
    const feed = document.getElementById('unified-log');
    if (!feed) return;
    if (!runLogEntries.length) {
        feed.innerHTML = '<div class="text-muted-foreground py-8 text-center text-sm">Run log will appear here…</div>';
        return;
    }
    feed.innerHTML = runLogEntries.map((entry) => {
        const lvl = entry.level || 'info';
        const color = lvl === 'error' ? 'text-red-600' : lvl === 'warn' ? 'text-amber-700' : lvl === 'success' ? 'text-emerald-700' : 'text-foreground/80';
        return `<div class="flex gap-2 py-1 border-b border-border/40 last:border-0">
            <span class="text-muted-foreground/50 shrink-0 tabular-nums">${formatTime(entry.ts)}</span>
            <span class="text-muted-foreground/40 shrink-0 uppercase text-[10px] tracking-wide w-14">${escapeHtml(entry.source || 'sys')}</span>
            <span class="${color}">${escapeHtml(entry.message)}</span>
        </div>`;
    }).join('');
    if (activityAutoScroll) feed.scrollTop = 0;
}

function setRunStepActive(phase) {
    RUN_STEPS.forEach((step) => {
        const el = document.getElementById(`run-step-${step}`);
        if (!el) return;
        const active = (
            (step === 'slideshow' && phase === 'slideshow')
            || (step === 'ingest' && phase === 'ingest')
            || (step === 'captions' && phase === 'captions')
            || (step === 'batch' && phase === 'batch')
        );
        el.classList.toggle('run-step-active', active);
        el.classList.toggle('run-step-done', false);
    });
}

function syncRunControlButtons(extra = {}) {
    const btnRun = document.getElementById('btn-run');
    const btnKill = document.getElementById('btn-kill');
    const embedStopBtn = document.getElementById('btn-slideshow-embed-stop');
    const jobRunning = String(extra.slideshowJob?.status || currentSlideshowJob?.status || '').toLowerCase() === 'running';
    const batchRunning = ['connecting', 'running', 'disconnecting'].includes(
        String(extra.batchStatus?.status || currentBatchStatus?.status || '').toLowerCase(),
    );
    const busy = Boolean(extra.progressActive)
        || jobRunning
        || batchRunning
        || Boolean(extra.orchestratorBusy);
    if (btnRun) btnRun.disabled = busy;
    if (btnKill) btnKill.disabled = !busy;
    if (embedStopBtn) embedStopBtn.disabled = !busy;
}

function applyRunProgress(progress) {
    const p = progress || {};
    const pct = Math.max(0, Math.min(100, Number(p.progress) || 0));
    const bar = document.getElementById('run-progress-bar');
    const pctEl = document.getElementById('run-pct');
    const phaseEl = document.getElementById('run-phase');
    const subtitle = document.getElementById('run-subtitle');
    if (bar) bar.style.width = `${pct}%`;
    if (pctEl) pctEl.textContent = `${pct}%`;
    if (phaseEl) phaseEl.textContent = p.phase_label || 'Ready';
    if (subtitle) subtitle.textContent = p.message || 'Select phones and start a daily run.';
    setRunStepActive(p.phase || 'idle');
    const active = Boolean(p.active);
    syncRunControlButtons({ progressActive: active });
    const msg = String(p.message || '').trim();
    if (msg && msg !== lastRunMessage) {
        lastRunMessage = msg;
        const lvl = p.phase === 'failed' ? 'error' : p.phase === 'complete' ? 'success' : 'info';
        appendRunLog(msg, lvl, p.phase || 'run');
    }
}

async function refreshRunConsole() {
    try {
        const q = slideshowJobId ? `?job_id=${encodeURIComponent(slideshowJobId)}` : '';
        const res = await api(`/run/status${q}`);
        currentBatchStatus = res.batch || currentBatchStatus;
        if (res.slideshow_job_id) slideshowJobId = res.slideshow_job_id;
        currentSlideshowJob = res.slideshow_job || currentSlideshowJob;
        applyRunProgress(res.progress);
        syncRunControlButtons({
            progressActive: Boolean(res.progress?.active),
            slideshowJob: currentSlideshowJob,
            batchStatus: currentBatchStatus,
            orchestratorBusy: res.slideshow_orchestrator_busy,
        });
        if (res.batch) updateBatchUI(res.batch);
        if (
            slideshowConfig.use_embedded_runner
            && currentSlideshowJob?.automation_url
            && String(currentSlideshowJob.status || '').toLowerCase() === 'running'
            && ['automation', 'ingesting'].includes(String(currentSlideshowJob.phase || '').toLowerCase())
        ) {
            showSlideshowEmbed(
                currentSlideshowJob.automation_url,
                currentSlideshowJob.message || 'Generating slideshows…',
            );
        }
    } catch (_) {}
}

function startRunConsolePoll() {
    if (runConsoleTimer) return;
    void refreshRunConsole();
    runConsoleTimer = setInterval(refreshRunConsole, 2500);
}

function stopRunConsolePoll() {
    if (!runConsoleTimer) return;
    clearInterval(runConsoleTimer);
    runConsoleTimer = null;
}

        function isAccountHandleFocused() {
            return document.activeElement?.id === 'account-handle';
        }

async function refreshSlideshowConfig() {
    try {
        const cfg = await api('/slideshow/config');
        slideshowConfig = cfg || slideshowConfig;
        const btn = document.getElementById('btn-run');
        if (btn && !cfg.enabled) btn.disabled = true;
    } catch (_) {}
}

function showSlideshowEmbed(url, statusText) {
    const panel = document.getElementById('slideshow-embed-panel');
    const frame = document.getElementById('slideshow-embed-frame');
    const statusEl = document.getElementById('slideshow-embed-status');
    const openLink = document.getElementById('slideshow-embed-open-tab');
    if (!panel || !frame) return;
    const nextUrl = String(url || '').trim();
    if (!nextUrl) return;
    const wasHidden = panel.classList.contains('hidden');
    panel.classList.remove('hidden');
    if (statusEl) statusEl.textContent = statusText || 'Generating slideshows…';
    if (openLink) {
        openLink.href = nextUrl;
        openLink.classList.remove('hidden');
    }
    const urlChanged = slideshowEmbedUrl !== nextUrl;
    if (urlChanged) {
        slideshowEmbedUrl = nextUrl;
        frame.src = 'about:blank';
        window.setTimeout(() => {
            frame.src = nextUrl;
        }, 0);
    }
    // Scroll only when the embed first opens or the URL changes — not on every status poll.
    if (wasHidden || urlChanged) {
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

function openSlideshowTab(url) {
    const nextUrl = String(url || slideshowEmbedUrl || '').trim();
    if (!nextUrl) return null;
    return window.open(nextUrl, '_blank', 'noopener,noreferrer');
}

function stopSlideshowEmbedGeneration() {
    const frame = document.getElementById('slideshow-embed-frame');
    const url = String(slideshowEmbedUrl || frame?.src || '').trim();
    if (!frame?.contentWindow || !url || url === 'about:blank') return;
    try {
        const origin = new URL(url, window.location.href).origin;
        frame.contentWindow.postMessage({ type: 'autoslideshow:stop' }, origin);
    } catch (_) {}
}

function hideSlideshowEmbed() {
    stopSlideshowEmbedGeneration();
    const panel = document.getElementById('slideshow-embed-panel');
    const frame = document.getElementById('slideshow-embed-frame');
    const openLink = document.getElementById('slideshow-embed-open-tab');
    if (panel) panel.classList.add('hidden');
    if (frame) frame.src = 'about:blank';
    if (openLink) openLink.classList.add('hidden');
    slideshowEmbedUrl = '';
}

function syncSlideshowEmbedFromJob(job) {
    if (!slideshowConfig.use_embedded_runner) return;
    const phase = String(job?.phase || '').toLowerCase();
    const status = String(job?.status || '').toLowerCase();
    const url = String(job?.automation_url || '').trim();
    if (url && (phase === 'automation' || phase === 'ingesting') && status === 'running') {
        showSlideshowEmbed(url, job?.message || 'Generating slideshows…');
        return;
    }
    if (status === 'completed' || status === 'failed' || phase === 'captions' || phase === 'batch' || phase === 'done') {
        hideSlideshowEmbed();
    }
}

function updateSlideshowUI(job) {
    currentSlideshowJob = job;
    syncSlideshowEmbedFromJob(job);
    void refreshRunConsole();
}

function stopSlideshowPoll() {
            if (slideshowPollTimer) {
                clearInterval(slideshowPollTimer);
                slideshowPollTimer = null;
            }
        }

        function startSlideshowPoll(jobId) {
            slideshowJobId = jobId;
            stopSlideshowPoll();
        const tick = async () => {
            try {
                const job = await api(`/slideshow/jobs/${encodeURIComponent(jobId)}`);
                updateSlideshowUI(job);
                if (job.status === 'completed' || job.status === 'failed') {
                    stopSlideshowPoll();
                    if (job.status === 'failed') appendRunLog(job.error || 'Slideshow job failed', 'error', 'slideshow');
                    slideshowJobId = null;
                    void refreshRunConsole();
                }
            } catch (_) {}
        };
            void tick();
            slideshowPollTimer = setInterval(tick, 4000);
        }

        async function tileSplitWindows() {
            try {
                const res = await api('/window-layout/split', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ brand: BRAND_ID }),
                });
                if (res?.warnings?.length) {
                    appendRunLog(res.warnings.join(' · '), 'warn', 'run');
                } else if (res?.chrome?.placed && res?.imouse?.placed) {
                    appendRunLog('Chrome and iMouseXP tiled 50/50.', 'info', 'run');
                }
            } catch (err) {
                appendRunLog(`Window layout: ${err.message || err}`, 'warn', 'run');
            }
        }

        async function startDailyRun() {
            void tileSplitWindows();
            const fromPost = getSelectedFromPost('batch-from-post');
            if (fromPost !== null) {
                await startFarmBatch({ skipConfirm: true });
            } else {
                await generateAndRunSlideshow();
            }
        }

        async function generateAndRunSlideshow() {
    const slots = [...batchSelectedSlots].map(s => parseInt(s, 10)).filter(n => !isNaN(n)).sort((a, b) => a - b);
    if (!slots.length) {
        alert('Select at least one phone slot.');
        return;
    }
    appendRunLog(`Starting daily run for slots ${slots.join(', ')}`, 'info', 'run');
    lastRunMessage = '';
    const btn = document.getElementById('btn-run');
    if (btn) btn.disabled = true;
    startRunConsolePoll();
    try {
        const res = await api('/slideshow/generate-and-run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ brand: BRAND_ID, slots, run_batch: true }),
        });
        updateSlideshowUI(res.job);
        if (res.automation_url && slideshowConfig.use_embedded_runner) {
            showSlideshowEmbed(res.automation_url, res.job?.message || 'Generating slideshows…');
        }
        if (res.job?.id) {
            slideshowJobId = res.job.id;
            startSlideshowPoll(res.job.id);
        }
    } catch (err) {
        appendRunLog(err.message || String(err), 'error', 'run');
        if (String(err.message || '').toLowerCase().includes('already running')) {
            appendRunLog('Click Stop to cancel the stuck slideshow job, then run again.', 'warn', 'run');
            await refreshRunConsole();
        } else {
            alert(err.message || String(err));
        }
        updateSlideshowUI(null);
        applyRunProgress({
            phase: 'idle',
            phase_label: 'Ready',
            progress: 0,
            message: 'Could not start run',
            active: false,
        });
    }
}

async function stopDailyRun() {
    appendRunLog('Stop requested', 'warn', 'run');
    stopSlideshowEmbedGeneration();
    try {
        await api('/batch/stop', { method: 'POST' });
    } catch (err) {
        appendRunLog(`Stop failed: ${err.message || err}`, 'error', 'run');
    }
    stopSlideshowPoll();
    hideSlideshowEmbed();
    slideshowJobId = null;
    currentSlideshowJob = null;
    lastRunMessage = '';
    applyRunProgress({
        phase: 'idle',
        phase_label: 'Stopped',
        progress: 0,
        message: 'Run stopped',
        active: false,
    });
    syncRunControlButtons({});
    await refreshRunConsole();
    refreshFarmDevices({ quiet: true });
}

        function bindAccountHandleInput() {
            const el = document.getElementById('account-handle');
            if (!el || el.dataset.bound === '1') return;
            el.dataset.bound = '1';
            el.addEventListener('focus', () => { accountHandleEditing = true; });
            el.addEventListener('blur', () => {
                accountHandleEditing = false;
                saveAccountProfile();
            });
        }

        function initBrandNav() {
            const labely = document.getElementById('brand-link-labely');
            const valcoin = document.getElementById('brand-link-valcoin');
            if (labely) labely.classList.toggle('active', BRAND_ID === 'labely');
            if (valcoin) valcoin.classList.toggle('active', BRAND_ID === 'valcoin');
        }

        function formatAccountStatus(profile) {
            if (!profile) return 'Run status: —';
            const handle = profile.tiktok_handle || '(no @ set)';
            const status = profile.last_run_status || 'idle';
            const posts = profile.posts_completed || 0;
            const target = profile.posts_target || 3;
            return `Run status: ${status} · ${posts}/${target} posts · ${handle}`;
        }

        async function loadSlotProfiles() {
            try {
                const res = await api(`/account-profiles?brand=${enc(BRAND_ID)}`);
                slotProfiles = res.profiles || {};
            } catch (_) {
                slotProfiles = {};
            }
        }

        async function loadAccountProfileForDevice() {
            if (!deviceId) return;
            try {
                const res = await api(`/devices/${enc(deviceId)}/account-profile?brand=${enc(BRAND_ID)}`);
                applyAccountProfileToForm(res.profile || {});
            } catch (_) {}
        }

        function applyAccountProfileToForm(profile) {
            const p = profile || {};
            const handleEl = document.getElementById('account-handle');
            if (handleEl && !accountHandleEditing && !isAccountHandleFocused()) {
                handleEl.value = p.tiktok_handle || '';
            }
            document.getElementById('account-status-line').textContent = formatAccountStatus(p);
        }

        async function saveAccountProfile() {
            const body = {
                tiktok_handle: document.getElementById('account-handle').value.trim(),
                brand: BRAND_ID,
            };
            try {
                let profile;
                if (deviceId) {
                    const res = await api(`/devices/${enc(deviceId)}/account-profile`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    });
                    profile = res.profile || {};
                } else if (selectedSlot) {
                    const res = await api(`/slots/${enc(selectedSlot)}/account-profile`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    });
                    profile = res.profile || {};
                } else {
                    return;
                }
                if (selectedSlot) slotProfiles[`slot:${selectedSlot}`] = profile;
                applyAccountProfileToForm(profile);
                renderFarmGrid();
            } catch (err) {
                alert(`Failed to save account: ${err.message}`);
            }
        }

        async function toggleWarmupSlot(slot, enabled) {
            if (BRAND_ID !== 'valcoin') return;
            const profile = slotProfiles[`slot:${slot}`] || {};
            const body = {
                brand: BRAND_ID,
                warmup_enabled: Boolean(enabled),
            };
            if (profile.tiktok_handle) {
                body.tiktok_handle = profile.tiktok_handle;
            }
            try {
                const res = await api(`/slots/${enc(slot)}/account-profile`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const updated = res.profile || {};
                slotProfiles[`slot:${slot}`] = updated;
                const d = slotToDevice[slot];
                if (d) d.account_profile = updated;
                renderFarmGrid();
            } catch (err) {
                alert(`Failed to save warmup setting: ${err.message}`);
                renderFarmGrid();
            }
        }

        async function setWarmupForAll(enabled) {
            if (BRAND_ID !== 'valcoin') return;
            const slots = registeredSlots();
            if (!slots.length) return;
            try {
                await Promise.all(slots.map(async (slot) => {
                    const profile = slotProfiles[`slot:${slot}`] || {};
                    const body = {
                        brand: BRAND_ID,
                        warmup_enabled: Boolean(enabled),
                    };
                    if (profile.tiktok_handle) {
                        body.tiktok_handle = profile.tiktok_handle;
                    }
                    const res = await api(`/slots/${enc(slot)}/account-profile`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    });
                    const updated = res.profile || {};
                    slotProfiles[`slot:${slot}`] = updated;
                    const d = slotToDevice[slot];
                    if (d) d.account_profile = updated;
                }));
                renderFarmGrid();
            } catch (err) {
                alert(`Failed to save warmup settings: ${err.message}`);
                renderFarmGrid();
            }
        }

        function onWarmupSelectAllChange(checked) {
            void setWarmupForAll(checked);
        }

        function updateWarmupSelectAllCheckbox() {
            if (BRAND_ID !== 'valcoin') return;
            const master = document.getElementById('warmup-select-all');
            if (!master) return;
            const reg = registeredSlots();
            const warmed = reg.filter((slot) => {
                const profile = slotProfiles[`slot:${slot}`] || slotToDevice[slot]?.account_profile || {};
                return Boolean(profile.warmup_enabled);
            });
            master.checked = reg.length > 0 && warmed.length === reg.length;
            master.indeterminate = warmed.length > 0 && warmed.length < reg.length;
            master.disabled = !reg.length;
        }

        function loadBatchSelection() {
            try {
                const saved = localStorage.getItem('batchSelectedSlots');
                if (saved) batchSelectedSlots = new Set(JSON.parse(saved));
            } catch (_) {
                batchSelectedSlots = new Set();
            }
        }

        function saveBatchSelection() {
            localStorage.setItem('batchSelectedSlots', JSON.stringify([...batchSelectedSlots]));
            updateBatchSlotCount();
        }

        function registeredSlots() {
            const slots = [];
            for (let i = 1; i <= FARM_SLOTS; i++) {
                if (slotToDevice[String(i)]) slots.push(String(i));
            }
            return slots;
        }

        function ensureBatchSelectionDefaults() {
            const reg = registeredSlots();
            batchSelectedSlots.forEach(s => {
                if (!slotToDevice[s]) batchSelectedSlots.delete(s);
            });
            // Only auto-select all on first visit (no saved preference yet).
            if (localStorage.getItem('batchSelectedSlots') !== null) return;
            if (!batchSelectedSlots.size && reg.length) {
                reg.forEach(s => batchSelectedSlots.add(s));
                saveBatchSelection();
            }
        }

        function updateBatchSlotCount() {
            const el = document.getElementById('batch-slot-count');
            if (!el) return;
            const n = batchSelectedSlots.size;
            el.textContent = n === 1 ? '1 phone selected' : `${n} phones selected`;
        }

        function toggleBatchSlot(slot, checked) {
            if (!slotToDevice[slot]) return;
            if (checked) batchSelectedSlots.add(slot);
            else batchSelectedSlots.delete(slot);
            saveBatchSelection();
            updateBatchSelectAllCheckbox();
        }

        function onBatchSelectAllChange(checked) {
            if (checked) selectAllBatchSlots();
            else clearBatchSlots();
        }

        function updateBatchSelectAllCheckbox() {
            const master = document.getElementById('batch-select-all');
            if (!master) return;
            const reg = registeredSlots();
            const picked = reg.filter(s => batchSelectedSlots.has(s));
            master.checked = reg.length > 0 && picked.length === reg.length;
            master.indeterminate = picked.length > 0 && picked.length < reg.length;
            master.disabled = !reg.length;
        }

        function selectAllBatchSlots() {
            registeredSlots().forEach(s => batchSelectedSlots.add(s));
            saveBatchSelection();
            renderFarmGrid();
        }

        function clearBatchSlots() {
            batchSelectedSlots.clear();
            saveBatchSelection();
            renderFarmGrid();
        }

        function setBatchPickerEnabled(enabled) {
            document.querySelectorAll('#farm-grid .phones-table-row input[type="checkbox"]').forEach(cb => {
                const row = cb.closest('.phones-table-row');
                cb.disabled = row?.classList.contains('empty') || !enabled;
            });
            const master = document.getElementById('batch-select-all');
            if (master) master.disabled = !enabled || !registeredSlots().length;
            document.querySelectorAll('.batch-slot-toolbar .link-btn').forEach(btn => {
                btn.disabled = !enabled;
                btn.style.opacity = enabled ? '1' : '0.45';
            });
        }

        function escapeHtml(text) {
            const d = document.createElement('div');
            d.textContent = text || '';
            return d.innerHTML;
        }

        function normalizeTiktokUsername(handle) {
            return String(handle || '').trim().replace(/^@+/, '');
        }

        function formatRelativeTime(iso) {
            if (!iso) return null;
            const then = new Date(iso);
            if (isNaN(then.getTime())) return null;
            const sec = Math.floor((Date.now() - then.getTime()) / 1000);
            if (sec < 10) return 'just now';
            if (sec < 60) return `${sec} seconds ago`;
            const min = Math.floor(sec / 60);
            if (min < 60) return min === 1 ? '1 minute ago' : `${min} minutes ago`;
            const hr = Math.floor(min / 60);
            if (hr < 24) return hr === 1 ? '1 hour ago' : `${hr} hours ago`;
            const day = Math.floor(hr / 24);
            if (day === 1) return '1 day ago';
            return `${day} days ago`;
        }

        function phoneStatusCell(d, online, pipe) {
            if (!d) {
                return { label: '—', badge: 'empty', pipeHint: '' };
            }
            let pipeHint = '';
            if (pipe && pipe.status === 'running') {
                pipeHint = `<span class="chip-pipe">${pipe.step}/${pipe.total_steps}</span>`;
                return { label: 'Running', badge: 'ACTIVE', pipeHint };
            }
            if (pipe && pipe.status === 'paused') {
                pipeHint = '<span class="chip-pipe">||</span>';
            }
            if (online) {
                return { label: 'Connected', badge: 'CONNECTED', pipeHint };
            }
            return { label: 'Off', badge: 'OFF', pipeHint };
        }

        function lastRunCell(profile) {
            if (!profile) return '<span class="phones-muted">—</span>';
            if (profile.last_run_status === 'running') {
                return '<span class="phones-last-run running">Running now</span>';
            }
            const rel = formatRelativeTime(profile.last_run_at);
            if (!rel) return '<span class="phones-muted">Never</span>';
            const status = profile.last_run_status || 'idle';
            const cls = status === 'failed' ? 'failed' : status === 'success' ? 'success' : '';
            const title = profile.last_run_at ? escapeHtml(String(profile.last_run_at)) : '';
            return `<span class="phones-last-run ${cls}"${title ? ` title="${title}"` : ''}>${escapeHtml(rel)}</span>`;
        }

        function tiktokHandleCell(handle) {
            const user = normalizeTiktokUsername(handle);
            if (!user) return '<span class="phones-muted">—</span>';
            const url = `https://www.tiktok.com/@${encodeURIComponent(user)}`;
            return `<a class="phones-handle-link" href="${url}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()" title="Open @${escapeHtml(user)} on TikTok">@${escapeHtml(user)}</a>`;
        }

        function renderFarmGrid() {
            const grid = document.getElementById('farm-grid');
            if (!grid) return;
            ensureBatchSelectionDefaults();
            const rows = [];
            for (let i = 1; i <= FARM_SLOTS; i++) {
                const key = String(i);
                const d = slotToDevice[key];
                const hasDevice = Boolean(d);
                const selected = selectedSlot === key;
                const checked = hasDevice && batchSelectedSlots.has(key);
                const online = Boolean(d && d.connected);
                const pipe = d && d.pipeline;
                const statusInfo = phoneStatusCell(d, online, pipe);
                const profile = d?.account_profile || slotProfiles[`slot:${key}`] || null;
                const handle = profile?.tiktok_handle || '';
                const warmupEnabled = BRAND_ID === 'valcoin' && Boolean(profile?.warmup_enabled);
                const warmupDays = parseInt(profile?.warmup_days_completed || 0, 10);
                const cantCast = Boolean(profile?.cant_cast_imouse);
                const runCell = lastRunCell(profile);
                const classes = [
                    'phones-table-row',
                    hasDevice ? '' : 'empty',
                    selected ? 'selected' : '',
                    pipe && pipe.status === 'running' ? 'running' : '',
                ].filter(Boolean).join(' ');
                const title = d ? escapeHtml(d.display_label || (`Phone ${key}`)) : `Slot ${key} — empty`;
                rows.push(`
                <tr class="${classes}" data-slot="${key}" data-selected="${selected ? 'true' : 'false'}"
                    title="${title}" onclick="selectSlot('${key}')">
                    <td class="phones-td phones-td-check" onclick="event.stopPropagation()">
                        <input type="checkbox" class="phones-check" ${hasDevice ? '' : 'disabled'}
                               ${checked ? 'checked' : ''}
                               onchange="toggleBatchSlot('${key}', this.checked)"
                               aria-label="Include phone ${key}">
                    </td>
                    <td class="phones-td phones-td-slot">${key}</td>
                    <td class="phones-td phones-td-handle">
                        ${tiktokHandleCell(handle)}
                        ${BRAND_ID === 'valcoin' ? `<span class="warmup-day-badge">${warmupDays > 0 ? `Day ${warmupDays} Warmup ✓` : 'Day 0 Warmup'}</span>` : ''}
                        ${cantCast ? `<span class="cant-cast-badge" title="Click to clear tag" onclick="event.stopPropagation(); clearCantCast('${key}')">⚠ cant cast iMouse</span>` : ''}
                    </td>
                    <td class="phones-td">
                        <div class="phones-status-cell">
                            <span class="status-dot ${online ? 'online' : 'offline'}"></span>
                            <span class="badge ${statusInfo.badge}">${statusInfo.label}</span>
                            ${statusInfo.pipeHint}
                        </div>
                    </td>
                    <td class="phones-td phones-td-warmup" onclick="event.stopPropagation()">
                        <input type="checkbox" class="phones-check" ${hasDevice ? '' : 'disabled'}
                               ${warmupEnabled ? 'checked' : ''}
                               onchange="toggleWarmupSlot('${key}', this.checked)"
                               aria-label="Warmup only (no posting) for phone ${key}">
                    </td>
                    <td class="phones-td phones-td-run">${runCell}</td>
                </tr>`);
            }
            grid.innerHTML = rows.join('');
            updateBatchSlotCount();
            updateBatchSelectAllCheckbox();
            updateWarmupSelectAllCheckbox();
        }

        function connectWS() {
            const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${proto}//${location.host}/ws`);
            const liveEl = document.getElementById('live-indicator');
            ws.onopen = () => {
                document.getElementById('connection-status').textContent = 'Live';
                liveEl.classList.remove('off');
            };
            ws.onclose = () => {
                document.getElementById('connection-status').textContent = 'Reconnecting';
                liveEl.classList.add('off');
                setTimeout(connectWS, 3000);
            };
            ws.onmessage = (e) => {
                const msg = JSON.parse(e.data);
                if (msg.event === 'activity' && !activityPaused) {
                    prependActivity(msg.data);
                }
                if (['workflow_started', 'state_changed', 'action_completed', 'action_failed',
                     'popup_detected', 'device_disconnected', 'device_connected',
                     'pipeline_started', 'pipeline_paused', 'pipeline_resumed',
                     'pipeline_stopped', 'pipeline_completed', 'pipeline_failed',
                     'batch_started', 'batch_connecting', 'batch_running',
                     'batch_disconnecting', 'batch_completed', 'batch_failed', 'batch_stopped'].includes(msg.event)) {
                    refreshFarmDevices({ quiet: true });
                    if (msg.event.startsWith('batch_')) {
                        updateBatchUI(msg.data || {});
                        appendRunLog(msg.event.replace('batch_', 'Batch: '), 'info', 'batch');
                    }
                    void refreshRunConsole();
                    if (deviceId) updateDeviceMeta();
                }
            };
        }

        async function api(path, opts = {}) {
            const res = await fetch(`/api${path}`, opts);
            if (!res.ok) {
                const text = await res.text();
                throw new Error(text || res.statusText);
            }
            return res.json();
        }

        function enc(id) { return encodeURIComponent(id); }

        function brandQ() {
            return `brand=${enc(BRAND_ID)}`;
        }

        function showBanner(msg) {
            const el = document.getElementById('page-banner');
            el.textContent = msg;
            el.style.display = 'block';
        }

        function hideBanner() {
            document.getElementById('page-banner').style.display = 'none';
        }

        function deviceSlot(device) {
            const slot = String(device.user_name || '').trim();
            if (slot) return slot;
            const m = (device.display_label || '').match(/Phone\s+(\d+)/i);
            return m ? m[1] : '';
        }

        function updateFarmHeaderStats() {
            const online = farmDevices.filter(d => d.connected).length;
            const el = document.getElementById('farm-online-count');
            if (el) el.textContent = `${online} / ${FARM_SLOTS}`;
        }

        async function refreshFarmDevices(opts = {}) {
            try {
                await loadSlotProfiles();
                farmDevices = await api(`/devices?brand=${enc(BRAND_ID)}`);
                slotToDevice = {};
                for (const d of farmDevices) {
                    const slot = deviceSlot(d);
                    if (slot && !slotToDevice[slot]) slotToDevice[slot] = d;
                }
                updateFarmHeaderStats();
                renderFarmGrid();
                if (selectedSlot) {
                    const current = slotToDevice[selectedSlot];
                    if (current && current.device_id === deviceId) updateDeviceUI(current);
                }
            } catch (err) {
                if (!opts.quiet) showBanner('Failed to load devices: ' + err.message);
            }
        }

        function firstOnlineSlot() {
            for (let i = 1; i <= FARM_SLOTS; i++) {
                const d = slotToDevice[String(i)];
                if (d && d.connected) return String(i);
            }
            for (let i = 1; i <= FARM_SLOTS; i++) {
                if (slotToDevice[String(i)]) return String(i);
            }
            return '1';
        }

        async function selectSlot(slot) {
            selectedSlot = slot;
            localStorage.setItem('farmSelectedSlot', slot);
            renderFarmGrid();
            const d = slotToDevice[slot];
            if (!d) {
                deviceId = null;
                applyAccountProfileToForm(slotProfiles[`slot:${slot}`] || {});
                showBanner(`Phone ${slot} not found. Set slot ${slot} in iMouseXP.`);
                return;
            }
            hideBanner();
            deviceId = d.device_id;
            updateDeviceUI(d);
            await loadPostTexts();
            await updateDeviceMeta();
            await refreshActivity();
        }

        function formatTime(iso) {
            if (!iso) return '—';
            const d = new Date(iso);
            if (isNaN(d)) return iso.slice(11, 19) || iso;
            return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        }

        function prependActivity(entry) {
            if (activityEntries.some(e => e.id === entry.id)) return;
            activityEntries.unshift(entry);
            if (activityEntries.length > 300) activityEntries.length = 300;
            const label = entry.device_label ? ` · ${entry.device_label}` : '';
            appendRunLog(`${entry.message || ''}${label}`, entry.level || 'info', entry.category || 'activity');
        }

        async function refreshActivity() {
            if (!deviceId) return;
            try {
                const entries = await api(`/activity?limit=40&device_id=${enc(deviceId)}`);
                entries.reverse().forEach((entry) => {
                    if (activityEntries.some(e => e.id === entry.id)) return;
                    prependActivity(entry);
                });
            } catch (_) {}
        }

        function toggleAutoscroll() {
            activityAutoScroll = !activityAutoScroll;
            document.getElementById('btn-autoscroll').classList.toggle('active', activityAutoScroll);
        }

        function togglePause() {
            activityPaused = !activityPaused;
            const btn = document.getElementById('btn-pause');
            btn.textContent = activityPaused ? 'Resume' : 'Pause';
            btn.classList.toggle('active', activityPaused);
        }

        function updateDeviceUI(device) {
            if (device.account_profile) {
                applyAccountProfileToForm(device.account_profile);
            }
            const btn = document.getElementById('btn-connect');
            if (btn) {
                btn.textContent = device.connected ? 'Reconnect' : 'Connect';
            }
            updatePipelineUI(device);
        }

        function updatePipelineUI(device) {
            const debugCb = document.getElementById('debug-skip-post');
            if (debugCb && typeof device.debug_skip_post === 'boolean') debugCb.checked = device.debug_skip_post;
        }

        async function saveDebugSkipPost() {
            if (!deviceId) return;
            try {
                await api(`/devices/${enc(deviceId)}/settings`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ debug_skip_post: document.getElementById('debug-skip-post').checked }),
                });
                refreshActivity();
            } catch (err) {
                alert(`Failed to save: ${err.message}`);
            }
        }

        async function flushPostTextSaves() {
            if (!deviceId) return;
            const tasks = [];
            document.querySelectorAll('#post-texts textarea[data-post]').forEach(el => {
                const key = `${el.dataset.post}-${el.dataset.field}`;
                if (postTextSaveTimers[key]) {
                    clearTimeout(postTextSaveTimers[key]);
                    delete postTextSaveTimers[key];
                }
                tasks.push(api(`/devices/${enc(deviceId)}/post-texts/${el.dataset.post}/${el.dataset.field}?${brandQ()}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: el.value }),
                }));
            });
            if (tasks.length) await Promise.all(tasks);
        }

        function getSelectedFromPost(groupName) {
            const el = document.querySelector(`input[name="${groupName}"]:checked`);
            if (!el || el.value === '') return null;
            const n = parseInt(el.value, 10);
            return (n >= 1 && n <= 3) ? n : null;
        }

        function validatePostTexts(fromPost = 1) {
            const start = fromPost == null ? 1 : fromPost;
            const missing = [];
            for (let post = start; post <= 3; post++) {
                if (!document.getElementById(`onscreen-${post}`)?.value.trim()) {
                    missing.push(`Post ${post}: onscreen text is empty`);
                }
                if (!document.getElementById(`final-${post}`)?.value.trim()) {
                    missing.push(`Post ${post}: final caption is empty`);
                }
            }
            return missing;
        }

        async function startPipeline() {
            if (!deviceId) return;
            const fromPost = getSelectedFromPost('pipeline-from-post');
            const checkFrom = fromPost == null ? 1 : fromPost;
            const missing = validatePostTexts(checkFrom);
            if (missing.length) {
                const range = checkFrom === 1 ? '1–3' : `${checkFrom}–3`;
                alert(`Fill captions for posts ${range}:\n\n${missing.join('\n')}`);
                return;
            }
            try {
                await flushPostTextSaves();
                await api(`/devices/${enc(deviceId)}/pipeline/start`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ from_post: fromPost, brand: BRAND_ID }),
                });
                await refreshFarmDevices({ quiet: true });
                await updateDeviceMeta();
                refreshActivity();
            } catch (err) { alert(`Start failed: ${err.message}`); }
        }

        async function pausePipeline() {
            if (!deviceId) return;
            try {
                await api(`/devices/${enc(deviceId)}/pipeline/pause`, { method: 'POST' });
                await refreshFarmDevices({ quiet: true });
                await updateDeviceMeta();
                refreshActivity();
            } catch (err) { alert(`Pause failed: ${err.message}`); }
        }

        async function resumePipeline() {
            if (!deviceId) return;
            try {
                await api(`/devices/${enc(deviceId)}/pipeline/resume`, { method: 'POST' });
                await refreshFarmDevices({ quiet: true });
                await updateDeviceMeta();
                refreshActivity();
            } catch (err) { alert(`Resume failed: ${err.message}`); }
        }

        async function stopPipeline() {
            if (!deviceId) return;
            try {
                await api(`/devices/${enc(deviceId)}/pipeline/stop`, { method: 'POST' });
                await refreshFarmDevices({ quiet: true });
                await updateDeviceMeta();
                refreshActivity();
            } catch (err) { alert(`Kill failed: ${err.message}`); }
        }

        async function updateDeviceMeta() {
            if (!deviceId) return;
            try {
                updateDeviceUI(await api(`/devices/${enc(deviceId)}`));
            } catch (_) {}
        }

        async function connectDevice() {
            if (!deviceId) return;
            const btn = document.getElementById('btn-connect');
            btn.disabled = true;
            btn.textContent = 'Connecting…';
            try {
                const res = await api(`/devices/${enc(deviceId)}/connect`, { method: 'POST' });
                await refreshFarmDevices({ quiet: true });
                await updateDeviceMeta();
                if (!res.connected) alert('AirPlay connect failed — check iMouseXP.');
            } catch (err) {
                alert(`Connect failed: ${err.message}`);
            } finally {
                btn.disabled = false;
                await updateDeviceMeta();
            }
        }

        async function disconnectDevice() {
            if (!deviceId) return;
            const btn = document.getElementById('btn-disconnect');
            btn.disabled = true;
            try {
                await api(`/devices/${enc(deviceId)}/disconnect`, { method: 'POST' });
                await refreshFarmDevices({ quiet: true });
                await updateDeviceMeta();
                refreshActivity();
            } catch (err) {
                alert(`Disconnect failed: ${err.message}`);
            } finally {
                btn.disabled = false;
            }
        }

        async function captureScreen() {
            if (!deviceId) return;
            try {
                await api(`/devices/${enc(deviceId)}/screenshot`, { method: 'POST' });
                refreshActivity();
            } catch (err) {
                alert(`Screenshot failed: ${err.message}`);
            }
        }

        let debugTestRunning = false;
        let debugTestAbort = null;

        function resetDebugRunButtons() {
            const runBtn = document.getElementById('btn-debug-run');
            const skipBtn = document.getElementById('btn-debug-run-skip-media');
            const killBtn = document.getElementById('btn-debug-kill');
            if (runBtn) {
                runBtn.disabled = false;
                runBtn.textContent = 'Run test';
            }
            if (skipBtn) {
                skipBtn.disabled = false;
                skipBtn.textContent = 'Run A→Z (skip media)';
            }
            if (killBtn) killBtn.disabled = true;
        }

        async function executeDebugStep(testId, skipMedia, signal) {
            const skipQs = skipMedia ? '&skip_media=1' : '';
            return api(`/devices/${enc(deviceId)}/debug/${enc(testId)}?brand=${enc(BRAND_ID)}${skipQs}`, {
                method: 'POST',
                signal,
            });
        }

        async function killDebugTest() {
            if (!deviceId) return;
            const killBtn = document.getElementById('btn-debug-kill');
            killBtn.disabled = true;
            if (debugTestAbort) {
                debugTestAbort.abort();
            }
            stopSlideshowEmbedGeneration();
            try {
                await api('/batch/stop', { method: 'POST' });
                await api(`/devices/${enc(deviceId)}/pipeline/stop`, { method: 'POST' });
                stopSlideshowPoll();
                hideSlideshowEmbed();
                slideshowJobId = null;
                refreshActivity();
            } catch (err) {
                alert(`Kill failed: ${err.message}`);
            } finally {
                debugTestRunning = false;
                debugTestAbort = null;
                resetDebugRunButtons();
            }
        }

        async function runDebugTest(skipMedia = false, runAll = false) {
            if (debugTestRunning) return;
            if (!deviceId) {
                const hint = selectedSlot
                    ? `Phone ${selectedSlot} is not connected — use Connect AirPlay, then run the test.`
                    : 'Select a device slot first.';
                showBanner(hint);
                return;
            }
            const select = document.getElementById('debug-test-select');
            const testId = select?.value;
            if (!testId) {
                showBanner('Choose a debug test from the dropdown.');
                return;
            }
            if (runAll && !skipMedia) {
                showBanner('Full A→Z is only available with skip media.');
                return;
            }
            if (runAll && !debugFlowStepIds.length) {
                showBanner('Pipeline steps not loaded yet — refresh the page.');
                return;
            }

            const btn = document.getElementById('btn-debug-run');
            const skipBtn = document.getElementById('btn-debug-run-skip-media');
            const killBtn = document.getElementById('btn-debug-kill');
            const controller = new AbortController();
            debugTestAbort = controller;
            debugTestRunning = true;
            btn.disabled = true;
            if (skipBtn) skipBtn.disabled = true;
            killBtn.disabled = false;

            const startIdx = runAll ? debugFlowStepIds.indexOf(testId) : -1;
            if (runAll && startIdx < 0) {
                showBanner('Selected step is not in the A→Z pipeline.');
                debugTestRunning = false;
                debugTestAbort = null;
                resetDebugRunButtons();
                return;
            }

            const activeBtn = runAll ? skipBtn : (skipMedia ? skipBtn : btn);
            if (activeBtn && !runAll) activeBtn.textContent = 'Running…';

            const stepTimeoutMs = 10 * 60 * 1000;
            let completedAll = false;

            try {
                const stepsToRun = runAll
                    ? debugFlowStepIds.slice(startIdx)
                    : [testId];

                for (let i = 0; i < stepsToRun.length; i++) {
                    if (controller.signal.aborted) break;

                    const stepId = stepsToRun[i];
                    select.value = stepId;
                    localStorage.setItem(DEBUG_STORAGE.test, stepId);

                    if (runAll && skipBtn) {
                        const overall = startIdx + i + 1;
                        skipBtn.textContent = `Running ${overall}/${debugFlowStepIds.length}…`;
                    }

                    const stepController = new AbortController();
                    const onAbort = () => stepController.abort();
                    controller.signal.addEventListener('abort', onAbort, { once: true });
                    const stepWatchdog = setTimeout(() => stepController.abort(), stepTimeoutMs);

                    let res;
                    try {
                        res = await executeDebugStep(stepId, skipMedia, stepController.signal);
                    } finally {
                        clearTimeout(stepWatchdog);
                        controller.signal.removeEventListener('abort', onAbort);
                    }

                    refreshActivity();
                    await refreshFarmDevices({ quiet: true });

                    if (res.automation_url) {
                        showSlideshowEmbed(res.automation_url, res.message || 'Generating slideshow…');
                        const tab = openSlideshowTab(res.automation_url);
                        if (res.job?.id) {
                            slideshowJobId = res.job.id;
                            startSlideshowPoll(res.job.id);
                            startRunConsolePoll();
                        }
                        showBanner(
                            tab
                                ? 'Slideshow opened in a new tab — complete generation there (panel also embedded above).'
                                : 'Slideshow panel opened above — allow pop-ups or use “Open in tab”.',
                        );
                        break;
                    }

                    if (!res.success) {
                        alert(res.message || `Step failed: ${stepId}`);
                        break;
                    }

                    if (i === stepsToRun.length - 1) {
                        completedAll = runAll;
                        if (runAll) {
                            showBanner(`A→Z complete (skip media) — ${debugFlowStepIds.length} steps`);
                        } else {
                            advanceDebugStep();
                            showBanner(res.message || 'Test completed — advanced to next step');
                        }
                    } else {
                        const nextId = stepsToRun[i + 1];
                        select.value = nextId;
                        localStorage.setItem(DEBUG_STORAGE.test, nextId);
                        if (runAll && !res.skipped) {
                            await new Promise(resolve => setTimeout(resolve, 3000));
                        }
                    }
                }
            } catch (err) {
                if (err.name !== 'AbortError') {
                    let msg = err.message || 'Test failed';
                    try {
                        const parsed = JSON.parse(msg);
                        if (parsed.detail) msg = String(parsed.detail);
                    } catch (_) {}
                    alert(msg);
                } else if (runAll && !completedAll) {
                    showBanner('A→Z run stopped');
                }
            } finally {
                debugTestRunning = false;
                debugTestAbort = null;
                resetDebugRunButtons();
            }
        }

        async function waitForServerBack() {
            const btn = document.getElementById('btn-restart-server');
            btn.disabled = true;
            btn.textContent = 'Waiting…';
            for (let i = 0; i < 45; i++) {
                await new Promise(r => setTimeout(r, 2000));
                try {
                    if ((await fetch('/api/health')).ok) {
                        btn.disabled = false;
                        btn.textContent = 'Restart server';
                        await loadDebugTests();
                        if (deviceId) {
                            await updateDeviceMeta();
                            refreshActivity();
                        }
                        connectWS();
                        showBanner('Server restarted');
                        return;
                    }
                } catch (_) {}
            }
            btn.disabled = false;
            btn.textContent = 'Restart server';
            alert('Server did not come back in time.');
        }

        async function restartServer() {
            if (!confirm('Restart the farm server?')) return;
            const btn = document.getElementById('btn-restart-server');
            btn.disabled = true;
            btn.textContent = 'Restarting…';
            try { await api('/server/restart', { method: 'POST' }); } catch (_) {}
            waitForServerBack();
        }

        function advanceDebugStep() {
            const select = document.getElementById('debug-test-select');
            if (!select || !debugFlowStepIds.length) return;
            const idx = debugFlowStepIds.indexOf(select.value);
            if (idx < 0 || idx >= debugFlowStepIds.length - 1) return;
            select.value = debugFlowStepIds[idx + 1];
            localStorage.setItem(DEBUG_STORAGE.test, select.value);
        }

        let currentDebugFlow = localStorage.getItem('debugFlow') || 'flow';

        async function loadDebugTests(group) {
            const flowGroup = group || currentDebugFlow || 'flow';
            try {
                const tests = await api(`/debug/tests?group=${enc(flowGroup)}`);
                const select = document.getElementById('debug-test-select');
                if (!tests.length) {
                    debugFlowStepIds = [];
                    select.innerHTML = '<option value="">No pipeline steps</option>';
                    return;
                }
                debugFlowStepIds = tests.map(t => t.id);
                select.innerHTML = tests.map(t =>
                    `<option value="${escapeHtml(t.id)}">${escapeHtml(t.label)}</option>`
                ).join('');
                const savedTest = localStorage.getItem(DEBUG_STORAGE.test);
                if (savedTest && debugFlowStepIds.includes(savedTest)) {
                    select.value = savedTest;
                } else {
                    select.value = debugFlowStepIds[0];
                    localStorage.setItem(DEBUG_STORAGE.test, select.value);
                }
            } catch (err) {
                debugFlowStepIds = [];
                document.getElementById('debug-test-select').innerHTML =
                    '<option value="">Unavailable</option>';
            }
        }

        function switchDebugFlow(value) {
            currentDebugFlow = value;
            localStorage.setItem('debugFlow', value);
            loadDebugTests(value);
        }

        function restoreDebugPanel() {
            const panel = document.getElementById('debug-panel');
            if (panel && localStorage.getItem(DEBUG_STORAGE.open) === '1') {
                panel.open = true;
            }
            const savedFlow = localStorage.getItem('debugFlow') || 'flow';
            currentDebugFlow = savedFlow;
            document.querySelectorAll('input[name="debug-flow-select"]').forEach(r => {
                r.checked = r.value === savedFlow;
            });
        }

        function bindDebugPanel() {
            const panel = document.getElementById('debug-panel');
            if (panel && panel.dataset.bound !== '1') {
                panel.dataset.bound = '1';
                panel.addEventListener('toggle', () => {
                    localStorage.setItem(DEBUG_STORAGE.open, panel.open ? '1' : '0');
                });
            }
            const select = document.getElementById('debug-test-select');
            if (select && select.dataset.bound !== '1') {
                select.dataset.bound = '1';
                select.addEventListener('change', () => {
                    const id = select.value;
                    if (id) localStorage.setItem(DEBUG_STORAGE.test, id);
                });
            }
        }

        async function loadCaptionAiSettings() {
            try {
                const settings = await api(`/caption-ai/settings?${brandQ()}`);
                const promptEl = document.getElementById('ai-prompt');
                const tagsEl = document.getElementById('ai-hashtags');
                if (promptEl && settings.prompt) promptEl.value = settings.prompt;
                if (tagsEl) tagsEl.value = settings.hashtags || '';
            } catch (_) {}
        }

        let aiSettingsSaveTimer = null;
        function scheduleCaptionAiSettingsSave() {
            if (aiSettingsSaveTimer) clearTimeout(aiSettingsSaveTimer);
            aiSettingsSaveTimer = setTimeout(async () => {
                try {
                    await api('/caption-ai/settings', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            prompt: document.getElementById('ai-prompt')?.value || '',
                            hashtags: document.getElementById('ai-hashtags')?.value || '',
                            brand: BRAND_ID,
                        }),
                    });
                } catch (_) {}
            }, 500);
        }

        function bindCaptionAiInputs() {
            document.getElementById('ai-prompt')?.addEventListener('input', scheduleCaptionAiSettingsSave);
            document.getElementById('ai-hashtags')?.addEventListener('input', scheduleCaptionAiSettingsSave);
        }

        async function flushCaptionAiSettings() {
            if (aiSettingsSaveTimer) {
                clearTimeout(aiSettingsSaveTimer);
                aiSettingsSaveTimer = null;
            }
            try {
                await api('/caption-ai/settings', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        prompt: document.getElementById('ai-prompt')?.value || '',
                        hashtags: document.getElementById('ai-hashtags')?.value || '',
                        brand: BRAND_ID,
                    }),
                });
            } catch (_) {}
        }

        function syncOnscreenTemplateOptions() {
            const templateEl = document.getElementById('onscreen-template');
            if (!templateEl) return;
            [...templateEl.options].forEach(opt => {
                const brand = opt.dataset.brand;
                if (!brand) return;
                opt.hidden = brand !== BRAND_ID;
            });
        }

        function updateBatchUI(status) {
            currentBatchStatus = status || currentBatchStatus;
            syncRunControlButtons({
                batchStatus: currentBatchStatus,
                slideshowJob: currentSlideshowJob,
            });
            setBatchPickerEnabled(!['connecting', 'running', 'disconnecting'].includes(String(currentBatchStatus.status || '').toLowerCase()));
            void refreshRunConsole();
        }

        async function loadBatchStatus() {
            try { updateBatchUI(await api('/batch/status')); } catch (_) {}
        }

        async function startFarmBatch(opts = {}) {
            ensureBatchSelectionDefaults();
            const slots = [...batchSelectedSlots].map(s => parseInt(s, 10)).filter(n => !isNaN(n)).sort((a, b) => a - b);
            if (!slots.length) {
                alert('Select at least one phone for the batch run.');
                return;
            }
            const fromPost = getSelectedFromPost('batch-from-post');
            if (!opts.skipConfirm) {
                const label = slots.length === 1 ? '1 phone' : `${slots.length} phones`;
                const postLabel = fromPost == null
                    ? 'full pipeline (prep → posts 1–3 → end)'
                    : `posts ${fromPost}→3 + end (skip prep)`;
                if (!confirm(`Run ${postLabel} on ${label}, one at a time (slots ${slots.join(', ')})?`)) return;
            }
            appendRunLog(`Starting batch for slots ${slots.join(', ')}`, 'info', 'batch');
            lastRunMessage = '';
            startRunConsolePoll();
            try {
                await flushPostTextSaves();
                await flushCaptionAiSettings();
                const res = await api('/batch/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ slots, from_post: fromPost, brand: BRAND_ID }),
                });
                updateBatchUI(res.status || {});
                refreshFarmDevices({ quiet: true });
                refreshActivity();
            } catch (err) { alert(`Batch failed: ${err.message}`); }
        }

        async function stopFarmBatch() {
            try {
                const res = await api('/batch/stop', { method: 'POST' });
                updateBatchUI(res.status || {});
                refreshFarmDevices({ quiet: true });
            } catch (err) { alert(`Kill failed: ${err.message}`); }
        }

        async function resetSession() {
            try {
                const res = await api('/batch/reset-session', { method: 'POST' });
                const slots = (res.cleared_slots || []).join(', ') || 'none';
                const videos = res.videos_removed ?? 0;
                appendRunLog(
                    `Session reset — cleared last run, upload state, and ${videos} gallery video(s) for all phones (slots: ${slots})`,
                    'info',
                    'batch',
                );
                refreshFarmDevices({ quiet: true });
            } catch (err) { alert(`Reset failed: ${err.message}`); }
        }

        async function clearCantCast(slot) {
            if (!confirm(`Clear "cant cast iMouse" tag for slot ${slot}? It will be attempted again on the next run.`)) return;
            try {
                await api(`/batch/clear-cant-cast/${encodeURIComponent(slot)}`, { method: 'POST' });
                appendRunLog(`Cleared cant cast tag for slot ${slot}`, 'info', 'batch');
                refreshFarmDevices({ quiet: true });
            } catch (err) { alert(`Clear failed: ${err.message}`); }
        }

        async function generateAiCaptions(allPhones = true) {
            if (!allPhones && !deviceId) {
                showBanner('Select a device first');
                return;
            }
            const statusEl = document.getElementById('ai-caption-status');
            const btnAll = document.getElementById('btn-ai-generate');
            const btnOne = document.getElementById('btn-ai-generate-device');
            const body = {
                prompt: document.getElementById('ai-prompt')?.value || '',
                hashtags: document.getElementById('ai-hashtags')?.value || '',
                onscreen_template: document.getElementById('onscreen-template')?.value || null,
                brand: BRAND_ID,
            };
            if (statusEl) statusEl.textContent = 'Generating…';
            if (btnAll) btnAll.disabled = true;
            if (btnOne) btnOne.disabled = true;
            try {
                await flushCaptionAiSettings();
                let res;
                if (allPhones) {
                    res = await api('/caption-ai/generate-all', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    });
                } else {
                    res = await api(`/devices/${enc(deviceId)}/caption-ai/generate`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    });
                }
                if (deviceId) await loadPostTexts();
                if (allPhones) {
                    const failed = res.failed || 0;
                    const ok = res.generated || 0;
                    if (statusEl) {
                        statusEl.textContent = failed ? `${ok} ok, ${failed} failed` : `${ok} phones generated`;
                        statusEl.className = failed ? 'adv-status-line error' : 'adv-status-line success';
                    }
                    if (failed && res.errors?.length) {
                        showBanner(res.errors.map(e => `Phone ${e.slot}: ${e.error}`).join(' · '));
                    }
                } else if (statusEl) {
                    statusEl.textContent = `Generated ${(res.posts || []).length} captions`;
                    statusEl.className = 'adv-status-line success';
                }
            } catch (err) {
                if (statusEl) {
                    statusEl.textContent = err.message;
                    statusEl.className = 'adv-status-line error';
                }
            } finally {
                if (btnAll) btnAll.disabled = false;
                if (btnOne) btnOne.disabled = false;
            }
        }

        async function applyOnscreenTemplate() {
            const templateKey = document.getElementById('onscreen-template')?.value || '';
            localStorage.setItem(`onscreenTemplate:${BRAND_ID}`, templateKey);
            if (!templateKey || !deviceId) return;
            try {
                const res = await api(`/devices/${enc(deviceId)}/onscreen-template/apply`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ template_key: templateKey, brand: BRAND_ID }),
                });
                for (const p of res.posts || []) {
                    const on = document.getElementById(`onscreen-${p.post}`);
                    if (on) on.value = p.onscreen || '';
                }
                hideBanner();
            } catch (err) {
                showBanner(err.message);
            }
        }

        async function clearAllPostTexts() {
            if (!deviceId) { showBanner('Select a device first'); return; }
            if (!confirm('Clear all captions for this device?')) return;
            try {
                await api(`/devices/${enc(deviceId)}/post-texts/clear?${brandQ()}`, { method: 'POST' });
                for (let i = 1; i <= 3; i++) {
                    const on = document.getElementById(`onscreen-${i}`);
                    const fin = document.getElementById(`final-${i}`);
                    if (on) on.value = '';
                    if (fin) fin.value = '';
                }
            } catch (err) { showBanner(err.message); }
        }

        async function loadPostTexts() {
            if (!deviceId) return;
            try {
                const res = await api(`/devices/${enc(deviceId)}/post-texts?${brandQ()}`);
                for (const p of res.posts || []) {
                    const title = document.querySelector(`.post-group[data-post="${p.post}"] .post-group-title`);
                    const file = p.media_file || p.placeholder || '';
                    if (title) title.textContent = file ? `Post ${p.post} · ${file}` : `Post ${p.post}`;
                    const on = document.getElementById(`onscreen-${p.post}`);
                    const fin = document.getElementById(`final-${p.post}`);
                    if (on) on.value = p.onscreen || '';
                    if (fin) fin.value = p.final || '';
                }
            } catch (_) {}
        }

        function schedulePostTextSave(postNum, field) {
            const key = `${postNum}-${field}`;
            if (postTextSaveTimers[key]) clearTimeout(postTextSaveTimers[key]);
            postTextSaveTimers[key] = setTimeout(async () => {
                if (!deviceId) return;
                const el = document.getElementById(`${field}-${postNum}`);
                if (!el) return;
                try {
                    await api(`/devices/${enc(deviceId)}/post-texts/${postNum}/${field}?${brandQ()}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ text: el.value }),
                    });
                } catch (_) {}
            }, 400);
        }

        function bindPostTextInputs() {
            document.querySelectorAll('#post-texts textarea[data-post]').forEach(el => {
                el.addEventListener('input', () => {
                    schedulePostTextSave(el.dataset.post, el.dataset.field);
                });
            });
        }

        async function execAction(type) {
            if (!deviceId) return;
            await api(`/devices/${enc(deviceId)}/actions/execute`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action_type: type, params: {} }),
            });
            refreshActivity();
        }

        async function init() {
            initBrandNav();
            bindAccountHandleInput();
            bindDebugPanel();
            restoreDebugPanel();
            connectWS();
            loadBatchSelection();
            bindPostTextInputs();
            bindCaptionAiInputs();
            const defaultTemplate = BRAND_ID === 'valcoin' ? 'valcoin_receipt' : 'america_sick';
            const savedTemplate = localStorage.getItem(`onscreenTemplate:${BRAND_ID}`) || defaultTemplate;
            const templateEl = document.getElementById('onscreen-template');
            if (templateEl && savedTemplate && [...templateEl.options].some(o => o.value === savedTemplate)) {
                templateEl.value = savedTemplate;
            }
            syncOnscreenTemplateOptions();
            try {
                await loadCaptionAiSettings();
                await loadDebugTests();
                await refreshSlideshowConfig();
                await refreshFarmDevices();
                const urlSlot = new URLSearchParams(location.search).get('slot');
                const savedSlot = localStorage.getItem('farmSelectedSlot');
                await selectSlot(urlSlot || savedSlot || firstOnlineSlot());
            } catch (e) {
                showBanner('Failed to initialize: ' + e.message);
            }
            setInterval(() => {
                refreshFarmDevices({ quiet: true });
                if (deviceId) updateDeviceMeta().catch(() => {});
            }, 10000);
            await loadBatchStatus();
            startRunConsolePoll();
            renderUnifiedLog();
            appendRunLog('Dashboard ready', 'success', 'system');
            window.addEventListener('beforeunload', () => {
                flushPostTextSaves();
                flushCaptionAiSettings();
            });
        }
        init();
