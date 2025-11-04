"""
Library browser component for managing Plex library content display and selection.

This module contains the LibraryBrowser class which handles all library content
loading, filtering, selection, and subtitle status display functionality.
"""

import customtkinter as ctk
import threading
import logging
from concurrent.futures import ThreadPoolExecutor
from plexapi.video import Movie, Episode, Show, Season


class LibraryBrowser:
    """Handles library content browsing, filtering, and selection."""

    def __init__(self, parent_frame, browser_scroll):
        """
        Initialize the library browser.

        Args:
            parent_frame: MainAppFrame instance for accessing parent callbacks
            browser_scroll: CTkScrollableFrame widget for displaying library content
        """
        self.parent = parent_frame
        self.browser_scroll = browser_scroll

        # State management
        self.all_movies = None  # Store all movies for filtering
        self.all_shows = None  # Store all shows for filtering
        self.show_frames = {}  # {show: (frame, expand_var, is_expanded)}
        self.season_frames = {}  # {season: (frame, expand_var, is_expanded)}

        # Pagination state
        self.items_per_page = 30
        self.current_page = 1

        # Performance optimizations
        self.subtitle_cache = {}  # Cache subtitle status: {item_key: bool}
        self.thread_pool = ThreadPoolExecutor(max_workers=5)  # Limit concurrent threads

    def clear_search(self):
        """Clear the search filter."""
        self.parent.search_text.set("")
        self.parent.filter_status_label.configure(text="")

    def set_subtitle_filter(self, filter_type):
        """Set the subtitle status filter (all, missing, has)."""
        self.parent.subtitle_status_filter = filter_type

        # Update button appearances to show active filter
        if filter_type == "all":
            self.parent.filter_all_btn.configure(fg_color=("blue", "#1f538d"), border_width=0)
            self.parent.filter_missing_btn.configure(fg_color="transparent", border_width=1)
            self.parent.filter_has_btn.configure(fg_color="transparent", border_width=1)
        elif filter_type == "missing":
            self.parent.filter_all_btn.configure(fg_color="transparent", border_width=1)
            self.parent.filter_missing_btn.configure(fg_color=("red", "#8b0000"), border_width=0)
            self.parent.filter_has_btn.configure(fg_color="transparent", border_width=1)
        elif filter_type == "has":
            self.parent.filter_all_btn.configure(fg_color="transparent", border_width=1)
            self.parent.filter_missing_btn.configure(fg_color="transparent", border_width=1)
            self.parent.filter_has_btn.configure(fg_color=("green", "#2d7a2d"), border_width=0)

        # Reapply filter
        self.filter_items()

    def filter_items(self):
        """Filter items based on search text and subtitle status."""
        # If we have movies or shows loaded, reload the page to apply search filter
        if self.all_movies is not None:
            self.load_movie_page(1)  # Reset to page 1 when filtering
        elif self.all_shows is not None:
            self.load_show_page(1)  # Reset to page 1 when filtering

    def apply_subtitle_status_filter(self):
        """Apply subtitle status filter to items."""
        filter_type = self.parent.subtitle_status_filter

        if filter_type == "all":
            # Show all items
            for frame in self.parent.top_level_frames:
                frame.grid()
            self.parent.filter_status_label.configure(text="")
        else:
            # Filter by subtitle status
            visible_count = 0
            total_count = len(self.parent.top_level_frames)

            for frame_data in self.parent.top_level_frames:
                if isinstance(frame_data, tuple):
                    frame, item = frame_data
                else:
                    # Fallback for old format
                    frame = frame_data
                    continue

                has_subs = self.check_has_subtitles(item, force_refresh=False)

                if filter_type == "missing" and not has_subs:
                    frame.grid()
                    visible_count += 1
                elif filter_type == "has" and has_subs:
                    frame.grid()
                    visible_count += 1
                else:
                    frame.grid_remove()

            # Update filter status label
            if filter_type == "missing":
                self.parent.filter_status_label.configure(
                    text=f"Showing {visible_count}/{total_count} items without subtitles"
                )
            elif filter_type == "has":
                self.parent.filter_status_label.configure(
                    text=f"Showing {visible_count}/{total_count} items with subtitles"
                )

    def load_library_content(self):
        """Load movies or TV shows from selected library."""
        library_name = self.parent.library_combo.get()
        if not library_name:
            self.parent.update_status("Please select a library")
            return

        # Clear browser
        for widget in self.browser_scroll.winfo_children():
            widget.destroy()
        self.parent.selected_items.clear()
        self.parent.top_level_frames.clear()
        self.show_frames.clear()
        self.season_frames.clear()
        self.parent.update_selection_label()

        def task():
            """Background thread to load library content from Plex."""
            self.parent.show_browser_loading()
            try:
                # Get library
                library = self.parent.plex.library.section(library_name)
                self.parent.current_library = library

                if library.type == 'movie':
                    items = library.all()
                    self.all_movies = items
                    self.all_shows = None
                    self.parent.safe_after(0, lambda: self.populate_movies(items))
                elif library.type == 'show':
                    items = library.all()
                    self.all_shows = items
                    self.all_movies = None
                    self.parent.safe_after(0, lambda: self.populate_shows(items))
                else:
                    self.parent.safe_after(0, lambda: self.parent.update_status(
                        f"Unsupported library type: {library.type}"))

                self.parent.safe_after(0, lambda: self.parent.update_status(
                    f"Loaded {len(items)} items from '{library_name}'"))
            except Exception as e:
                self.parent.log(f"Error loading library: {e}", level="error")
                self.parent.safe_after(0, lambda: self.parent.update_status(f"Error loading library: {e}"))
            finally:
                self.parent.hide_browser_loading()

        threading.Thread(target=task, daemon=True).start()

    def truncate_title(self, title, max_length=80):
        """Truncate title if too long."""
        if len(title) > max_length:
            return title[:max_length-3] + "..."
        return title

    def populate_movies(self, movies):
        """Setup movies and load first page."""
        self.all_movies = movies
        self.all_shows = None
        self.current_page = 1
        self.load_movie_page(1)

    def load_movie_page(self, page_num):
        """Load a specific page of filtered movies."""
        # Apply search filter
        search_term = self.parent.search_text.get().lower()
        if search_term:
            filtered_movies = [m for m in self.all_movies if search_term in m.title.lower()]
        else:
            filtered_movies = self.all_movies

        # Calculate pagination
        total_movies = len(filtered_movies)
        total_pages = max(1, (total_movies + self.items_per_page - 1) // self.items_per_page)

        if page_num < 1 or page_num > total_pages:
            return

        # Clear browser
        for widget in self.browser_scroll.winfo_children():
            widget.destroy()
        self.parent.top_level_frames.clear()

        self.current_page = page_num

        # Calculate range
        start_idx = (page_num - 1) * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, total_movies)

        if not filtered_movies:
            ctk.CTkLabel(self.browser_scroll, text="No movies found",
                        font=ctk.CTkFont(size=14), text_color="gray").pack(pady=20)
            self.parent.pagination_frame.grid_remove()
            if search_term:
                self.parent.filter_status_label.configure(
                    text=f"No matches for '{search_term}' (0/{len(self.all_movies)} movies)"
                )
            return

        # Create UI for movies on this page
        for i in range(start_idx, end_idx):
            movie = filtered_movies[i]

            # Movie frame
            movie_frame = ctk.CTkFrame(self.browser_scroll, fg_color=("gray85", "gray25"))
            movie_frame.pack(fill="x", padx=10, pady=3)
            movie_frame.grid_columnconfigure(1, weight=1)

            # Store frame reference
            self.parent.top_level_frames.append((movie_frame, movie))

            # Selection checkbox
            var = ctk.BooleanVar(value=False)
            checkbox = ctk.CTkCheckBox(movie_frame, text="", variable=var, width=20,
                                      command=lambda m=movie, v=var: self.on_item_selected(m, v))
            checkbox.grid(row=0, column=0, padx=(10, 5), pady=8, sticky="w")

            # Title with year
            year = f" ({movie.year})" if hasattr(movie, 'year') and movie.year else ""
            title_text = self.truncate_title(movie.title + year)
            title_label = ctk.CTkLabel(movie_frame, text=title_text,
                                      font=ctk.CTkFont(size=12), anchor="w")
            title_label.grid(row=0, column=1, padx=5, pady=8, sticky="ew")

            # Subtitle status indicator
            status_label = ctk.CTkLabel(movie_frame, text="", width=20)
            status_label.grid(row=0, column=2, padx=10, pady=8)

            # Check subtitle status using thread pool
            def check_status(item=movie, label=status_label):
                if self.parent._is_destroyed:
                    return
                has_subs = self.check_has_subtitles(item)
                if self.parent._is_destroyed:
                    return
                if has_subs:
                    self.parent.safe_after(0, lambda: label.configure(
                        text="✓", text_color=("green", "#2d7a2d"), font=ctk.CTkFont(size=14, weight="bold")))
                else:
                    self.parent.safe_after(0, lambda: label.configure(
                        text="✗", text_color=("red", "#8b0000"), font=ctk.CTkFont(size=14)))

            # Submit to thread pool instead of creating new thread
            self.thread_pool.submit(check_status)

        # Update pagination controls
        self.update_pagination_controls(page_num, total_pages, start_idx, end_idx, total_movies, "movies")

        # Update filter status
        if search_term:
            self.parent.filter_status_label.configure(
                text=f"Page {page_num}/{total_pages} - {len(filtered_movies)}/{len(self.all_movies)} movies matching '{search_term}'"
            )
        else:
            self.parent.filter_status_label.configure(text="")

        self.parent.update_selection_label()

    def update_pagination_controls(self, page_num, total_pages, start_idx, end_idx, total_items, item_type):
        """Update pagination controls UI."""
        # Clear pagination frame
        for widget in self.parent.pagination_frame.winfo_children():
            widget.destroy()

        # Previous button
        prev_btn = ctk.CTkButton(self.parent.pagination_frame, text="◀ Previous",
                                width=100, height=32,
                                command=lambda: (self.load_movie_page(page_num - 1) if item_type == "movies"
                                               else self.load_show_page(page_num - 1)),
                                state="normal" if page_num > 1 else "disabled")
        prev_btn.grid(row=0, column=0, padx=5)

        # Page label
        page_label = ctk.CTkLabel(self.parent.pagination_frame,
                                 text=f"Page {page_num} of {total_pages}",
                                 font=ctk.CTkFont(size=12))
        page_label.grid(row=0, column=1, padx=5)

        # Next button
        next_btn = ctk.CTkButton(self.parent.pagination_frame, text="Next ▶",
                                width=100, height=32,
                                command=lambda: (self.load_movie_page(page_num + 1) if item_type == "movies"
                                               else self.load_show_page(page_num + 1)),
                                state="normal" if page_num < total_pages else "disabled")
        next_btn.grid(row=0, column=2, padx=5)

        # Show pagination frame
        self.parent.pagination_frame.grid()

        # Update status
        self.parent.update_status(f"Page {page_num}/{total_pages} ({start_idx + 1}-{end_idx} of {total_items} {item_type})")

    def populate_shows(self, shows):
        """Setup shows and load first page."""
        self.all_shows = shows
        self.all_movies = None
        self.current_page = 1
        self.load_show_page(1)

    def load_show_page(self, page_num):
        """Load a specific page of filtered shows."""
        # Apply search filter
        search_term = self.parent.search_text.get().lower()
        if search_term:
            filtered_shows = [s for s in self.all_shows if search_term in s.title.lower()]
        else:
            filtered_shows = self.all_shows

        # Calculate pagination
        total_shows = len(filtered_shows)
        total_pages = max(1, (total_shows + self.items_per_page - 1) // self.items_per_page)

        if page_num < 1 or page_num > total_pages:
            return

        # Clear browser
        for widget in self.browser_scroll.winfo_children():
            widget.destroy()
        self.parent.top_level_frames.clear()
        self.show_frames.clear()
        self.season_frames.clear()

        self.current_page = page_num

        # Calculate range
        start_idx = (page_num - 1) * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, total_shows)

        if not filtered_shows:
            ctk.CTkLabel(self.browser_scroll, text="No shows found",
                        font=ctk.CTkFont(size=14), text_color="gray").pack(pady=20)
            self.parent.pagination_frame.grid_remove()
            if search_term:
                self.parent.filter_status_label.configure(
                    text=f"No matches for '{search_term}' (0/{len(self.all_shows)} shows)"
                )
            return

        # Create UI for shows on this page
        for i in range(start_idx, end_idx):
            show = filtered_shows[i]

            # Show frame (collapsible)
            show_frame = ctk.CTkFrame(self.browser_scroll, fg_color=("gray85", "gray25"))
            show_frame.pack(fill="x", padx=10, pady=3)
            show_frame.grid_columnconfigure(2, weight=1)

            # Store frame reference
            self.parent.top_level_frames.append((show_frame, show))

            # Expand/collapse variable
            expand_var = ctk.BooleanVar(value=False)

            # Expand/collapse button
            expand_btn = ctk.CTkButton(show_frame, text="▶", width=25, height=25,
                                      fg_color="transparent", hover_color=("gray75", "gray30"),
                                      command=lambda s=show, f=show_frame, v=expand_var: self.toggle_show(s, f, v))
            expand_btn.grid(row=0, column=0, padx=(10, 0), pady=5, sticky="w")

            # Selection checkbox
            var = ctk.BooleanVar(value=False)
            checkbox = ctk.CTkCheckBox(show_frame, text="", variable=var, width=20,
                                      command=lambda s=show, v=var, sf=show_frame: self.on_show_selected(s, v, sf))
            checkbox.grid(row=0, column=1, padx=5, pady=5, sticky="w")

            # Show title
            year = f" ({show.year})" if hasattr(show, 'year') and show.year else ""
            title_text = self.truncate_title(show.title + year)
            title_label = ctk.CTkLabel(show_frame, text=title_text,
                                      font=ctk.CTkFont(size=12, weight="bold"), anchor="w")
            title_label.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

            # Store show frame data
            self.show_frames[show] = (show_frame, expand_var, False)

        # Update pagination controls
        self.update_pagination_controls(page_num, total_pages, start_idx, end_idx, total_shows, "shows")

        # Update filter status
        if search_term:
            self.parent.filter_status_label.configure(
                text=f"Page {page_num}/{total_pages} - {len(filtered_shows)}/{len(self.all_shows)} shows matching '{search_term}'"
            )
        else:
            self.parent.filter_status_label.configure(text="")

        self.parent.update_selection_label()

    def toggle_show(self, show, frame, expand_var):
        """Toggle show expansion to show/hide seasons."""
        if show not in self.show_frames:
            return

        show_frame, var, is_expanded = self.show_frames[show]

        if is_expanded:
            # Collapse - remove season widgets
            for widget in show_frame.winfo_children():
                if widget.grid_info().get('row', 0) > 0:  # Keep only row 0
                    widget.destroy()

            # Update button
            expand_btn = show_frame.winfo_children()[0]
            expand_btn.configure(text="▶")
            self.show_frames[show] = (show_frame, var, False)
        else:
            # Expand - load seasons
            expand_btn = show_frame.winfo_children()[0]
            expand_btn.configure(text="▼")
            self.show_frames[show] = (show_frame, var, True)

            # Load seasons in background
            def load_seasons():
                """Background thread to load seasons for the show."""
                try:
                    seasons = show.seasons()
                    self.parent.safe_after(0, lambda: self.populate_seasons(show_frame, seasons))
                except Exception as e:
                    self.parent.log(f"Error loading seasons for {show.title}: {e}")

            threading.Thread(target=load_seasons, daemon=True).start()

    def populate_seasons(self, show_frame, seasons):
        """Populate seasons within a show frame."""
        row = 1
        for season in seasons:
            # Season frame (nested within show frame)
            season_frame = ctk.CTkFrame(show_frame, fg_color=("gray75", "gray30"))
            season_frame.grid(row=row, column=0, columnspan=3, sticky="ew", padx=(40, 10), pady=2)
            season_frame.grid_columnconfigure(2, weight=1)

            # Expand/collapse variable
            expand_var = ctk.BooleanVar(value=False)

            # Expand/collapse button
            expand_btn = ctk.CTkButton(season_frame, text="▶", width=25, height=25,
                                      fg_color="transparent", hover_color=("gray70", "gray35"),
                                      command=lambda s=season, f=season_frame, v=expand_var: self.toggle_season(s, f, v))
            expand_btn.grid(row=0, column=0, padx=(10, 0), pady=3, sticky="w")

            # Selection checkbox
            var = ctk.BooleanVar(value=False)
            checkbox = ctk.CTkCheckBox(season_frame, text="", variable=var, width=20,
                                      command=lambda s=season, v=var, sf=season_frame: self.on_season_selected(s, v, sf))
            checkbox.grid(row=0, column=1, padx=5, pady=3, sticky="w")

            # Season title
            season_title = f"Season {season.seasonNumber}" if hasattr(season, 'seasonNumber') else season.title
            title_label = ctk.CTkLabel(season_frame, text=season_title,
                                      font=ctk.CTkFont(size=11), anchor="w")
            title_label.grid(row=0, column=2, padx=5, pady=3, sticky="ew")

            # Store season frame data
            self.season_frames[season] = (season_frame, expand_var, False)

            row += 1

    def toggle_season(self, season, frame, expand_var):
        """Toggle season expansion to show/hide episodes."""
        if season not in self.season_frames:
            return

        season_frame, var, is_expanded = self.season_frames[season]

        if is_expanded:
            # Collapse - remove episode widgets
            for widget in season_frame.winfo_children():
                if widget.grid_info().get('row', 0) > 0:  # Keep only row 0
                    widget.destroy()

            # Update button
            expand_btn = season_frame.winfo_children()[0]
            expand_btn.configure(text="▶")
            self.season_frames[season] = (season_frame, var, False)
        else:
            # Expand - load episodes
            expand_btn = season_frame.winfo_children()[0]
            expand_btn.configure(text="▼")
            self.season_frames[season] = (season_frame, var, True)

            # Load episodes in background
            def load_episodes():
                """Background thread to load episodes for the season."""
                try:
                    episodes = season.episodes()
                    self.parent.safe_after(0, lambda: self.populate_episodes(season_frame, episodes))
                except Exception as e:
                    self.parent.log(f"Error loading episodes for {season.title}: {e}")

            threading.Thread(target=load_episodes, daemon=True).start()

    def populate_episodes(self, season_frame, episodes):
        """Populate episodes within a season frame."""
        row = 1
        for episode in episodes:
            # Episode frame (nested within season frame)
            episode_frame = ctk.CTkFrame(season_frame, fg_color="transparent")
            episode_frame.grid(row=row, column=0, columnspan=3, sticky="ew", padx=(40, 0), pady=1)
            episode_frame.grid_columnconfigure(1, weight=1)

            # Selection checkbox
            var = ctk.BooleanVar(value=False)
            checkbox = ctk.CTkCheckBox(episode_frame, text="", variable=var, width=20,
                                      command=lambda e=episode, v=var: self.on_item_selected(e, v))
            checkbox.grid(row=0, column=0, padx=5, pady=2, sticky="w")

            # Episode title
            episode_num = f"E{episode.index:02d}" if hasattr(episode, 'index') else ""
            episode_title = f"{episode_num} - {self.truncate_title(episode.title, 60)}"
            title_label = ctk.CTkLabel(episode_frame, text=episode_title,
                                      font=ctk.CTkFont(size=10), anchor="w")
            title_label.grid(row=0, column=1, padx=5, pady=2, sticky="ew")

            # Subtitle status indicator
            status_label = ctk.CTkLabel(episode_frame, text="", width=20)
            status_label.grid(row=0, column=2, padx=5, pady=2)

            # Check subtitle status in background
            def check_status(item=episode, label=status_label):
                if self.parent._is_destroyed:
                    return
                has_subs = self.check_has_subtitles(item)
                if self.parent._is_destroyed:
                    return
                if has_subs:
                    self.parent.safe_after(0, lambda: label.configure(
                        text="✓", text_color=("green", "#2d7a2d"), font=ctk.CTkFont(size=12, weight="bold")))
                else:
                    self.parent.safe_after(0, lambda: label.configure(
                        text="✗", text_color=("red", "#8b0000"), font=ctk.CTkFont(size=12)))

            threading.Thread(target=check_status, daemon=True).start()

            row += 1

    def on_item_selected(self, item, var):
        """Handle individual item (movie/episode) selection."""
        if var.get():
            if item not in self.parent.selected_items:
                self.parent.selected_items.append(item)
        else:
            if item in self.parent.selected_items:
                self.parent.selected_items.remove(item)

        self.parent.update_selection_label()

    def on_show_selected(self, show, var, show_frame):
        """Handle show selection - select/deselect all episodes in show."""
        if var.get():
            # Select all episodes in show
            def select_all():
                """Background thread to select all items."""
                try:
                    for season in show.seasons():
                        for episode in season.episodes():
                            if episode not in self.parent.selected_items:
                                self.parent.selected_items.append(episode)

                    # Update UI selection count
                    self.parent.safe_after(0, self.parent.update_selection_label)
                except Exception as e:
                    self.parent.log(f"Error selecting episodes for {show.title}: {e}")

            threading.Thread(target=select_all, daemon=True).start()
        else:
            # Deselect all episodes in show
            def deselect_all():
                """Background thread to deselect all items."""
                try:
                    for season in show.seasons():
                        for episode in season.episodes():
                            if episode in self.parent.selected_items:
                                self.parent.selected_items.remove(episode)

                    # Update UI selection count
                    self.parent.safe_after(0, self.parent.update_selection_label)
                except Exception as e:
                    self.parent.log(f"Error deselecting episodes for {show.title}: {e}")

            threading.Thread(target=deselect_all, daemon=True).start()

    def on_season_selected(self, season, var, season_frame):
        """Handle season selection - select/deselect all episodes in season."""
        if var.get():
            # Select all episodes in season
            def select_all():
                """Background thread to select all items."""
                try:
                    for episode in season.episodes():
                        if episode not in self.parent.selected_items:
                            self.parent.selected_items.append(episode)

                    # Update UI selection count
                    self.parent.safe_after(0, self.parent.update_selection_label)
                except Exception as e:
                    self.parent.log(f"Error selecting episodes for {season.title}: {e}")

            threading.Thread(target=select_all, daemon=True).start()
        else:
            # Deselect all episodes in season
            def deselect_all():
                """Background thread to deselect all items."""
                try:
                    for episode in season.episodes():
                        if episode in self.parent.selected_items:
                            self.parent.selected_items.remove(episode)

                    # Update UI selection count
                    self.parent.safe_after(0, self.parent.update_selection_label)
                except Exception as e:
                    self.parent.log(f"Error deselecting episodes for {season.title}: {e}")

            threading.Thread(target=deselect_all, daemon=True).start()

    def select_all_items(self):
        """Select all visible items in the browser."""
        def task():
            """Background thread to select all visible items."""
            try:
                if self.all_movies:
                    # Select all movies
                    for movie in self.all_movies:
                        if movie not in self.parent.selected_items:
                            self.parent.selected_items.append(movie)
                elif self.all_shows:
                    # Select all episodes in all shows
                    for show in self.all_shows:
                        for season in show.seasons():
                            for episode in season.episodes():
                                if episode not in self.parent.selected_items:
                                    self.parent.selected_items.append(episode)

                self.parent.safe_after(0, self.parent.update_selection_label)
                self.parent.safe_after(0, lambda: self.parent.update_status(
                    f"Selected {len(self.parent.selected_items)} item(s)"))
            except Exception as e:
                self.parent.log(f"Error selecting all items: {e}")

        threading.Thread(target=task, daemon=True).start()

    def clear_selection(self):
        """Clear all selected items."""
        self.parent.selected_items.clear()
        self.parent.update_selection_label()

    def update_selection_label(self):
        """Update the selection count label."""
        count = len(self.parent.selected_items)
        if count == 0:
            self.parent.selection_label.configure(text="No items selected")
        elif count == 1:
            self.parent.selection_label.configure(text="1 item selected")
        else:
            self.parent.selection_label.configure(text=f"{count} items selected")

    def show_subtitle_status(self, item):
        """Show current subtitle status for a video item."""
        def check_status():
            if self.parent._is_destroyed:
                return

            has_subs = self.check_has_subtitles(item)
            status_text = "Has subtitles" if has_subs else "No subtitles"

            # Get subtitle details
            subtitle_details = []
            try:
                for media in item.media:
                    for part in media.parts:
                        subs = part.subtitleStreams()
                        if subs:
                            for sub in subs:
                                lang = sub.language or "Unknown"
                                codec = sub.codec or "?"
                                forced = " [Forced]" if sub.forced else ""
                                sdh = " [SDH]" if sub.hearingImpaired else ""
                                subtitle_details.append(f"  • {lang} ({codec}){forced}{sdh}")
            except (AttributeError, RuntimeError, Exception) as e:
                # Failed to read subtitle streams - item may be inaccessible or API error
                logging.debug(f"Error reading subtitle details for item: {e}")

            if subtitle_details:
                details_text = "\n".join(subtitle_details)
                full_status = f"{status_text}:\n{details_text}"
            else:
                full_status = status_text

            self.parent.safe_after(0, lambda: self.parent.log(f"Subtitle status for {self.parent._get_item_title(item)}:\n{full_status}"))
            self.parent.safe_after(0, lambda: self.parent.update_status(status_text))

        threading.Thread(target=check_status, daemon=True).start()

    def check_has_subtitles(self, item, force_refresh=False):
        """
        Check if an item has subtitles.

        Args:
            item: Movie or Episode object
            force_refresh: If True, bypass cache and check Plex API

        Returns:
            bool: True if item has subtitles, False otherwise
        """
        # Check local cache first (faster)
        if not force_refresh and item.ratingKey in self.subtitle_cache:
            return self.subtitle_cache[item.ratingKey]

        # Check parent cache (shared across components)
        if not force_refresh and item.ratingKey in self.parent.subtitle_status_cache:
            result = self.parent.subtitle_status_cache[item.ratingKey]
            self.subtitle_cache[item.ratingKey] = result  # Copy to local cache
            return result

        # Check Plex API
        try:
            for media in item.media:
                for part in media.parts:
                    if part.subtitleStreams():
                        self.subtitle_cache[item.ratingKey] = True
                        self.parent.subtitle_status_cache[item.ratingKey] = True
                        return True

            self.subtitle_cache[item.ratingKey] = False
            self.parent.subtitle_status_cache[item.ratingKey] = False
            return False
        except (AttributeError, RuntimeError, Exception) as e:
            # Failed to check subtitle streams - item may be inaccessible or API error
            logging.debug(f"Error checking subtitle status for item: {e}")
            return False

    def refresh_subtitle_indicators(self, items_to_refresh=None):
        """
        Refresh subtitle status indicators for items.

        Args:
            items_to_refresh: List of items to refresh, or None to refresh all visible items
        """
        # Implementation note: This triggers a re-render of the browser
        # by reloading the current library content
        if self.all_movies:
            self.populate_movies(self.all_movies)
        elif self.all_shows:
            self.populate_shows(self.all_shows)
