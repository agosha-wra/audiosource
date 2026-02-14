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

plugins: []
"""
        config_file = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        config_file.write(config)
        config_file.close()
        return config_file.name
    
    @classmethod
    def check_album_match(cls, folder_path: str, library_path: str = "/music",
                          artist_hint: str = None, album_hint: str = None,
                          musicbrainz_id: str = None) -> List[BeetsCandidate]:
        """
        Check an album folder against MusicBrainz using beets.
        Returns list of potential matches sorted by confidence.
        
        Args:
            folder_path: Path to folder with audio files
            library_path: Music library path
            artist_hint: Expected artist name (helps beets search)
            album_hint: Expected album name (helps beets search)
            musicbrainz_id: If known, we can create a candidate directly
        """
        candidates = []
        
        if not os.path.exists(folder_path):
            print(f"beets: Folder not found: {folder_path}")
            return candidates
        
        # If we already have the MusicBrainz ID, create a candidate directly
        # This bypasses beets' unreliable search
        if musicbrainz_id and artist_hint and album_hint:
            print(f"beets: Using known MusicBrainz ID: {musicbrainz_id}")
            candidates.append(BeetsCandidate(
                id=musicbrainz_id,
                artist=artist_hint,
                album=album_hint,
                year=None,
                tracks=0,
                distance=0.0,  # Perfect match since we know the ID
                musicbrainz_url=f"https://musicbrainz.org/release-group/{musicbrainz_id}"
            ))
            return candidates
        
        # List files in folder for debugging
        try:
            files = list(Path(folder_path).glob("*"))
            print(f"beets: Checking folder with {len(files)} files: {folder_path}")
        except Exception as e:
            print(f"beets: Error listing folder: {e}")
        
        config_path = cls._create_beets_config(library_path)
        
        try:
            # Run beets import in pretend mode
            # -p = pretend (don't actually import)
            # Pipe 's' (skip) repeatedly to stdin so beets doesn't hang on prompts
            result = subprocess.run(
                [
                    "beet", "-c", config_path,
                    "import", "-p", folder_path
                ],
                capture_output=True,
                text=True,
                input="s\ns\ns\ns\ns\n",  # Skip any prompts
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
        """Parse beets output to extract match candidates with MusicBrainz IDs."""
        candidates = []
        lines = output.split('\n')
        
        current_candidate = {}
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # Look for MusicBrainz URL (contains the release ID)
            if 'musicbrainz.org/release/' in line.lower():
                mb_match = cls.MB_ID_PATTERN.search(line)
                if mb_match:
                    current_candidate['mb_id'] = mb_match.group(0)
                    current_candidate['mb_url'] = f"https://musicbrainz.org/release/{mb_match.group(0)}"
            
            # Look for similarity percentage - various formats beets uses
            # Format 1: "(Similarity: 95.2%)"
            # Format 2: "95.2% similar"
            # Format 3: "(95.2%)"
            similarity_match = re.search(r'\(Similarity:\s*(\d+\.?\d*)%\)', line_stripped)
            if not similarity_match:
                similarity_match = re.search(r'(\d+\.?\d*)%\s*similar', line_stripped)
            if not similarity_match:
                similarity_match = re.search(r'\((\d+\.?\d*)%\)', line_stripped)
            
            if similarity_match:
                try:
                    similarity = float(similarity_match.group(1))
                    distance = 1.0 - (similarity / 100.0)
                    current_candidate['distance'] = distance
                    
                    # Try to extract artist - album from the same line
                    # Remove the similarity part and parse the rest
                    rest = re.sub(r'\(Similarity:\s*\d+\.?\d*%\)', '', line_stripped)
                    rest = re.sub(r'\(\d+\.?\d*%\)', '', rest)
                    rest = rest.strip()
                    
                    if ' - ' in rest:
                        parts = rest.split(' - ', 1)
                        current_candidate['artist'] = parts[0].strip()
                        album_part = parts[1]
                        
                        # Parse album, year, tracks from "Album, 2020, 12 tracks"
                        album_parts = album_part.split(', ')
                        current_candidate['album'] = album_parts[0].strip()
                        
                        for part in album_parts[1:]:
                            part = part.strip()
                            if part.isdigit() and len(part) == 4:
                                current_candidate['year'] = int(part)
                            elif 'track' in part.lower():
                                try:
                                    current_candidate['tracks'] = int(part.split()[0])
                                except:
                                    pass
                    
                    # If we have enough info, create a candidate
                    if 'artist' in current_candidate and 'album' in current_candidate:
                        candidate = BeetsCandidate(
                            id=current_candidate.get('mb_id', f"unknown_{hash(str(current_candidate))}"),
                            artist=current_candidate['artist'],
                            album=current_candidate['album'],
                            year=current_candidate.get('year'),
                            tracks=current_candidate.get('tracks', 0),
                            distance=current_candidate['distance'],
                            musicbrainz_url=current_candidate.get('mb_url')
                        )
                        candidates.append(candidate)
                        current_candidate = {}  # Reset for next candidate
                        
                except Exception as e:
                    print(f"beets: Error parsing similarity line '{line_stripped}': {e}")
            
            # Also try to catch "Tagging:" section which indicates the recommended match
            if line_stripped.startswith('Tagging:'):
                # Next non-empty line should be "Artist - Album"
                for j in range(i + 1, min(i + 5, len(lines))):
                    next_line = lines[j].strip()
                    if next_line and ' - ' in next_line:
                        parts = next_line.split(' - ', 1)
                        if len(parts) == 2:
                            current_candidate['artist'] = parts[0].strip()
                            current_candidate['album'] = parts[1].strip()
                        break
        
        # Sort by confidence (lowest distance first)
        candidates.sort(key=lambda c: c.distance)
        
        # Remove duplicates based on MB ID
        seen_ids = set()
        unique_candidates = []
        for c in candidates:
            if c.id not in seen_ids:
                seen_ids.add(c.id)
                unique_candidates.append(c)
        
        return unique_candidates
    
    @classmethod
    def apply_tags(cls, folder_path: str, match_id: Optional[str] = None, 
                   library_path: str = "/music") -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Apply beets tagging to an album folder.
        
        Args:
            folder_path: Path to album folder
            match_id: MusicBrainz release or release-group ID to use
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
            # Build command - use --search-id if we have a MusicBrainz ID
            cmd = ["beet", "-c", config_path, "import", "-q", "--flat"]
            
            if match_id:
                # Use the specific MusicBrainz ID for matching
                cmd.extend(["--search-id", match_id])
                print(f"beets: Using MusicBrainz ID for tagging: {match_id}")
            
            cmd.append(folder_path)
            
            print(f"beets: Running command: {' '.join(cmd)}")
            
            # Run beets import with auto-tagging
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                input="s\ns\ns\n",  # Skip any unexpected prompts
                timeout=180,
                env={**os.environ, "BEETSDIR": "/tmp"}
            )
            
            full_output = result.stdout + "\n" + result.stderr
            print(f"beets: Apply output:\n{full_output[:2000]}")
            
            # Try to extract what was applied
            mb_match = cls.MB_ID_PATTERN.search(full_output)
            if match_id:
                # We used a specific ID, use that
                applied_info = {
                    "musicbrainz_id": match_id,
                    "musicbrainz_url": f"https://musicbrainz.org/release-group/{match_id}",
                    "status": "applied"
                }
            elif mb_match:
                applied_info = {
                    "musicbrainz_id": mb_match.group(0),
                    "musicbrainz_url": f"https://musicbrainz.org/release/{mb_match.group(0)}",
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
