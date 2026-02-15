/**
 * PlexSubSetter - Alpine.js app state and browser interaction handlers.
 */

// Global state for current library
let currentLibrary = '';
let currentPage = 1;
let fetchGeneration = 0;

// Subtitle selections for download: { ratingKey: selectedIndex }
let subSelections = {};

/**
 * Main Alpine.js application state.
 */
function appState() {
    return {
        // UI state
        showSettings: false,
        showLogs: false,

        // Library browser state
        searchText: '',
        subFilter: (window.APP_SETTINGS && APP_SETTINGS.default_subtitle_filter) || 'all',
        showSubFilter: false,
        filterStatus: '',
        _cacheWaitingFilter: null,

        // Selection
        selectionCount: 0,

        // Options (initialized from saved settings)
        language: 'English',
        provider: 'opensubtitles',
        sdh: window.APP_SETTINGS ? APP_SETTINGS.prefer_hearing_impaired : false,
        forced: window.APP_SETTINGS ? APP_SETTINGS.prefer_forced : false,

        // Operation state
        operationRunning: false,
        progressPercent: 0,
        progressText: '',
        hasSearchResults: false,

        // Log refresh
        _logInterval: null,
        _logLoaded: false,

        init() {
            // Show log panel on startup if configured
            if (window.APP_SETTINGS && APP_SETTINGS.show_log_on_startup) {
                this.showLogs = true;
            }

            // Load libraries on init (and auto-select last library if configured)
            this.loadLibraries().then(() => {
                if (window.APP_SETTINGS && APP_SETTINGS.remember_last_library && APP_SETTINGS.last_library) {
                    const select = document.getElementById('library-select');
                    const option = Array.from(select.options).find(o => o.value === APP_SETTINGS.last_library);
                    if (option) {
                        select.value = APP_SETTINGS.last_library;
                        this.loadLibrary(APP_SETTINGS.last_library);
                    }
                }
            });

            // Auto-refresh logs while panel is open
            this.$watch('showLogs', (open) => {
                if (open) {
                    this._openLogPanel();
                } else {
                    this._closeLogPanel();
                }
            });
        },

        async _openLogPanel() {
            // Load full modal HTML if first time
            if (!this._logLoaded) {
                const container = document.getElementById('log-modal-content');
                if (!container) return;
                try {
                    const resp = await fetch('/logs');
                    if (resp.ok) {
                        container.innerHTML = await resp.text();
                        this._logLoaded = true;
                    }
                } catch (e) { return; }
            }
            // Always refresh content and scroll to bottom on open
            await this._refreshLogContent(true);
            // Start polling
            this._logInterval = setInterval(() => this._refreshLogContent(false), 3000);
        },

        _closeLogPanel() {
            if (this._logInterval) {
                clearInterval(this._logInterval);
                this._logInterval = null;
            }
        },

        async _refreshLogContent(scrollToBottom) {
            const logArea = document.getElementById('log-content-area');
            if (!logArea) return;
            try {
                const resp = await fetch('/logs/content');
                if (!resp.ok) return;
                const wasAtBottom = scrollToBottom || (logArea.scrollHeight - logArea.scrollTop - logArea.clientHeight) < 30;
                logArea.textContent = await resp.text();
                if (wasAtBottom) logArea.scrollTop = logArea.scrollHeight;
            } catch (e) { /* panel may have closed */ }
        },

        async loadLibraries() {
            try {
                const resp = await fetch('/libraries');
                const libs = await resp.json();
                const select = document.getElementById('library-select');
                select.innerHTML = '<option value="">Select a library...</option>';
                libs.forEach(lib => {
                    const opt = document.createElement('option');
                    opt.value = lib.title;
                    opt.textContent = `${lib.title} (${lib.type})`;
                    select.appendChild(opt);
                });
            } catch (e) {
                console.error('Failed to load libraries:', e);
            }
        },

        loadLibrary(name) {
            if (!name) return;
            currentLibrary = name;
            currentPage = 1;
            this.searchText = '';
            this.subFilter = (window.APP_SETTINGS && APP_SETTINGS.default_subtitle_filter) || 'all';
            this.showSubFilter = false;
            this.selectionCount = 0;
            this.hasSearchResults = false;
            subSelections = {};
            this._fetchItems();

            // Save as last library if remember is enabled
            if (window.APP_SETTINGS && APP_SETTINGS.remember_last_library) {
                fetch('/settings/last-library', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: name })
                }).catch(() => {});
            }
        },

        reloadLibrary() {
            if (!currentLibrary) return;
            currentPage = 1;
            this._fetchItems();
        },

        filterItems() {
            currentPage = 1;
            this._fetchItems();
        },

        setSubFilter(filter) {
            this.subFilter = filter;
            currentPage = 1;
            this._fetchItems();
        },

        async _fetchItems() {
            if (!currentLibrary) { console.log('_fetchItems: no currentLibrary'); return; }
            const myGen = ++fetchGeneration;
            console.log('_fetchItems: fetching page', currentPage, 'library', currentLibrary);
            const params = new URLSearchParams({
                page: currentPage,
                search: this.searchText,
                filter: this.subFilter,
            });

            const target = document.getElementById('browser-items');
            target.innerHTML = '<div class="text-center py-8"><div class="animate-spin rounded-full h-6 w-6 border-b-2 border-plex-gold mx-auto mb-2"></div><span class="text-gray-500 text-sm">Loading...</span></div>';

            try {
                const resp = await fetch(`/libraries/${encodeURIComponent(currentLibrary)}/items?${params}`);
                if (myGen !== fetchGeneration) return; // stale response, discard
                const html = await resp.text();
                target.innerHTML = html;

                // Detect if movie library (show sub filter) — only turn ON, never turn off from empty results
                if (html.includes('item-checkbox') && !html.includes('show-checkbox')) {
                    this.showSubFilter = true;
                } else if (html.includes('show-checkbox')) {
                    this.showSubFilter = false;
                }

                // Update selection count
                this._syncSelectionCount();
            } catch (e) {
                target.innerHTML = `<div class="text-red-400 text-sm text-center py-4">Error loading items: ${e.message}</div>`;
            }
        },

        _refreshExpandedSeasons() {
            // Re-fetch all currently expanded season episode panels to update subtitle indicators
            document.querySelectorAll('.expand-btn[data-expanded="true"]').forEach(btn => {
                const seasonDiv = btn.closest('[data-season-key]');
                if (!seasonDiv) return;
                const ratingKey = seasonDiv.dataset.seasonKey;
                const container = seasonDiv.querySelector('.episodes-container');
                if (!container || !currentLibrary) return;
                fetch(`/libraries/${encodeURIComponent(currentLibrary)}/seasons/${ratingKey}/episodes`)
                    .then(resp => resp.text())
                    .then(html => { container.innerHTML = html; })
                    .catch(() => {});
            });
        },

        async selectAll() {
            if (!currentLibrary) return;
            try {
                const resp = await fetch('/selection/add-all', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ library_name: currentLibrary })
                });
                const data = await resp.json();
                if (data.task_id) {
                    // Task-based selection - count will update via events
                    this.operationRunning = true;
                    this.progressText = 'Selecting all items...';
                } else {
                    this.selectionCount = data.count;
                }
            } catch (e) {
                console.error('Select all failed:', e);
            }
        },

        async clearSelection() {
            try {
                await fetch('/selection/clear', { method: 'POST' });
                this.selectionCount = 0;
                // Uncheck all visible checkboxes
                document.querySelectorAll('.item-checkbox, .show-checkbox, .season-checkbox').forEach(cb => cb.checked = false);
            } catch (e) {
                console.error('Clear selection failed:', e);
            }
        },

        _confirmBatch(action) {
            if (!window.APP_SETTINGS) return true;
            if (APP_SETTINGS.confirm_batch_operations && this.selectionCount >= APP_SETTINGS.batch_operation_threshold) {
                return confirm(`You are about to ${action} on ${this.selectionCount} items. Continue?`);
            }
            return true;
        },

        async searchSubtitles() {
            if (!this._confirmBatch('search')) return;
            this.operationRunning = true;
            this.progressPercent = 0;
            this.progressText = 'Searching for subtitles...';
            subSelections = {};

            try {
                const resp = await fetch('/subtitles/search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        language: this.language,
                        providers: this.provider,
                        sdh: this.sdh,
                        forced: this.forced,
                    })
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({ error: 'Request failed' }));
                    this._showInfoMessage(err.error || 'Search request failed', 'error');
                    this.operationRunning = false;
                    return;
                }
                const data = await resp.json();
                if (data.error) {
                    this._showInfoMessage(data.error, 'error');
                }
                // Results will arrive via SSE task_complete, with polling fallback
                if (data.task_id) this._pollTaskStatus(data.task_id);
            } catch (e) {
                this.operationRunning = false;
                this._showInfoMessage('Search failed: ' + e.message, 'error');
            }
        },

        async listSubtitles() {
            this.operationRunning = true;
            this.progressText = 'Fetching subtitle info...';

            try {
                const resp = await fetch('/subtitles/list', { method: 'POST' });
                const html = await resp.text();
                document.getElementById('info-panel').innerHTML = html;
                this.operationRunning = false;
            } catch (e) {
                this.operationRunning = false;
                this._showInfoMessage('Failed to list subtitles: ' + e.message, 'error');
            }
        },

        async dryRun() {
            if (!this._confirmBatch('dry run')) return;
            this.operationRunning = true;
            this.progressPercent = 0;
            this.progressText = 'Running dry run...';

            try {
                const resp = await fetch('/subtitles/dry-run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        language: this.language,
                        providers: this.provider,
                        sdh: this.sdh,
                        forced: this.forced,
                    })
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({ error: 'Request failed' }));
                    this._showInfoMessage(err.error || 'Dry run request failed', 'error');
                    this.operationRunning = false;
                    return;
                }
                const data = await resp.json();
                if (data.error) {
                    this._showInfoMessage(data.error, 'error');
                    this.operationRunning = false;
                }
                // Results via SSE task_complete, with polling fallback
                if (data.task_id) this._pollTaskStatus(data.task_id);
            } catch (e) {
                this.operationRunning = false;
                this._showInfoMessage('Dry run failed: ' + e.message, 'error');
            }
        },

        async deleteSubtitles() {
            // Always confirm deletes regardless of threshold
            if (!confirm(`Delete ALL subtitle streams from ${this.selectionCount} selected items?\n\nThis cannot be undone!`)) return;

            this.operationRunning = true;
            this.progressPercent = 0;
            this.progressText = 'Deleting subtitles...';

            try {
                const resp = await fetch('/subtitles/delete', { method: 'POST' });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({ error: 'Request failed' }));
                    this._showInfoMessage(err.error || 'Delete request failed', 'error');
                    this.operationRunning = false;
                    return;
                }
                const data = await resp.json();
                if (data.error) {
                    this._showInfoMessage(data.error, 'error');
                    this.operationRunning = false;
                }
                // Results via SSE task_complete, with polling fallback
                if (data.task_id) this._pollTaskStatus(data.task_id);
            } catch (e) {
                this.operationRunning = false;
                this._showInfoMessage('Delete failed: ' + e.message, 'error');
            }
        },

        async downloadSubtitles() {
            if (!this._confirmBatch('download')) return;
            this.operationRunning = true;
            this.progressPercent = 0;
            this.progressText = 'Downloading subtitles...';

            try {
                const resp = await fetch('/subtitles/download', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        selections: subSelections,
                        language: this.language,
                    })
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({ error: 'Request failed' }));
                    this._showInfoMessage(err.error || 'Download request failed', 'error');
                    this.operationRunning = false;
                    return;
                }
                const data = await resp.json();
                if (data.error) {
                    this._showInfoMessage(data.error, 'error');
                    this.operationRunning = false;
                }
                // Results via SSE task_complete, with polling fallback
                if (data.task_id) this._pollTaskStatus(data.task_id);
            } catch (e) {
                this.operationRunning = false;
                this._showInfoMessage('Download failed: ' + e.message, 'error');
            }
        },

        // SSE event handlers (called from sse.js)
        handleProgress(data) {
            if (data.total && data.current) {
                this.progressPercent = Math.round((data.current / data.total) * 100);
                this.progressText = `${data.current}/${data.total}` + (data.item ? ` - ${data.item}` : '');
            }
        },

        async handleTaskComplete(data) {
            this.operationRunning = false;
            this.progressPercent = 100;

            if (data.task_type === 'subtitle_search') {
                // Fetch and show search results
                try {
                    const resp = await fetch('/subtitles/search-results');
                    const html = await resp.text();
                    document.getElementById('info-panel').innerHTML = html;
                    this.hasSearchResults = data.success;
                    // Auto-select best subtitle (index 0) for all items
                    document.querySelectorAll('[data-sub-select]').forEach(sel => {
                        const rk = parseInt(sel.dataset.subSelect);
                        const val = parseInt(sel.value);
                        window.setSubSelection(rk, val);
                    });
                } catch (e) {
                    console.error('Failed to load search results:', e);
                }
            } else if (data.task_type === 'dry_run') {
                try {
                    const resp = await fetch('/subtitles/dry-run-results');
                    const html = await resp.text();
                    document.getElementById('info-panel').innerHTML = html;
                } catch (e) {
                    console.error('Failed to load dry run results:', e);
                }
            } else if (data.task_type === 'subtitle_download') {
                this.hasSearchResults = false;
                subSelections = {};
                if (data.success) {
                    // Clear selection after successful download
                    await this.clearSelection();
                    // Fetch and show download summary
                    try {
                        const resp = await fetch('/subtitles/download-results');
                        const html = await resp.text();
                        document.getElementById('info-panel').innerHTML = html;
                    } catch (e) {
                        this._showInfoMessage('Download complete!', 'success');
                    }
                } else {
                    this._showInfoMessage(`Download failed: ${data.error || 'Unknown error'}`, 'error');
                }
                // Refresh browser items and expanded seasons to update subtitle indicators
                this._fetchItems();
                this._refreshExpandedSeasons();
            } else if (data.task_type === 'subtitle_delete') {
                this._showInfoMessage(
                    data.success ? 'Subtitles deleted successfully.' : `Delete failed: ${data.error || 'Unknown error'}`,
                    data.success ? 'success' : 'error'
                );
                this._fetchItems();
                this._refreshExpandedSeasons();
            } else if (data.task_type === 'select_all') {
                this._syncSelectionCount();
                this._fetchItems();
            }
        },

        _pollTaskStatus(taskId) {
            // Polling fallback in case SSE misses the task_complete event
            const poll = async () => {
                if (!this.operationRunning) return; // SSE already handled it
                try {
                    const resp = await fetch(`/subtitles/task/${taskId}`);
                    if (!resp.ok) return;
                    const task = await resp.json();
                    if (task.status === 'complete' || task.status === 'error') {
                        // SSE missed it — handle completion now
                        if (this.operationRunning) {
                            this.handleTaskComplete({
                                task_id: taskId,
                                task_type: task.type,
                                success: task.status === 'complete',
                                error: task.error || null,
                            });
                        }
                        return;
                    }
                    // Still running, poll again
                    setTimeout(poll, 2000);
                } catch (e) {
                    // Network error, retry
                    setTimeout(poll, 3000);
                }
            };
            // Start polling after a delay to give SSE a chance first
            setTimeout(poll, 3000);
        },

        handleSubtitleStatus(data) {
            // Update the subtitle indicator for this item in real-time
            const key = data.rating_key;
            const item = document.querySelector(`.browser-item[data-key="${key}"]`);
            if (!item) return;

            const indicator = item.querySelector('.sub-indicator');
            if (indicator) {
                if (data.has_subtitles) {
                    indicator.className = 'sub-indicator text-green-500 font-bold text-xs';
                    indicator.title = 'Has subtitles';
                    indicator.innerHTML = '&#10003;';
                } else {
                    indicator.className = 'sub-indicator text-red-500 text-xs';
                    indicator.title = 'No subtitles';
                    indicator.innerHTML = '&#10007;';
                }
            }
        },

        _showInfoMessage(msg, type) {
            const panel = document.getElementById('info-panel');
            const color = type === 'error' ? 'text-red-400' : type === 'success' ? 'text-green-400' : 'text-gray-300';
            panel.innerHTML = `<div class="${color} text-sm text-center py-8">${msg}</div>`;
        },

        async _syncSelectionCount() {
            try {
                const resp = await fetch('/selection');
                const data = await resp.json();
                this.selectionCount = data.count;
            } catch (e) {
                // silently fail
            }
        },
    }
}

// === Global functions called from template onclick handlers ===

window.toggleItem = async function(checkbox) {
    const key = parseInt(checkbox.dataset.key);
    const action = checkbox.checked ? 'add' : 'remove';
    try {
        const resp = await fetch(`/selection/${action}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keys: [key] })
        });
        const data = await resp.json();
        // Update Alpine state
        const appEl = document.querySelector('[x-data]');
        if (appEl && appEl._x_dataStack) {
            Alpine.$data(appEl).selectionCount = data.count;
        }
    } catch (e) {
        console.error('Toggle item failed:', e);
    }
};

window.toggleShow = async function(btn, libraryName, ratingKey) {
    const expanded = btn.dataset.expanded === 'true';
    const container = btn.closest('[data-key]').querySelector('.seasons-container');

    if (expanded) {
        container.classList.add('hidden');
        container.innerHTML = '';
        btn.dataset.expanded = 'false';
    } else {
        btn.dataset.expanded = 'true';

        try {
            const resp = await fetch(`/libraries/${encodeURIComponent(libraryName)}/shows/${ratingKey}/seasons`);
            const html = await resp.text();
            container.innerHTML = html;
            container.classList.remove('hidden');
        } catch (e) {
            btn.dataset.expanded = 'false';
            console.error('Failed to load seasons:', e);
        }
    }
};

window.toggleSeason = async function(btn, libraryName, ratingKey) {
    const expanded = btn.dataset.expanded === 'true';
    const container = btn.closest('[data-season-key]').querySelector('.episodes-container');

    if (expanded) {
        container.classList.add('hidden');
        container.innerHTML = '';
        btn.dataset.expanded = 'false';
    } else {
        btn.dataset.expanded = 'true';

        try {
            const resp = await fetch(`/libraries/${encodeURIComponent(libraryName)}/seasons/${ratingKey}/episodes`);
            const html = await resp.text();
            container.innerHTML = html;
            container.classList.remove('hidden');
        } catch (e) {
            btn.dataset.expanded = 'false';
            console.error('Failed to load episodes:', e);
        }
    }
};

window.toggleShowSelect = async function(checkbox, libraryName, ratingKey) {
    // When a show is selected, we need to select all its episodes server-side
    const showName = checkbox.dataset.showName;
    // For now, trigger expand and select all episodes
    // This would need a dedicated endpoint to select all show episodes
    const key = parseInt(checkbox.dataset.key);
    // Simple approach: just add the show key - server will resolve episodes
    try {
        const action = checkbox.checked ? 'add' : 'remove';
        const resp = await fetch(`/selection/${action}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keys: [key] })
        });
        const data = await resp.json();
        const appEl = document.querySelector('[x-data]');
        if (appEl && appEl._x_dataStack) {
            Alpine.$data(appEl).selectionCount = data.count;
        }
    } catch (e) {
        console.error('Show select failed:', e);
    }
};

window.toggleSeasonSelect = async function(checkbox, libraryName, ratingKey) {
    const key = parseInt(checkbox.dataset.key);
    const isChecked = checkbox.checked;
    try {
        const action = isChecked ? 'add' : 'remove';
        const resp = await fetch(`/selection/${action}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keys: [key] })
        });
        const data = await resp.json();
        const appEl = document.querySelector('[x-data]');
        if (appEl && appEl._x_dataStack) {
            Alpine.$data(appEl).selectionCount = data.count;
        }
        // Sync episode checkboxes within this season's panel
        const seasonDiv = checkbox.closest('[data-season-key]');
        if (seasonDiv) {
            const episodeContainer = seasonDiv.querySelector('.episodes-container');
            if (episodeContainer) {
                episodeContainer.querySelectorAll('.item-checkbox').forEach(cb => {
                    cb.checked = isChecked;
                });
            }
        }
    } catch (e) {
        console.error('Season select failed:', e);
    }
};

window.changePage = function(page) {
    console.log('changePage called with page:', page, 'currentLibrary:', currentLibrary);
    currentPage = page;
    const appEl = document.querySelector('[x-data]');
    if (appEl && appEl._x_dataStack) {
        Alpine.$data(appEl)._fetchItems();
    } else {
        console.error('Could not find Alpine app state');
    }
};

window.setSubSelection = function(ratingKey, index) {
    subSelections[ratingKey] = index;
};
