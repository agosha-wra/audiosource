"""
Beets integration service for checking and applying album metadata.
Uses beets to identify albums and fix tags before importing to library.
"""

import subprocess
import json
import os
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class BeetsCandidate:
    """Represents a potential album match from beets."""
    id: str  # MusicBrainz album ID
    artist: str
    album: str
    year: Optional[int]
    tracks: int
    distance: float  # 0.0 = perfect match, 1.0 = no match
    
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
        }


class BeetsService:
    """Service for interacting with beets for music tagging."""
    
    # Confidence threshold for auto-applying (95%)
    AUTO_APPLY_THRESHOLD = 0.05  # distance <= 0.05 means >= 95% confidence
    
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
    strong_rec_thresh: 0.05
    
plugins: []
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
        
        Args:
            folder_path: Path to the folder containing downloaded files
            library_path: Path to the music library (for beets config)
            
        Returns:
            List of BeetsCandidate objects, sorted by confidence (best first)
        """
        candidates = []
        
        if not os.path.exists(folder_path):
            print(f"beets: Folder not found: {folder_path}")
            return candidates
        
        # Create temporary beets config
        config_path = cls._create_beets_config(library_path)
        
        try:
            # Run beets import in pretend mode with verbose output
            # -p = pretend (don't actually import)
            # -t = timid (always ask, which gives us all candidates in verbose mode)
            result = subprocess.run(
                [
                    "beet", "-c", config_path,
                    "import", "-p", "-t", folder_path
                ],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout
                env={**os.environ, "BEETSDIR": "/tmp"}
            )
            
            # Parse the output to extract candidates
            candidates = cls._parse_beets_output(result.stdout + result.stderr)
            
        except subprocess.TimeoutExpired:
            print(f"beets: Timeout checking {folder_path}")
        except FileNotFoundError:
            print("beets: beet command not found - is beets installed?")
        except Exception as e:
            print(f"beets: Error checking album: {e}")
        finally:
            # Clean up temp config
            try:
                os.unlink(config_path)
            except:
                pass
        
        return candidates
    
    @classmethod
    def _parse_beets_output(cls, output: str) -> List[BeetsCandidate]:
        """Parse beets output to extract match candidates."""
        candidates = []
        
        # Beets output format varies, but typically shows candidates like:
        # Tagging:
        #     Artist - Album
        # (Similarity: 95.2%) Artist - Album, 2020, 12 tracks
        # ...
        
        lines = output.split('\n')
        current_similarity = None
        
        for line in lines:
            line = line.strip()
            
            # Look for similarity percentage
            if '(Similarity:' in line:
                try:
                    # Extract similarity percentage
                    sim_start = line.find('(Similarity:') + len('(Similarity:')
                    sim_end = line.find('%', sim_start)
                    similarity = float(line[sim_start:sim_end].strip())
                    distance = 1.0 - (similarity / 100.0)
                    
                    # Extract rest of info after the percentage
                    rest = line[sim_end + 2:].strip()  # Skip "%) "
                    
                    # Parse "Artist - Album, Year, N tracks" or similar
                    parts = rest.split(' - ', 1)
                    if len(parts) >= 2:
                        artist = parts[0].strip()
                        album_info = parts[1]
                        
                        # Try to extract year and tracks
                        album_parts = album_info.split(', ')
                        album = album_parts[0].strip()
                        year = None
                        tracks = 0
                        
                        for part in album_parts[1:]:
                            part = part.strip()
                            if part.isdigit() and len(part) == 4:
                                year = int(part)
                            elif 'track' in part.lower():
                                try:
                                    tracks = int(part.split()[0])
                                except:
                                    pass
                        
                        # Generate a pseudo-ID (in real implementation would extract MB ID)
                        candidate_id = f"mb_{hash(f'{artist}_{album}_{year}')}"
                        
                        candidates.append(BeetsCandidate(
                            id=candidate_id,
                            artist=artist,
                            album=album,
                            year=year,
                            tracks=tracks,
                            distance=distance
                        ))
                except Exception as e:
                    print(f"beets: Error parsing line '{line}': {e}")
                    continue
            
            # Also look for "Finding tags for..." or track listing patterns
            elif line.startswith('Finding tags for'):
                # This just indicates the album being checked
                pass
        
        # Sort by confidence (lowest distance first)
        candidates.sort(key=lambda c: c.distance)
        
        return candidates
    
    @classmethod
    def apply_tags(cls, folder_path: str, match_id: Optional[str] = None, 
                   library_path: str = "/music") -> bool:
        """
        Apply beets tagging to an album folder.
        
        Args:
            folder_path: Path to the folder containing files to tag
            match_id: Optional specific match ID to use (not yet implemented)
            library_path: Path to the music library
            
        Returns:
            True if tagging was successful, False otherwise
        """
        if not os.path.exists(folder_path):
            print(f"beets: Folder not found: {folder_path}")
            return False
        
        # Create temporary beets config
        config_path = cls._create_beets_config(library_path)
        
        try:
            # Run beets import with auto-tagging
            # -q = quiet (accept best match automatically)
            # --flat = don't create subdirectories
            result = subprocess.run(
                [
                    "beet", "-c", config_path,
                    "import", "-q", "--flat", folder_path
                ],
                capture_output=True,
                text=True,
                timeout=180,  # 3 minute timeout
                env={**os.environ, "BEETSDIR": "/tmp"}
            )
            
            if result.returncode == 0:
                print(f"beets: Successfully tagged {folder_path}")
                return True
            else:
                print(f"beets: Tagging failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"beets: Timeout tagging {folder_path}")
            return False
        except FileNotFoundError:
            print("beets: beet command not found - is beets installed?")
            return False
        except Exception as e:
            print(f"beets: Error applying tags: {e}")
            return False
        finally:
            # Clean up temp config and database
            try:
                os.unlink(config_path)
                os.unlink("/tmp/beets_temp.db")
            except:
                pass
    
    @classmethod
    def should_auto_apply(cls, candidates: List[BeetsCandidate]) -> bool:
        """
        Determine if we should auto-apply tags based on match confidence.
        
        Returns True if:
        - There's exactly one candidate with >= 95% confidence
        - Or the best candidate has >= 95% confidence and is clearly better than others
        """
        if not candidates:
            return False
        
        best = candidates[0]
        
        # Check if best match meets threshold
        if best.distance > cls.AUTO_APPLY_THRESHOLD:
            return False
        
        # If there's only one candidate, auto-apply
        if len(candidates) == 1:
            return True
        
        # If best is significantly better than second best (>10% difference), auto-apply
        second = candidates[1]
        if second.distance - best.distance >= 0.10:
            return True
        
        # Multiple close candidates - let user choose
        return False
