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
_thread_pool = ThreadPoolExecutor(max_workers=5)


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
    Load all items from a library.

    Returns:
        tuple: (items_list, library_type)
    """
    library = plex.library.section(library_name)
    items = library.all()
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
        bool: True if item has subtitles
    """
    if not skip_reload and not force_refresh:
        try:
            item.reload()
        except Exception as e:
            logging.debug(f"Error reloading item for subtitle check: {e}")

    try:
        for media in item.media:
            for part in media.parts:
                if part.subtitleStreams():
                    return True
        return False
    except (AttributeError, RuntimeError, Exception) as e:
        logging.debug(f"Error checking subtitle status: {e}")
        return False


def batch_check_subtitles(items, state, task_manager=None):
    """
    Check subtitle status for a batch of items, updating the cache.

    Args:
        items: List of Plex items
        state: SessionState instance
        task_manager: Optional TaskManager for progress events
    """
    total = len(items)
    checked = 0

    def check_one(item):
        nonlocal checked
        has_subs = check_subtitle_status(item, skip_reload=False)
        state.cache_subtitle_status(item.ratingKey, has_subs)
        checked += 1

        if task_manager and checked % 50 == 0:
            pct = int((checked / total) * 100)
            task_manager.emit('progress', {
                'type': 'subtitle_cache',
                'current': checked,
                'total': total,
                'percent': pct,
            })

    futures = []
    for item in items:
        # Skip if already cached
        if state.get_subtitle_status(item.ratingKey) is not None:
            checked += 1
            continue
        futures.append(_thread_pool.submit(check_one, item))

    # Wait for all to complete
    for f in futures:
        try:
            f.result(timeout=120)
        except Exception as e:
            logging.debug(f"Error in batch subtitle check: {e}")

    logging.info(f"Batch subtitle check complete: {checked}/{total}")


def get_item_title(item):
    """Get formatted display title for an item."""
    if isinstance(item, Movie):
        year = f" ({item.year})" if hasattr(item, 'year') and item.year else ""
        return f"{item.title}{year}"
    elif isinstance(item, Episode):
        return f"{item.grandparentTitle} S{item.seasonNumber:02d}E{item.index:02d} - {item.title}"
    else:
        return item.title
