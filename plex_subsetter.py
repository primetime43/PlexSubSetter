#!/usr/bin/env python3
"""
PlexSubSetter - Mass Subtitle Finder and Setter for Plex
A tool to search, download, and set subtitles for your Plex media library.
"""

import argparse
import sys
from plexapi.server import PlexServer
from plexapi.video import Movie, Episode


class PlexSubSetter:
    """Main class for managing Plex subtitles."""

    def __init__(self, baseurl, token):
        """
        Initialize connection to Plex server.

        Args:
            baseurl (str): Plex server URL (e.g., 'http://localhost:32400')
            token (str): Plex authentication token
        """
        try:
            self.plex = PlexServer(baseurl, token)
            print(f"Successfully connected to Plex server: {self.plex.friendlyName}")
        except Exception as e:
            print(f"Error connecting to Plex server: {e}")
            sys.exit(1)

    def list_libraries(self):
        """List all available libraries on the Plex server."""
        print("\nAvailable libraries:")
        for section in self.plex.library.sections():
            print(f"  - {section.title} (Type: {section.type})")

    def get_video_items(self, library_name=None, item_type='all'):
        """
        Get video items from specified library.

        Args:
            library_name (str): Name of the library (None for all)
            item_type (str): 'movie', 'show', or 'all'

        Returns:
            list: List of video items (Movies or Episodes)
        """
        items = []

        if library_name:
            try:
                section = self.plex.library.section(library_name)
                if section.type == 'movie' and item_type in ['movie', 'all']:
                    items.extend(section.all())
                elif section.type == 'show' and item_type in ['show', 'all']:
                    for show in section.all():
                        for episode in show.episodes():
                            items.append(episode)
            except Exception as e:
                print(f"Error accessing library '{library_name}': {e}")
        else:
            # Get from all libraries
            for section in self.plex.library.sections():
                if section.type == 'movie' and item_type in ['movie', 'all']:
                    items.extend(section.all())
                elif section.type == 'show' and item_type in ['show', 'all']:
                    for show in section.all():
                        for episode in show.episodes():
                            items.append(episode)

        return items

    def search_and_download_subtitles(self, items, language='en', hearing_impaired=False, forced=False):
        """
        Search and download subtitles for given items.

        Args:
            items (list): List of video items
            language (str): ISO 639-1 language code (default: 'en')
            hearing_impaired (bool): Search for SDH subtitles
            forced (bool): Search for forced subtitles
        """
        print(f"\nSearching for subtitles in language: {language}")

        for item in items:
            title = self._get_item_title(item)

            try:
                # Search for available subtitles
                subtitles = item.searchSubtitles(
                    language=language,
                    hearingImpaired=hearing_impaired,
                    forced=forced
                )

                if subtitles:
                    print(f"  [FOUND] {title} - {len(subtitles)} subtitle(s) available")
                    # Download the first available subtitle
                    item.downloadSubtitles(subtitles[0])
                    print(f"    → Downloading subtitle (this may take a moment)")
                else:
                    print(f"  [NONE] {title} - No subtitles found")

            except Exception as e:
                print(f"  [ERROR] {title} - {e}")

    def list_subtitles(self, items):
        """
        List all available subtitle streams for given items.

        Args:
            items (list): List of video items
        """
        print("\nListing subtitle streams:")

        for item in items:
            title = self._get_item_title(item)
            print(f"\n{title}:")

            try:
                # Get all media parts
                for media in item.media:
                    for part in media.parts:
                        subs = part.subtitleStreams()

                        if subs:
                            for sub in subs:
                                selected = "[SELECTED]" if sub.selected else ""
                                language = sub.language or "Unknown"
                                codec = sub.codec or "Unknown"
                                forced = "[FORCED]" if sub.forced else ""
                                sdh = "[SDH]" if sub.hearingImpaired else ""

                                print(f"  {selected} ID: {sub.id} | {language} ({codec}) {forced} {sdh}")
                        else:
                            print("  No subtitle streams available")

            except Exception as e:
                print(f"  Error: {e}")

    def set_subtitles(self, items, language=None, subtitle_id=None, disable=False):
        """
        Set subtitle stream for given items.

        Args:
            items (list): List of video items
            language (str): Language code to select (e.g., 'eng', 'spa')
            subtitle_id (int): Specific subtitle stream ID to select
            disable (bool): Disable subtitles (set to None)
        """
        print("\nSetting subtitle streams:")

        for item in items:
            title = self._get_item_title(item)

            try:
                for media in item.media:
                    for part in media.parts:
                        if disable:
                            part.resetSelectedSubtitleStream()
                            print(f"  ✓ {title} - Subtitles disabled")
                        elif subtitle_id:
                            # Find subtitle by ID
                            subs = part.subtitleStreams()
                            target_sub = next((s for s in subs if s.id == subtitle_id), None)

                            if target_sub:
                                part.setSelectedSubtitleStream(target_sub)
                                print(f"  ✓ {title} - Set to subtitle ID {subtitle_id}")
                            else:
                                print(f"  ✗ {title} - Subtitle ID {subtitle_id} not found")
                        elif language:
                            # Find subtitle by language
                            subs = part.subtitleStreams()
                            target_sub = next((s for s in subs if s.languageCode == language), None)

                            if target_sub:
                                part.setSelectedSubtitleStream(target_sub)
                                print(f"  ✓ {title} - Set to {language} subtitles")
                            else:
                                print(f"  ✗ {title} - No {language} subtitles available")

            except Exception as e:
                print(f"  ✗ {title} - Error: {e}")

    def _get_item_title(self, item):
        """Get formatted title for an item."""
        if isinstance(item, Movie):
            return f"{item.title} ({item.year})"
        elif isinstance(item, Episode):
            return f"{item.grandparentTitle} - S{item.seasonNumber:02d}E{item.index:02d} - {item.title}"
        else:
            return item.title


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description='PlexSubSetter - Mass Subtitle Finder and Setter for Plex',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all libraries
  python plex_subsetter.py --baseurl http://localhost:32400 --token YOUR_TOKEN --list-libraries

  # Search and download English subtitles for all movies
  python plex_subsetter.py --baseurl http://localhost:32400 --token YOUR_TOKEN --library "Movies" --search --language en

  # List available subtitles for TV shows
  python plex_subsetter.py --baseurl http://localhost:32400 --token YOUR_TOKEN --library "TV Shows" --list-subs

  # Set English subtitles for all items in a library
  python plex_subsetter.py --baseurl http://localhost:32400 --token YOUR_TOKEN --library "Movies" --set-language eng

  # Disable subtitles for all items
  python plex_subsetter.py --baseurl http://localhost:32400 --token YOUR_TOKEN --library "Movies" --disable-subs
        """
    )

    # Connection arguments
    parser.add_argument('--baseurl', required=True, help='Plex server URL (e.g., http://localhost:32400)')
    parser.add_argument('--token', required=True, help='Plex authentication token')

    # Library selection
    parser.add_argument('--library', help='Library name to operate on (default: all libraries)')
    parser.add_argument('--type', choices=['movie', 'show', 'all'], default='all',
                        help='Type of content to process (default: all)')

    # Actions
    parser.add_argument('--list-libraries', action='store_true', help='List all available libraries')
    parser.add_argument('--search', action='store_true', help='Search and download subtitles')
    parser.add_argument('--list-subs', action='store_true', help='List available subtitle streams')
    parser.add_argument('--set-language', help='Set subtitle by language code (e.g., eng, spa, fre)')
    parser.add_argument('--set-id', type=int, help='Set subtitle by stream ID')
    parser.add_argument('--disable-subs', action='store_true', help='Disable subtitles')

    # Search options
    parser.add_argument('--language', default='en', help='Language code for subtitle search (default: en)')
    parser.add_argument('--hearing-impaired', action='store_true', help='Search for SDH subtitles')
    parser.add_argument('--forced', action='store_true', help='Search for forced subtitles')

    args = parser.parse_args()

    # Initialize PlexSubSetter
    subsetter = PlexSubSetter(args.baseurl, args.token)

    # Execute requested action
    if args.list_libraries:
        subsetter.list_libraries()
        return

    # Get items from library
    if args.search or args.list_subs or args.set_language or args.set_id or args.disable_subs:
        items = subsetter.get_video_items(args.library, args.type)

        if not items:
            print("No items found in the specified library.")
            return

        print(f"\nFound {len(items)} item(s) to process")

        if args.search:
            subsetter.search_and_download_subtitles(
                items,
                language=args.language,
                hearing_impaired=args.hearing_impaired,
                forced=args.forced
            )
        elif args.list_subs:
            subsetter.list_subtitles(items)
        elif args.set_language:
            subsetter.set_subtitles(items, language=args.set_language)
        elif args.set_id:
            subsetter.set_subtitles(items, subtitle_id=args.set_id)
        elif args.disable_subs:
            subsetter.set_subtitles(items, disable=True)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
