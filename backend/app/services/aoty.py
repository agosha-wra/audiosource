"""Service for scraping Album of the Year (AOTY) for new releases and enrichment."""

import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re
import logging
import time
import urllib.parse
from sqlalchemy.orm import Session

from app.models import NewRelease, NewReleasesScrapeStatus, AOTYEnrichmentStatus, Album, Artist

logger = logging.getLogger(__name__)


class AOTYService:
    """Service for scraping AOTY weekly releases."""
    
    BASE_URL = "https://www.albumoftheyear.org"
    
    def __init__(self, db: Session):
        self.db = db
    
    def _create_scraper(self):
        """Create a cloudscraper instance."""
        return cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
    
    def get_or_create_scrape_status(self) -> NewReleasesScrapeStatus:
        """Get or create the scrape status record."""
        status = self.db.query(NewReleasesScrapeStatus).first()
        if not status:
            status = NewReleasesScrapeStatus(
                status="idle",
                next_scrape_at=datetime.utcnow()
            )
            self.db.add(status)
            self.db.commit()
            self.db.refresh(status)
        return status
    
    def get_current_week(self) -> tuple[int, int]:
        """Get current year and ISO week number."""
        now = datetime.utcnow()
        iso_calendar = now.isocalendar()
        return iso_calendar[0], iso_calendar[1]
    
    def scrape_weekly_releases(
        self,
        year: Optional[int] = None,
        week: Optional[int] = None
    ) -> Dict[str, Any]:
        """Scrape the weekly releases from AOTY."""
        status = self.get_or_create_scrape_status()
        
        if status.status == "scraping":
            return {"status": "already_scraping", "message": "Scrape already in progress"}
        
        if year is None or week is None:
            year, week = self.get_current_week()
        
        status.status = "scraping"
        status.last_scrape_at = datetime.utcnow()
        status.error_message = None
        self.db.commit()
        
        try:
            url = f"{self.BASE_URL}/week/{year}/{week}/releases/?sort=popular"
            logger.info(f"[AOTY] Scraping {url}")
            
            scraper = self._create_scraper()
            response = scraper.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "lxml")
            albums_found = 0
            album_blocks = soup.select(".albumBlock")
            
            for block in album_blocks:
                try:
                    release_data = self._parse_album_block(block, year, week)
                    if release_data:
                        self._save_release(release_data)
                        albums_found += 1
                except Exception as e:
                    logger.warning(f"[AOTY] Error parsing album block: {e}")
            
            status.status = "completed"
            status.albums_found = albums_found
            status.next_scrape_at = datetime.utcnow() + timedelta(hours=24)
            self.db.commit()
            
            return {"status": "completed", "albums_found": albums_found, "year": year, "week": week}
            
        except Exception as e:
            logger.error(f"[AOTY] Scrape failed: {e}")
            status.status = "error"
            status.error_message = str(e)
            self.db.commit()
            return {"status": "error", "message": str(e)}
    
    def _parse_album_block(self, block, year: int, week: int) -> Optional[Dict[str, Any]]:
        """Parse a single album block from AOTY."""
        try:
            title_elem = block.select_one(".albumTitle")
            if not title_elem:
                return None
            
            album_title = title_elem.get_text(strip=True)
            if not album_title:
                return None
            
            album_link = ""
            parent = title_elem.parent
            if parent and parent.name == "a":
                album_link = parent.get("href", "")
            if not album_link:
                img_link = block.select_one(".image a")
                if img_link:
                    album_link = img_link.get("href", "")
            if not album_link:
                return None
            
            aoty_url = f"{self.BASE_URL}{album_link}" if album_link.startswith("/") else album_link
            
            artist_elem = block.select_one(".artistTitle")
            artist_name = artist_elem.get_text(strip=True) if artist_elem else "Unknown Artist"
            
            cover_art_url = None
            img_elem = block.select_one(".image img")
            if img_elem:
                srcset = img_elem.get("srcset", "")
                cover_art_url = srcset.split(" ")[0] if srcset else img_elem.get("src")
            
            release_date = None
            release_type = "LP"
            type_elem = block.select_one(".type")
            if type_elem:
                type_text = type_elem.get_text(strip=True)
                if "•" in type_text:
                    parts = type_text.split("•")
                    release_date = parts[0].strip()
                    release_type = parts[1].strip() if len(parts) > 1 else "LP"
                else:
                    release_date = type_text
            
            critic_score = None
            score_elem = block.select_one(".ratingRow .rating, .rating")
            if score_elem:
                try:
                    critic_score = int(score_elem.get_text(strip=True))
                except ValueError:
                    pass
            
            num_critics = None
            for rt in block.select(".ratingText"):
                match = re.search(r"\((\d+)\)", rt.get_text(strip=True))
                if match:
                    num_critics = int(match.group(1))
                    break
            
            return {
                "artist_name": artist_name, "album_title": album_title,
                "release_date": release_date, "release_type": release_type,
                "aoty_url": aoty_url, "cover_art_url": cover_art_url,
                "critic_score": critic_score, "num_critics": num_critics,
                "week_year": year, "week_number": week
            }
        except Exception as e:
            logger.warning(f"[AOTY] Error parsing album block: {e}")
            return None
    
    def _save_release(self, data: Dict[str, Any]) -> NewRelease:
        """Save or update a release in the database."""
        existing = self.db.query(NewRelease).filter(NewRelease.aoty_url == data["aoty_url"]).first()
        if existing:
            existing.critic_score = data["critic_score"]
            existing.num_critics = data["num_critics"]
            existing.scraped_at = datetime.utcnow()
            self.db.commit()
            return existing
        
        release = NewRelease(**data)
        self.db.add(release)
        self.db.commit()
        self.db.refresh(release)
        return release
    
    def get_releases(self, year: Optional[int] = None, week: Optional[int] = None, limit: int = 50) -> List[NewRelease]:
        """Get releases from the database."""
        query = self.db.query(NewRelease)
        if year:
            query = query.filter(NewRelease.week_year == year)
        if week:
            query = query.filter(NewRelease.week_number == week)
        return query.order_by(
            NewRelease.critic_score.desc().nullslast(),
            NewRelease.num_critics.desc().nullslast()
        ).limit(limit).all()
    
    def get_latest_releases(self, limit: int = 50) -> List[NewRelease]:
        """Get the latest week's releases."""
        latest = self.db.query(NewRelease).order_by(
            NewRelease.week_year.desc(), NewRelease.week_number.desc()
        ).first()
        if not latest:
            return []
        return self.get_releases(year=latest.week_year, week=latest.week_number, limit=limit)
    
    # ============ AOTY Enrichment Methods ============
    
    def get_or_create_enrichment_status(self) -> AOTYEnrichmentStatus:
        """Get or create the AOTY enrichment status record."""
        status = self.db.query(AOTYEnrichmentStatus).first()
        if not status:
            status = AOTYEnrichmentStatus(status="idle", albums_enriched=0, total_albums_enriched=0)
            self.db.add(status)
            self.db.commit()
            self.db.refresh(status)
        return status
    
    def search_artist_on_aoty(self, artist_name: str, max_candidates: int = 3) -> List[str]:
        """
        Search for an artist on AOTY and return up to max_candidates artist page URLs.
        Returns list of URL paths like ["/artist/68701-geese/", "/artist/123-geese/"].
        Returns multiple candidates for generic names that might have multiple matches.
        """
        try:
            encoded_query = urllib.parse.quote(artist_name)
            search_url = f"{self.BASE_URL}/search/artists/?q={encoded_query}"
            
            logger.info(f"[AOTY] Searching for artist: {artist_name} (up to {max_candidates} candidates)")
            
            scraper = self._create_scraper()
            response = scraper.get(search_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "lxml")
            artist_links = soup.select("a[href*='/artist/']")
            
            if not artist_links:
                logger.info(f"[AOTY] No artist results found for: {artist_name}")
                return []
            
            artist_lower = artist_name.lower().strip()
            candidates = []
            seen_urls = set()
            
            for link in artist_links:
                link_text = link.get_text(strip=True).lower()
                href = link.get("href", "")
                
                if not href or "/artist/" not in href:
                    continue
                
                # Skip duplicates
                if href in seen_urls:
                    continue
                
                # Check if name matches
                if (artist_lower == link_text or 
                    artist_lower in link_text or 
                    link_text in artist_lower or
                    self._fuzzy_match(artist_lower, link_text, threshold=0.8)):
                    candidates.append(href)
                    seen_urls.add(href)
                    logger.info(f"[AOTY] Found artist candidate {len(candidates)}: {href}")
                    
                    if len(candidates) >= max_candidates:
                        break
            
            if not candidates:
                logger.info(f"[AOTY] No matching artist found for: {artist_name}")
            
            return candidates
            
        except Exception as e:
            logger.error(f"[AOTY] Artist search error for {artist_name}: {e}")
            return []
    
    def scrape_artist_discography(self, artist_url: str) -> List[Dict[str, Any]]:
        """
        Scrape an artist's page to get all their albums with scores.
        Returns list of dicts with title, aoty_url, and critic_score.
        """
        try:
            full_url = f"{self.BASE_URL}{artist_url}" if artist_url.startswith("/") else artist_url
            logger.info(f"[AOTY] Scraping artist discography: {full_url}")
            
            scraper = self._create_scraper()
            response = scraper.get(full_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "lxml")
            albums = []
            
            for block in soup.select(".albumBlock"):
                try:
                    album_data = self._parse_artist_page_album(block)
                    if album_data:
                        albums.append(album_data)
                except Exception as e:
                    logger.warning(f"[AOTY] Error parsing album on artist page: {e}")
            
            logger.info(f"[AOTY] Found {len(albums)} albums on artist page")
            return albums
            
        except Exception as e:
            logger.error(f"[AOTY] Error scraping artist page {artist_url}: {e}")
            return []
    
    def _parse_artist_page_album(self, block) -> Optional[Dict[str, Any]]:
        """Parse an album block from an artist's page."""
        try:
            title_elem = block.select_one(".albumTitle")
            if not title_elem:
                return None
            
            album_title = title_elem.get_text(strip=True)
            if not album_title:
                return None
            
            album_link = ""
            parent = title_elem.parent
            if parent and parent.name == "a":
                album_link = parent.get("href", "")
            if not album_link:
                img_link = block.select_one(".image a")
                if img_link:
                    album_link = img_link.get("href", "")
            if not album_link:
                return None
            
            aoty_url = f"{self.BASE_URL}{album_link}" if album_link.startswith("/") else album_link
            
            critic_score = None
            score_elem = block.select_one(".ratingRow .rating, .rating")
            if score_elem:
                try:
                    critic_score = int(score_elem.get_text(strip=True))
                except ValueError:
                    pass
            
            return {"title": album_title, "aoty_url": aoty_url, "critic_score": critic_score}
            
        except Exception as e:
            logger.warning(f"[AOTY] Error parsing artist page album: {e}")
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
        normalized = re.sub(r'\s*\([^)]*\)\s*$', '', normalized).strip()
        normalized = re.sub(r'[^\w\s]', '', normalized).strip()
        return normalized
    
    def _count_album_matches(self, missing_albums: List[Album], aoty_albums: List[Dict[str, Any]]) -> int:
        """Count how many of our albums match the AOTY discography."""
        matches = 0
        for album in missing_albums:
            album_title_normalized = self._normalize_title(album.title)
            for aoty_album in aoty_albums:
                aoty_title_normalized = self._normalize_title(aoty_album.get("title", ""))
                if (album_title_normalized == aoty_title_normalized or
                    self._fuzzy_match(album_title_normalized, aoty_title_normalized, threshold=0.85)):
                    matches += 1
                    break
        return matches

    def enrich_artist_albums(self, artist: Artist) -> int:
        """
        Enrich all missing albums for an artist with AOTY data.
        Tries multiple artist candidates if the name is generic (e.g., "Amen").
        Picks the artist whose discography best matches our albums.
        """
        missing_albums = self.db.query(Album).filter(
            Album.artist_id == artist.id,
            Album.is_owned == False,
            Album.aoty_url == None
        ).all()
        
        if not missing_albums:
            logger.info(f"[AOTY] No albums to enrich for {artist.name}")
            return 0
        
        logger.info(f"[AOTY] Enriching {len(missing_albums)} albums for {artist.name}")
        
        # Step 1: Search for artist candidates (up to 3 for generic names)
        artist_urls = self.search_artist_on_aoty(artist.name, max_candidates=3)
        
        if not artist_urls:
            logger.info(f"[AOTY] Could not find artist on AOTY: {artist.name}")
            for album in missing_albums:
                album.aoty_url = ""  # Mark as checked
            self.db.commit()
            return 0
        
        # Step 2: Try each artist candidate and find the best match
        best_aoty_albums = None
        best_match_count = 0
        best_artist_url = None
        
        for i, artist_url in enumerate(artist_urls):
            if i > 0:
                time.sleep(1)  # Small delay between requests
            
            logger.info(f"[AOTY] Trying candidate {i+1}/{len(artist_urls)}: {artist_url}")
            aoty_albums = self.scrape_artist_discography(artist_url)
            
            if not aoty_albums:
                continue
            
            # Count how many of our albums match this candidate's discography
            match_count = self._count_album_matches(missing_albums, aoty_albums)
            logger.info(f"[AOTY] Candidate {i+1} has {match_count} matching albums")
            
            if match_count > best_match_count:
                best_match_count = match_count
                best_aoty_albums = aoty_albums
                best_artist_url = artist_url
            
            # If first candidate has good matches, no need to try others
            if match_count >= len(missing_albums) * 0.5:  # 50%+ match rate
                logger.info(f"[AOTY] Good match found on candidate {i+1}, stopping search")
                break
        
        if not best_aoty_albums or best_match_count == 0:
            logger.info(f"[AOTY] No matching albums found for any artist candidate: {artist.name}")
            for album in missing_albums:
                album.aoty_url = ""
            self.db.commit()
            return 0
        
        logger.info(f"[AOTY] Using best candidate: {best_artist_url} with {best_match_count} matches")
        
        # Step 3: Match our missing albums against the best candidate's albums
        enriched_count = 0
        
        for album in missing_albums:
            album_title_normalized = self._normalize_title(album.title)
            matched = False
            
            for aoty_album in best_aoty_albums:
                aoty_title_normalized = self._normalize_title(aoty_album.get("title", ""))
                
                if (album_title_normalized == aoty_title_normalized or
                    self._fuzzy_match(album_title_normalized, aoty_title_normalized, threshold=0.85)):
                    album.aoty_url = aoty_album.get("aoty_url")
                    album.critic_score = aoty_album.get("critic_score")
                    enriched_count += 1
                    matched = True
                    logger.info(f"[AOTY] Enriched: {album.title} (score: {aoty_album.get('critic_score')})")
                    break
            
            if not matched:
                album.aoty_url = ""  # Mark as checked but not found
        
        self.db.commit()
        logger.info(f"[AOTY] Enriched {enriched_count}/{len(missing_albums)} albums for {artist.name}")
        return enriched_count
    
    def run_enrichment_job(self) -> Dict[str, Any]:
        """
        Run the AOTY enrichment job for one artist.
        Called by scheduler every ~10 minutes, processes artists round-robin.
        """
        status = self.get_or_create_enrichment_status()
        
        if status.status == "running":
            return {"status": "already_running", "message": "Enrichment job already in progress"}
        
        status.status = "running"
        status.last_run_at = datetime.utcnow()
        status.error_message = None
        self.db.commit()
        
        try:
            # Find artists with missing albums that need enrichment
            artists_needing_enrichment = self.db.query(Artist).join(Album).filter(
                Album.is_owned == False,
                Album.aoty_url == None
            ).distinct().all()
            
            if not artists_needing_enrichment:
                status.status = "completed"
                status.albums_enriched = 0
                self.db.commit()
                logger.info("[AOTY] No artists need enrichment")
                return {"status": "completed", "message": "No artists need enrichment", "enriched": 0}
            
            # Round-robin: find next artist after last_artist_id
            artist_to_process = None
            if status.last_artist_id:
                for artist in sorted(artists_needing_enrichment, key=lambda a: a.id):
                    if artist.id > status.last_artist_id:
                        artist_to_process = artist
                        break
            
            if not artist_to_process:
                artist_to_process = min(artists_needing_enrichment, key=lambda a: a.id)
            
            logger.info(f"[AOTY] Processing artist: {artist_to_process.name} (ID: {artist_to_process.id})")
            
            enriched = self.enrich_artist_albums(artist_to_process)
            
            status.status = "completed"
            status.last_artist_id = artist_to_process.id
            status.last_artist_name = artist_to_process.name
            status.albums_enriched = enriched
            status.total_albums_enriched = (status.total_albums_enriched or 0) + enriched
            self.db.commit()
            
            logger.info(f"[AOTY] Enrichment completed for {artist_to_process.name}: {enriched} albums enriched")
            
            return {
                "status": "completed",
                "artist": artist_to_process.name,
                "enriched": enriched,
                "total_enriched": status.total_albums_enriched
            }
            
        except Exception as e:
            logger.error(f"[AOTY] Enrichment job error: {e}")
            status.status = "error"
            status.error_message = str(e)
            self.db.commit()
            return {"status": "error", "message": str(e)}
