"""
Subtitle operations service.

Extracted from ui/subtitle_operations.py. No UI dependencies.
"""

import os
import sys
import tempfile
import logging

from plexapi.video import Movie, Episode
from subliminal import download_subtitles, list_subtitles
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
        fake_name = f"{item.grandparentTitle}.S{item.seasonNumber:02d}E{item.index:02d}.mkv"
        video = SubliminalEpisode(
            name=fake_name,
            series=item.grandparentTitle,
            season=item.seasonNumber,
            episodes=item.index,
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


def search(items, language_name, providers, task_manager=None):
    """
    Search for available subtitles.

    Args:
        items: List of Plex items
        language_name: Language display name (e.g. "English")
        providers: Comma-separated provider string
        task_manager: Optional TaskManager for progress events

    Returns:
        dict: {rating_key: {title, subtitles: [{provider, release_info, index}]}}
    """
    language_code = SEARCH_LANGUAGES.get(language_name, 'en')
    lang = Language.fromalpha2(language_code)
    provider_list = [p.strip() for p in providers.split(',') if p.strip()]

    results = {}
    total = len(items)

    for idx, item in enumerate(items):
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
            video = _make_video_object(item)
            subtitles = list_subtitles({video}, languages={lang}, providers=provider_list)
            subs_list = list(subtitles.get(video, []))

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

        except Exception as e:
            logging.error(f"Error searching subtitles for {title}: {e}")
            if task_manager:
                task_manager.emit('log', {
                    'message': f"Error searching for {title}: {e}",
                    'level': 'error',
                })

    return results


def download(items, search_results, selections, language_name, save_method, task_manager=None):
    """
    Download selected subtitles.

    Args:
        items: List of Plex items
        search_results: Results from search() (keyed by rating_key)
        selections: Dict of {rating_key: selected_index} (-1 = skip)
        language_name: Language name
        save_method: 'plex' or 'file'
        task_manager: Optional TaskManager

    Returns:
        dict: {success_count, total_count, successful_keys}
    """
    language_code = SEARCH_LANGUAGES.get(language_name, 'en')
    success_count = 0
    successful_keys = []
    total_count = len(selections)

    for rating_key, selected_index in selections.items():
        if selected_index == -1:
            if task_manager:
                result_data = search_results.get(rating_key, {})
                task_manager.emit('log', {'message': f"Skipped: {result_data.get('title', rating_key)}"})
            continue

        result_data = search_results.get(rating_key)
        if not result_data:
            continue

        item = result_data['item']
        subs_list = result_data.get('subtitles_raw', [])
        title = result_data['title']

        if selected_index >= len(subs_list):
            continue

        selected_sub = subs_list[selected_index]

        if task_manager:
            task_manager.emit('progress', {
                'type': 'download',
                'current': success_count + 1,
                'total': total_count,
                'item': title,
            })

        try:
            provider = getattr(selected_sub, 'provider_name', 'unknown')
            download_subtitles([selected_sub], providers=[provider])

            temp_dir = tempfile.gettempdir()
            subtitle_filename = sanitize_subtitle_filename(item, language_code)
            subtitle_path = os.path.join(temp_dir, subtitle_filename)

            try:
                validate_subtitle_content_size(selected_sub.content)
            except ValueError as e:
                if task_manager:
                    task_manager.emit('log', {'message': f"Error: {e}", 'level': 'error'})
                continue

            with open(subtitle_path, 'wb') as f:
                f.write(selected_sub.content)

            if save_method == 'file':
                _save_to_file(item, subtitle_path, language_code, task_manager)
            else:
                item.uploadSubtitles(subtitle_path)

            # Clean up temp file
            try:
                os.remove(subtitle_path)
            except (OSError, PermissionError) as cleanup_error:
                logging.debug(f"Could not delete temp file: {cleanup_error}")

            success_count += 1
            successful_keys.append(rating_key)

            if task_manager:
                task_manager.emit('log', {'message': f"Successfully downloaded subtitle for: {title}"})

        except Exception as e:
            logging.error(f"Error downloading subtitle for {title}: {e}")
            if task_manager:
                task_manager.emit('log', {'message': f"Error downloading for {title}: {e}", 'level': 'error'})

    # Reload successful items
    for rk in successful_keys:
        result_data = search_results.get(rk)
        if result_data and result_data.get('item'):
            try:
                result_data['item'].reload()
            except Exception:
                pass

    return {
        'success_count': success_count,
        'total_count': total_count,
        'successful_keys': successful_keys,
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


def dry_run(items, language_name, providers, task_manager=None):
    """
    Preview subtitle availability without downloading.

    Returns:
        dict with keys: already_have, available, not_available, errors
    """
    language_code = SEARCH_LANGUAGES.get(language_name, 'en')
    lang = Language.fromalpha2(language_code)
    provider_list = [p.strip() for p in providers.split(',') if p.strip()]

    already_have = []
    available = []
    not_available = []
    errors = []
    total = len(items)

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
            # Check if already has subtitles for this language
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
                continue

            video = _make_video_object(item)
            subtitles = list_subtitles({video}, languages={lang}, providers=provider_list)
            count = len(list(subtitles.get(video, [])))

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


def delete(items, task_manager=None):
    """
    Delete all subtitle streams from items.

    Returns:
        dict: {success_count, total_count, successful_keys}
    """
    success_count = 0
    successful_keys = []
    total = len(items)

    for idx, item in enumerate(items):
        title = get_item_title(item)

        if task_manager:
            task_manager.emit('progress', {
                'type': 'delete',
                'current': idx + 1,
                'total': total,
                'item': title,
            })

        try:
            deleted_count = 0
            for media in item.media:
                for part in media.parts:
                    for sub_stream in part.subtitleStreams():
                        part.removeSubtitleStream(sub_stream)
                        deleted_count += 1

            if deleted_count > 0:
                success_count += 1
                successful_keys.append(item.ratingKey)
                if task_manager:
                    task_manager.emit('log', {
                        'message': f"Deleted {deleted_count} subtitle stream(s) from: {title}"
                    })
            else:
                if task_manager:
                    task_manager.emit('log', {
                        'message': f"No subtitles to delete for: {title}",
                        'level': 'warning',
                    })

        except Exception as e:
            logging.error(f"Error deleting subtitles from {title}: {e}")
            if task_manager:
                task_manager.emit('log', {
                    'message': f"Error deleting from {title}: {e}",
                    'level': 'error',
                })

    # Reload successful items
    for rk in successful_keys:
        for item in items:
            if item.ratingKey == rk:
                try:
                    item.reload()
                except Exception:
                    pass
                break

    return {
        'success_count': success_count,
        'total_count': total,
        'successful_keys': successful_keys,
    }
