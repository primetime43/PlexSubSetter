"""
In-memory session state for PlexSubSetter.

Holds all runtime state: Plex connection, selections, caches.
Thread-safe via Lock for mutations.
"""

import threading
import logging


class SessionState:
    """Thread-safe in-memory session state for a single-user local app."""

    def __init__(self):
        self._lock = threading.Lock()
        self.account = None          # MyPlexAccount
        self.plex = None             # PlexServer
        self.selected_items = []     # list of Plex video items (Movie/Episode)
        self.search_results = {}     # {item: [subtitles]}
        self.subtitle_status_cache = {}  # {rating_key: bool}
        self.libraries = []          # list of library sections
        self.current_library = None  # current library section object
        self.all_movies = None       # cached movie list for current library
        self.all_shows = None        # cached show list for current library
        self.library_items_cache = {}  # {library_name: items}
        self.current_log_file = None
        self.subtitle_selections = {}  # {rating_key: selected_index}

    def set_account(self, account):
        with self._lock:
            self.account = account

    def set_plex(self, plex):
        with self._lock:
            self.plex = plex

    def clear_auth(self):
        with self._lock:
            self.account = None
            self.plex = None
            self.selected_items.clear()
            self.search_results.clear()
            self.subtitle_status_cache.clear()
            self.libraries.clear()
            self.current_library = None
            self.all_movies = None
            self.all_shows = None
            self.library_items_cache.clear()
            self.subtitle_selections.clear()

    def add_selection(self, item):
        with self._lock:
            if item not in self.selected_items:
                self.selected_items.append(item)

    def remove_selection(self, item):
        with self._lock:
            if item in self.selected_items:
                self.selected_items.remove(item)

    def clear_selection(self):
        with self._lock:
            self.selected_items.clear()

    def set_selection_by_keys(self, rating_keys, items_map):
        """Set selection from a list of rating keys."""
        with self._lock:
            self.selected_items = [
                items_map[k] for k in rating_keys if k in items_map
            ]

    def get_selected_keys(self):
        with self._lock:
            return [item.ratingKey for item in self.selected_items]

    def cache_subtitle_status(self, rating_key, has_subs):
        with self._lock:
            self.subtitle_status_cache[rating_key] = has_subs

    def get_subtitle_status(self, rating_key):
        with self._lock:
            return self.subtitle_status_cache.get(rating_key)

    def clear_subtitle_cache(self, rating_keys=None):
        with self._lock:
            if rating_keys:
                for key in rating_keys:
                    self.subtitle_status_cache.pop(key, None)
            else:
                self.subtitle_status_cache.clear()

    def get_items_map(self):
        """Get a map of rating_key -> item for all cached items."""
        items_map = {}
        with self._lock:
            if self.all_movies:
                for m in self.all_movies:
                    items_map[m.ratingKey] = m
            if self.all_shows:
                for s in self.all_shows:
                    items_map[s.ratingKey] = s
        return items_map
