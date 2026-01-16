"""Service for scraping Rate Your Music (RYM) for album scores."""

import cloudscraper
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
import re
import logging
import time
import urllib.parse
from sqlalchemy.orm import Session

from app.models import Album, Artist

logger = logging.getLogger(__name__)


class RYMService:
    """Service for scraping RYM album ratings."""
    
    BASE_URL = "https://rateyourmusic.com"
    
    def __init__(self, db: Session):
        self.db = db
        self._scraper = None
    
    def _create_scraper(self):
        """Create a cloudscraper instance with browser-like headers."""
        if self._scraper is None:
            self._scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True
                }
            )
            # Add extra headers to look more like a real browser
            self._scraper.headers.update({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            })
        return self._scraper
    
    def search_artist_on_rym(self, artist_name: str, max_candidates: int = 3) -> List[str]:
        """
        Search for an artist on RYM and return up to max_candidates artist page URLs.
        Returns list of URL paths like ["/artist/radiohead", "/artist/radiohead-1"].
        """
        try:
            # RYM search URL format
            encoded_query = urllib.parse.quote(artist_name)
            search_url = f"{self.BASE_URL}/search?searchterm={encoded_query}&searchtype=a"
            
            logger.info(f"[RYM] Searching for artist: {artist_name} (up to {max_candidates} candidates)")
            
            scraper = self._create_scraper()
            
            # Add delay to be respectful
            time.sleep(2)
            
            response = scraper.get(search_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "lxml")
            
            # Look for artist links in search results
            # RYM search results have artist links in various formats
            candidates = []
            seen_urls = set()
            artist_lower = artist_name.lower().strip()
            
            # Try finding artist links in search results
            for link in soup.select("a.searchpage"):
                href = link.get("href", "")
                if "/artist/" not in href:
                    continue
                
                link_text = link.get_text(strip=True).lower()
                
                if href in seen_urls:
                    continue
                
                # Check if name matches
                if (artist_lower == link_text or 
                    artist_lower in link_text or 
                    link_text in artist_lower or
                    self._fuzzy_match(artist_lower, link_text, threshold=0.8)):
                    candidates.append(href)
                    seen_urls.add(href)
                    logger.info(f"[RYM] Found artist candidate: {href}")
                    
                    if len(candidates) >= max_candidates:
                        break
            
            # Also try the general artist links if searchpage class didn't work
            if not candidates:
                for link in soup.select("a[href*='/artist/']"):
                    href = link.get("href", "")
                    if "/artist/" not in href or href in seen_urls:
                        continue
                    
                    # Skip non-artist pages
                    if "/artist/releases" in href or "/artist/credits" in href:
                        continue
                        
                    link_text = link.get_text(strip=True).lower()
                    
                    if (artist_lower == link_text or 
                        artist_lower in link_text or 
                        link_text in artist_lower or
                        self._fuzzy_match(artist_lower, link_text, threshold=0.8)):
                        candidates.append(href)
                        seen_urls.add(href)
                        logger.info(f"[RYM] Found artist candidate (alt): {href}")
                        
                        if len(candidates) >= max_candidates:
                            break
            
            if not candidates:
                logger.info(f"[RYM] No matching artist found for: {artist_name}")
            
            return candidates
            
        except Exception as e:
            logger.error(f"[RYM] Artist search error for {artist_name}: {e}")
            return []
    
    def scrape_artist_discography(self, artist_url: str) -> List[Dict[str, Any]]:
        """
        Scrape an artist's page to get all their albums with scores.
        Returns list of dicts with title, rym_url, and rym_score (0-100 scale).
        """
        try:
            full_url = f"{self.BASE_URL}{artist_url}" if artist_url.startswith("/") else artist_url
            logger.info(f"[RYM] Scraping artist discography: {full_url}")
            
            scraper = self._create_scraper()
            
            # Add delay to be respectful
            time.sleep(2)
            
            response = scraper.get(full_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "lxml")
            albums = []
            
            # RYM uses a discography section with album entries
            # Look for album entries in the discography
            for disco_item in soup.select(".disco_release"):
                try:
                    album_data = self._parse_disco_item(disco_item)
                    if album_data:
                        albums.append(album_data)
                except Exception as e:
                    logger.warning(f"[RYM] Error parsing album entry: {e}")
            
            # Also try main album blocks if disco_release didn't work
            if not albums:
                for album_block in soup.select(".album_info, .release"):
                    try:
                        album_data = self._parse_album_block(album_block)
                        if album_data:
                            albums.append(album_data)
                    except Exception as e:
                        logger.warning(f"[RYM] Error parsing album block: {e}")
            
            logger.info(f"[RYM] Found {len(albums)} albums on artist page")
            return albums
            
        except Exception as e:
            logger.error(f"[RYM] Error scraping artist page {artist_url}: {e}")
            return []
    
    def _parse_disco_item(self, item) -> Optional[Dict[str, Any]]:
        """Parse a discography item from an artist's page."""
        try:
            # Get album title
            title_elem = item.select_one(".disco_info a.album, .disco_album_title a, a.album")
            if not title_elem:
                # Try alternative selectors
                title_elem = item.select_one("a[href*='/release/']")
            
            if not title_elem:
                return None
            
            album_title = title_elem.get_text(strip=True)
            if not album_title:
                return None
            
            # Get album URL
            album_link = title_elem.get("href", "")
            if not album_link:
                return None
            
            rym_url = f"{self.BASE_URL}{album_link}" if album_link.startswith("/") else album_link
            
            # Get rating (RYM uses 0-5 scale, we convert to 0-100)
            rym_score = None
            
            # Try various rating selectors
            rating_elem = item.select_one(".disco_avg_rating, .avg_rating, .rating")
            if rating_elem:
                rating_text = rating_elem.get_text(strip=True)
                try:
                    # RYM shows ratings like "3.85" on 5-point scale
                    rating = float(rating_text)
                    if rating <= 5:
                        # Convert 0-5 to 0-100
                        rym_score = int(rating * 20)
                except ValueError:
                    pass
            
            return {
                "title": album_title,
                "rym_url": rym_url,
                "rym_score": rym_score
            }
            
        except Exception as e:
            logger.warning(f"[RYM] Error parsing disco item: {e}")
            return None
    
    def _parse_album_block(self, block) -> Optional[Dict[str, Any]]:
        """Parse an album block (alternative format)."""
        try:
            # Get album title
            title_elem = block.select_one("a.album, a[href*='/release/']")
            if not title_elem:
                return None
            
            album_title = title_elem.get_text(strip=True)
            if not album_title:
                return None
            
            album_link = title_elem.get("href", "")
            if not album_link:
                return None
            
            rym_url = f"{self.BASE_URL}{album_link}" if album_link.startswith("/") else album_link
            
            # Get rating
            rym_score = None
            rating_elem = block.select_one(".avg_rating, .rating")
            if rating_elem:
                rating_text = rating_elem.get_text(strip=True)
                try:
                    rating = float(rating_text)
                    if rating <= 5:
                        rym_score = int(rating * 20)
                except ValueError:
                    pass
            
            return {
                "title": album_title,
                "rym_url": rym_url,
                "rym_score": rym_score
            }
            
        except Exception as e:
            logger.warning(f"[RYM] Error parsing album block: {e}")
            return None
    
    def _fuzzy_match(self, str1: str, str2: str, threshold: float = 0.85) -> bool:
        """Simple fuzzy matching using Jaccard similarity."""
        if not str1 or not str2:
            return False
        s1 = set(str1.lower().replace(' ', ''))
        s2 = set(str2.lower().replace(' ', ''))
        if not s1 or not s2:
            return False
        intersection = len(s1 & s2)
        union = len(s1 | s2)
        return (intersection / union if union > 0 else 0) >= threshold
    
    def _normalize_title(self, title: str) -> str:
        """Normalize an album title for matching."""
        if not title:
            return ""
        normalized = title.lower().strip()
        # Remove common suffixes like (Deluxe Edition)
        normalized = re.sub(r'\s*\([^)]*\)\s*$', '', normalized).strip()
        # Remove special characters
        normalized = re.sub(r'[^\w\s]', '', normalized).strip()
        return normalized
    
    def _count_album_matches(self, missing_albums: List[Album], rym_albums: List[Dict[str, Any]]) -> int:
        """Count how many of our albums match the RYM discography."""
        matches = 0
        for album in missing_albums:
            album_title_normalized = self._normalize_title(album.title)
            for rym_album in rym_albums:
                rym_title_normalized = self._normalize_title(rym_album.get("title", ""))
                if (album_title_normalized == rym_title_normalized or
                    self._fuzzy_match(album_title_normalized, rym_title_normalized, threshold=0.85)):
                    matches += 1
                    break
        return matches
    
    def enrich_artist_albums(self, artist: Artist) -> int:
        """
        Enrich all missing albums for an artist with RYM data.
        Tries multiple artist candidates if the name is generic.
        """
        # Get albums that don't have RYM data yet
        missing_albums = self.db.query(Album).filter(
            Album.artist_id == artist.id,
            Album.is_owned == False,
            Album.rym_url == None
        ).all()
        
        if not missing_albums:
            logger.info(f"[RYM] No albums to enrich for {artist.name}")
            return 0
        
        logger.info(f"[RYM] Enriching {len(missing_albums)} albums for {artist.name}")
        
        # Step 1: Search for artist candidates
        artist_urls = self.search_artist_on_rym(artist.name, max_candidates=3)
        
        if not artist_urls:
            logger.info(f"[RYM] Could not find artist on RYM: {artist.name}")
            for album in missing_albums:
                album.rym_url = ""  # Mark as checked
            self.db.commit()
            return 0
        
        # Step 2: Try each artist candidate and find the best match
        best_rym_albums = None
        best_match_count = 0
        best_artist_url = None
        
        for i, artist_url in enumerate(artist_urls):
            if i > 0:
                time.sleep(2)  # Delay between requests
            
            logger.info(f"[RYM] Trying candidate {i+1}/{len(artist_urls)}: {artist_url}")
            rym_albums = self.scrape_artist_discography(artist_url)
            
            if not rym_albums:
                continue
            
            # Count how many of our albums match this candidate's discography
            match_count = self._count_album_matches(missing_albums, rym_albums)
            logger.info(f"[RYM] Candidate {i+1} has {match_count} matching albums")
            
            if match_count > best_match_count:
                best_match_count = match_count
                best_rym_albums = rym_albums
                best_artist_url = artist_url
            
            # If good match, stop looking
            if match_count >= len(missing_albums) * 0.5:
                logger.info(f"[RYM] Good match found on candidate {i+1}, stopping search")
                break
        
        if not best_rym_albums or best_match_count == 0:
            logger.info(f"[RYM] No matching albums found for any artist candidate: {artist.name}")
            for album in missing_albums:
                album.rym_url = ""
            self.db.commit()
            return 0
        
        logger.info(f"[RYM] Using best candidate: {best_artist_url} with {best_match_count} matches")
        
        # Step 3: Match our missing albums against the best candidate's albums
        enriched_count = 0
        
        for album in missing_albums:
            album_title_normalized = self._normalize_title(album.title)
            matched = False
            
            for rym_album in best_rym_albums:
                rym_title_normalized = self._normalize_title(rym_album.get("title", ""))
                
                if (album_title_normalized == rym_title_normalized or
                    self._fuzzy_match(album_title_normalized, rym_title_normalized, threshold=0.85)):
                    album.rym_url = rym_album.get("rym_url")
                    album.rym_score = rym_album.get("rym_score")
                    enriched_count += 1
                    matched = True
                    logger.info(f"[RYM] Enriched: {album.title} (score: {rym_album.get('rym_score')})")
                    break
            
            if not matched:
                album.rym_url = ""  # Mark as checked but not found
        
        self.db.commit()
        logger.info(f"[RYM] Enriched {enriched_count}/{len(missing_albums)} albums for {artist.name}")
        return enriched_count
