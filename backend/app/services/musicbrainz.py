import musicbrainzngs
import time
import requests
from datetime import datetime, date
from typing import Optional, Dict, Any, List
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
    def search_releases_multi(
        cls,
        query: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search for releases in MusicBrainz and return multiple results.
        Used for the search feature.
        """
        cls._rate_limit()

        try:
            result = musicbrainzngs.search_release_groups(
                query=query,
                limit=limit
            )

            release_groups = result.get("release-group-list", [])
            results = []
            
            for rg in release_groups:
                # Extract artist info
                artist_credit = rg.get("artist-credit", [])
                artist_name = None
                artist_mbid = None
                if artist_credit:
                    first_artist = artist_credit[0]
                    if isinstance(first_artist, dict):
                        artist = first_artist.get("artist", first_artist)
                        artist_name = artist.get("name")
                        artist_mbid = artist.get("id")
                
                rg_id = rg.get("id")
                results.append({
                    "musicbrainz_id": rg_id,
                    "title": rg.get("title"),
                    "artist_name": artist_name,
                    "artist_musicbrainz_id": artist_mbid,
                    "release_date": rg.get("first-release-date", ""),
                    "release_type": rg.get("primary-type", "Album"),
                    "cover_art_url": cls.get_release_group_cover_art_url(rg_id) if rg_id else None,
                })
            
            return results

        except Exception as e:
            print(f"MusicBrainz search error: {e}")
            return []

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
    def get_release_group_cover_art_url(cls, release_group_id: str) -> Optional[str]:
        """Get the cover art URL for a release group."""
        return f"https://coverartarchive.org/release-group/{release_group_id}/front-250"

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
    def get_artist_releases(
        cls,
        artist_musicbrainz_id: str,
        release_types: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all release groups (albums) by an artist from MusicBrainz.
        
        Args:
            artist_musicbrainz_id: The MusicBrainz ID of the artist
            release_types: List of release types to include (e.g., ["album", "ep"])
                          If None, defaults to ["album", "ep"]
        
        Returns:
            List of release group information dictionaries
        """
        if release_types is None:
            release_types = ["album", "ep"]
        
        all_releases = []
        offset = 0
        limit = 100  # Max allowed by MusicBrainz
        
        while True:
            cls._rate_limit()
            
            try:
                result = musicbrainzngs.browse_release_groups(
                    artist=artist_musicbrainz_id,
                    release_type=release_types,
                    limit=limit,
                    offset=offset
                )
                
                release_groups = result.get("release-group-list", [])
                if not release_groups:
                    break
                
                for rg in release_groups:
                    release_info = cls._extract_release_group_info(rg)
                    if release_info:
                        all_releases.append(release_info)
                
                # Check if we've fetched all releases
                total = int(result.get("release-group-count", 0))
                offset += len(release_groups)
                
                if offset >= total:
                    break
                    
            except Exception as e:
                print(f"MusicBrainz get artist releases error: {e}")
                break
        
        return all_releases

    @classmethod
    def _extract_release_group_info(cls, release_group: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract information from a release group."""
        try:
            rg_id = release_group.get("id")
            title = release_group.get("title")
            
            if not rg_id or not title:
                return None
            
            # Get the primary type (Album, EP, Single, etc.)
            primary_type = release_group.get("primary-type", "Album")
            
            # Get first release date
            first_release_date = release_group.get("first-release-date", "")
            
            return {
                "musicbrainz_id": rg_id,
                "title": title,
                "release_type": primary_type,
                "release_date": first_release_date,
                "cover_art_url": cls.get_release_group_cover_art_url(rg_id),
            }
        except Exception as e:
            print(f"Error extracting release group info: {e}")
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
            info["release_group_id"] = release_group.get("id")

        # Track count from medium list
        medium_list = release.get("medium-list", [])
        track_count = sum(
            int(medium.get("track-count", 0))
            for medium in medium_list
        )
        info["track_count"] = track_count if track_count > 0 else None

        return info

    @classmethod
    def get_artist_image_url(cls, musicbrainz_id: str) -> Optional[str]:
        """
        Get artist image URL. Tries multiple sources:
        1. Fanart.tv (if API key is set)
        2. Wikidata/Wikipedia via MusicBrainz relations
        """
        import os
        
        # Try Fanart.tv first if API key is available
        api_key = os.environ.get("FANART_TV_API_KEY", "")
        if api_key:
            try:
                url = f"https://webservice.fanart.tv/v3/music/{musicbrainz_id}?api_key={api_key}"
                response = requests.get(url, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    thumbs = data.get("artistthumb", [])
                    if thumbs:
                        return thumbs[0].get("url")
                    backgrounds = data.get("artistbackground", [])
                    if backgrounds:
                        return backgrounds[0].get("url")
            except Exception as e:
                print(f"Error fetching from Fanart.tv: {e}")
        
        # Fallback: Try to get image from Wikidata via MusicBrainz
        try:
            # Get artist info with URL relations
            cls._rate_limit()
            result = musicbrainzngs.get_artist_by_id(
                musicbrainz_id,
                includes=["url-rels"]
            )
            
            artist = result.get("artist", {})
            url_relations = artist.get("url-relation-list", [])
            
            # Look for Wikidata URL
            wikidata_id = None
            for rel in url_relations:
                rel_type = rel.get("type", "")
                url = rel.get("target", "")
                if "wikidata" in rel_type or "wikidata.org" in url:
                    # Extract Q-ID from URL like https://www.wikidata.org/wiki/Q123
                    wikidata_id = url.split("/")[-1]
                    break
            
            if wikidata_id:
                # Query Wikidata for image
                wikidata_url = f"https://www.wikidata.org/wiki/Special:EntityData/{wikidata_id}.json"
                headers = {"User-Agent": "AudioSource/1.0 (https://github.com/audiosource)"}
                response = requests.get(wikidata_url, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    entity = data.get("entities", {}).get(wikidata_id, {})
                    claims = entity.get("claims", {})
                    
                    # P18 is the property for "image"
                    if "P18" in claims:
                        image_claim = claims["P18"][0]
                        image_name = image_claim.get("mainsnak", {}).get("datavalue", {}).get("value", "")
                        if image_name:
                            # Convert to Wikimedia Commons URL
                            image_name_encoded = image_name.replace(" ", "_")
                            # Use MD5 hash for path
                            import hashlib
                            md5 = hashlib.md5(image_name_encoded.encode()).hexdigest()
                            image_url = f"https://upload.wikimedia.org/wikipedia/commons/{md5[0]}/{md5[0:2]}/{image_name_encoded}"
                            return image_url
                            
        except Exception as e:
            print(f"Error fetching from Wikidata: {e}")
        
        return None

    @classmethod
    def get_upcoming_releases(
        cls,
        artist_musicbrainz_id: str,
        release_types: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get upcoming (future) releases for an artist.
        
        Args:
            artist_musicbrainz_id: The MusicBrainz ID of the artist
            release_types: List of release types to include
        
        Returns:
            List of upcoming release information dictionaries
        """
        if release_types is None:
            release_types = ["album", "ep"]
        
        today = date.today().isoformat()
        upcoming = []
        
        # Get all releases and filter for future ones
        all_releases = cls.get_artist_releases(artist_musicbrainz_id, release_types)
        
        for release in all_releases:
            release_date = release.get("release_date", "")
            if release_date and release_date > today:
                upcoming.append(release)
        
        # Sort by release date
        upcoming.sort(key=lambda x: x.get("release_date", ""))
        
        return upcoming
