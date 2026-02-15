"""Library browsing routes."""

import logging
from flask import Blueprint, render_template, jsonify, redirect, url_for, request, current_app

from core import library_service
from plexapi.video import Movie, Season, Show
from utils.constants import SEARCH_LANGUAGES, SUBTITLE_PROVIDERS

libraries_bp = Blueprint('libraries', __name__)

ITEMS_PER_PAGE = 30


@libraries_bp.route('/app')
def app_page():
    """Render main application page."""
    state = current_app.state
    if not state.plex:
        return redirect(url_for('servers.servers_page'))

    from utils.config_manager import ConfigManager
    config = ConfigManager()
    settings = config.load_settings()

    return render_template('app.html',
                           server_name=state.plex.friendlyName,
                           languages=SEARCH_LANGUAGES,
                           providers=SUBTITLE_PROVIDERS,
                           settings=settings)


@libraries_bp.route('/libraries')
def list_libraries():
    """Get library list."""
    state = current_app.state
    if not state.plex:
        return jsonify({'error': 'Not connected'}), 401

    try:
        all_libs = library_service.get_libraries(state.plex)
        # Only show movie and TV show libraries
        libs = [l for l in all_libs if l['type'] in ('movie', 'show')]
        state.libraries = libs
        return jsonify(libs)
    except Exception as e:
        logging.error(f"Error loading libraries: {e}")
        return jsonify({'error': str(e)}), 500


@libraries_bp.route('/libraries/<name>/items')
def library_items(name):
    """Get paginated library items as HTML partial."""
    state = current_app.state
    if not state.plex:
        return 'Not connected', 401

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    subtitle_filter = request.args.get('filter', 'all')
    logging.info(f"Library items request: library={name}, page={page}, filter={subtitle_filter}, search={search}")

    # Load library items (use cache if available)
    if name not in state.library_items_cache:
        try:
            items, lib_type = library_service.get_library_items(state.plex, name)
            state.library_items_cache[name] = items
            if lib_type == 'movie':
                state.all_movies = items
                state.all_shows = None
            else:
                state.all_shows = items
                state.all_movies = None
            state.current_library = state.plex.library.section(name)
        except Exception as e:
            logging.error(f"Error loading library {name}: {e}")
            return f'<div class="text-red-400 p-4">Error loading library: {e}</div>', 500

    items = state.library_items_cache[name]
    is_movie = isinstance(items[0], Movie) if items else False

    # Subtitle cache for movies
    cache = state.subtitle_status_cache  # direct dict ref, reads are thread-safe in CPython
    if is_movie:
        all_uncached = [i for i in items if i.ratingKey not in cache]

        if all_uncached:
            # Synchronously check the current page's items so the first response has indicators.
            # Compute which items will be on this page (approximate — before subtitle filtering).
            start_idx = (page - 1) * ITEMS_PER_PAGE
            end_idx = start_idx + ITEMS_PER_PAGE
            if search:
                search_lower = search.lower()
                page_candidates = [i for i in items if search_lower in i.title.lower()][start_idx:end_idx]
            else:
                page_candidates = items[start_idx:end_idx]
            page_uncached = [i for i in page_candidates if i.ratingKey not in cache]
            if page_uncached:
                library_service.batch_check_subtitles_sync(page_uncached, state)

            # Background task for remaining uncached items (not on this page)
            remaining = [i for i in items if i.ratingKey not in cache]
            if remaining:
                tm = current_app.task_manager
                running = any(
                    t['type'] == 'subtitle_cache' and t['status'] == 'running'
                    for t in tm._tasks.values()
                )
                if not running:
                    tm.submit('subtitle_cache', library_service.batch_check_subtitles,
                              items=remaining, state=state, task_manager=tm)

    # Check if cache is complete (for UI status message)
    cache_complete = all(i.ratingKey in cache for i in items) if is_movie else True

    # Always apply the requested filter — uncached items are included by default
    effective_filter = subtitle_filter

    result = library_service.get_items_page(
        items, page, ITEMS_PER_PAGE, search, effective_filter, state.subtitle_status_cache
    )

    selected_keys = state.get_selected_keys()

    return render_template('partials/browser_items.html',
                           items=result['items'],
                           is_movie=is_movie,
                           page=result['page'],
                           total_pages=result['total_pages'],
                           total_items=result['total_items'],
                           start=result['start'],
                           end=result['end'],
                           filtered_count=result['filtered_count'],
                           unfiltered_count=result['unfiltered_count'],
                           search=search,
                           subtitle_filter=subtitle_filter,
                           effective_filter=effective_filter,
                           subtitle_cache=state.subtitle_status_cache,
                           selected_keys=selected_keys,
                           library_name=name,
                           cache_complete=cache_complete)


@libraries_bp.route('/libraries/<name>/shows/<int:rating_key>/seasons')
def show_seasons(name, rating_key):
    """Get seasons for a show."""
    state = current_app.state
    if not state.plex:
        return 'Not connected', 401

    try:
        # Find the show from cache
        items = state.library_items_cache.get(name, [])
        show = None
        for item in items:
            if item.ratingKey == rating_key:
                show = item
                break

        if not show:
            return '<div class="text-red-400">Show not found</div>', 404

        seasons = library_service.get_seasons(show)
        selected_keys = state.get_selected_keys()
        return render_template('partials/show_seasons.html',
                               seasons=seasons,
                               library_name=name,
                               show_key=rating_key,
                               selected_keys=selected_keys)
    except Exception as e:
        logging.error(f"Error loading seasons: {e}")
        return f'<div class="text-red-400 p-4">Error: {e}</div>', 500


@libraries_bp.route('/libraries/<name>/seasons/<int:rating_key>/episodes')
def season_episodes(name, rating_key):
    """Get episodes for a season."""
    state = current_app.state
    if not state.plex:
        return 'Not connected', 401

    try:
        # Find the season from the Plex server directly
        season = state.plex.fetchItem(rating_key)
        episodes = library_service.get_episodes(season)
        selected_keys = state.get_selected_keys()

        # Check subtitle status synchronously for uncached episodes.
        # A season is typically 10-25 episodes — checking in parallel is fast
        # and avoids SSE race conditions where events arrive before DOM is ready.
        cache = state.subtitle_status_cache
        uncached = [ep for ep in episodes if ep.ratingKey not in cache]
        if uncached:
            library_service.batch_check_subtitles_sync(uncached, state)

        return render_template('partials/season_episodes.html',
                               episodes=episodes,
                               library_name=name,
                               subtitle_cache=state.subtitle_status_cache,
                               selected_keys=selected_keys)
    except Exception as e:
        logging.error(f"Error loading episodes: {e}")
        return f'<div class="text-red-400 p-4">Error: {e}</div>', 500


@libraries_bp.route('/selection/add', methods=['POST'])
def add_selection():
    """Add items to selection by rating keys."""
    state = current_app.state
    keys = request.json.get('keys', [])

    # Build items map from all cached items
    items_map = {}
    for lib_items in state.library_items_cache.values():
        for item in lib_items:
            items_map[item.ratingKey] = item

    # For episodes, we need to resolve them
    plex = state.plex
    for key in keys:
        if key not in items_map and plex:
            try:
                item = plex.fetchItem(key)
                items_map[key] = item
            except Exception:
                pass

    for key in keys:
        if key in items_map:
            item = items_map[key]
        else:
            continue

        # Expand Season/Show into individual episodes
        if isinstance(item, Season):
            try:
                for episode in item.episodes():
                    state.add_selection(episode)
            except Exception as e:
                logging.error(f"Error expanding season {item.title}: {e}")
        elif isinstance(item, Show):
            try:
                for season in item.seasons():
                    for episode in season.episodes():
                        state.add_selection(episode)
            except Exception as e:
                logging.error(f"Error expanding show {item.title}: {e}")
        else:
            state.add_selection(item)

    return jsonify({'count': len(state.selected_items)})


@libraries_bp.route('/selection/remove', methods=['POST'])
def remove_selection():
    """Remove items from selection by rating keys."""
    state = current_app.state
    keys = request.json.get('keys', [])

    # Expand Season/Show keys into episode keys
    expanded_keys = set(keys)
    plex = state.plex
    for key in keys:
        if plex:
            try:
                item = plex.fetchItem(key)
                if isinstance(item, Season):
                    for episode in item.episodes():
                        expanded_keys.add(episode.ratingKey)
                elif isinstance(item, Show):
                    for season in item.seasons():
                        for episode in season.episodes():
                            expanded_keys.add(episode.ratingKey)
            except Exception:
                pass

    for item in list(state.selected_items):
        if item.ratingKey in expanded_keys:
            state.remove_selection(item)

    return jsonify({'count': len(state.selected_items)})


@libraries_bp.route('/selection/clear', methods=['POST'])
def clear_selection():
    """Clear all selections."""
    current_app.state.clear_selection()
    return jsonify({'count': 0})


@libraries_bp.route('/selection')
def get_selection():
    """Get current selection."""
    state = current_app.state
    selected = []
    for item in state.selected_items:
        selected.append({
            'rating_key': item.ratingKey,
            'title': library_service.get_item_title(item),
        })
    return jsonify({'items': selected, 'count': len(selected)})


@libraries_bp.route('/selection/add-all', methods=['POST'])
def add_all_selection():
    """Select all items in current library (resolves episodes for shows)."""
    state = current_app.state
    tm = current_app.task_manager

    library_name = request.json.get('library_name', '')
    items = state.library_items_cache.get(library_name, [])

    if not items:
        return jsonify({'count': 0})

    is_movie = isinstance(items[0], Movie)

    def do_select_all():
        if is_movie:
            for item in items:
                state.add_selection(item)
        else:
            # Shows: select all episodes
            for show in items:
                try:
                    for season in show.seasons():
                        for episode in season.episodes():
                            state.add_selection(episode)
                except Exception as e:
                    logging.error(f"Error selecting episodes for {show.title}: {e}")

        tm.emit('status', {'message': f"Selected {len(state.selected_items)} items"})
        return {'count': len(state.selected_items)}

    task_id = tm.submit('select_all', do_select_all)
    return jsonify({'task_id': task_id})
