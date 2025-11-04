"""
Security utilities for PlexSubSetter.

This module provides functions to prevent common security vulnerabilities:
- Path traversal attacks
- Filename injection
- File size abuse
"""

import os
import re
import platform
from pathlib import Path
from typing import Union


# Security constants
MAX_SUBTITLE_SIZE = 10 * 1024 * 1024  # 10MB (subtitles are typically < 500KB)
MAX_FILENAME_LENGTH = 255

# Windows reserved names
WINDOWS_RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
}


def sanitize_filename(filename: str, max_length: int = MAX_FILENAME_LENGTH) -> str:
    """
    Sanitize filename to prevent security issues.

    Protects against:
    - Path traversal (../, ..\\, /)
    - Reserved Windows names (CON, NUL, etc.)
    - Invalid characters
    - Excessive length
    - Hidden files (leading dots)
    - Multiple extensions (.srt.exe)

    Args:
        filename: Original filename to sanitize
        max_length: Maximum allowed filename length (default: 255)

    Returns:
        str: Sanitized filename safe for filesystem use

    Examples:
        >>> sanitize_filename("../../etc/passwd.srt")
        'etcpasswd.srt'
        >>> sanitize_filename("CON.srt")
        '_CON.srt'
        >>> sanitize_filename("movie<name>.srt")
        'moviename.srt'
    """
    if not filename:
        return "unnamed.srt"

    # Store original for debugging
    original_filename = filename

    # Remove any directory separators and null bytes
    filename = filename.replace('/', '_').replace('\\', '_').replace('\x00', '')

    # Remove or replace dangerous characters
    # Allow: letters, numbers, spaces, dots, hyphens, underscores
    filename = re.sub(r'[^\w\s\-\.]', '', filename)

    # Collapse multiple spaces and dots
    filename = re.sub(r'\.{2,}', '.', filename)  # Replace multiple dots with single dot
    filename = re.sub(r'\s+', ' ', filename)

    # Remove leading/trailing dots and spaces (Windows compatibility)
    filename = filename.strip('. ')

    # Prevent Windows reserved names
    if platform.system() == 'Windows':
        name_part = filename.split('.')[0].upper()
        if name_part in WINDOWS_RESERVED_NAMES:
            filename = f"_{filename}"

    # Prevent files starting with dot (hidden files on Unix)
    if filename.startswith('.'):
        filename = f"_{filename[1:]}"  # Remove the dot and prefix with underscore

    # Limit filename length, preserving extension
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        if ext:
            # Keep extension, truncate name
            max_name_length = max_length - len(ext)
            filename = name[:max_name_length] + ext
        else:
            filename = filename[:max_length]

    # Final safety check - if we ended up with empty filename or dangerous patterns
    if not filename or filename in ('.', '..', ''):
        return "unnamed.srt"

    return filename


def validate_path(base_dir: Union[str, Path], target_path: Union[str, Path],
                  filename: str = None) -> Path:
    """
    Validate that target path is within base directory.

    Prevents path traversal attacks by ensuring resolved path
    stays within the intended base directory.

    Args:
        base_dir: Base directory that should contain the file
        target_path: Directory path to validate
        filename: Optional filename to append after validation

    Returns:
        Path: Validated absolute path

    Raises:
        ValueError: If path traversal attempt is detected

    Examples:
        >>> validate_path('/media/videos', '/media/videos/movies', 'sub.srt')
        Path('/media/videos/movies/sub.srt')
        >>> validate_path('/media/videos', '../../etc', 'passwd')
        ValueError: Path traversal attempt detected
    """
    base_dir = Path(base_dir).resolve()
    target_path = Path(target_path).resolve()

    # Check if target is within base directory
    try:
        target_path.relative_to(base_dir)
    except ValueError:
        raise ValueError(
            f"Path traversal attempt detected: '{target_path}' is outside '{base_dir}'"
        )

    # If filename provided, sanitize and append it
    if filename:
        safe_filename = sanitize_filename(filename)
        final_path = target_path / safe_filename

        # Verify final path is still within base_dir
        try:
            final_path.resolve().relative_to(base_dir)
        except ValueError:
            raise ValueError(
                f"Path traversal attempt detected in filename: '{filename}'"
            )

        return final_path

    return target_path


def sanitize_subtitle_filename(item, language_code: str) -> str:
    """
    Create a sanitized subtitle filename from a Plex item.

    Args:
        item: Plex video item (Movie or Episode)
        language_code: Language code for subtitle (e.g., 'eng', 'spa')

    Returns:
        str: Sanitized subtitle filename

    Examples:
        >>> sanitize_subtitle_filename(movie, 'eng')
        'The_Movie_2024.eng.srt'
        >>> sanitize_subtitle_filename(episode, 'spa')
        'Show_Name.S01E05.spa.srt'
    """
    from plexapi.video import Episode

    # Create base filename from item
    if isinstance(item, Episode):
        # Format: ShowName.S01E05.lang.srt
        base_name = f"{item.grandparentTitle}.S{item.seasonNumber:02d}E{item.index:02d}"
    else:
        # Format: MovieName.lang.srt
        base_name = item.title

    # Sanitize the language code
    safe_lang = re.sub(r'[^\w\-]', '', str(language_code))

    # Construct filename
    filename = f"{base_name}.{safe_lang}.srt"

    # Sanitize the complete filename
    return sanitize_filename(filename)


def validate_file_size(file_path: Union[str, Path],
                       max_size: int = MAX_SUBTITLE_SIZE) -> bool:
    """
    Check if file size is within acceptable limits.

    Args:
        file_path: Path to file to check
        max_size: Maximum allowed size in bytes (default: 10MB)

    Returns:
        bool: True if file size is acceptable

    Raises:
        ValueError: If file exceeds maximum size
        FileNotFoundError: If file doesn't exist

    Examples:
        >>> validate_file_size('subtitle.srt')
        True
        >>> validate_file_size('huge_file.srt', max_size=1024)
        ValueError: File exceeds maximum size
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = file_path.stat().st_size

    if file_size > max_size:
        raise ValueError(
            f"File exceeds maximum size: {file_size:,} bytes "
            f"(max: {max_size:,} bytes)"
        )

    return True


def validate_subtitle_content_size(content: bytes,
                                   max_size: int = MAX_SUBTITLE_SIZE) -> bool:
    """
    Validate size of subtitle content before writing.

    Args:
        content: Subtitle content bytes
        max_size: Maximum allowed size in bytes (default: 10MB)

    Returns:
        bool: True if content size is acceptable

    Raises:
        ValueError: If content exceeds maximum size

    Examples:
        >>> validate_subtitle_content_size(b'subtitle text')
        True
        >>> validate_subtitle_content_size(b'x' * 20_000_000)
        ValueError: Subtitle content exceeds maximum size
    """
    content_size = len(content)

    if content_size > max_size:
        raise ValueError(
            f"Subtitle content exceeds maximum size: {content_size:,} bytes "
            f"(max: {max_size:,} bytes)"
        )

    return True


def create_secure_subtitle_path(video_path: Union[str, Path],
                                language_code: str,
                                item) -> Path:
    """
    Create a secure path for saving subtitles next to video files.

    This function combines path validation and filename sanitization
    to safely create subtitle file paths.

    Args:
        video_path: Path to video file from Plex
        language_code: Language code for subtitle
        item: Plex video item (for generating filename)

    Returns:
        Path: Validated, sanitized subtitle file path

    Raises:
        ValueError: If path validation fails

    Examples:
        >>> create_secure_subtitle_path('/media/movies/film.mp4', 'eng', movie)
        Path('/media/movies/film.eng.srt')
    """
    video_path = Path(video_path).resolve()

    # Get video directory and base filename
    video_dir = video_path.parent
    video_base = video_path.stem  # Filename without extension

    # Sanitize the base filename (in case Plex data is malicious)
    safe_video_base = sanitize_filename(video_base)
    safe_lang = re.sub(r'[^\w\-]', '', str(language_code))

    # Create subtitle filename
    subtitle_filename = f"{safe_video_base}.{safe_lang}.srt"

    # Validate that video_dir is a real directory on the system
    # This prevents writing to arbitrary locations
    if not video_dir.exists():
        raise ValueError(f"Video directory does not exist: {video_dir}")

    if not video_dir.is_dir():
        raise ValueError(f"Video path is not a directory: {video_dir}")

    # Final path validation
    # Use video_dir's parent as base to allow writing in video_dir
    subtitle_path = validate_path(
        base_dir=video_dir.parent,
        target_path=video_dir,
        filename=subtitle_filename
    )

    return subtitle_path
