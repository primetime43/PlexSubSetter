"""
Library browsing service.

Extracted from ui/library_browser.py. No UI dependencies.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from plexapi.video import Movie, Episode, Show, Season

from error_handling import (
    retry_with_backoff,
    PlexConnectionError,
    PlexAuthenticationError,
    ErrorContext,
    get_crash_reporter,
)
from utils.constants import DEFAULT_RETRY_ATTEMPTS, DEFAULT_RETRY_DELAY

# Shared thread pool for subtitle checks
_thread_pool = ThreadPoolExecutor(max_workers=8)


def get_libraries(plex):
    """
    Get all libraries from the Plex server.

    Returns:
        list of dicts: [{title, type, key}, ...]
    """
    @retry_with_backoff(max_attempts=DEFAULT_RETRY_ATTEMPTS, initial_delay=DEFAULT_RETRY_DELAY, exceptions=(Exception,))
    def fetch():
        try:
            sections = plex.library.sections()
            return [{'title': s.title, 'type': s.type, 'key': s.key} for s in sections]
        except ConnectionError as e:
            raise PlexConnectionError(original_error=e)
        except Exception as e:
            if "unauthorized" in str(e).lower():
                raise PlexAuthenticationError(e)
            raise

    return fetch()


def get_library_items(plex, library_name):
    """
    Load all items from a library, including subtitle stream data.

    Returns:
        tuple: (items_list, library_type)
    """
    library = plex.library.section(library_name)
    # Include stream data so subtitle checks don't need item.reload()
    items = library.all(includeGuids=False)
    return items, library.type


def get_items_page(items, page, per_page, search='', subtitle_filter='all', subtitle_cache=None):
    """
    Get a paginated, filtered page of items.

    Args:
        items: Full list of items
        page: 1-based page number
        per_page: Items per page
        search: Search filter string
        subtitle_filter: 'all', 'missing', or 'has'
        subtitle_cache: dict of {rating_key: bool} for subtitle status

    Returns:
        dict with keys: items, page, total_pages, total_items, start, end, filtered_count
    """
    if subtitle_cache is None:
        subtitle_cache = {}

    # Apply search filter
    if search:
        search_lower = search.lower()
        filtered = [i for i in items if search_lower in i.title.lower()]
    else:
        filtered = list(items)

    # Apply subtitle status filter
    if subtitle_filter != 'all' and subtitle_cache:
        status_filtered = []
        for item in filtered:
            has_subs = subtitle_cache.get(item.ratingKey)
            if has_subs is None:
                # Unknown status - include by default
                status_filtered.append(item)
            elif subtitle_filter == 'missing' and not has_subs:
                status_filtered.append(item)
            elif subtitle_filter == 'has' and has_subs:
                status_filtered.append(item)
        filtered = status_filtered

    total = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    start = (page - 1) * per_page
    end = min(start + per_page, total)

    page_items = filtered[start:end]

    return {
        'items': page_items,
        'page': page,
        'total_pages': total_pages,
        'total_items': total,
        'start': start + 1,
        'end': end,
        'filtered_count': total,
        'unfiltered_count': len(items),
    }


def get_seasons(show):
    """Get seasons for a show."""
    return show.seasons()


def get_episodes(season):
    """Get episodes for a season."""
    return season.episodes()


def check_subtitle_status(item, force_refresh=False, skip_reload=False):
    """
    Check if a single item has subtitles.

    Returns:
        bool or None: True if has subtitles, False if none, None if check failed
    """
    if not skip_reload and not force_refresh:
        try:
            # checkFiles=1 ensures external subtitles (SRT, etc.) are included
            item.reload(checkFiles=1)
        except Exception as e:
            logging.warning(f"Error reloading item for subtitle check: {e}")
            return None  # Signal that check failed — don't cache

    try:
        for media in item.media:
            for part in media.parts:
                if part.subtitleStreams():
                    return True
        return False
    except (AttributeError, RuntimeError, Exception) as e:
        logging.warning(f"Error checking subtitle status: {e}")
        return None


def batch_check_subtitles_sync(items, state):
    """
    Check subtitle status synchronously for a small batch of items (e.g. one season).
    Uses the thread pool for parallelism but blocks until all checks complete.
    Results are cached in state. No SSE events emitted.
    """
    def check_one(item):
        has_subs = check_subtitle_status(item, skip_reload=False)
        if has_subs is not None:
            state.cache_subtitle_status(item.ratingKey, has_subs)

    futures = [_thread_pool.submit(check_one, item) for item in items]
    for f in futures:
        try:
            f.result(timeout=30)
        except Exception as e:
            logging.warning(f"Error in sync subtitle check: {e}")


def batch_check_subtitles(items, state, task_manager=None):
    """
    Check subtitle status for a batch of items, updating the cache.

    First tries without reload (fast, uses already-loaded data).
    Falls back to reload for items that don't have media data yet.

    Args:
        items: List of Plex items
        state: SessionState instance
        task_manager: Optional TaskManager for progress events
    """
    total = len(items)
    checked = 0
    needs_reload = []

    # Fast pass: check items that already have media data loaded
    # Only trust positive results (has subtitles) from the fast pass.
    # Negative results may be due to streams not being loaded yet,
    # so those items go to the slow pass for a full reload.
    for item in items:
        if state.get_subtitle_status(item.ratingKey) is not None:
            checked += 1
            continue

        has_media = hasattr(item, 'media') and item.media
        if has_media:
            has_subs = check_subtitle_status(item, skip_reload=True)
            if has_subs:
                state.cache_subtitle_status(item.ratingKey, has_subs)
                checked += 1
                if task_manager:
                    task_manager.emit('subtitle_status', {
                        'rating_key': item.ratingKey,
                        'has_subtitles': True,
                    })
            else:
                # Streams may not be loaded yet — verify with reload
                needs_reload.append(item)
        else:
            needs_reload.append(item)

    # Slow pass: reload items that need it (in parallel)
    if needs_reload:
        def check_one(item):
            nonlocal checked
            has_subs = check_subtitle_status(item, skip_reload=False)
            if has_subs is not None:
                state.cache_subtitle_status(item.ratingKey, has_subs)
                checked += 1
                if task_manager:
                    task_manager.emit('subtitle_status', {
                        'rating_key': item.ratingKey,
                        'has_subtitles': has_subs,
                    })
            else:
                logging.warning(f"Subtitle check failed for item {item.ratingKey}, skipping cache")

        futures = [_thread_pool.submit(check_one, item) for item in needs_reload]
        for f in futures:
            try:
                f.result(timeout=120)
            except Exception as e:
                logging.warning(f"Error in batch subtitle check: {e}")

    logging.info(f"Batch subtitle check complete: {checked}/{total}")

    if task_manager:
        task_manager.emit('subtitle_cache_complete', {'total': total})


def get_item_title(item):
    """Get formatted display title for an item."""
    if isinstance(item, Movie):
        year = f" ({item.year})" if hasattr(item, 'year') and item.year else ""
        return f"{item.title}{year}"
    elif isinstance(item, Episode):
        ep_num = item.index if item.index is not None else 0
        season_num = item.seasonNumber if item.seasonNumber is not None else 0
        return f"{item.grandparentTitle} S{season_num:02d}E{ep_num:02d} - {item.title}"
    else:
        return item.title
