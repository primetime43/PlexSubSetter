"""Subtitle operation routes."""

import logging
from collections import OrderedDict
from flask import Blueprint, render_template, jsonify, request, current_app

from plexapi.video import Episode

from core import subtitle_service
from utils.config_manager import ConfigManager

subtitles_bp = Blueprint('subtitles', __name__)


@subtitles_bp.route('/subtitles/search', methods=['POST'])
def search_subtitles():
    """Start subtitle search (background task)."""
    state = current_app.state
    tm = current_app.task_manager

    if not state.selected_items:
        return jsonify({'error': 'No items selected'}), 400

    config = ConfigManager()
    settings = config.load_settings()

    language = request.json.get('language', settings.get('default_language', 'English'))
    providers = request.json.get('providers', settings.get('default_providers', 'opensubtitles,podnapisi'))
    timeout = settings.get('search_timeout', 30)
    sdh = request.json.get('sdh', False)
    forced = request.json.get('forced', False)

    items = list(state.selected_items)

    def do_search():
        results = subtitle_service.search(items, language, providers, tm, timeout=timeout, sdh=sdh, forced=forced)
        # Store results in state for download
        state.search_results = results
        return results

    task_id = tm.submit('subtitle_search', do_search)
    return jsonify({'task_id': task_id, 'item_count': len(items)})


@subtitles_bp.route('/subtitles/search-results')
def search_results():
    """Get search results as HTML partial."""
    state = current_app.state
    results = state.search_results

    if not results:
        return '<div class="text-gray-400 p-4 text-center">No search results. Run a search first.</div>'

    # Group results by type: movies vs shows (grouped by show/season)
    movies = []
    shows_dict = {}  # {show_name: {season_num: [episodes...]}}
    total_searched = len(state.selected_items) if state.selected_items else len(results)
    found_count = len(results)

    for rk, data in results.items():
        item = data.get('item')
        entry = {
            'rating_key': rk,
            'subtitles': data.get('subtitles', []),
            'total_count': len(data.get('subtitles_raw', [])),
        }

        if isinstance(item, Episode):
            show_name = item.grandparentTitle or 'Unknown Show'
            season_num = item.seasonNumber if item.seasonNumber is not None else 0
            ep_num = item.index if item.index is not None else 0
            entry['episode_title'] = f"E{ep_num:02d} - {item.title}"
            entry['episode_index'] = ep_num

            if show_name not in shows_dict:
                shows_dict[show_name] = {}
            if season_num not in shows_dict[show_name]:
                shows_dict[show_name][season_num] = []
            shows_dict[show_name][season_num].append(entry)
        else:
            entry['title'] = data['title']
            movies.append(entry)

    # Sort shows by name, seasons by number, episodes by index
    shows = OrderedDict()
    for show_name in sorted(shows_dict.keys()):
        shows[show_name] = OrderedDict()
        for season_num in sorted(shows_dict[show_name].keys()):
            episodes = shows_dict[show_name][season_num]
            episodes.sort(key=lambda e: e['episode_index'])
            shows[show_name][season_num] = episodes

    return render_template('partials/search_results.html',
                           movies=movies, shows=shows,
                           found_count=found_count,
                           total_searched=total_searched)


@subtitles_bp.route('/subtitles/download', methods=['POST'])
def download_subtitles():
    """Start subtitle download (background task)."""
    state = current_app.state
    tm = current_app.task_manager

    if not state.search_results:
        return jsonify({'error': 'No search results'}), 400

    config = ConfigManager()
    settings = config.load_settings()

    selections = request.json.get('selections', {})
    # Convert string keys to int
    selections = {int(k): int(v) for k, v in selections.items()}

    language = request.json.get('language', settings.get('default_language', 'English'))
    save_method = request.json.get('save_method', settings.get('subtitle_save_method', 'plex'))
    concurrent_downloads = settings.get('concurrent_downloads', 3)

    search_results = state.search_results

    def do_download():
        result = subtitle_service.download(
            state.selected_items, search_results, selections, language, save_method, tm,
            concurrent_downloads=concurrent_downloads
        )
        # Clear subtitle cache for successful items
        if result['successful_keys']:
            state.clear_subtitle_cache(result['successful_keys'])
            # Clear search results after successful download
            state.search_results = {}
        # Store download results for summary display
        state.last_download_result = result
        return result

    task_id = tm.submit('subtitle_download', do_download)
    return jsonify({'task_id': task_id})


@subtitles_bp.route('/subtitles/download-results')
def download_results():
    """Get download results as HTML partial."""
    state = current_app.state
    result = getattr(state, 'last_download_result', None)

    if not result:
        return '<div class="text-gray-400 p-4 text-center">No download results available.</div>'

    return render_template('partials/download_results.html',
                           succeeded=result.get('succeeded', []),
                           failed=result.get('failed', []),
                           skipped=result.get('skipped', []))


@subtitles_bp.route('/subtitles/dry-run', methods=['POST'])
def dry_run():
    """Start dry run (background task)."""
    state = current_app.state
    tm = current_app.task_manager

    if not state.selected_items:
        return jsonify({'error': 'No items selected'}), 400

    config = ConfigManager()
    settings = config.load_settings()

    language = request.json.get('language', settings.get('default_language', 'English'))
    providers = request.json.get('providers', settings.get('default_providers', 'opensubtitles,podnapisi'))
    timeout = settings.get('search_timeout', 30)
    sdh = request.json.get('sdh', False)
    forced = request.json.get('forced', False)

    items = list(state.selected_items)

    def do_dry_run():
        return subtitle_service.dry_run(items, language, providers, tm, timeout=timeout, sdh=sdh, forced=forced)

    task_id = tm.submit('dry_run', do_dry_run)
    return jsonify({'task_id': task_id, 'item_count': len(items)})


@subtitles_bp.route('/subtitles/dry-run-results')
def dry_run_results():
    """Get dry run results as HTML partial."""
    state = current_app.state
    tm = current_app.task_manager

    # Find last dry_run task result
    task_data = None
    for tid, tinfo in list(tm._tasks.items()):
        if tinfo['type'] == 'dry_run' and tinfo['status'] == 'complete':
            task_data = tinfo['result']

    if not task_data:
        return '<div class="text-gray-400 p-4 text-center">No dry run results available.</div>'

    return render_template('partials/dry_run_results.html',
                           already_have=task_data.get('already_have', []),
                           available=task_data.get('available', []),
                           not_available=task_data.get('not_available', []),
                           errors=task_data.get('errors', []))


@subtitles_bp.route('/subtitles/list', methods=['POST'])
def list_subtitles():
    """List current subtitles for selected items."""
    state = current_app.state
    if not state.selected_items:
        return '<div class="text-gray-400 p-4 text-center">No items selected.</div>'

    try:
        result = subtitle_service.list_current(state.selected_items)
        return render_template('partials/subtitle_list.html', items=result)
    except Exception as e:
        return f'<div class="text-red-400 p-4">Error: {e}</div>', 500




@subtitles_bp.route('/subtitles/task/<task_id>')
def task_status(task_id):
    """Get task status."""
    tm = current_app.task_manager
    task = tm.get_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify({
        'status': task.get('status'),
        'type': task.get('type'),
        'error': task.get('error'),
    })
