"""
slskd integration service for downloading albums from Soulseek.
Based on the slskd API: https://github.com/slskd/slskd
"""

import os
import time
import shutil
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.models import Download, Album, Artist
from app.config import get_settings


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
        
        artist_name = album.artist.name if album.artist else "Unknown Artist"
        album_title = album.title
        expected_tracks = album.track_count or 0
        
        # Update download to searching status
        download.status = "searching"
        download.artist_name = artist_name
        download.album_title = album_title
        self.db.commit()
        
        try:
            # Search for the album
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
                    
                    # Find matching audio files
                    matching_files = self._find_matching_files(
                        files, artist_name, album_title
                    )
                    
                    if matching_files:
                        score = self._calculate_score(
                            matching_files, artist_name, album_title, expected_tracks
                        )
                        
                        if score > 0:
                            all_candidates.append({
                                "username": username,
                                "files": matching_files,
                                "score": score,
                                "track_count": len(matching_files)
                            })
                
                # If we have good candidates, stop searching
                if len(all_candidates) >= 3:
                    break
            
            if not all_candidates:
                download.status = "failed"
                download.error_message = "No suitable sources found"
                self.db.commit()
                return download
            
            # Sort by score and try to download from best candidate
            all_candidates.sort(key=lambda x: x["score"], reverse=True)
            
            for candidate in all_candidates[:3]:
                if self.client.download_files(candidate["username"], candidate["files"]):
                    download.status = "downloading"
                    download.slskd_username = candidate["username"]
                    download.total_files = len(candidate["files"])
                    download.total_bytes = sum(f.get("size", 0) for f in candidate["files"])
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
    
    def _find_matching_files(
        self,
        files: List[Dict],
        artist_name: str,
        album_title: str
    ) -> List[Dict]:
        """Find audio files that match the artist/album."""
        matching = []
        
        artist_words = [w.lower() for w in artist_name.split() if len(w) > 2]
        title_words = [w.lower() for w in album_title.split() if len(w) > 2]
        
        for file_info in files:
            filename = file_info.get("filename", "").lower()
            size = file_info.get("size", 0)
            
            # Check if it's an audio file (prefer MP3, exclude FLAC for size)
            if any(ext in filename for ext in [".mp3", ".m4a", ".ogg"]):
                artist_match = any(w in filename for w in artist_words)
                title_match = any(w in filename for w in title_words)
                
                if artist_match or title_match:
                    matching.append({
                        **file_info,
                        "artist_match": artist_match,
                        "title_match": title_match
                    })
        
        return matching
    
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
        
        return max(score, 0)
    
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
                    
                    total_files = 0
                    completed_files = 0
                    failed_files = 0
                    total_bytes = 0
                    completed_bytes = 0
                    
                    for directory in directories:
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
                                # All files failed
                                download.status = "failed"
                                download.error_message = f"All {failed_files} files failed to download"
                                download.completed_at = datetime.utcnow()
                            elif success_rate < 0.5:
                                # Less than 50% success - mark as failed
                                download.status = "failed"
                                download.error_message = f"Only {completed_files} of {total_files} files downloaded ({int(success_rate*100)}%)"
                                download.completed_at = datetime.utcnow()
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
        
        return download
    
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
        
        if cancelled_count > 0:
            self.db.commit()
        
        return cancelled_count
    
    def move_completed_download(self, download_id: int) -> bool:
        """Move completed download to music library."""
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
            # Find downloaded files in slskd download directory
            download_dir = Path(slskd_config.download_dir)
            music_dir = Path(get_settings().music_folder)
            
            if not download_dir.exists():
                print(f"slskd: Download directory not found: {download_dir}")
                return False
            
            # Look for files from this user
            username = download.slskd_username
            if not username:
                return False
            
            # slskd organizes downloads by username
            user_dir = download_dir / username
            if not user_dir.exists():
                # Try to find any folder matching artist/album
                user_dir = download_dir
            
            # Find folders that might contain our album
            artist_name = download.artist_name.replace("/", "_").replace("\\", "_")
            album_title = download.album_title.replace("/", "_").replace("\\", "_")
            
            target_dir = music_dir / artist_name / album_title
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Find and move audio files
            moved_count = 0
            for root, dirs, files in os.walk(user_dir):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in [".mp3", ".m4a", ".ogg", ".flac"]):
                        # Check if file path contains artist or album name
                        file_path = Path(root) / file
                        path_lower = str(file_path).lower()
                        
                        artist_words = [w.lower() for w in download.artist_name.split() if len(w) > 2]
                        album_words = [w.lower() for w in download.album_title.split() if len(w) > 2]
                        
                        if any(w in path_lower for w in artist_words) or any(w in path_lower for w in album_words):
                            dest_path = target_dir / file
                            shutil.move(str(file_path), str(dest_path))
                            moved_count += 1
            
            if moved_count > 0:
                download.status = "moved"
                self.db.commit()
                
                # Update album to mark as owned and scan the folder for metadata
                if download.album_id:
                    album = self.db.query(Album).filter(Album.id == download.album_id).first()
                    if album:
                        album.is_owned = True
                        album.is_wishlisted = False
                        album.folder_path = str(target_dir)
                        self.db.commit()
                        
                        # Scan the folder to extract track info, duration, etc.
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
            
        except Exception as e:
            print(f"slskd: Error moving files: {e}")
            download.error_message = f"Failed to move files: {e}"
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

