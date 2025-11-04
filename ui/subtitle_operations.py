"""
Subtitle operations for PlexSubSetter.

This module handles all subtitle-related operations including:
- Searching for subtitles
- Downloading subtitles
- Listing existing subtitles
- Deleting subtitles
- Displaying subtitle selection UI
"""

import os
import threading
import logging
import customtkinter as ctk
from plexapi.video import Movie, Episode
from subliminal import download_subtitles
from subliminal.video import Episode as SubliminalEpisode, Movie as SubliminalMovie
from babelfish import Language

from utils.constants import (
    SEARCH_LANGUAGES,
    MAX_SUBTITLE_RESULTS
)
from utils.security import (
    sanitize_subtitle_filename,
    create_secure_subtitle_path,
    validate_subtitle_content_size
)


class SubtitleOperations:
    """Handles all subtitle search, download, list, and delete operations."""

    def __init__(self, parent_frame):
        """
        Initialize subtitle operations.

        Args:
            parent_frame: Main application frame (for callbacks and UI access)
        """
        self.parent = parent_frame
        self.search_results = {}  # Store search results: {item: [subtitles]}
        self.subtitle_selections = {}  # Store UI selections: {item: IntVar}

    # ==================== SUBTITLE SEARCH ====================

    def search_subtitles(self):
        """Search for available subtitles (does not download)."""
        items = self.parent.get_video_items()
        if not items:
            self.parent.update_status("No items selected")
            return

        # Get language
        language_name = self.parent.default_language
        language_code = SEARCH_LANGUAGES.get(language_name, 'en')

        # Show confirmation for large batches
        if self.parent.confirm_batch_operations and len(items) >= self.parent.batch_operation_threshold:
            confirmed = self.parent.show_confirmation_dialog(
                title="Search Subtitles",
                message=f"Search for subtitles for {len(items)} items?",
                item_count=len(items)
            )
            if not confirmed:
                self.parent.update_status("Search cancelled")
                return

        def task():
            self.parent.show_progress()
            self.parent.disable_action_buttons()

            # Clear previous results
            self.search_results.clear()
            self.subtitle_selections.clear()

            self.parent.update_status(f"Searching for {language_name} subtitles...")
            self.parent.log(f"Searching for {language_name} subtitles for {len(items)} items")

            found_count = 0
            for item in items:
                title = self.parent._get_item_title(item)

                try:
                    # Create subliminal video object
                    if isinstance(item, Episode):
                        video = SubliminalEpisode(
                            name=item.grandparentTitle,
                            season=item.seasonNumber,
                            episode=item.index,
                            title=item.title
                        )
                    else:  # Movie
                        video = SubliminalMovie(
                            name=item.title,
                            year=item.year if hasattr(item, 'year') else None
                        )

                    # Search for subtitles
                    lang = Language(language_code)
                    subtitles = download_subtitles(
                        {video},
                        languages={lang},
                        providers=self.parent.default_providers.split(',')
                    )

                    # Get subtitles for this video
                    subs_list = list(subtitles.get(video, []))

                    if subs_list:
                        self.search_results[item] = subs_list
                        found_count += 1
                        self.parent.safe_after(0, lambda t=title, c=len(subs_list):
                            self.parent.log(f"Found {c} subtitle(s) for: {t}"))
                    else:
                        self.parent.safe_after(0, lambda t=title:
                            self.parent.log(f"No subtitles found for: {t}", "warning"))

                except Exception as e:
                    self.parent.safe_after(0, lambda t=title, err=str(e):
                        self.parent.log(f"Error searching for {t}: {err}", "error"))

            # Update UI with results
            self.parent.safe_after(0, lambda: self._finalize_search(found_count, len(items), language_name))

        threading.Thread(target=task, daemon=True).start()

    def _finalize_search(self, found_count, total_count, language_name):
        """Finalize search and update UI."""
        self.parent.hide_progress()
        self.parent.enable_action_buttons()

        if found_count > 0:
            self.parent.update_status(
                f"Found subtitles for {found_count}/{total_count} items - Click 'Download' to continue"
            )
            self.parent.log(f"Search complete: {found_count}/{total_count} items have available subtitles")
            # Populate selection panel
            self.populate_subtitle_selection_panel()
        else:
            self.parent.update_status(f"No {language_name} subtitles found")
            self.parent.log("No subtitles found for selected items", "warning")

    # ==================== SUBTITLE SELECTION PANEL ====================

    def populate_subtitle_selection_panel(self):
        """Populate the info panel with search results for subtitle selection."""
        # Clear existing widgets
        self.parent.clear_info_panel()

        if not self.search_results:
            return

        # Configure panel for subtitle selection
        self.parent.info_panel_title.configure(text="📝 Select Subtitles to Download")
        self.parent.info_panel_action_btn.configure(text="Clear", command=self.parent.clear_info_panel)

        # Show the info panel
        self.parent.info_frame.grid()

        row = 0
        for item, subs_list in self.search_results.items():
            if not subs_list:
                continue

            title = self.parent._get_item_title(item)

            # Get actual file name from Plex
            actual_filename = "Unknown"
            try:
                for media in item.media:
                    for part in media.parts:
                        if part.file:
                            actual_filename = os.path.basename(part.file)
                            break
                    if actual_filename != "Unknown":
                        break
            except:
                pass

            # Video header frame
            video_frame = ctk.CTkFrame(self.parent.info_scroll, fg_color=("gray85", "gray25"))
            video_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
            video_frame.grid_columnconfigure(0, weight=1)

            # Video title
            ctk.CTkLabel(video_frame, text=title, font=ctk.CTkFont(weight="bold"),
                        anchor="w").grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))

            # File name
            ctk.CTkLabel(video_frame, text=f"File: {actual_filename}",
                        font=ctk.CTkFont(size=11), text_color="gray",
                        anchor="w").grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))

            # Subtitle options
            selection_var = ctk.IntVar(value=0)  # Default to first subtitle
            self.subtitle_selections[item] = selection_var

            for i, sub in enumerate(subs_list[:MAX_SUBTITLE_RESULTS], 0):  # Show top results
                # Get subtitle info
                release_info = (
                    getattr(sub, 'movie_release_name', None) or
                    getattr(sub, 'release', None) or
                    getattr(sub, 'filename', None) or
                    getattr(sub, 'info', None) or
                    f"ID: {getattr(sub, 'subtitle_id', 'Unknown')}"
                )
                provider_info = getattr(sub, 'provider_name', 'unknown')

                # Radio button for this subtitle
                radio_text = f"[{provider_info}] {str(release_info)[:100]}"
                radio = ctk.CTkRadioButton(video_frame, text=radio_text, variable=selection_var,
                                          value=i)
                radio.grid(row=i+2, column=0, sticky="w", padx=20, pady=2)

            if len(subs_list) > MAX_SUBTITLE_RESULTS:
                ctk.CTkLabel(video_frame,
                            text=f"... and {len(subs_list) - MAX_SUBTITLE_RESULTS} more (showing top {MAX_SUBTITLE_RESULTS})",
                            font=ctk.CTkFont(size=11), text_color="gray").grid(
                    row=MAX_SUBTITLE_RESULTS+2, column=0, sticky="w", padx=20, pady=(2, 10))
            else:
                # Add padding at the end
                ctk.CTkLabel(video_frame, text="").grid(row=len(subs_list)+2, column=0, pady=5)

            row += 1

    # ==================== SUBTITLE DOWNLOAD ====================

    def download_subtitles(self):
        """Download selected subtitles from search results."""
        if not self.search_results:
            self.parent.update_status("No search results - Search first")
            return

        # Get selected items and their subtitle choices
        items_to_download = []
        for item in self.search_results.keys():
            if item in self.subtitle_selections:
                items_to_download.append(item)

        if not items_to_download:
            self.parent.update_status("No subtitles selected")
            return

        language_name = self.parent.default_language
        language_code = SEARCH_LANGUAGES.get(language_name, 'en')

        def task():
            self.parent.show_progress()
            self.parent.disable_action_buttons()
            self.parent.update_status(f"Downloading {language_name} subtitles...")

            success_count = 0
            successful_items = []

            for item in items_to_download:
                title = self.parent._get_item_title(item)
                subs_list = self.search_results.get(item, [])

                if not subs_list:
                    continue

                # Get selected subtitle index
                selected_index = self.subtitle_selections[item].get()
                if selected_index >= len(subs_list):
                    continue

                selected_sub = subs_list[selected_index]

                try:
                    # Determine provider
                    provider = getattr(selected_sub, 'provider_name', 'unknown')

                    # Update status
                    self.parent.safe_after(0, lambda t=title: self.parent.update_status(f"Downloading: {t}"))

                    # Download the subtitle content using subliminal API
                    download_subtitles([selected_sub], providers=[provider])

                    # Save to temporary file
                    import tempfile
                    temp_dir = tempfile.gettempdir()

                    # Create secure subtitle filename
                    subtitle_filename = sanitize_subtitle_filename(item, language_code)
                    subtitle_path = os.path.join(temp_dir, subtitle_filename)

                    # Validate subtitle content size (prevent disk exhaustion)
                    try:
                        validate_subtitle_content_size(selected_sub.content)
                    except ValueError as e:
                        self.parent.log(f"Error: {e}")
                        continue

                    # Write subtitle content to file
                    with open(subtitle_path, 'wb') as f:
                        f.write(selected_sub.content)

                    # Save subtitle based on user preference
                    if self.parent.subtitle_save_method == 'file':
                        # Save subtitle next to video file
                        try:
                            # Get video file path from Plex
                            if hasattr(item, 'media') and item.media:
                                video_path = item.media[0].parts[0].file

                                # Create secure subtitle path (prevents path traversal)
                                try:
                                    final_subtitle_path = create_secure_subtitle_path(
                                        video_path, language_code, item
                                    )
                                except ValueError as path_error:
                                    self.parent.log(f"Security error: {path_error}")
                                    self.parent.log("Falling back to Plex upload method")
                                    item.uploadSubtitles(subtitle_path)
                                    continue

                                # Copy subtitle file to video directory
                                import shutil
                                shutil.copy2(subtitle_path, str(final_subtitle_path))

                                self.parent.log(f"Saved subtitle to: {final_subtitle_path}")

                                # Trigger Plex partial scan to detect new subtitle
                                try:
                                    # Get the library section for this item
                                    if isinstance(item, Episode):
                                        library_section = item.section()
                                    else:
                                        library_section = item.section()

                                    # Scan the specific file path
                                    video_dir = os.path.dirname(str(final_subtitle_path))
                                    library_section.update(video_dir)
                                    self.parent.log(f"Triggered Plex scan for: {video_dir}")
                                except Exception as scan_error:
                                    self.parent.log(f"Note: Could not trigger Plex scan: {scan_error}")
                                    self.parent.log("You may need to manually refresh the library in Plex")
                            else:
                                self.parent.log(f"Warning: Could not get video file path for {title}")
                                # Fallback to Plex upload
                                item.uploadSubtitles(subtitle_path)
                        except Exception as file_error:
                            self.parent.log(f"Error saving subtitle file: {file_error}")
                            self.parent.log("Falling back to Plex upload method")
                            # Fallback to Plex upload if file save fails
                            item.uploadSubtitles(subtitle_path)
                    else:
                        # Upload to Plex server (default behavior)
                        item.uploadSubtitles(subtitle_path)

                    # Clean up temp file
                    try:
                        os.remove(subtitle_path)
                    except (OSError, PermissionError) as cleanup_error:
                        # Log but don't fail - cleanup is non-critical
                        logging.debug(f"Could not delete temp file {subtitle_path}: {cleanup_error}")

                    success_count += 1
                    successful_items.append(item)

                    self.parent.safe_after(0, lambda t=title:
                        self.parent.log(f"Successfully downloaded subtitle for: {t}"))

                except Exception as e:
                    self.parent.safe_after(0, lambda t=title, err=str(e):
                        self.parent.log(f"Error downloading subtitle for {t}: {err}", "error"))

            # Update UI after completion
            self.parent.safe_after(0, lambda: self._finalize_download(success_count, len(items_to_download)))

        threading.Thread(target=task, daemon=True).start()

    def _finalize_download(self, success_count, total_count):
        """Finalize download and update UI."""
        self.parent.hide_progress()
        self.parent.enable_action_buttons()

        if success_count > 0:
            self.parent.update_status(f"Downloaded {success_count}/{total_count} subtitles")
            self.parent.log(f"Download complete: {success_count}/{total_count} succeeded")

            # Clear search results and selection panel
            self.search_results.clear()
            self.subtitle_selections.clear()
            self.parent.clear_info_panel()

            # Refresh subtitle indicators
            self.parent.refresh_subtitle_indicators()
        else:
            self.parent.update_status("No subtitles downloaded")
            self.parent.log("Download failed for all items", "error")

    # ==================== DRY RUN (Preview) ====================

    def dry_run_missing_subtitles(self):
        """Preview which subtitles would be available for items missing them (no download)."""
        items = self.parent.get_video_items()
        if not items:
            self.parent.update_status("No items selected")
            return

        language_name = self.parent.default_language
        language_code = SEARCH_LANGUAGES.get(language_name, 'en')

        # Show confirmation
        if self.parent.confirm_batch_operations and len(items) >= self.parent.batch_operation_threshold:
            confirmed = self.parent.show_confirmation_dialog(
                title="Dry Run - Preview Available Subtitles",
                message=f"Preview subtitle availability for {len(items)} items?\n(No subtitles will be downloaded)",
                item_count=len(items)
            )
            if not confirmed:
                self.parent.update_status("Dry run cancelled")
                return

        def task():
            self.parent.show_progress()
            self.parent.disable_action_buttons()
            self.parent.update_status(f"Checking subtitle availability...")
            self.parent.log(f"Dry run: Checking {language_name} subtitle availability for {len(items)} items")

            results = []  # List of (item, has_subs, subs_available, error)

            for item in items:
                title = self.parent._get_item_title(item)

                try:
                    # Check if item already has subtitles for this language
                    has_subs = False
                    for media in item.media:
                        for part in media.parts:
                            for sub_stream in part.subtitleStreams():
                                if sub_stream.languageCode == language_code:
                                    has_subs = True
                                    break
                            if has_subs:
                                break
                        if has_subs:
                            break

                    # If already has subtitles, skip
                    if has_subs:
                        results.append((item, True, 0, None))
                        continue

                    # Check if subtitles are available
                    if isinstance(item, Episode):
                        video = SubliminalEpisode(
                            name=item.grandparentTitle,
                            season=item.seasonNumber,
                            episode=item.index,
                            title=item.title
                        )
                    else:
                        video = SubliminalMovie(
                            name=item.title,
                            year=item.year if hasattr(item, 'year') else None
                        )

                    lang = Language(language_code)
                    subtitles = download_subtitles(
                        {video},
                        languages={lang},
                        providers=self.parent.default_providers.split(',')
                    )

                    subs_available = len(list(subtitles.get(video, [])))
                    results.append((item, False, subs_available, None))

                    self.parent.safe_after(0, lambda t=title, c=subs_available:
                        self.parent.log(f"{t}: {c} subtitle(s) available"))

                except Exception as e:
                    results.append((item, False, 0, str(e)))
                    self.parent.safe_after(0, lambda t=title, err=str(e):
                        self.parent.log(f"Error checking {t}: {err}", "error"))

            # Display results
            provider_name = self.parent.default_providers.split(',')[0] if self.parent.default_providers else "all"
            self.parent.safe_after(0, lambda: self.display_dry_run_results(results, language_name, provider_name))

        threading.Thread(target=task, daemon=True).start()

    def display_dry_run_results(self, results, language_name, provider_name):
        """Display dry run results in info panel."""
        self.parent.clear_info_panel()
        self.parent.info_panel_title.configure(text=f"👁 Dry Run Preview - {language_name} ({provider_name})")
        self.parent.info_panel_action_btn.configure(text="Clear", command=self.parent.clear_info_panel)
        self.parent.info_frame.grid()

        self.parent.hide_progress()
        self.parent.enable_action_buttons()

        # Categorize results
        already_have = []
        available = []
        not_available = []
        errors = []

        for item, has_subs, subs_available, error in results:
            if error:
                errors.append((item, error))
            elif has_subs:
                already_have.append(item)
            elif subs_available > 0:
                available.append((item, subs_available))
            else:
                not_available.append(item)

        # Build summary
        summary_text = (
            f"✅ Already have subtitles: {len(already_have)}\n"
            f"📥 Subtitles available: {len(available)}\n"
            f"❌ No subtitles found: {len(not_available)}\n"
            f"⚠️ Errors: {len(errors)}"
        )

        summary_label = ctk.CTkLabel(
            self.parent.info_scroll,
            text=summary_text,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
            justify="left"
        )
        summary_label.grid(row=0, column=0, sticky="ew", pady=(0, 15))

        current_row = 1

        # Show items with available subtitles
        if available:
            header = ctk.CTkLabel(
                self.parent.info_scroll,
                text="📥 Subtitles Available:",
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w"
            )
            header.grid(row=current_row, column=0, sticky="ew", pady=(5, 5))
            current_row += 1

            for item, count in available:
                title = self.parent._get_item_title(item)
                label = ctk.CTkLabel(
                    self.parent.info_scroll,
                    text=f"  • {title} ({count} options)",
                    anchor="w",
                    font=ctk.CTkFont(size=11)
                )
                label.grid(row=current_row, column=0, sticky="ew", padx=10)
                current_row += 1

        # Show items that already have subtitles
        if already_have:
            header = ctk.CTkLabel(
                self.parent.info_scroll,
                text="✅ Already Have Subtitles:",
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w"
            )
            header.grid(row=current_row, column=0, sticky="ew", pady=(10, 5))
            current_row += 1

            for item in already_have:
                title = self.parent._get_item_title(item)
                label = ctk.CTkLabel(
                    self.parent.info_scroll,
                    text=f"  • {title}",
                    anchor="w",
                    font=ctk.CTkFont(size=11),
                    text_color="gray"
                )
                label.grid(row=current_row, column=0, sticky="ew", padx=10)
                current_row += 1

        self.parent.update_status(f"Dry run complete: {len(available)} items have available subtitles")
        self.parent.log(f"Dry run summary: {len(already_have)} have, {len(available)} available, {len(not_available)} none found")

    # ==================== LIST SUBTITLES ====================

    def list_subtitles(self):
        """List available subtitles in info panel."""
        def task():
            self.parent.show_progress()
            self.parent.disable_action_buttons()
            self.parent.update_status("Fetching subtitle information...")

            items = self.parent.get_video_items()
            if not items:
                self.parent.safe_after(0, lambda: self.parent.update_status("No items selected"))
                self.parent.safe_after(0, lambda: self.parent.hide_progress())
                self.parent.safe_after(0, lambda: self.parent.enable_action_buttons())
                return

            subtitle_info = []  # List of (item, subtitle_streams)

            for item in items:
                try:
                    streams = []
                    for media in item.media:
                        for part in media.parts:
                            for sub_stream in part.subtitleStreams():
                                streams.append(sub_stream)

                    if streams:
                        subtitle_info.append((item, streams))

                except Exception as e:
                    logging.debug(f"Error fetching subtitles for {item.title}: {e}")

            # Display results in info panel
            self.parent.safe_after(0, lambda: self._display_subtitle_list(subtitle_info))

        threading.Thread(target=task, daemon=True).start()

    def _display_subtitle_list(self, subtitle_info):
        """Display subtitle list in info panel."""
        self.parent.clear_info_panel()
        self.parent.info_panel_title.configure(text="📄 Available Subtitles")
        self.parent.info_panel_action_btn.configure(text="Clear", command=self.parent.clear_info_panel)
        self.parent.info_frame.grid()

        self.parent.hide_progress()
        self.parent.enable_action_buttons()

        if not subtitle_info:
            label = ctk.CTkLabel(
                self.parent.info_scroll,
                text="No subtitle streams found for selected items",
                font=ctk.CTkFont(size=12),
                text_color="gray"
            )
            label.grid(row=0, column=0, sticky="ew", pady=20)
            self.parent.update_status("No subtitles found")
            return

        row = 0
        for item, streams in subtitle_info:
            title = self.parent._get_item_title(item)

            # Item header
            header_frame = ctk.CTkFrame(self.parent.info_scroll, fg_color=("gray85", "gray25"))
            header_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
            header_frame.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                header_frame,
                text=title,
                font=ctk.CTkFont(weight="bold"),
                anchor="w"
            ).grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))

            # List subtitle streams
            for i, stream in enumerate(streams):
                lang = stream.language or "Unknown"
                codec = stream.codec or "Unknown"
                forced = "[FORCED]" if stream.forced else ""
                sdh = "[SDH]" if stream.hearingImpaired else ""
                selected = "✓ " if stream.selected else "  "

                stream_text = f"{selected}{lang} ({codec}) {forced} {sdh}".strip()

                ctk.CTkLabel(
                    header_frame,
                    text=stream_text,
                    anchor="w",
                    font=ctk.CTkFont(size=11)
                ).grid(row=i+1, column=0, sticky="ew", padx=20, pady=2)

            # Padding
            ctk.CTkLabel(header_frame, text="").grid(row=len(streams)+1, column=0, pady=5)

            row += 1

        self.parent.update_status(f"Found subtitles for {len(subtitle_info)} items")

    # ==================== DELETE SUBTITLES ====================

    def delete_subtitles(self):
        """Delete all subtitle streams from selected items."""
        items = self.parent.get_video_items()
        if not items:
            self.parent.update_status("No items selected")
            return

        # Show confirmation
        if self.parent.confirm_batch_operations:
            confirmed = self.parent.show_confirmation_dialog(
                title="Delete Subtitles",
                message=f"Delete ALL subtitle streams from {len(items)} items?\n\nThis cannot be undone!",
                item_count=len(items)
            )
            if not confirmed:
                self.parent.update_status("Delete cancelled")
                return

        def task():
            self.parent.show_progress()
            self.parent.disable_action_buttons()
            self.parent.update_status("Deleting subtitle streams...")
            self.parent.log(f"Deleting subtitles from {len(items)} items")

            success_count = 0

            for item in items:
                title = self.parent._get_item_title(item)

                try:
                    deleted_count = 0
                    for media in item.media:
                        for part in media.parts:
                            for sub_stream in part.subtitleStreams():
                                part.removeSubtitleStream(sub_stream)
                                deleted_count += 1

                    if deleted_count > 0:
                        success_count += 1
                        self.parent.safe_after(0, lambda t=title, c=deleted_count:
                            self.parent.log(f"Deleted {c} subtitle stream(s) from: {t}"))
                    else:
                        self.parent.safe_after(0, lambda t=title:
                            self.parent.log(f"No subtitles to delete for: {t}", "warning"))

                except Exception as e:
                    self.parent.safe_after(0, lambda t=title, err=str(e):
                        self.parent.log(f"Error deleting subtitles from {t}: {err}", "error"))

            # Update UI
            self.parent.safe_after(0, lambda: self._finalize_delete(success_count, len(items)))

        threading.Thread(target=task, daemon=True).start()

    def _finalize_delete(self, success_count, total_count):
        """Finalize delete and update UI."""
        self.parent.hide_progress()
        self.parent.enable_action_buttons()

        if success_count > 0:
            self.parent.update_status(f"Deleted subtitles from {success_count}/{total_count} items")
            self.parent.log(f"Delete complete: {success_count}/{total_count} succeeded")
            # Refresh subtitle indicators
            self.parent.refresh_subtitle_indicators()
        else:
            self.parent.update_status("No subtitles deleted")
            self.parent.log("No subtitles were deleted", "warning")
