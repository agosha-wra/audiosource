import musicbrainzngs
import time
from typing import Optional, Dict, Any
from app.config import get_settings

settings = get_settings()

# Initialize MusicBrainz client
musicbrainzngs.set_useragent(
    settings.musicbrainz_app_name,
    settings.musicbrainz_app_version,
    settings.musicbrainz_contact
)


class MusicBrainzService:
    """Service for interacting with the MusicBrainz API."""

    # Rate limiting: MusicBrainz allows 1 request per second
    _last_request_time: float = 0
    _min_request_interval: float = 1.1  # Slightly more than 1 second

    @classmethod
    def _rate_limit(cls):
        """Ensure we don't exceed rate limits."""
        elapsed = time.time() - cls._last_request_time
        if elapsed < cls._min_request_interval:
            time.sleep(cls._min_request_interval - elapsed)
        cls._last_request_time = time.time()

    @classmethod
    def search_release(
        cls,
        album_title: str,
        artist_name: Optional[str] = None,
        limit: int = 5
    ) -> Optional[Dict[str, Any]]:
        """
        Search for a release (album) in MusicBrainz.
        Returns the best matching release or None.
        """
        cls._rate_limit()

        try:
            query = f'release:"{album_title}"'
            if artist_name:
                query += f' AND artist:"{artist_name}"'

            result = musicbrainzngs.search_releases(
                query=query,
                limit=limit
            )

            releases = result.get("release-list", [])
            if not releases:
                return None

            # Return the first (best) match
            return releases[0]

        except Exception as e:
            print(f"MusicBrainz search error: {e}")
            return None

    @classmethod
    def get_release_details(cls, musicbrainz_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific release."""
        cls._rate_limit()

        try:
            result = musicbrainzngs.get_release_by_id(
                musicbrainz_id,
                includes=["artists", "recordings", "release-groups"]
            )
            return result.get("release")
        except Exception as e:
            print(f"MusicBrainz get release error: {e}")
            return None

    @classmethod
    def get_cover_art_url(cls, musicbrainz_id: str) -> Optional[str]:
        """Get the cover art URL for a release."""
        # Cover Art Archive URL format
        return f"https://coverartarchive.org/release/{musicbrainz_id}/front-250"

    @classmethod
    def search_artist(cls, artist_name: str) -> Optional[Dict[str, Any]]:
        """Search for an artist in MusicBrainz."""
        cls._rate_limit()

        try:
            result = musicbrainzngs.search_artists(
                artist=artist_name,
                limit=5
            )
            artists = result.get("artist-list", [])
            if not artists:
                return None
            return artists[0]
        except Exception as e:
            print(f"MusicBrainz artist search error: {e}")
            return None

    @classmethod
    def extract_release_info(cls, release: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant information from a MusicBrainz release."""
        info = {
            "musicbrainz_id": release.get("id"),
            "title": release.get("title"),
            "release_date": release.get("date"),
            "country": release.get("country"),
            "status": release.get("status"),
        }

        # Extract artist info
        artist_credit = release.get("artist-credit", [])
        if artist_credit:
            first_artist = artist_credit[0]
            if isinstance(first_artist, dict):
                artist = first_artist.get("artist", first_artist)
                info["artist_name"] = artist.get("name")
                info["artist_musicbrainz_id"] = artist.get("id")
                info["artist_sort_name"] = artist.get("sort-name")

        # Extract release group info (for album type)
        release_group = release.get("release-group", {})
        if release_group:
            info["release_type"] = release_group.get("primary-type", "Album")

        # Track count from medium list
        medium_list = release.get("medium-list", [])
        track_count = sum(
            int(medium.get("track-count", 0))
            for medium in medium_list
        )
        info["track_count"] = track_count if track_count > 0 else None

        return info

