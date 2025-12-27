import os
import re
import shutil
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

# Characters not allowed in filenames
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')


def sanitize_filename(name: str) -> str:
    """Remove or replace characters that are invalid in filenames."""
    if not name:
        return "Unknown"
    # Replace invalid characters with underscore
    sanitized = INVALID_FILENAME_CHARS.sub('_', name)
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(' .')
    # Limit length to avoid path issues
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    return sanitized or "Unknown"


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
                # Fetch image if missing
                if not artist.image_url and artist.musicbrainz_id:
                    image_url = MusicBrainzService.get_artist_image_url(artist.musicbrainz_id)
                    if image_url:
                        artist.image_url = image_url
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
            # Fetch image if missing
            if not artist.image_url and artist.musicbrainz_id:
                image_url = MusicBrainzService.get_artist_image_url(artist.musicbrainz_id)
                if image_url:
                    artist.image_url = image_url
                    self.db.commit()
            return artist

        # Create new artist
        artist = Artist(name=name, musicbrainz_id=musicbrainz_id, sort_name=sort_name)
        self.db.add(artist)
        self.db.commit()
        self.db.refresh(artist)
        
        # Fetch image for new artist
        if artist.musicbrainz_id:
            image_url = MusicBrainzService.get_artist_image_url(artist.musicbrainz_id)
            if image_url:
                artist.image_url = image_url
                self.db.commit()
        
        return artist

    def _is_properly_organized(
        self,
        folder_path: str,
        artist_name: str,
        album_title: str
    ) -> bool:
        """
        Check if a folder is already in the proper Artist/Album structure.
        Returns True if folder matches {music_folder}/{artist}/{album}/
        """
        folder = Path(folder_path)
        music_root = Path(settings.music_folder)
        
        try:
            relative = folder.relative_to(music_root)
            parts = relative.parts
            
            # Should be exactly 2 levels deep: Artist/Album
            if len(parts) != 2:
                return False
            
            expected_artist = sanitize_filename(artist_name)
            expected_album = sanitize_filename(album_title)
            
            # Check if folder names match (case-insensitive)
            return (
                parts[0].lower() == expected_artist.lower() and
                parts[1].lower() == expected_album.lower()
            )
        except ValueError:
            # folder_path is not under music_root
            return False

    def organize_album_folder(
        self,
        current_folder: str,
        artist_name: str,
        album_title: str,
        tracks_info: List[dict]
    ) -> Tuple[str, List[dict]]:
        """
        Organize an album folder into the proper structure:
        {music_folder}/{Artist}/{Album}/{track_number} - {track_title}.ext
        
        Returns (new_folder_path, updated_tracks_info)
        """
        if not artist_name:
            artist_name = "Unknown Artist"
        
        # Check if already organized
        if self._is_properly_organized(current_folder, artist_name, album_title):
            print(f"Album already organized: {album_title}")
            return current_folder, tracks_info
        
        music_root = Path(settings.music_folder)
        safe_artist = sanitize_filename(artist_name)
        safe_album = sanitize_filename(album_title)
        
        # Create target directory
        target_dir = music_root / safe_artist / safe_album
        
        # Check if target already exists
        if target_dir.exists() and target_dir != Path(current_folder):
            # Add a suffix to avoid collision
            counter = 1
            while target_dir.exists():
                target_dir = music_root / safe_artist / f"{safe_album} ({counter})"
                counter += 1
        
        print(f"Organizing: {current_folder} -> {target_dir}")
        
        # Create directory structure
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if we have multiple discs
        disc_numbers = set(t.get("disc_number", 1) for t in tracks_info)
        has_multiple_discs = len(disc_numbers) > 1
        
        # Move and rename each track
        updated_tracks = []
        for track in tracks_info:
            old_path = Path(track["file_path"])
            if not old_path.exists():
                updated_tracks.append(track)
                continue
            
            # Build new filename
            track_num = track.get("track_number")
            disc_num = track.get("disc_number", 1)
            title = sanitize_filename(track.get("title", old_path.stem))
            ext = old_path.suffix.lower()
            
            if track_num:
                if has_multiple_discs:
                    new_name = f"{disc_num}-{track_num:02d} - {title}{ext}"
                else:
                    new_name = f"{track_num:02d} - {title}{ext}"
            else:
                new_name = f"{title}{ext}"
            
            new_path = target_dir / new_name
            
            # Handle filename collision
            if new_path.exists() and new_path != old_path:
                counter = 1
                stem = new_path.stem
                while new_path.exists():
                    new_path = target_dir / f"{stem} ({counter}){ext}"
                    counter += 1
            
            # Move file
            try:
                if old_path != new_path:
                    shutil.move(str(old_path), str(new_path))
                    print(f"  Moved: {old_path.name} -> {new_path.name}")
                
                # Update track info
                updated_track = track.copy()
                updated_track["file_path"] = str(new_path)
                updated_tracks.append(updated_track)
            except Exception as e:
                print(f"  Error moving {old_path}: {e}")
                updated_tracks.append(track)
        
        # Move any remaining files (cover art, etc.)
        current_folder_path = Path(current_folder)
        if current_folder_path.exists():
            for item in current_folder_path.iterdir():
                if item.is_file():
                    target_file = target_dir / item.name
                    if not target_file.exists():
                        try:
                            shutil.move(str(item), str(target_file))
                            print(f"  Moved extra file: {item.name}")
                        except Exception as e:
                            print(f"  Error moving {item}: {e}")
        
        # Remove old folder if empty
        self._remove_empty_folders(current_folder_path)
        
        return str(target_dir), updated_tracks

    def _remove_empty_folders(self, folder: Path):
        """Recursively remove empty folders up to the music root."""
        music_root = Path(settings.music_folder)
        
        current = folder
        while current != music_root and current.exists():
            try:
                # Check if folder is empty (or only contains hidden files like .DS_Store)
                contents = [f for f in current.iterdir() if not f.name.startswith('.')]
                if not contents:
                    # Remove hidden files too
                    for f in current.iterdir():
                        f.unlink()
                    current.rmdir()
                    print(f"  Removed empty folder: {current}")
                    current = current.parent
                else:
                    break
            except Exception as e:
                print(f"  Error removing folder {current}: {e}")
                break

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

        # Use MusicBrainz data for artist/album names if available
        final_artist_name = mb_info.get("artist_name") if mb_info else artist_name
        final_album_title = mb_info.get("title", album_title) if mb_info else album_title

        # Organize the folder structure
        new_folder_path, updated_tracks = self.organize_album_folder(
            folder_path,
            final_artist_name,
            final_album_title,
            tracks_info
        )

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

        # Check if album exists at new path (in case folder was reorganized)
        if new_folder_path != folder_path:
            existing_at_new = self.db.query(Album).filter(
                Album.folder_path == new_folder_path
            ).first()
            if existing_at_new:
                # Update existing album at new location
                album = existing_at_new
            elif existing:
                # Update the existing album's path
                album = existing
                album.folder_path = new_folder_path
            else:
                album = None
        else:
            album = existing

        # Create or update album
        if album:
            album.title = final_album_title
            album.artist_id = artist.id if artist else None
            album.is_owned = True
            album.folder_path = new_folder_path
        else:
            album = Album(
                title=final_album_title,
                folder_path=new_folder_path,
                artist_id=artist.id if artist else None,
                is_owned=True
            )
            self.db.add(album)

        # Update with MusicBrainz info if available
        if mb_info:
            album.musicbrainz_id = mb_info.get("musicbrainz_id")
            album.release_date = mb_info.get("release_date")
            album.release_type = mb_info.get("release_type")
            album.track_count = mb_info.get("track_count") or len(updated_tracks)

            # Set cover art URL - prefer release group (more reliable) over release
            release_group_id = mb_info.get("release_group_id")
            if release_group_id:
                album.cover_art_url = MusicBrainzService.get_release_group_cover_art_url(release_group_id)
            elif album.musicbrainz_id:
                album.cover_art_url = MusicBrainzService.get_cover_art_url(album.musicbrainz_id)
        else:
            album.track_count = len(updated_tracks)

        album.is_scanned = True
        self.db.commit()
        self.db.refresh(album)

        # Create tracks with updated paths
        self._create_tracks(album, updated_tracks)

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
            print(f"Finding album folders in {settings.music_folder}...", flush=True)
            album_folders = self.find_album_folders(settings.music_folder)
            status.total_folders = len(album_folders)
            self.db.commit()
            print(f"Found {len(album_folders)} album folders to scan", flush=True)

            # Scan each folder (this will also organize files)
            scanned_paths = set()
            errors = []
            for i, folder_path in enumerate(album_folders):
                status.current_folder = folder_path
                status.scanned_folders = i + 1
                
                # Commit progress every 10 albums to reduce DB load
                if i % 10 == 0:
                    self.db.commit()
                    print(f"Progress: {i + 1}/{len(album_folders)} - {folder_path}", flush=True)

                try:
                    album = self.scan_album_folder(folder_path, force_rescan)
                    if album and album.folder_path:
                        scanned_paths.add(album.folder_path)
                except Exception as e:
                    import traceback
                    error_msg = f"Error scanning {folder_path}: {e}"
                    print(error_msg, flush=True)
                    print(traceback.format_exc(), flush=True)
                    errors.append(error_msg)
                    # Rollback any failed transaction and continue
                    try:
                        self.db.rollback()
                    except:
                        pass
                    continue
            
            # Store any errors for debugging
            if errors:
                print(f"Completed with {len(errors)} errors", flush=True)
                status.error_message = f"{len(errors)} albums failed to scan. First error: {errors[0][:200]}"

            # Check for albums that no longer exist on disk
            print("Checking for deleted albums...", flush=True)
            owned_albums = self.db.query(Album).filter(
                Album.is_owned == True,
                Album.folder_path.isnot(None)
            ).all()
            
            deleted_count = 0
            for album in owned_albums:
                # Check if folder still exists
                if album.folder_path and not Path(album.folder_path).exists():
                    print(f"Album folder deleted: {album.title} ({album.folder_path})", flush=True)
                    album.is_owned = False
                    album.folder_path = None
                    # Delete associated tracks since files are gone
                    self.db.query(Track).filter(Track.album_id == album.id).delete()
                    deleted_count += 1
            
            if deleted_count > 0:
                self.db.commit()
                print(f"Marked {deleted_count} albums as no longer owned (folders deleted)", flush=True)

            # After scanning owned albums, fetch discographies for all artists
            print("Fetching artist discographies...", flush=True)
            artists = self.db.query(Artist).filter(
                Artist.musicbrainz_id.isnot(None)
            ).all()
            
            for idx, artist in enumerate(artists):
                try:
                    if idx % 10 == 0:
                        print(f"Artist discography progress: {idx + 1}/{len(artists)}", flush=True)
                    # Reset discography_fetched if force_rescan
                    if force_rescan:
                        artist.discography_fetched = False
                        self.db.commit()
                    self.fetch_artist_discography(artist)
                except Exception as e:
                    import traceback
                    print(f"Error fetching discography for {artist.name}: {e}", flush=True)
                    print(traceback.format_exc(), flush=True)
                    try:
                        self.db.rollback()
                    except:
                        pass
                    continue

            status.status = "completed"
            status.completed_at = datetime.utcnow()
            print(f"Scan completed! Scanned {status.scanned_folders} folders.", flush=True)

        except Exception as e:
            import traceback
            print(f"Fatal scan error: {e}", flush=True)
            print(traceback.format_exc(), flush=True)
            status.status = "error"
            status.error_message = str(e)[:500]
            status.completed_at = datetime.utcnow()

        self.db.commit()
        return status
