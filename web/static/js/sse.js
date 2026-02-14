/**
 * SSE (Server-Sent Events) client for PlexSubSetter.
 * Connects to /events and dispatches events to the Alpine.js app state.
 */

(function() {
    let eventSource = null;
    let reconnectDelay = 1000;

    function connect() {
        eventSource = new EventSource('/events');

        eventSource.onopen = function() {
            reconnectDelay = 1000; // Reset on successful connect
        };

        eventSource.addEventListener('progress', function(e) {
            const data = JSON.parse(e.data);
            const appEl = document.querySelector('[x-data="appState()"]');
            if (appEl && appEl.__x) {
                appEl.__x.$data.handleProgress(data);
            }
        });

        eventSource.addEventListener('task_complete', function(e) {
            const data = JSON.parse(e.data);
            const appEl = document.querySelector('[x-data="appState()"]');
            if (appEl && appEl.__x) {
                appEl.__x.$data.handleTaskComplete(data);
            }
        });

        eventSource.addEventListener('status', function(e) {
            const data = JSON.parse(e.data);
            // Could update a status bar if needed
        });

        eventSource.addEventListener('log', function(e) {
            const data = JSON.parse(e.data);
            // Could display in a live log panel
        });

        eventSource.addEventListener('subtitle_status', function(e) {
            const data = JSON.parse(e.data);
            const appEl = document.querySelector('[x-data="appState()"]');
            if (appEl && appEl.__x) {
                appEl.__x.$data.handleSubtitleStatus(data);
            }
        });

        eventSource.onerror = function() {
            eventSource.close();
            // Reconnect with backoff
            setTimeout(connect, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, 30000);
        };
    }

    // Only connect if we're on the app page (not login/servers)
    if (document.querySelector('[x-data="appState()"]')) {
        connect();
    }
})();
