import os
from pathlib import Path
from typing import List, Optional, Tuple, Set
from datetime import datetime
from sqlalchemy.orm import Session
from mutagen import File as MutagenFile

from app.models import Album, Artist, Track, ScanStatus
from app.services.musicbrainz import MusicBrainzService
from app.config import get_settings

settings = get_settings()

# Supported audio file extensions
AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav", ".wma", ".aiff"}


class ScannerService:
    """Service for scanning music folders and populating the database."""

    def __init__(self, db: Session):
        self.db = db

    def get_or_create_scan_status(self) -> ScanStatus:
        """Get or create the scan status record."""
        status = self.db.query(ScanStatus).first()
        if not status:
            status = ScanStatus(status="idle")
            self.db.add(status)
            self.db.commit()
            self.db.refresh(status)
        return status

    def find_album_folders(self, root_path: str) -> List[str]:
        """
        Find all folders that contain audio files (potential albums).
        Returns a list of folder paths.
        """
        album_folders = []
        root = Path(root_path)

        if not root.exists():
            return album_folders

        for dirpath, dirnames, filenames in os.walk(root):
            # Check if this directory contains audio files
            has_audio = any(
                Path(f).suffix.lower() in AUDIO_EXTENSIONS
                for f in filenames
            )
            if has_audio:
                album_folders.append(dirpath)

        return album_folders

    def extract_metadata_from_files(
        self, folder_path: str
    ) -> Tuple[Optional[str], Optional[str], List[dict]]:
        """
        Extract album and artist info from audio files in a folder.
        Returns (album_title, artist_name, tracks_info).
        """
        tracks_info = []
        album_titles = []
        artist_names = []

        folder = Path(folder_path)
        audio_files = [
            f for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
        ]

        for audio_file in sorted(audio_files):
            try:
                track_info = self._extract_track_metadata(audio_file)
                if track_info:
                    tracks_info.append(track_info)
                    if track_info.get("album"):
                        album_titles.append(track_info["album"])
                    if track_info.get("artist"):
                        artist_names.append(track_info["artist"])
            except Exception as e:
                print(f"Error reading {audio_file}: {e}")
                # Still add the file with minimal info
                tracks_info.append({
                    "title": audio_file.stem,
                    "file_path": str(audio_file),
                    "file_format": audio_file.suffix.lstrip(".").upper()
                })

        # Use most common album/artist name, or folder name as fallback
        album_title = max(set(album_titles), key=album_titles.count) if album_titles else folder.name
        artist_name = max(set(artist_names), key=artist_names.count) if artist_names else None

        return album_title, artist_name, tracks_info

    def _extract_track_metadata(self, file_path: Path) -> Optional[dict]:
        """Extract metadata from a single audio file."""
        try:
            audio = MutagenFile(file_path, easy=True)
            if audio is None:
                return None

            # Get duration
            duration = None
            raw_audio = MutagenFile(file_path)
            if raw_audio and hasattr(raw_audio.info, "length"):
                duration = int(raw_audio.info.length)

            # Handle different formats
            if isinstance(audio, dict) or hasattr(audio, "get"):
                return {
                    "title": self._get_tag(audio, "title", file_path.stem),
                    "album": self._get_tag(audio, "album"),
                    "artist": self._get_tag(audio, "artist"),
                    "track_number": self._parse_track_number(self._get_tag(audio, "tracknumber")),
                    "disc_number": self._parse_track_number(self._get_tag(audio, "discnumber")) or 1,
                    "duration_seconds": duration,
                    "file_path": str(file_path),
                    "file_format": file_path.suffix.lstrip(".").upper()
                }
        except Exception as e:
            print(f"Error extracting metadata from {file_path}: {e}")
            return None

    def _get_tag(self, audio, tag_name: str, default: str = None) -> Optional[str]:
        """Safely get a tag value from audio metadata."""
        try:
            value = audio.get(tag_name)
            if value:
                return value[0] if isinstance(value, list) else str(value)
        except (KeyError, IndexError, TypeError):
            pass
        return default

    def _parse_track_number(self, value: Optional[str]) -> Optional[int]:
        """Parse track number from various formats (e.g., '1', '1/12', '01')."""
        if not value:
            return None
        try:
            # Handle "1/12" format
            if "/" in str(value):
                value = str(value).split("/")[0]
            return int(value)
        except (ValueError, TypeError):
            return None

    def get_or_create_artist(
        self, 
        name: str, 
        musicbrainz_id: Optional[str] = None,
        sort_name: Optional[str] = None
    ) -> Artist:
        """Get an existing artist or create a new one."""
        if musicbrainz_id:
            artist = self.db.query(Artist).filter(
                Artist.musicbrainz_id == musicbrainz_id
            ).first()
            if artist:
                # Update sort_name if we have it and artist doesn't
                if sort_name and not artist.sort_name:
                    artist.sort_name = sort_name
                    self.db.commit()
                return artist

        # Try to find by name
        artist = self.db.query(Artist).filter(Artist.name == name).first()
        if artist:
            # Update musicbrainz_id if we have it and artist doesn't
            if musicbrainz_id and not artist.musicbrainz_id:
                artist.musicbrainz_id = musicbrainz_id
                if sort_name and not artist.sort_name:
                    artist.sort_name = sort_name
                self.db.commit()
            return artist

        # Create new artist
        artist = Artist(name=name, musicbrainz_id=musicbrainz_id, sort_name=sort_name)
        self.db.add(artist)
        self.db.commit()
        self.db.refresh(artist)
        return artist

    def scan_album_folder(self, folder_path: str, force_rescan: bool = False) -> Optional[Album]:
        """Scan a single album folder and create/update database records."""
        # Check if album already exists
        existing = self.db.query(Album).filter(Album.folder_path == folder_path).first()
        if existing and existing.is_scanned and not force_rescan:
            return existing

        # Extract metadata from files
        album_title, artist_name, tracks_info = self.extract_metadata_from_files(folder_path)

        # Search MusicBrainz for additional info
        mb_info = None
        if album_title:
            mb_release = MusicBrainzService.search_release(album_title, artist_name)
            if mb_release:
                mb_info = MusicBrainzService.extract_release_info(mb_release)

        # Determine artist
        artist = None
        if mb_info and mb_info.get("artist_name"):
            artist = self.get_or_create_artist(
                mb_info["artist_name"],
                mb_info.get("artist_musicbrainz_id"),
                mb_info.get("artist_sort_name")
            )
        elif artist_name:
            artist = self.get_or_create_artist(artist_name)

        # Create or update album
        if existing:
            album = existing
            album.title = mb_info.get("title", album_title) if mb_info else album_title
            album.artist_id = artist.id if artist else None
            album.is_owned = True
        else:
            album = Album(
                title=mb_info.get("title", album_title) if mb_info else album_title,
                folder_path=folder_path,
                artist_id=artist.id if artist else None,
                is_owned=True
            )
            self.db.add(album)

        # Update with MusicBrainz info if available
        if mb_info:
            album.musicbrainz_id = mb_info.get("musicbrainz_id")
            album.release_date = mb_info.get("release_date")
            album.release_type = mb_info.get("release_type")
            album.track_count = mb_info.get("track_count") or len(tracks_info)

            # Set cover art URL
            if album.musicbrainz_id:
                album.cover_art_url = MusicBrainzService.get_cover_art_url(album.musicbrainz_id)
        else:
            album.track_count = len(tracks_info)

        album.is_scanned = True
        self.db.commit()
        self.db.refresh(album)

        # Create tracks
        self._create_tracks(album, tracks_info)

        return album

    def _create_tracks(self, album: Album, tracks_info: List[dict]):
        """Create track records for an album."""
        # Remove existing tracks if any
        self.db.query(Track).filter(Track.album_id == album.id).delete()

        for track_info in tracks_info:
            track = Track(
                title=track_info.get("title", "Unknown"),
                album_id=album.id,
                track_number=track_info.get("track_number"),
                disc_number=track_info.get("disc_number", 1),
                duration_seconds=track_info.get("duration_seconds"),
                file_path=track_info.get("file_path"),
                file_format=track_info.get("file_format")
            )
            self.db.add(track)

        self.db.commit()

    def fetch_artist_discography(self, artist: Artist) -> int:
        """
        Fetch all albums by an artist from MusicBrainz and add missing ones.
        Returns the number of missing albums added.
        """
        if not artist.musicbrainz_id:
            print(f"Artist {artist.name} has no MusicBrainz ID, skipping discography fetch")
            return 0

        # Skip if we've already fetched the discography recently
        if artist.discography_fetched:
            return 0

        print(f"Fetching discography for {artist.name}...")
        
        # Get all release groups from MusicBrainz
        releases = MusicBrainzService.get_artist_releases(artist.musicbrainz_id)
        
        if not releases:
            print(f"No releases found for {artist.name}")
            artist.discography_fetched = True
            self.db.commit()
            return 0

        # Get existing album MusicBrainz IDs for this artist
        existing_mb_ids: Set[str] = set()
        for album in self.db.query(Album).filter(Album.artist_id == artist.id).all():
            if album.musicbrainz_id:
                existing_mb_ids.add(album.musicbrainz_id)

        # Also check by title to avoid duplicates
        existing_titles: Set[str] = set()
        for album in self.db.query(Album).filter(Album.artist_id == artist.id).all():
            existing_titles.add(album.title.lower())

        missing_count = 0
        for release in releases:
            mb_id = release.get("musicbrainz_id")
            title = release.get("title", "")
            
            # Skip if we already have this album (by MB ID or title)
            if mb_id in existing_mb_ids:
                continue
            if title.lower() in existing_titles:
                continue

            # Create missing album entry
            missing_album = Album(
                title=title,
                musicbrainz_id=mb_id,
                artist_id=artist.id,
                release_date=release.get("release_date"),
                release_type=release.get("release_type"),
                cover_art_url=release.get("cover_art_url"),
                folder_path=None,  # No local folder
                is_owned=False,  # We don't have this album
                is_scanned=True  # No need to scan, it's from MusicBrainz
            )
            self.db.add(missing_album)
            existing_mb_ids.add(mb_id)
            existing_titles.add(title.lower())
            missing_count += 1

        artist.discography_fetched = True
        self.db.commit()
        
        print(f"Added {missing_count} missing albums for {artist.name}")
        return missing_count

    def scan_library(self, force_rescan: bool = False) -> ScanStatus:
        """Scan the entire music library."""
        status = self.get_or_create_scan_status()

        # Check if scan is already running
        if status.status == "scanning":
            return status

        # Start scanning
        status.status = "scanning"
        status.started_at = datetime.utcnow()
        status.completed_at = None
        status.error_message = None
        status.scanned_folders = 0
        self.db.commit()

        try:
            # Find all album folders
            album_folders = self.find_album_folders(settings.music_folder)
            status.total_folders = len(album_folders)
            self.db.commit()

            # Scan each folder
            for i, folder_path in enumerate(album_folders):
                status.current_folder = folder_path
                status.scanned_folders = i + 1
                self.db.commit()

                try:
                    self.scan_album_folder(folder_path, force_rescan)
                except Exception as e:
                    print(f"Error scanning {folder_path}: {e}")
                    continue

            # After scanning owned albums, fetch discographies for all artists
            print("Fetching artist discographies...")
            artists = self.db.query(Artist).filter(
                Artist.musicbrainz_id.isnot(None)
            ).all()
            
            for artist in artists:
                try:
                    # Reset discography_fetched if force_rescan
                    if force_rescan:
                        artist.discography_fetched = False
                        self.db.commit()
                    self.fetch_artist_discography(artist)
                except Exception as e:
                    print(f"Error fetching discography for {artist.name}: {e}")
                    continue

            status.status = "completed"
            status.completed_at = datetime.utcnow()

        except Exception as e:
            status.status = "error"
            status.error_message = str(e)
            status.completed_at = datetime.utcnow()

        self.db.commit()
        return status
