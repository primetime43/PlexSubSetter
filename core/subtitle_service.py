"""
Subtitle operations service.

Extracted from ui/subtitle_operations.py. No UI dependencies.
"""

import os
import tempfile
import logging
import concurrent.futures

from plexapi.video import Movie, Episode
from subliminal import list_subtitles
from subliminal.core import ProviderPool
from subliminal.video import Episode as SubliminalEpisode, Movie as SubliminalMovie
from babelfish import Language

from utils.constants import SEARCH_LANGUAGES, MAX_SUBTITLE_RESULTS
from utils.security import (
    sanitize_subtitle_filename,
    create_secure_subtitle_path,
    validate_subtitle_content_size,
)
from core.library_service import get_item_title


def _make_video_object(item):
    """Create a subliminal Video object from a Plex item."""
    if isinstance(item, Episode):
        ep_num = item.index if item.index is not None else 0
        season_num = item.seasonNumber if item.seasonNumber is not None else 0
        fake_name = f"{item.grandparentTitle}.S{season_num:02d}E{ep_num:02d}.mkv"
        video = SubliminalEpisode(
            name=fake_name,
            series=item.grandparentTitle,
            season=season_num,
            episodes=ep_num,
        )
        video.title = item.title
        if hasattr(item, 'year') and item.year:
            video.year = item.year
    else:
        year = getattr(item, 'year', '')
        fake_name = f"{item.title}.{year}.mkv" if year else f"{item.title}.mkv"
        video = SubliminalMovie(
            name=fake_name,
            title=item.title,
            year=getattr(item, 'year', None),
        )
    return video


def search(items, language_name, providers, task_manager=None, timeout=None, sdh=False, forced=False):
    """
    Search for available subtitles.

    Args:
        items: List of Plex items
        language_name: Language display name (e.g. "English")
        providers: Comma-separated provider string
        task_manager: Optional TaskManager for progress events
        timeout: Optional search timeout in seconds per provider
        sdh: If True, prefer hearing-impaired subtitles (sort to top)
        forced: If True, prefer forced subtitles (sort to top)

    Returns:
        dict: {rating_key: {title, subtitles: [{provider, release_info, index}]}}
    """
    language_code = SEARCH_LANGUAGES.get(language_name, 'en')
    lang = Language.fromalpha2(language_code)
    if not providers:
        providers = 'opensubtitles,podnapisi'
    provider_list = [p.strip() for p in providers.split(',') if p.strip()]

    # Build provider configs with timeout if specified
    provider_configs = {}
    if timeout:
        for p in provider_list:
            provider_configs[p] = {'timeout': timeout}

    results = {}
    total = len(items)

    # Build video objects and map them back to Plex items
    video_item_pairs = []
    for item in items:
        try:
            video = _make_video_object(item)
            video_item_pairs.append((video, item))
        except Exception as e:
            title = get_item_title(item)
            logging.error(f"Error creating video object for {title}: {e}")
            if task_manager:
                task_manager.emit('log', {
                    'message': f"Error preparing {title}: {e}",
                    'level': 'error',
                })

    # Single provider session — one login/logout for all items, with per-item progress
    pool_kwargs = {}
    if provider_configs:
        pool_kwargs['provider_configs'] = provider_configs

    with ProviderPool(providers=provider_list, **pool_kwargs) as pool:
        for idx, (video, item) in enumerate(video_item_pairs):
            title = get_item_title(item)

            if task_manager:
                task_manager.emit('progress', {
                    'type': 'search',
                    'current': idx + 1,
                    'total': total,
                    'item': title,
                })
                task_manager.emit('log', {'message': f"Searching subtitles for: {title}"})

            try:
                subs_list = list(pool.list_subtitles(video, languages={lang}))
            except Exception as e:
                logging.error(f"Error searching subtitles for {title}: {e}")
                if task_manager:
                    task_manager.emit('log', {
                        'message': f"Error searching for {title}: {e}",
                        'level': 'error',
                    })
                continue

            # Preference sort: SDH/forced subs come first if requested
            if subs_list and (sdh or forced):
                def _sort_key(sub):
                    score = 0
                    if sdh and getattr(sub, 'hearing_impaired', False):
                        score -= 1
                    if forced and getattr(sub, 'forced', False):
                        score -= 1
                    return score
                subs_list.sort(key=_sort_key)

            if subs_list:
                results[item.ratingKey] = {
                    'title': title,
                    'item': item,
                    'subtitles_raw': subs_list,
                    'subtitles': [],
                }
                for i, sub in enumerate(subs_list[:MAX_SUBTITLE_RESULTS]):
                    release_info = (
                        getattr(sub, 'movie_release_name', None) or
                        getattr(sub, 'release', None) or
                        getattr(sub, 'filename', None) or
                        getattr(sub, 'info', None) or
                        f"ID: {getattr(sub, 'subtitle_id', 'Unknown')}"
                    )
                    results[item.ratingKey]['subtitles'].append({
                        'index': i,
                        'provider': getattr(sub, 'provider_name', 'unknown'),
                        'release_info': str(release_info)[:100],
                    })

                if task_manager:
                    task_manager.emit('log', {
                        'message': f"Found {len(subs_list)} subtitle(s) for: {title}"
                    })
            else:
                if task_manager:
                    task_manager.emit('log', {
                        'message': f"No subtitles found for: {title}",
                        'level': 'warning',
                    })

    return results


def download(items, search_results, selections, language_name, save_method, task_manager=None, concurrent_downloads=1):
    """
    Download selected subtitles.

    Args:
        items: List of Plex items
        search_results: Results from search() (keyed by rating_key)
        selections: Dict of {rating_key: selected_index} (-1 = skip)
        language_name: Language name
        save_method: 'plex' or 'file'
        task_manager: Optional TaskManager
        concurrent_downloads: Number of parallel download workers

    Returns:
        dict: {success_count, total_count, successful_keys}
    """
    language_code = SEARCH_LANGUAGES.get(language_name, 'en')
    successful_keys = []
    total_count = len(selections)

    # Build list of download tasks (skip entries with index -1 or missing data)
    download_tasks = []
    for rating_key, selected_index in selections.items():
        if selected_index == -1:
            if task_manager:
                result_data = search_results.get(rating_key, {})
                task_manager.emit('log', {'message': f"Skipped: {result_data.get('title', rating_key)}"})
            continue

        result_data = search_results.get(rating_key)
        if not result_data:
            logging.warning(f"Download: no search results for rating_key={rating_key} (type={type(rating_key)}), available keys={list(search_results.keys())[:5]}")
            continue

        subs_list = result_data.get('subtitles_raw', [])
        if selected_index >= len(subs_list):
            logging.warning(f"Download: selected_index={selected_index} >= subs count={len(subs_list)} for {result_data.get('title')}")
            continue

        download_tasks.append((rating_key, result_data, subs_list[selected_index]))

    skipped_items = []
    failed_items = []
    succeeded_items = []

    # Track skipped items
    for rating_key, selected_index in selections.items():
        if selected_index == -1:
            result_data = search_results.get(rating_key, {})
            skipped_items.append(result_data.get('title', str(rating_key)))

    logging.info(f"Download: {len(selections)} selections, {len(download_tasks)} tasks to download")

    if download_tasks:
        # Download and save each subtitle with per-item progress
        all_providers = list({getattr(task[2], 'provider_name', 'unknown') for task in download_tasks})

        if task_manager:
            task_manager.emit('log', {'message': f"Downloading {len(download_tasks)} subtitle(s)..."})

        total_tasks = len(download_tasks)
        with ProviderPool(providers=all_providers) as pool:
            for idx, (rating_key, result_data, selected_sub) in enumerate(download_tasks):
                item = result_data['item']
                title = result_data['title']

                if task_manager:
                    task_manager.emit('progress', {
                        'type': 'download',
                        'current': idx,
                        'total': total_tasks,
                        'item': f"Downloading: {title}",
                    })

                try:
                    # Download this subtitle's content
                    pool.download_subtitle(selected_sub)

                    if not getattr(selected_sub, 'content', None):
                        if task_manager:
                            task_manager.emit('log', {'message': f"No content downloaded for: {title}", 'level': 'warning'})
                        failed_items.append({'title': title, 'error': 'No content downloaded'})
                        continue

                    validate_subtitle_content_size(selected_sub.content)

                    if task_manager:
                        task_manager.emit('progress', {
                            'type': 'download',
                            'current': idx,
                            'total': total_tasks,
                            'item': f"Saving: {title}",
                        })

                    temp_dir = tempfile.gettempdir()
                    subtitle_filename = sanitize_subtitle_filename(item, language_code)
                    subtitle_path = os.path.join(temp_dir, subtitle_filename)

                    try:
                        with open(subtitle_path, 'wb') as f:
                            f.write(selected_sub.content)

                        if save_method == 'file':
                            _save_to_file(item, subtitle_path, language_code, task_manager)
                        else:
                            item.uploadSubtitles(subtitle_path)

                        provider = getattr(selected_sub, 'provider_name', 'unknown')
                        if task_manager:
                            task_manager.emit('log', {'message': f"Successfully downloaded subtitle for: {title}"})
                        successful_keys.append(rating_key)
                        succeeded_items.append({'title': title, 'provider': provider})
                    finally:
                        try:
                            os.remove(subtitle_path)
                        except (OSError, PermissionError) as cleanup_error:
                            logging.debug(f"Could not delete temp file: {cleanup_error}")

                except Exception as e:
                    logging.error(f"Error downloading/saving subtitle for {title}: {e}")
                    failed_items.append({'title': title, 'error': str(e)})
                    if task_manager:
                        task_manager.emit('log', {'message': f"Error for {title}: {e}", 'level': 'error'})
                finally:
                    # Emit progress after each item completes (success or fail) so bar advances
                    if task_manager:
                        task_manager.emit('progress', {
                            'type': 'download',
                            'current': idx + 1,
                            'total': total_tasks,
                            'item': title,
                        })

    # Reload successful items
    for rk in successful_keys:
        result_data = search_results.get(rk)
        if result_data and result_data.get('item'):
            try:
                result_data['item'].reload()
            except Exception:
                pass

    return {
        'success_count': len(successful_keys),
        'total_count': total_count,
        'successful_keys': successful_keys,
        'succeeded': succeeded_items,
        'failed': failed_items,
        'skipped': skipped_items,
    }


def _save_to_file(item, subtitle_path, language_code, task_manager=None):
    """Save subtitle next to the video file, with fallback to Plex upload."""
    import shutil
    try:
        if hasattr(item, 'media') and item.media:
            video_path = item.media[0].parts[0].file

            try:
                final_path = create_secure_subtitle_path(video_path, language_code, item)
            except ValueError as path_error:
                if task_manager:
                    task_manager.emit('log', {'message': f"Security error: {path_error}, falling back to Plex upload"})
                item.uploadSubtitles(subtitle_path)
                return

            shutil.copy2(subtitle_path, str(final_path))

            if task_manager:
                task_manager.emit('log', {'message': f"Saved subtitle to: {final_path}"})

            # Trigger Plex scan
            try:
                library_section = item.section()
                video_dir = os.path.dirname(str(final_path))
                library_section.update(video_dir)
            except Exception as scan_error:
                if task_manager:
                    task_manager.emit('log', {'message': f"Could not trigger Plex scan: {scan_error}"})
        else:
            item.uploadSubtitles(subtitle_path)
    except Exception as file_error:
        if task_manager:
            task_manager.emit('log', {'message': f"File save failed: {file_error}, falling back to Plex upload"})
        item.uploadSubtitles(subtitle_path)


def dry_run(items, language_name, providers, task_manager=None, timeout=None, sdh=False, forced=False):
    """
    Preview subtitle availability without downloading.

    Args:
        sdh: Accepted for API consistency (not used in dry run)
        forced: Accepted for API consistency (not used in dry run)

    Returns:
        dict with keys: already_have, available, not_available, errors
    """
    language_code = SEARCH_LANGUAGES.get(language_name, 'en')
    lang = Language.fromalpha2(language_code)
    if not providers:
        providers = 'opensubtitles,podnapisi'
    provider_list = [p.strip() for p in providers.split(',') if p.strip()]

    # Build provider configs with timeout if specified
    provider_configs = {}
    if timeout:
        for p in provider_list:
            provider_configs[p] = {'timeout': timeout}

    already_have = []
    available = []
    not_available = []
    errors = []
    total = len(items)

    # First pass: separate items that already have subs from those needing search
    needs_search = []  # (item, title) pairs
    for idx, item in enumerate(items):
        title = get_item_title(item)

        if task_manager:
            task_manager.emit('progress', {
                'type': 'dry_run',
                'current': idx + 1,
                'total': total,
                'item': title,
            })

        try:
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

            if has_subs:
                already_have.append({'title': title, 'rating_key': item.ratingKey})
            else:
                needs_search.append((item, title))
        except Exception as e:
            errors.append({'title': title, 'rating_key': item.ratingKey, 'error': str(e)})
            if task_manager:
                task_manager.emit('log', {'message': f"Error checking {title}: {e}", 'level': 'error'})

    # Second pass: search items that need subtitles (single provider session)
    if needs_search:
        pool_kwargs = {}
        if provider_configs:
            pool_kwargs['provider_configs'] = provider_configs

        with ProviderPool(providers=provider_list, **pool_kwargs) as pool:
            for item, title in needs_search:
                if task_manager:
                    task_manager.emit('progress', {
                        'type': 'dry_run',
                        'current': len(already_have) + len(available) + len(not_available) + len(errors) + 1,
                        'total': total,
                        'item': title,
                    })

                try:
                    video = _make_video_object(item)
                    subs_list = list(pool.list_subtitles(video, languages={lang}))
                    count = len(subs_list)

                    if count > 0:
                        available.append({'title': title, 'rating_key': item.ratingKey, 'count': count})
                    else:
                        not_available.append({'title': title, 'rating_key': item.ratingKey})

                    if task_manager:
                        task_manager.emit('log', {'message': f"{title}: {count} subtitle(s) available"})
                except Exception as e:
                    errors.append({'title': title, 'rating_key': item.ratingKey, 'error': str(e)})
                    if task_manager:
                        task_manager.emit('log', {'message': f"Error checking {title}: {e}", 'level': 'error'})

    return {
        'already_have': already_have,
        'available': available,
        'not_available': not_available,
        'errors': errors,
    }


def list_current(items):
    """
    List current subtitle streams for items.

    Returns:
        list of dicts: [{title, rating_key, streams: [{language, codec, forced, sdh, selected}]}]
    """
    result = []
    for item in items:
        title = get_item_title(item)
        streams = []
        try:
            for media in item.media:
                for part in media.parts:
                    for sub_stream in part.subtitleStreams():
                        streams.append({
                            'language': sub_stream.language or "Unknown",
                            'codec': sub_stream.codec or "Unknown",
                            'forced': bool(sub_stream.forced),
                            'sdh': bool(sub_stream.hearingImpaired),
                            'selected': bool(sub_stream.selected),
                        })
        except Exception as e:
            logging.debug(f"Error reading subtitle streams for {title}: {e}")

        if streams:
            result.append({
                'title': title,
                'rating_key': item.ratingKey,
                'streams': streams,
            })

    return result


