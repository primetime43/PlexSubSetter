/**
 * PlexSubSetter - Alpine.js app state and browser interaction handlers.
 */

// Global state for current library
let currentLibrary = '';
let currentPage = 1;

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
        subFilter: 'all',
        showSubFilter: false,
        filterStatus: '',

        // Selection
        selectionCount: 0,

        // Options
        language: 'English',
        provider: 'opensubtitles',
        sdh: false,
        forced: false,

        // Operation state
        operationRunning: false,
        progressPercent: 0,
        progressText: '',
        hasSearchResults: false,

        init() {
            // Load libraries on init
            this.loadLibraries();

            // Listen for SSE events
            this.$watch('operationRunning', () => {});
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
            this.subFilter = 'all';
            this.showSubFilter = false;
            this.selectionCount = 0;
            this.hasSearchResults = false;
            subSelections = {};
            this._fetchItems();
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
            if (!currentLibrary) return;
            const params = new URLSearchParams({
                page: currentPage,
                search: this.searchText,
                filter: this.subFilter,
            });

            const target = document.getElementById('browser-items');
            target.innerHTML = '<div class="text-center py-8"><div class="animate-spin rounded-full h-6 w-6 border-b-2 border-plex-gold mx-auto mb-2"></div><span class="text-gray-500 text-sm">Loading...</span></div>';

            try {
                const resp = await fetch(`/libraries/${encodeURIComponent(currentLibrary)}/items?${params}`);
                const html = await resp.text();
                target.innerHTML = html;

                // Detect if movie library (show sub filter)
                this.showSubFilter = html.includes('item-checkbox') && !html.includes('show-checkbox');

                // Update selection count
                this._syncSelectionCount();
            } catch (e) {
                target.innerHTML = `<div class="text-red-400 text-sm text-center py-4">Error loading items: ${e.message}</div>`;
            }
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

        async searchSubtitles() {
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
                    })
                });
                const data = await resp.json();
                if (data.error) {
                    this._showInfoMessage(data.error, 'error');
                }
                // Results will arrive via SSE task_complete
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
                    })
                });
                const data = await resp.json();
                if (data.error) {
                    this._showInfoMessage(data.error, 'error');
                    this.operationRunning = false;
                }
                // Results via SSE task_complete
            } catch (e) {
                this.operationRunning = false;
                this._showInfoMessage('Dry run failed: ' + e.message, 'error');
            }
        },

        async deleteSubtitles() {
            if (!confirm('Delete ALL subtitle streams from selected items?\n\nThis cannot be undone!')) return;

            this.operationRunning = true;
            this.progressPercent = 0;
            this.progressText = 'Deleting subtitles...';

            try {
                const resp = await fetch('/subtitles/delete', { method: 'POST' });
                const data = await resp.json();
                if (data.error) {
                    this._showInfoMessage(data.error, 'error');
                    this.operationRunning = false;
                }
                // Results via SSE task_complete
            } catch (e) {
                this.operationRunning = false;
                this._showInfoMessage('Delete failed: ' + e.message, 'error');
            }
        },

        async downloadSubtitles() {
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
                const data = await resp.json();
                if (data.error) {
                    this._showInfoMessage(data.error, 'error');
                    this.operationRunning = false;
                }
                // Results via SSE task_complete
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
                this._showInfoMessage(
                    data.success ? 'Download complete!' : `Download failed: ${data.error || 'Unknown error'}`,
                    data.success ? 'success' : 'error'
                );
                // Refresh browser items to update subtitle indicators
                this._fetchItems();
            } else if (data.task_type === 'subtitle_delete') {
                this._showInfoMessage(
                    data.success ? 'Subtitles deleted successfully.' : `Delete failed: ${data.error || 'Unknown error'}`,
                    data.success ? 'success' : 'error'
                );
                this._fetchItems();
            } else if (data.task_type === 'select_all') {
                this._syncSelectionCount();
                this._fetchItems();
            }
        },

        handleSubtitleStatus(data) {
            // Could update individual indicators without full refresh
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
        const appEl = document.querySelector('[x-data="appState()"]');
        if (appEl && appEl.__x) {
            appEl.__x.$data.selectionCount = data.count;
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
        const appEl = document.querySelector('[x-data="appState()"]');
        if (appEl && appEl.__x) {
            appEl.__x.$data.selectionCount = data.count;
        }
    } catch (e) {
        console.error('Show select failed:', e);
    }
};

window.toggleSeasonSelect = async function(checkbox, libraryName, ratingKey) {
    const key = parseInt(checkbox.dataset.key);
    try {
        const action = checkbox.checked ? 'add' : 'remove';
        const resp = await fetch(`/selection/${action}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keys: [key] })
        });
        const data = await resp.json();
        const appEl = document.querySelector('[x-data="appState()"]');
        if (appEl && appEl.__x) {
            appEl.__x.$data.selectionCount = data.count;
        }
    } catch (e) {
        console.error('Season select failed:', e);
    }
};

window.changePage = function(page) {
    currentPage = page;
    const appEl = document.querySelector('[x-data="appState()"]');
    if (appEl && appEl.__x) {
        appEl.__x.$data._fetchItems();
    }
};

window.setSubSelection = function(ratingKey, index) {
    subSelections[ratingKey] = index;
};
