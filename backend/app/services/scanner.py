import os
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4

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

    def get_or_create_artist(self, name: str, musicbrainz_id: Optional[str] = None) -> Artist:
        """Get an existing artist or create a new one."""
        if musicbrainz_id:
            artist = self.db.query(Artist).filter(
                Artist.musicbrainz_id == musicbrainz_id
            ).first()
            if artist:
                return artist

        # Try to find by name
        artist = self.db.query(Artist).filter(Artist.name == name).first()
        if artist:
            return artist

        # Create new artist
        artist = Artist(name=name, musicbrainz_id=musicbrainz_id)
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
                mb_info.get("artist_musicbrainz_id")
            )
            # Update artist with additional info if available
            if mb_info.get("artist_sort_name") and not artist.sort_name:
                artist.sort_name = mb_info["artist_sort_name"]
                self.db.commit()
        elif artist_name:
            artist = self.get_or_create_artist(artist_name)

        # Create or update album
        if existing:
            album = existing
            album.title = mb_info.get("title", album_title) if mb_info else album_title
            album.artist_id = artist.id if artist else None
        else:
            album = Album(
                title=mb_info.get("title", album_title) if mb_info else album_title,
                folder_path=folder_path,
                artist_id=artist.id if artist else None
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

            status.status = "completed"
            status.completed_at = datetime.utcnow()

        except Exception as e:
            status.status = "error"
            status.error_message = str(e)
            status.completed_at = datetime.utcnow()

        self.db.commit()
        return status

