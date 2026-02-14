"""
Beets integration service for checking and applying album metadata.
Uses beets to identify albums and fix tags before importing to library.
"""

import subprocess
import re
import os
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass


@dataclass
class BeetsCandidate:
    """Represents a potential album match from beets."""
    id: str  # MusicBrainz release ID
    artist: str
    album: str
    year: Optional[int]
    tracks: int
    distance: float  # 0.0 = perfect match, 1.0 = no match
    musicbrainz_url: Optional[str] = None
    
    @property
    def confidence(self) -> float:
        """Convert distance to confidence percentage (0-100)."""
        return round((1.0 - self.distance) * 100, 1)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "artist": self.artist,
            "album": self.album,
            "year": self.year,
            "tracks": self.tracks,
            "distance": self.distance,
            "confidence": self.confidence,
            "musicbrainz_url": self.musicbrainz_url,
        }


class BeetsService:
    """Service for interacting with beets for music tagging."""
    
    # Confidence threshold for auto-applying (disabled - always require review)
    AUTO_APPLY_THRESHOLD = 0.0  # Set to 0 to always require review
    
    # MusicBrainz release ID pattern (UUID format)
    MB_ID_PATTERN = re.compile(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', re.IGNORECASE)
    
    @classmethod
    def _create_beets_config(cls, library_path: str) -> str:
        """Create a temporary beets config file."""
        config = f"""
directory: {library_path}
library: /tmp/beets_temp.db

import:
    write: yes
    copy: no
    move: no
    autotag: yes
    quiet: no
    
match:
    strong_rec_thresh: 0.04
    preferred:
        countries: ['US', 'GB', 'XW']
        media: ['Digital Media', 'CD']

# IMPORTANT: musicbrainz plugin MUST be loaded for MusicBrainz searches to work
plugins: [musicbrainz]
"""
        config_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        config_file.write(config)
        config_file.close()
        return config_file.name
    
    @classmethod
    def check_album_match(cls, folder_path: str, library_path: str = "/music") -> List[BeetsCandidate]:
        """
        Check an album folder against MusicBrainz using beets.
        Returns list of potential matches sorted by confidence.
        """
        candidates = []
        
        if not os.path.exists(folder_path):
            print(f"beets: Folder not found: {folder_path}")
            return candidates
        
        # List files in folder for debugging
        try:
            files = [f for f in Path(folder_path).glob("*") if f.suffix.lower() in ('.mp3', '.flac', '.m4a', '.ogg', '.opus', '.wav')]
            print(f"beets: Checking folder with {len(files)} audio files: {folder_path}")
            for f in files[:3]:  # Show first 3 files
                print(f"beets:   - {f.name}")
            if len(files) > 3:
                print(f"beets:   ... and {len(files) - 3} more")
        except Exception as e:
            print(f"beets: Error listing folder: {e}")
        
        config_path = cls._create_beets_config(library_path)
        
        try:
            # Run beets import in pretend mode with timid to show all candidates
            # -p = pretend (don't actually import)
            # -t = timid (always ask, shows all candidates)
            # Pipe 'b' (abort) to exit after seeing candidates
            print(f"beets: Running: beet -c {config_path} import -p -t {folder_path}")
            result = subprocess.run(
                [
                    "beet", "-c", config_path,
                    "import", "-p", "-t", folder_path
                ],
                capture_output=True,
                text=True,
                input="b\n",  # Abort after seeing candidates
                timeout=120,
                env={**os.environ, "BEETSDIR": "/tmp"}
            )
            
            full_output = result.stdout + "\n" + result.stderr
            print(f"beets: Raw output:\n{full_output[:2000]}")  # Log first 2000 chars
            
            candidates = cls._parse_beets_output(full_output)
            print(f"beets: Parsed {len(candidates)} candidates")
            for c in candidates:
                print(f"beets:   - {c.artist} - {c.album} ({c.confidence}%) MB: {c.id}")
            
        except subprocess.TimeoutExpired:
            print(f"beets: Timeout checking {folder_path}")
        except FileNotFoundError:
            print("beets: beet command not found - is beets installed?")
        except Exception as e:
            print(f"beets: Error checking album: {e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                os.unlink(config_path)
            except:
                pass
        
        return candidates
    
    @classmethod
    def _parse_beets_output(cls, output: str) -> List[BeetsCandidate]:
        """Parse beets output to extract match candidates with MusicBrainz IDs.
        
        Beets output format (timid mode):
        
        /path/to/folder (15 items)
        
          Match (98.2%):
          Artist Name - Album Title
          ≠ media, tracks
          MusicBrainz, CD, 2007, US, Label Name
          https://musicbrainz.org/release/uuid-here
          
        Or for multiple candidates:
          1. Artist - Album (95.0%)
          ...
        """
        candidates = []
        lines = output.split('\n')
        
        current_candidate = {}
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # Skip ANSI escape codes
            clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line_stripped)
            clean_line = clean_line.strip()
            
            # Format: "Match (98.2%):" - start of a match block
            match_header = re.match(r'Match\s*\((\d+\.?\d*)%\):', clean_line)
            if match_header:
                # Save previous candidate if complete
                if cls._is_candidate_complete(current_candidate):
                    candidates.append(cls._create_candidate_from_dict(current_candidate))
                
                current_candidate = {
                    'confidence': float(match_header.group(1)),
                    'distance': 1.0 - (float(match_header.group(1)) / 100.0)
                }
                continue
            
            # Format: "Artist Name - Album Title" (line after Match header)
            if current_candidate.get('confidence') and not current_candidate.get('artist'):
                if ' - ' in clean_line and not clean_line.startswith(('≠', '*', '#', '(')):
                    parts = clean_line.split(' - ', 1)
                    if len(parts) == 2:
                        current_candidate['artist'] = parts[0].strip()
                        current_candidate['album'] = parts[1].strip()
                        continue
            
            # Format: "MusicBrainz, CD, 2007, US, Label" - metadata line
            if clean_line.startswith('MusicBrainz'):
                parts = clean_line.split(', ')
                for part in parts:
                    part = part.strip()
                    # Year is a 4-digit number
                    if re.match(r'^(19|20)\d{2}$', part):
                        current_candidate['year'] = int(part)
                continue
            
            # Look for MusicBrainz URL
            if 'musicbrainz.org/release/' in clean_line.lower():
                mb_match = cls.MB_ID_PATTERN.search(clean_line)
                if mb_match:
                    current_candidate['mb_id'] = mb_match.group(0)
                    current_candidate['mb_url'] = f"https://musicbrainz.org/release/{mb_match.group(0)}"
                continue
            
            # Format: "1. Artist - Album (95.0%)" - numbered candidate
            numbered_match = re.match(r'^\d+\.\s+(.+?)\s+-\s+(.+?)\s+\((\d+\.?\d*)%\)', clean_line)
            if numbered_match:
                # Save previous candidate if complete
                if cls._is_candidate_complete(current_candidate):
                    candidates.append(cls._create_candidate_from_dict(current_candidate))
                
                current_candidate = {
                    'artist': numbered_match.group(1).strip(),
                    'album': numbered_match.group(2).strip(),
                    'confidence': float(numbered_match.group(3)),
                    'distance': 1.0 - (float(numbered_match.group(3)) / 100.0)
                }
                continue
            
            # Legacy format: "(Similarity: 95.2%)" or "(95.2%)"
            similarity_match = re.search(r'\(Similarity:\s*(\d+\.?\d*)%\)', clean_line)
            if not similarity_match:
                similarity_match = re.search(r'\((\d+\.?\d*)%\)', clean_line)
            
            if similarity_match and not current_candidate.get('confidence'):
                try:
                    similarity = float(similarity_match.group(1))
                    current_candidate['confidence'] = similarity
                    current_candidate['distance'] = 1.0 - (similarity / 100.0)
                except:
                    pass
        
        # Don't forget the last candidate
        if cls._is_candidate_complete(current_candidate):
            candidates.append(cls._create_candidate_from_dict(current_candidate))
        
        print(f"beets: Parsed {len(candidates)} candidates")
        return candidates
    
    @classmethod
    def _is_candidate_complete(cls, candidate: dict) -> bool:
        """Check if a candidate dict has minimum required fields."""
        return (candidate.get('artist') and 
                candidate.get('album') and 
                candidate.get('confidence') is not None)
    
    @classmethod
    def _create_candidate_from_dict(cls, d: dict) -> 'BeetsCandidate':
        """Create a BeetsCandidate from a parsed dict."""
        return BeetsCandidate(
            id=d.get('mb_id', f"unknown_{hash(str(d))}"),
            artist=d['artist'],
            album=d['album'],
            year=d.get('year'),
            tracks=d.get('tracks', 0),
            distance=d.get('distance', 0.0),
            musicbrainz_url=d.get('mb_url')
        )
    
    @classmethod
    def apply_tags(cls, folder_path: str, match_id: Optional[str] = None, 
                   library_path: str = "/music") -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Apply beets tagging to an album folder.
        
        Args:
            folder_path: Path to album folder
            match_id: MusicBrainz release ID to use (optional)
            library_path: Music library path
        
        Returns:
            Tuple of (success, applied_match_info)
            applied_match_info contains details about what was applied
        """
        if not os.path.exists(folder_path):
            print(f"beets: Folder not found: {folder_path}")
            return False, None
        
        config_path = cls._create_beets_config(library_path)
        applied_info = None
        
        try:
            # Build command
            # -q = quiet (don't ask, just apply best match)
            # --flat = don't use album directories
            cmd = ["beet", "-c", config_path, "import", "-q", "--flat"]
            
            # If we have a specific ID, use --search-id to guide beets
            if match_id:
                cmd.extend(["--search-id", match_id])
                print(f"beets: Using MusicBrainz ID hint: {match_id}")
            
            cmd.append(folder_path)
            
            print(f"beets: Running: {' '.join(cmd)}")
            
            # Run beets import
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                input="",  # No stdin
                timeout=180,
                env={**os.environ, "BEETSDIR": "/tmp"}
            )
            
            full_output = result.stdout + "\n" + result.stderr
            print(f"beets: Apply output:\n{full_output[:2000]}")
            
            # Try to extract what was applied from beets output
            mb_match = cls.MB_ID_PATTERN.search(full_output)
            if mb_match:
                applied_info = {
                    "musicbrainz_id": mb_match.group(0),
                    "musicbrainz_url": f"https://musicbrainz.org/release/{mb_match.group(0)}",
                    "status": "applied"
                }
            elif match_id:
                # Fallback to the ID we provided
                applied_info = {
                    "musicbrainz_id": match_id,
                    "musicbrainz_url": f"https://musicbrainz.org/release/{match_id}",
                    "status": "applied"
                }
            else:
                applied_info = {
                    "status": "applied_unknown",
                    "note": "Tags applied but could not extract MusicBrainz ID"
                }
            
            if result.returncode == 0:
                print(f"beets: Successfully tagged {folder_path}")
                return True, applied_info
            else:
                # Check if it's a "no match" situation
                if 'no suitable match' in full_output.lower() or 'skipping' in full_output.lower():
                    applied_info = {"status": "no_match", "note": "No suitable match found"}
                    print(f"beets: No match found for {folder_path}")
                else:
                    applied_info = {"status": "failed", "error": result.stderr[:500]}
                    print(f"beets: Tagging failed: {result.stderr}")
                return False, applied_info
                
        except subprocess.TimeoutExpired:
            print(f"beets: Timeout tagging {folder_path}")
            return False, {"status": "timeout"}
        except FileNotFoundError:
            print("beets: beet command not found - is beets installed?")
            return False, {"status": "not_installed"}
        except Exception as e:
            print(f"beets: Error applying tags: {e}")
            return False, {"status": "error", "error": str(e)}
        finally:
            try:
                os.unlink(config_path)
            except:
                pass
            try:
                os.unlink("/tmp/beets_temp.db")
            except:
                pass
    
    @classmethod
    def should_auto_apply(cls, candidates: List[BeetsCandidate]) -> bool:
        """
        Determine if we should auto-apply tags.
        Currently disabled - always returns False to require user review.
        """
        # Disabled - always require user review for safety
        return False
