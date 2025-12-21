"""Service for scraping Album of the Year (AOTY) for new releases."""

import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import re
from sqlalchemy.orm import Session

from app.models import NewRelease, NewReleasesScrapeStatus


class AOTYService:
    """Service for scraping AOTY weekly releases."""
    
    BASE_URL = "https://www.albumoftheyear.org"
    USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    
    def __init__(self, db: Session):
        self.db = db
    
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
        """
        Scrape the weekly releases from AOTY.
        
        Args:
            year: Year to scrape (default: current year)
            week: Week number to scrape (default: current week)
        
        Returns:
            Dict with scrape results
        """
        status = self.get_or_create_scrape_status()
        
        # If already scraping, return current status
        if status.status == "scraping":
            return {"status": "already_scraping", "message": "Scrape already in progress"}
        
        # Set defaults
        if year is None or week is None:
            year, week = self.get_current_week()
        
        # Update status to scraping
        status.status = "scraping"
        status.last_scrape_at = datetime.utcnow()
        status.error_message = None
        self.db.commit()
        
        try:
            # Construct URL
            url = f"{self.BASE_URL}/week/{year}/{week}/releases/?sort=critic"
            
            # Make request
            headers = {"User-Agent": self.USER_AGENT}
            response = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, "lxml")
            
            # Find all album blocks
            albums_found = 0
            album_blocks = soup.select(".albumBlock")
            
            for block in album_blocks:
                try:
                    release_data = self._parse_album_block(block, year, week)
                    if release_data:
                        self._save_release(release_data)
                        albums_found += 1
                except Exception as e:
                    print(f"Error parsing album block: {e}")
                    continue
            
            # Update status
            status.status = "completed"
            status.albums_found = albums_found
            status.next_scrape_at = datetime.utcnow() + timedelta(hours=24)
            self.db.commit()
            
            return {
                "status": "completed",
                "albums_found": albums_found,
                "year": year,
                "week": week
            }
            
        except Exception as e:
            status.status = "error"
            status.error_message = str(e)
            self.db.commit()
            return {"status": "error", "message": str(e)}
    
    def _parse_album_block(
        self, 
        block, 
        year: int, 
        week: int
    ) -> Optional[Dict[str, Any]]:
        """Parse a single album block from AOTY."""
        try:
            # Get album title element
            title_elem = block.select_one(".albumTitle")
            if not title_elem:
                return None
            
            album_title = title_elem.get_text(strip=True)
            if not album_title:
                return None
            
            # Get album link from parent anchor or image anchor
            album_link = ""
            
            # Try to find the link that wraps the title
            parent = title_elem.parent
            if parent and parent.name == "a":
                album_link = parent.get("href", "")
            
            # Alternatively, try the image link
            if not album_link:
                img_link = block.select_one(".image a")
                if img_link:
                    album_link = img_link.get("href", "")
            
            if not album_link:
                return None
            
            # Full URL
            aoty_url = f"{self.BASE_URL}{album_link}" if album_link.startswith("/") else album_link
            
            # Get artist name
            artist_elem = block.select_one(".artistTitle")
            artist_name = artist_elem.get_text(strip=True) if artist_elem else "Unknown Artist"
            
            # Get cover art from image
            cover_art_url = None
            img_elem = block.select_one(".image img")
            if img_elem:
                # Try srcset first for higher quality, then src
                srcset = img_elem.get("srcset", "")
                if srcset:
                    # Get the 2x image from srcset
                    cover_art_url = srcset.split(" ")[0]
                else:
                    cover_art_url = img_elem.get("src")
            
            # Get release date and type from .type element
            release_date = None
            release_type = "LP"
            type_elem = block.select_one(".type")
            if type_elem:
                type_text = type_elem.get_text(strip=True)
                # Parse "Oct 31 • Box Set" format
                if "•" in type_text:
                    parts = type_text.split("•")
                    release_date = parts[0].strip()
                    release_type = parts[1].strip() if len(parts) > 1 else "LP"
                else:
                    release_date = type_text
            
            # Get critic score
            critic_score = None
            score_elem = block.select_one(".ratingRow .rating, .rating")
            if score_elem:
                score_text = score_elem.get_text(strip=True)
                try:
                    critic_score = int(score_text)
                except ValueError:
                    pass
            
            # Get number of critics from ratingText
            num_critics = None
            rating_texts = block.select(".ratingText")
            for rt in rating_texts:
                text = rt.get_text(strip=True)
                # Look for "(13)" format
                match = re.search(r"\((\d+)\)", text)
                if match:
                    num_critics = int(match.group(1))
                    break
            
            return {
                "artist_name": artist_name,
                "album_title": album_title,
                "release_date": release_date,
                "release_type": release_type,
                "aoty_url": aoty_url,
                "cover_art_url": cover_art_url,
                "critic_score": critic_score,
                "num_critics": num_critics,
                "week_year": year,
                "week_number": week
            }
            
        except Exception as e:
            print(f"Error parsing album block: {e}")
            return None
    
    def _save_release(self, data: Dict[str, Any]) -> NewRelease:
        """Save or update a release in the database."""
        # Check if release already exists (by AOTY URL)
        existing = self.db.query(NewRelease).filter(
            NewRelease.aoty_url == data["aoty_url"]
        ).first()
        
        if existing:
            # Update existing record
            existing.critic_score = data["critic_score"]
            existing.num_critics = data["num_critics"]
            existing.scraped_at = datetime.utcnow()
            self.db.commit()
            return existing
        
        # Create new record
        release = NewRelease(
            artist_name=data["artist_name"],
            album_title=data["album_title"],
            release_date=data["release_date"],
            release_type=data["release_type"],
            aoty_url=data["aoty_url"],
            cover_art_url=data["cover_art_url"],
            critic_score=data["critic_score"],
            num_critics=data["num_critics"],
            week_year=data["week_year"],
            week_number=data["week_number"]
        )
        self.db.add(release)
        self.db.commit()
        self.db.refresh(release)
        return release
    
    def get_releases(
        self,
        year: Optional[int] = None,
        week: Optional[int] = None,
        limit: int = 50
    ) -> List[NewRelease]:
        """
        Get releases from the database.
        
        Args:
            year: Filter by year
            week: Filter by week
            limit: Maximum number of results
        
        Returns:
            List of NewRelease objects sorted by critic score
        """
        query = self.db.query(NewRelease)
        
        if year:
            query = query.filter(NewRelease.week_year == year)
        if week:
            query = query.filter(NewRelease.week_number == week)
        
        # Sort by critic score descending, then by num_critics
        return query.order_by(
            NewRelease.critic_score.desc().nullslast(),
            NewRelease.num_critics.desc().nullslast()
        ).limit(limit).all()
    
    def get_latest_releases(self, limit: int = 50) -> List[NewRelease]:
        """Get the latest week's releases."""
        # Find the most recent week we have data for
        latest = self.db.query(NewRelease).order_by(
            NewRelease.week_year.desc(),
            NewRelease.week_number.desc()
        ).first()
        
        if not latest:
            return []
        
        return self.get_releases(
            year=latest.week_year,
            week=latest.week_number,
            limit=limit
        )
