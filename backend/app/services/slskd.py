"""
slskd integration service for downloading albums from Soulseek.
Based on the slskd API: https://github.com/slskd/slskd
"""

import os
import re
import time
import shutil
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.models import Download, Album, Artist
from app.config import get_settings
from app.services.beets_service import BeetsService


class SlskdConfig:
    """Configuration for slskd integration."""
    
    def __init__(self):
        self.enabled = os.environ.get("SLSKD_ENABLED", "false").lower() == "true"
        self.url = os.environ.get("SLSKD_URL", "http://localhost:5030").rstrip("/")
        self.api_key = os.environ.get("SLSKD_API_KEY", "")
        self.download_dir = os.environ.get("SLSKD_DOWNLOAD_DIR", "/downloads")
    
    def is_configured(self) -> bool:
        """Check if slskd is properly configured."""
        return self.enabled and bool(self.url) and bool(self.api_key)


slskd_config = SlskdConfig()


class SlskdClient:
    """Client for interacting with slskd API."""
    
    def __init__(self):
        self.config = slskd_config
        self.session = requests.Session()
        if self.config.api_key:
            self.session.headers.update({"X-API-Key": self.config.api_key})
    
    def is_available(self) -> bool:
        """Check if slskd is available and responding."""
        if not self.config.is_configured():
            return False
        try:
            response = self.session.get(f"{self.config.url}/api/v0/application", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    def search(self, query: str, timeout: int = 45) -> Optional[str]:
        """
        Start a search and return the search ID.
        Returns None if the search couldn't be started.
        """
        try:
            print(f"slskd: Starting search for '{query}'")
            response = self.session.post(
                f"{self.config.url}/api/v0/searches",
                json={"searchText": query, "timeout": timeout * 1000},
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                search_data = response.json()
                search_id = search_data.get("id")
                print(f"slskd: Search started with ID: {search_id}")
                return search_id
            else:
                print(f"slskd: Failed to start search: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"slskd: Error starting search: {e}")
            return None
    
    def get_search_status(self, search_id: str) -> Dict[str, Any]:
        """Get the status of a search."""
        try:
            response = self.session.get(
                f"{self.config.url}/api/v0/searches/{search_id}",
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            print(f"slskd: Error getting search status: {e}")
            return {}
    
    def get_search_responses(self, search_id: str) -> List[Dict[str, Any]]:
        """Get all responses from a completed search."""
        try:
            all_responses = []
            page = 0
            page_size = 100
            
            while True:
                response = self.session.get(
                    f"{self.config.url}/api/v0/searches/{search_id}/responses",
                    params={"pageIndex": page, "pageSize": page_size},
                    timeout=30
                )
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                
                if isinstance(data, list):
                    responses = data
                elif isinstance(data, dict):
                    responses = data.get("responses", data.get("data", []))
                else:
                    break
                
                if not responses:
                    break
                
                all_responses.extend(responses)
                
                if len(responses) < page_size:
                    break
                
                page += 1
                if page > 20:  # Safety limit
                    break
            
            return all_responses
            
        except Exception as e:
            print(f"slskd: Error getting search responses: {e}")
            return []
    
    def wait_for_search(self, search_id: str, timeout: int = 45) -> List[Dict[str, Any]]:
        """Wait for a search to complete and return results."""
        start_time = time.time()
        min_wait = 10  # Wait at least 10 seconds for results
        
        while time.time() - start_time < timeout:
            status = self.get_search_status(search_id)
            is_complete = status.get("isComplete", False)
            response_count = status.get("responseCount", 0)
            elapsed = int(time.time() - start_time)
            
            # If we have responses and waited minimum time, fetch them
            if response_count > 0 and elapsed >= min_wait:
                responses = self.get_search_responses(search_id)
                if responses:
                    return responses
            
            if is_complete:
                return self.get_search_responses(search_id)
            
            time.sleep(2)
        
        # Timeout - try to get whatever we have
        return self.get_search_responses(search_id)
    
    def download_files(self, username: str, files: List[Dict[str, Any]]) -> bool:
        """
        Queue files for download from a user.
        files should be a list of dicts with 'filename' and 'size' keys.
        """
        try:
            print(f"slskd: Downloading {len(files)} files from {username}")
            
            files_to_download = [
                {"filename": f.get("filename"), "size": f.get("size", 0)}
                for f in files
            ]
            
            response = self.session.post(
                f"{self.config.url}/api/v0/transfers/downloads/{username}",
                json=files_to_download,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                print(f"slskd: Download started successfully")
                return True
            else:
                print(f"slskd: Download failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"slskd: Error downloading files: {e}")
            return False
    
    def get_downloads(self) -> List[Dict[str, Any]]:
        """Get all current downloads."""
        try:
            response = self.session.get(
                f"{self.config.url}/api/v0/transfers/downloads",
                timeout=30
            )
            if response.status_code == 200:
                return response.json()
            return []
        except Exception as e:
            print(f"slskd: Error getting downloads: {e}")
            return []


class SlskdService:
    """Service for managing slskd downloads."""
    
    def __init__(self, db: Session):
        self.db = db
        self.client = SlskdClient()
    
    def is_available(self) -> bool:
        """Check if slskd is configured and available."""
        return self.client.is_available()
    
    def search_and_download_album(self, download_id: int) -> Optional[Download]:
        """
        Search for an album on Soulseek and start downloading.
        Uses an existing Download record (created by the API endpoint).
        Returns the Download record or None if failed.
        """
        # Get the existing download record
        download = self.db.query(Download).filter(Download.id == download_id).first()
        if not download:
            print(f"slskd: Download record {download_id} not found")
            return None
        
        # Get album info
        album = self.db.query(Album).filter(Album.id == download.album_id).first()
        if not album:
            download.status = "failed"
            download.error_message = "Album not found in database"
            self.db.commit()
            return download
        
        # Clean up files from any previous failed/cancelled/pending downloads for this album
        previous_downloads = self.db.query(Download).filter(
            Download.album_id == download.album_id,
            Download.id != download.id,
            Download.status.in_(["failed", "cancelled", "pending", "searching", "downloading"])
        ).all()
        for prev_download in previous_downloads:
            self._cleanup_download_files(prev_download)
        
        artist_name = album.artist.name if album.artist else "Unknown Artist"
        album_title = album.title
        
        # Fetch track count from MusicBrainz if missing
        if not album.track_count and album.musicbrainz_id:
            from app.services.musicbrainz import MusicBrainzService
            print(f"slskd: Fetching track count from MusicBrainz for {album_title}...")
            track_count = MusicBrainzService.get_release_group_track_count(album.musicbrainz_id)
            if track_count:
                album.track_count = track_count
                self.db.commit()
                print(f"slskd: Found {track_count} tracks for {album_title}")
        
        expected_tracks = album.track_count or 0
        
        # Extract year from release_date for self-titled albums
        release_year = None
        if album.release_date:
            year_match = re.search(r'\b(19|20)\d{2}\b', album.release_date)
            if year_match:
                release_year = year_match.group(0)
        
        # Check if it's a self-titled album
        is_self_titled = artist_name.lower().strip() == album_title.lower().strip()
        
        # Update download to searching status
        download.status = "searching"
        download.artist_name = artist_name
        download.album_title = album_title
        self.db.commit()
        
        try:
            # Search for the album
            # For self-titled albums, include year if available to disambiguate
            if is_self_titled and release_year:
                print(f"slskd: Self-titled album detected, using year {release_year} in search")
                search_queries = [
                    f'"{artist_name}" "{album_title}" {release_year}',
                    f'{artist_name} {album_title} {release_year}',
                    f'{artist_name} - {album_title} {release_year}',
                    f'"{artist_name}" "{album_title}"',  # Fallback without year
                ]
            else:
                search_queries = [
                    f'"{artist_name}" "{album_title}"',
                    f'{artist_name} {album_title}',
                    f'{artist_name} - {album_title}',
                ]
            
            all_candidates = []
            
            for query in search_queries:
                search_id = self.client.search(query)
                if not search_id:
                    continue
                
                responses = self.client.wait_for_search(search_id, timeout=45)
                
                for response in responses:
                    username = response.get("username", "")
                    files = response.get("files", [])
                    
                    # Find matching audio files grouped by folder
                    folders = self._find_matching_files_by_folder(
                        files, artist_name, album_title
                    )
                    
                    # Score each folder separately and add as individual candidates
                    for folder_path, folder_files in folders.items():
                        if folder_files:
                            score = self._calculate_score(
                                folder_files, artist_name, album_title, expected_tracks
                            )
                            
                            if score > 0:
                                all_candidates.append({
                                    "username": username,
                                    "folder": folder_path,
                                    "files": folder_files,
                                    "score": score,
                                    "track_count": len(folder_files)
                                })
                
                # If we have good candidates, stop searching
                if len(all_candidates) >= 5:
                    break
            
            if not all_candidates:
                download.status = "failed"
                download.error_message = "No suitable sources found"
                self.db.commit()
                return download
            
            # Sort by score and try to download from best candidate (single folder)
            all_candidates.sort(key=lambda x: x["score"], reverse=True)
            
            print(f"slskd: Found {len(all_candidates)} candidate folders")
            for i, c in enumerate(all_candidates[:5]):
                print(f"slskd:   #{i+1} score={c['score']} tracks={c['track_count']} user={c['username']} folder={c.get('folder', 'unknown')}")
            
            # Only try the single best candidate
            best = all_candidates[0]
            print(f"slskd: Downloading from best candidate: {best['username']} - {best.get('folder', 'unknown')} (score={best['score']}, {best['track_count']} tracks)")
            
            if self.client.download_files(best["username"], best["files"]):
                download.status = "downloading"
                download.slskd_username = best["username"]
                download.slskd_remote_folder = best.get("folder") or None
                download.local_folder_path = None
                download.total_files = len(best["files"])
                download.total_bytes = sum(f.get("size", 0) for f in best["files"])
                download.started_at = datetime.utcnow()
                self.db.commit()
                return download
            
            download.status = "failed"
            download.error_message = "Failed to start download from any source"
            self.db.commit()
            return download
            
        except Exception as e:
            download.status = "failed"
            download.error_message = str(e)
            self.db.commit()
            print(f"slskd: Error searching/downloading: {e}")
            return download
    
    def _get_folder_path(self, filename: str) -> str:
        """Extract the folder path from a full file path."""
        # Handle both forward and backslashes
        if '\\' in filename:
            parts = filename.rsplit('\\', 1)
        else:
            parts = filename.rsplit('/', 1)
        return parts[0] if len(parts) > 1 else ""
    
    def _find_matching_files_by_folder(
        self,
        files: List[Dict],
        artist_name: str,
        album_title: str
    ) -> Dict[str, List[Dict]]:
        """Find audio files that match the artist/album, grouped by folder."""
        folders: Dict[str, List[Dict]] = {}
        
        artist_words = [w.lower() for w in artist_name.split() if len(w) > 2]
        title_words = [w.lower() for w in album_title.split() if len(w) > 2]
        
        for file_info in files:
            filename = file_info.get("filename", "").lower()
            
            # Check if it's an audio file (prefer MP3, exclude FLAC for size)
            if any(ext in filename for ext in [".mp3", ".m4a", ".ogg"]):
                artist_match = any(w in filename for w in artist_words)
                title_match = any(w in filename for w in title_words)
                
                if artist_match or title_match:
                    folder = self._get_folder_path(file_info.get("filename", ""))
                    if folder not in folders:
                        folders[folder] = []
                    folders[folder].append({
                        **file_info,
                        "artist_match": artist_match,
                        "title_match": title_match
                    })
        
        return folders
    
    def _find_matching_files(
        self,
        files: List[Dict],
        artist_name: str,
        album_title: str
    ) -> List[Dict]:
        """Find audio files that match the artist/album - returns best folder only."""
        # Group by folder first
        folders = self._find_matching_files_by_folder(files, artist_name, album_title)
        
        if not folders:
            return []
        
        # Return the folder with the most files (as a heuristic for "complete album")
        best_folder = max(folders.keys(), key=lambda f: len(folders[f]))
        return folders[best_folder]
    
    def _calculate_score(
        self,
        files: List[Dict],
        artist_name: str,
        album_title: str,
        expected_tracks: int
    ) -> int:
        """Calculate a quality score for a set of files."""
        if not files:
            return 0
        
        score = 0
        num_tracks = len(files)
        
        # Track count matching
        if expected_tracks > 0:
            track_diff = abs(num_tracks - expected_tracks)
            if track_diff == 0:
                score += 50
            elif track_diff <= 1:
                score += 35
            elif track_diff <= 2:
                score += 25
            elif track_diff <= 5:
                score += 10
            else:
                score -= 10
        else:
            score += min(num_tracks, 20)
        
        # Match quality
        both_matches = sum(1 for f in files if f.get("artist_match") and f.get("title_match"))
        artist_only = sum(1 for f in files if f.get("artist_match") and not f.get("title_match"))
        
        score += both_matches * 5
        score += artist_only * 3
        
        # File format bonus
        mp3_files = sum(1 for f in files if ".mp3" in f.get("filename", "").lower())
        if mp3_files > num_tracks * 0.8:
            score += 10
        
        # Reasonable file sizes (6-15MB for MP3 320)
        good_sizes = sum(
            1 for f in files
            if 6_000_000 <= f.get("size", 0) <= 15_000_000
        )
        if good_sizes == num_tracks:
            score += 8
        
        # Penalty for too few tracks
        if num_tracks < 3:
            score -= 15
        elif num_tracks < 5:
            score -= 5
        
        # Penalty for duplicate-pattern filenames (e.g., track_1.mp3, track (1).mp3)
        # These indicate a messy source with renamed duplicates
        duplicate_patterns = 0
        for f in files:
            filename = f.get("filename", "").lower()
            # Match patterns like: _1.mp3, _2.mp3, (1).mp3, (2).mp3, - Copy.mp3
            if any(p in filename for p in ['_1.', '_2.', '_3.', '(1).', '(2).', '(3).', ' copy.', ' - copy.']):
                duplicate_patterns += 1
        
        if duplicate_patterns > 0:
            # Heavy penalty - this folder has duplicates
            score -= 30 + (duplicate_patterns * 10)
            print(f"slskd:     Penalty for {duplicate_patterns} duplicate-pattern files")
        
        return max(score, 0)

    _AUDIO_EXTENSIONS = (".mp3", ".m4a", ".ogg", ".flac", ".opus", ".wav")

    def _is_audio_file(self, filename: str) -> bool:
        return any(filename.lower().endswith(ext) for ext in self._AUDIO_EXTENSIONS)

    def _download_roots(self, username: Optional[str] = None) -> List[Path]:
        """
        Directories to search for completed downloads.

        slskd may write to /downloads/{username}/... or flat under /downloads/...
        """
        download_dir = Path(slskd_config.download_dir)
        roots: List[Path] = []
        seen: set[str] = set()

        def add(path: Path) -> None:
            if not path.is_dir():
                return
            key = str(path.resolve())
            if key not in seen:
                seen.add(key)
                roots.append(path)

        if username:
            add(download_dir / username)
        add(download_dir)
        return roots

    def _album_title_path_variants(self, album_title: str) -> List[str]:
        """Variants for matching paths like '1995 Methodrone' to album 'Methodrone'."""
        variants: List[str] = []
        base = album_title.lower().strip()
        if base:
            variants.append(base)
        stripped = re.sub(r"^[\[\(]?\s*\d{4}\s*[\]\)]?\s*[-–:]?\s*", "", base).strip()
        if stripped and stripped not in variants:
            variants.append(stripped)
        return variants

    def _album_in_path(self, path_lower: str, album_title: str) -> bool:
        return any(v in path_lower for v in self._album_title_path_variants(album_title))

    def _path_match_score(self, path: str, artist_name: str, album_title: str) -> int:
        """Score how well a path matches the expected artist/album (higher = better)."""
        path_lower = path.lower()
        artist_clean = artist_name.lower().strip()

        score = 0
        if self._album_in_path(path_lower, album_title):
            score += 100
        if artist_clean and artist_clean in path_lower:
            score += 40

        album_words = [w for w in album_title.split() if len(w) > 2]
        artist_words = [w for w in artist_name.split() if len(w) > 2]
        album_hits = sum(1 for w in album_words if w.lower() in path_lower)
        artist_hits = sum(1 for w in artist_words if w.lower() in path_lower)

        score += album_hits * 15
        score += artist_hits * 5

        # Penalize if only artist matches (common when multiple albums share an artist)
        if artist_hits and not album_hits and not self._album_in_path(path_lower, album_title):
            score -= 30

        return score

    def _directory_name(self, directory: Dict[str, Any]) -> str:
        return directory.get("name") or directory.get("directory") or ""

    def _directory_matches_download(self, directory: Dict[str, Any], download: Download) -> bool:
        """Return True if a slskd transfer directory belongs to this download."""
        dir_name = self._directory_name(directory)
        if not dir_name:
            return False

        if download.slskd_remote_folder:
            remote = download.slskd_remote_folder.replace("\\", "/").lower().strip("/")
            current = dir_name.replace("\\", "/").lower().strip("/")
            if current == remote or current.endswith("/" + remote) or remote.endswith("/" + current):
                return True

        return self._path_match_score(dir_name, download.artist_name, download.album_title) >= 50

    def _local_path_for_slskd_directory(
        self,
        username: str,
        directory_name: str,
        artist_name: Optional[str] = None,
        album_title: Optional[str] = None,
    ) -> Optional[Path]:
        """Map a slskd directory name to the local folder on disk."""
        for root in self._download_roots(username):
            found = self._local_path_for_slskd_directory_in_root(
                root, directory_name, artist_name, album_title
            )
            if found:
                return found
        return None

    def _local_path_for_slskd_directory_in_root(
        self,
        root: Path,
        directory_name: str,
        artist_name: Optional[str] = None,
        album_title: Optional[str] = None,
    ) -> Optional[Path]:
        parts = [p for p in re.split(r"[/\\]+", directory_name.strip()) if p]
        if not parts:
            return None

        # Try progressively shorter suffixes of the remote path
        for i in range(len(parts)):
            candidate = root.joinpath(*parts[i:])
            if candidate.is_dir() and self._count_audio_in_folder(candidate) > 0:
                return candidate

        # Match by leaf folder name (album folder)
        leaf = parts[-1].lower()
        matches: List[Path] = []
        for dir_root, _dirs, files in os.walk(root):
            if not any(self._is_audio_file(f) for f in files):
                continue
            folder = Path(dir_root)
            folder_name = folder.name.lower()
            if folder_name == leaf or leaf in folder_name:
                matches.append(folder)

        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]
        if artist_name and album_title:
            return max(
                matches,
                key=lambda p: self._path_match_score(str(p), artist_name, album_title),
            )
        return max(matches, key=lambda p: p.stat().st_mtime)

    def _resolve_folder_from_remote(self, download: Download) -> Optional[Path]:
        """Resolve local folder using the remote path stored at download start."""
        if not download.slskd_remote_folder or not download.slskd_username:
            return None
        return self._local_path_for_slskd_directory(
            download.slskd_username,
            download.slskd_remote_folder,
            download.artist_name,
            download.album_title,
        )

    def _count_audio_in_folder(self, folder: Path) -> int:
        count = 0
        for root, _dirs, files in os.walk(folder):
            count += sum(1 for f in files if self._is_audio_file(f))
        return count
    
    def update_download_progress(self, download_id: int) -> Optional[Download]:
        """Update download progress from slskd."""
        download = self.db.query(Download).filter(Download.id == download_id).first()
        if not download or download.status not in ["downloading", "searching"]:
            return download
        
        try:
            # Get current downloads from slskd
            slskd_downloads = self.client.get_downloads()
            
            # Find our download by username
            if download.slskd_username:
                user_download = None
                for d in slskd_downloads:
                    if d.get("username") == download.slskd_username:
                        user_download = d
                        break
                
                if user_download:
                    # Calculate progress - slskd returns directories with files
                    directories = user_download.get("directories", [])

                    # Only track directories that belong to THIS download (same peer
                    # may be used for multiple albums in the queue).
                    matching_directories = [
                        d for d in directories if self._directory_matches_download(d, download)
                    ]
                    if not matching_directories and len(directories) == 1:
                        matching_directories = directories
                    
                    total_files = 0
                    completed_files = 0
                    failed_files = 0
                    total_bytes = 0
                    completed_bytes = 0
                    
                    for directory in matching_directories:
                        dir_name = self._directory_name(directory)
                        if dir_name and download.slskd_username:
                            local_path = self._local_path_for_slskd_directory(
                                download.slskd_username,
                                dir_name,
                                download.artist_name,
                                download.album_title,
                            )
                            if local_path:
                                download.local_folder_path = str(local_path)

                        files = directory.get("files", [])
                        for file_dl in files:
                            total_files += 1
                            file_size = file_dl.get("size", 0)
                            total_bytes += file_size
                            
                            # slskd states can be comma-separated like "Completed, Succeeded"
                            state = str(file_dl.get("state", "")).lower()
                            bytes_transferred = file_dl.get("bytesTransferred", 0)
                            
                            # Check if state contains completed/succeeded
                            if "completed" in state or "succeeded" in state:
                                completed_files += 1
                                completed_bytes += file_size
                            elif "errored" in state or "timedout" in state or "cancelled" in state or "rejected" in state:
                                failed_files += 1
                            else:
                                # InProgress, Queued, Initializing, Requested, etc.
                                completed_bytes += bytes_transferred
                    
                    # Update counts
                    if total_files > 0:
                        download.total_files = total_files
                    download.completed_files = completed_files
                    if total_bytes > 0:
                        download.total_bytes = total_bytes
                    download.completed_bytes = completed_bytes
                    
                    print(f"slskd: Download {download.id} progress: {completed_files}/{total_files} files, {completed_bytes}/{total_bytes} bytes, failed: {failed_files}")
                    
                    # Check if complete or failed
                    if total_files > 0:
                        if completed_files + failed_files >= total_files:
                            # Calculate success rate
                            success_rate = completed_files / total_files if total_files > 0 else 0
                            
                            if completed_files == 0:
                                # All files failed - cleanup downloaded files
                                download.status = "failed"
                                download.error_message = f"All {failed_files} files failed to download"
                                download.completed_at = datetime.utcnow()
                                self.db.commit()
                                self._cleanup_download_files(download)
                                return download
                            elif success_rate < 0.5:
                                # Less than 50% success - mark as failed and cleanup
                                download.status = "failed"
                                download.error_message = f"Only {completed_files} of {total_files} files downloaded ({int(success_rate*100)}%)"
                                download.completed_at = datetime.utcnow()
                                self.db.commit()
                                self._cleanup_download_files(download)
                                return download
                            elif failed_files > 0:
                                # Majority succeeded but some failed - completed with warning, NO auto-move
                                download.status = "completed"
                                download.error_message = f"{failed_files} of {total_files} files failed"
                                download.completed_at = datetime.utcnow()
                                print(f"slskd: Download {download.id} completed with {failed_files} failures - NOT auto-moving")
                            else:
                                # All complete - automatically move to library
                                download.status = "completed"
                                download.completed_at = datetime.utcnow()
                                print(f"slskd: Download {download.id} completed successfully! Auto-moving to library...")
                                self.db.commit()
                                # Auto-move to library
                                self.move_completed_download(download.id)
                                return download
                    
                    self.db.commit()
            
            return download
            
        except Exception as e:
            print(f"slskd: Error updating download progress: {e}")
            return download
    
    def retry_download(self, download_id: int) -> Optional[Download]:
        """Retry a failed download."""
        download = self.db.query(Download).filter(Download.id == download_id).first()
        if not download:
            return None
        
        if download.status not in ["failed", "cancelled"]:
            return download
        
        # Reset status and try again
        download.status = "pending"
        download.error_message = None
        download.completed_files = 0
        download.completed_bytes = 0
        download.slskd_username = None
        download.slskd_remote_folder = None
        download.local_folder_path = None
        self.db.commit()
        
        # Run the search again
        return self.search_and_download_album(download_id)
    
    def cancel_download(self, download_id: int) -> Optional[Download]:
        """Cancel an active download."""
        download = self.db.query(Download).filter(Download.id == download_id).first()
        if not download:
            return None
        
        if download.status not in ["pending", "searching", "downloading"]:
            return download
        
        # Try to cancel in slskd if we have a username
        if download.slskd_username:
            try:
                # Cancel all downloads from this user
                response = self.client.session.delete(
                    f"{self.client.config.url}/api/v0/transfers/downloads/{download.slskd_username}",
                    timeout=10
                )
                if response.status_code in [200, 204]:
                    print(f"slskd: Cancelled downloads from {download.slskd_username}")
            except Exception as e:
                print(f"slskd: Error cancelling download: {e}")
        
        download.status = "cancelled"
        download.error_message = "Cancelled by user"
        self.db.commit()
        
        # Clean up any downloaded files
        self._cleanup_download_files(download)
        
        return download
    
    def _cleanup_download_files(self, download: Download) -> int:
        """
        Clean up downloaded files for a failed/cancelled download.
        Removes files from the slskd download directory to prevent duplicates.
        Returns the number of files deleted.
        """
        if not download.slskd_username:
            return 0
        
        try:
            deleted_count = 0
            artist_words = [w.lower() for w in download.artist_name.split() if len(w) > 2]
            
            dirs_to_check = []
            for search_root in self._download_roots(download.slskd_username):
                for root, dirs, files in os.walk(search_root):
                    path_lower = root.lower()
                    if not (
                        any(w in path_lower for w in artist_words)
                        or self._album_in_path(path_lower, download.album_title)
                    ):
                        continue
                    for file in files:
                        if any(file.lower().endswith(ext) for ext in [".mp3", ".m4a", ".ogg", ".flac"]):
                            file_path = Path(root) / file
                            try:
                                file_path.unlink()
                                deleted_count += 1
                            except Exception as e:
                                print(f"slskd: Error deleting {file_path}: {e}")
                    dirs_to_check.append(root)
            
            # Clean up empty directories
            for dir_path in sorted(dirs_to_check, key=len, reverse=True):
                try:
                    dir_obj = Path(dir_path)
                    if dir_obj.exists() and not any(dir_obj.iterdir()):
                        dir_obj.rmdir()
                except Exception:
                    pass
            
            if deleted_count > 0:
                print(f"slskd: Cleaned up {deleted_count} files from failed download {download.id}")
            
            return deleted_count
            
        except Exception as e:
            print(f"slskd: Error cleaning up download files: {e}")
            return 0
    
    def check_and_timeout_downloads(self, timeout_minutes: int = 5) -> int:
        """Check for downloads that have been running too long and cancel them."""
        from datetime import timedelta
        
        timeout_threshold = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        
        # Find downloads that are stuck (only pending/searching, not downloading)
        # Downloading status means slskd is actively working on it
        stuck_downloads = self.db.query(Download).filter(
            Download.status.in_(["pending", "searching"]),
            Download.created_at < timeout_threshold
        ).all()
        
        cancelled_count = 0
        for download in stuck_downloads:
            # Double-check by updating progress first
            self.update_download_progress(download.id)
            self.db.refresh(download)
            
            # Only timeout if still stuck (not completed/downloading)
            if download.status in ["pending", "searching"]:
                print(f"slskd: Timing out download {download.id} ({download.album_title})")
                download.status = "failed"
                download.error_message = f"Timed out after {timeout_minutes} minutes (stuck in {download.status})"
                cancelled_count += 1
                self._cleanup_download_files(download)
        
        if cancelled_count > 0:
            self.db.commit()
        
        return cancelled_count
    
    def move_completed_download(self, download_id: int) -> bool:
        """
        Move completed download to music library with beets tagging.
        
        This method:
        1. Checks the downloaded files with beets for matching
        2. If confidence >= 95%, auto-applies tags and moves
        3. If confidence < 95%, sets status to pending_review for user action
        """
        import json
        
        download = self.db.query(Download).filter(Download.id == download_id).first()
        if not download or download.status != "completed":
            return False
        
        # Safety check: don't move if most files failed
        if download.total_files > 0 and download.completed_files > 0:
            success_rate = download.completed_files / download.total_files
            if success_rate < 0.5:
                print(f"slskd: Refusing to move download {download_id} - only {download.completed_files}/{download.total_files} files completed")
                return False
        
        try:
            # Find the download folder
            download_folder = self._find_download_folder(download)
            if not download_folder:
                print(f"slskd: Could not find download folder for {download.artist_name} - {download.album_title}")
                download.status = "pending_review"
                download.error_message = "Could not locate downloaded files on disk"
                download.beets_candidates = json.dumps([])
                self.db.commit()
                return False
            
            music_dir = Path(get_settings().music_folder)
            
            # Run beets check on the download folder
            print(f"slskd: Checking album tags with beets for {download.artist_name} - {download.album_title}")
            print(f"slskd: Download folder: {download_folder}")
            
            candidates = BeetsService.check_album_match(str(download_folder), str(music_dir))
            
            if candidates:
                best_match = candidates[0]
                print(f"slskd: Found {len(candidates)} beets candidates, best match: {best_match.confidence}% ({best_match.artist} - {best_match.album})")
                
                # Auto-apply if confidence >= 90%
                if best_match.confidence >= 90.0:
                    print(f"slskd: High confidence match ({best_match.confidence}%), auto-applying tags...")
                    success, applied_info = BeetsService.apply_tags(
                        str(download_folder), 
                        best_match.id,
                        str(music_dir)
                    )
                    
                    if success:
                        download.beets_applied_match = json.dumps(applied_info or {
                            "status": "auto_applied",
                            "musicbrainz_id": best_match.id,
                            "musicbrainz_url": best_match.musicbrainz_url,
                            "confidence": best_match.confidence
                        })
                        # Move files to library
                        return self._move_files_to_library(download, download_folder)
                    else:
                        print(f"slskd: Auto-apply failed, falling back to pending_review")
                        # Fall through to pending_review
                
                # Confidence < 90% or auto-apply failed - need user review
                download.beets_candidates = json.dumps([c.to_dict() for c in candidates])
                download.status = "pending_review"
                self.db.commit()
                print(f"slskd: Download {download_id} set to pending_review - user action required")
            else:
                # No matches found - still need user to choose skip tagging
                download.beets_candidates = json.dumps([])
                download.status = "pending_review"
                self.db.commit()
                print(f"slskd: No beets matches found - user must choose to skip tagging")
            
            return True
            
        except Exception as e:
            print(f"slskd: Error in move_completed_download: {e}")
            download.error_message = f"Failed to process download: {e}"
            self.db.commit()
            return False
    
    def _find_download_folder(self, download: Download) -> Optional[Path]:
        """Find the folder containing downloaded files for this download."""
        # 1. Use path captured during download progress (most reliable)
        if download.local_folder_path:
            stored = Path(download.local_folder_path)
            if stored.exists() and self._count_audio_in_folder(stored) > 0:
                print(f"slskd: Using stored local_folder_path: {stored}")
                return stored

        # 2. Resolve from remote folder recorded at download start
        resolved = self._resolve_folder_from_remote(download)
        if resolved and resolved.exists():
            print(f"slskd: Resolved folder from slskd_remote_folder: {resolved}")
            download.local_folder_path = str(resolved)
            self.db.commit()
            return resolved

        search_roots = self._download_roots(download.slskd_username)
        if not search_roots:
            return self._find_folder_in_music_library(download)

        # 3. Score all candidate folders and pick the best match (not first match)
        best_folder: Optional[Path] = None
        best_score = -1

        for search_root in search_roots:
            for root, _dirs, files in os.walk(search_root):
                if not any(self._is_audio_file(f) for f in files):
                    continue

                folder = Path(root)
                score = self._path_match_score(str(folder), download.artist_name, download.album_title)

                if score < 50:
                    continue

                audio_count = sum(1 for f in files if self._is_audio_file(f))
                if download.total_files > 0:
                    score += max(0, 30 - abs(audio_count - download.total_files) * 3)

                try:
                    score += int(folder.stat().st_mtime / 1000) % 1000  # prefer newer as tiebreaker
                except OSError:
                    pass

                if score > best_score:
                    best_score = score
                    best_folder = folder

        if best_folder:
            print(f"slskd: Best folder match (score={best_score}): {best_folder}")
            download.local_folder_path = str(best_folder)
            self.db.commit()
            return best_folder

        library_folder = self._find_folder_in_music_library(download)
        if library_folder:
            print(f"slskd: Found folder in music library: {library_folder}")
            download.local_folder_path = str(library_folder)
            self.db.commit()
            return library_folder

        print(f"slskd: No matching folder found for {download.artist_name} - {download.album_title}")
        return None

    def _find_folder_in_music_library(self, download: Download) -> Optional[Path]:
        """Fallback: files may already sit under the artist folder in the music library."""
        music_dir = Path(get_settings().music_folder)
        if not music_dir.is_dir():
            return None

        artist_names = {
            download.artist_name.replace("/", "_").replace("\\", "_"),
            download.artist_name,
        }
        for entry in music_dir.iterdir():
            if entry.is_dir() and entry.name.lower() == download.artist_name.lower():
                artist_names.add(entry.name)

        since = download.started_at or download.created_at
        best_folder: Optional[Path] = None
        best_score = -1

        for artist_name in artist_names:
            artist_dir = music_dir / artist_name
            if not artist_dir.is_dir():
                continue
            for album_dir in artist_dir.iterdir():
                if not album_dir.is_dir():
                    continue
                if self._count_audio_in_folder(album_dir) == 0:
                    continue
                score = self._path_match_score(
                    str(album_dir), download.artist_name, download.album_title
                )
                if score < 50:
                    continue
                if since:
                    try:
                        if album_dir.stat().st_mtime < since.timestamp() - 120:
                            continue
                    except OSError:
                        pass
                if score > best_score:
                    best_score = score
                    best_folder = album_dir

        return best_folder
    
    def _move_files_to_library(self, download: Download, source_folder: Path) -> bool:
        """Move audio files from source folder to music library."""
        music_dir = Path(get_settings().music_folder)
        
        artist_name = download.artist_name.replace("/", "_").replace("\\", "_")
        album_title = download.album_title.replace("/", "_").replace("\\", "_")
        
        target_dir = music_dir / artist_name / album_title
        target_dir.mkdir(parents=True, exist_ok=True)
        
        moved_count = 0
        artist_words = [w.lower() for w in download.artist_name.split() if len(w) > 2]
        album_words = [w.lower() for w in download.album_title.split() if len(w) > 2]
        
        copy_only_fallback = False
        for root, dirs, files in os.walk(source_folder):
            for file in files:
                if any(file.lower().endswith(ext) for ext in [".mp3", ".m4a", ".ogg", ".flac"]):
                    file_path = Path(root) / file
                    path_lower = str(file_path).lower()

                    if any(w in path_lower for w in artist_words) or any(w in path_lower for w in album_words):
                        dest_path = target_dir / file
                        try:
                            shutil.move(str(file_path), str(dest_path))
                        except PermissionError:
                            # Source lives in a directory we can't write to
                            # (e.g. slskd wrote it as root). Fall back to a
                            # copy so the album still lands in the library;
                            # the leftover source files will need to be
                            # cleaned up out-of-band (see warning below).
                            shutil.copy2(str(file_path), str(dest_path))
                            copy_only_fallback = True
                        moved_count += 1

        if copy_only_fallback:
            print(
                f"slskd: WARNING - could not delete source files in {source_folder} "
                f"(permission denied). Files were COPIED into the library instead. "
                f"You'll need to remove the leftovers manually or fix slskd's "
                f"download-dir ownership/umask so it writes group-writable files."
            )
        
        if moved_count > 0:
            download.status = "moved"
            self.db.commit()
            
            # Update album to mark as owned
            if download.album_id:
                album = self.db.query(Album).filter(Album.id == download.album_id).first()
                if album:
                    album.is_owned = True
                    album.is_wishlisted = False
                    album.folder_path = str(target_dir)
                    album.created_at = datetime.utcnow()
                    self.db.commit()
                    
                    # Scan the folder for metadata
                    from app.services.scanner import ScannerService
                    scanner = ScannerService(self.db)
                    try:
                        scanner.scan_album_folder(str(target_dir), force_rescan=True)
                        print(f"slskd: Scanned imported album at {target_dir}")
                    except Exception as scan_error:
                        print(f"slskd: Warning - failed to scan imported album: {scan_error}")
            
            print(f"slskd: Moved {moved_count} files to {target_dir}")
            return True
        
        return False
    
    def apply_match_and_move(self, download_id: int, match_id: Optional[str] = None, 
                             skip_tagging: bool = False) -> bool:
        """
        Apply a beets match and move files to library.
        Called when user selects a match from pending_review state.
        
        Args:
            download_id: ID of the download
            match_id: Optional specific match ID (MusicBrainz release ID)
            skip_tagging: If True, skip beets tagging and just move files
        """
        import json
        
        download = self.db.query(Download).filter(Download.id == download_id).first()
        if not download:
            return False
        
        if download.status not in ["completed", "pending_review"]:
            return False
        
        try:
            download_folder = self._find_download_folder(download)
            if not download_folder:
                print(f"slskd: Could not find download folder for apply_match_and_move")
                return False
            
            music_dir = Path(get_settings().music_folder)
            
            # Apply beets tagging if not skipping
            applied_info = None
            if not skip_tagging:
                print(f"slskd: Applying beets tags for {download.artist_name} - {download.album_title}")
                success, applied_info = BeetsService.apply_tags(str(download_folder), match_id, str(music_dir))
                
                # Store the applied match info
                if applied_info:
                    # If user selected a specific match, include that info
                    if match_id:
                        applied_info['selected_match_id'] = match_id
                    download.beets_applied_match = json.dumps(applied_info)
            else:
                # User skipped tagging
                download.beets_applied_match = json.dumps({
                    "status": "skipped",
                    "note": "User chose to skip tagging"
                })
            
            # Clear candidates and move files
            download.beets_candidates = None
            self.db.commit()
            
            return self._move_files_to_library(download, download_folder)
            
        except Exception as e:
            print(f"slskd: Error in apply_match_and_move: {e}")
            download.error_message = f"Failed to apply match: {e}"
            self.db.commit()
            return False
    
    def get_all_downloads(self) -> List[Download]:
        """Get all downloads ordered by creation date."""
        return self.db.query(Download).order_by(Download.created_at.desc()).all()
    
    def get_active_downloads(self) -> List[Download]:
        """Get currently active downloads."""
        return self.db.query(Download).filter(
            Download.status.in_(["searching", "downloading"])
        ).all()

