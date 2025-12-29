"""Service for fetching concerts from Bandsintown API."""

import httpx
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import distinct

from app.models import Artist, Album, Concert, ConcertScrapeStatus
from app.config import get_settings


class BandsintownService:
    """Service for fetching concerts from Bandsintown."""
    
    BASE_URL = "https://rest.bandsintown.com"
    
    def __init__(self, db: Session):
        self.db = db
        settings = get_settings()
        self.api_key = getattr(settings, 'bandsintown_api_key', '')
    
    def get_or_create_scrape_status(self) -> ConcertScrapeStatus:
        """Get or create the scrape status record."""
        status = self.db.query(ConcertScrapeStatus).first()
        if not status:
            status = ConcertScrapeStatus(status="idle")
            self.db.add(status)
            self.db.commit()
            self.db.refresh(status)
        return status
    
    def get_library_artists(self) -> List[Artist]:
        """Get all artists that have owned albums."""
        # Get artist IDs that have at least one owned album
        artist_ids_with_owned = (
            self.db.query(distinct(Album.artist_id))
            .filter(Album.is_owned == True, Album.artist_id != None)
            .all()
        )
        artist_ids = [aid[0] for aid in artist_ids_with_owned]
        
        return self.db.query(Artist).filter(Artist.id.in_(artist_ids)).all()
    
    def fetch_artist_events(self, artist_name: str) -> List[Dict[str, Any]]:
        """Fetch upcoming events for an artist from Bandsintown."""
        if not self.api_key:
            print("[CONCERTS] No Bandsintown API key configured")
            return []
        
        # URL encode the artist name
        import urllib.parse
        encoded_name = urllib.parse.quote(artist_name)
        
        url = f"{self.BASE_URL}/artists/{encoded_name}/events"
        params = {
            "app_id": self.api_key,
            "date": "upcoming"
        }
        
        try:
            response = httpx.get(url, params=params, timeout=30)
            
            if response.status_code == 404:
                # Artist not found on Bandsintown
                return []
            
            if response.status_code != 200:
                print(f"[CONCERTS] Bandsintown error for '{artist_name}': {response.status_code}")
                return []
            
            data = response.json()
            
            # Bandsintown returns an error object if artist not found
            if isinstance(data, dict) and data.get("errorMessage"):
                return []
            
            return data if isinstance(data, list) else []
            
        except Exception as e:
            print(f"[CONCERTS] Error fetching events for '{artist_name}': {e}")
            return []
    
    def scrape_concerts(self) -> Dict[str, Any]:
        """Scrape concerts for all library artists."""
        status = self.get_or_create_scrape_status()
        
        if not self.api_key:
            status.status = "error"
            status.error_message = "No Bandsintown API key configured. Set BANDSINTOWN_API_KEY in environment."
            self.db.commit()
            return {"status": "error", "message": status.error_message}
        
        # Update status
        status.status = "scraping"
        status.last_scrape_at = datetime.utcnow()
        status.error_message = None
        self.db.commit()
        
        try:
            # Get library artists
            artists = self.get_library_artists()
            total_artists = len(artists)
            
            print(f"[CONCERTS] Checking {total_artists} artists for upcoming concerts...")
            
            status.total_artists = total_artists
            status.artists_checked = 0
            status.current_artist = 0
            status.concerts_found = 0
            self.db.commit()
            
            concerts_added = 0
            
            for idx, artist in enumerate(artists, 1):
                status.current_artist = idx
                status.artists_checked = idx
                
                # Update progress every 5 artists
                if idx % 5 == 0 or idx == 1:
                    self.db.commit()
                    print(f"[CONCERTS] Checking artist {idx}/{total_artists}: {artist.name}")
                
                # Fetch events from Bandsintown
                events = self.fetch_artist_events(artist.name)
                
                for event in events:
                    try:
                        event_id = str(event.get("id", ""))
                        if not event_id:
                            continue
                        
                        # Check if we already have this concert
                        existing = self.db.query(Concert).filter(
                            Concert.bandsintown_id == event_id
                        ).first()
                        
                        if existing:
                            # Update existing concert info
                            existing.ticket_url = event.get("url")
                            continue
                        
                        # Parse event date
                        event_datetime = None
                        if event.get("datetime"):
                            try:
                                event_datetime = datetime.fromisoformat(
                                    event["datetime"].replace("Z", "+00:00")
                                )
                            except:
                                pass
                        
                        if not event_datetime:
                            continue
                        
                        # Get venue info
                        venue = event.get("venue", {})
                        
                        # Get lineup (other artists)
                        lineup_artists = event.get("lineup", [])
                        lineup = ", ".join(lineup_artists) if lineup_artists else None
                        
                        # Create new concert
                        concert = Concert(
                            bandsintown_id=event_id,
                            artist_id=artist.id,
                            artist_name=artist.name,
                            event_date=event_datetime,
                            venue_name=venue.get("name"),
                            venue_city=venue.get("city"),
                            venue_region=venue.get("region"),
                            venue_country=venue.get("country"),
                            ticket_url=event.get("url"),
                            event_url=event.get("url"),
                            lineup=lineup,
                            description=event.get("description")
                        )
                        self.db.add(concert)
                        concerts_added += 1
                        
                    except Exception as e:
                        print(f"[CONCERTS] Error processing event: {e}")
                        continue
                
                # Rate limiting - Bandsintown recommends 1 request per second
                time.sleep(1)
            
            self.db.commit()
            
            # Update status
            status.status = "completed"
            status.concerts_found = concerts_added
            self.db.commit()
            
            print(f"[CONCERTS] Scrape completed: {total_artists} artists, {concerts_added} concerts added")
            
            return {
                "status": "completed",
                "artists_checked": total_artists,
                "concerts_found": concerts_added
            }
            
        except Exception as e:
            import traceback
            print(f"[CONCERTS] Scrape failed: {e}")
            print(f"[CONCERTS] Traceback: {traceback.format_exc()}")
            status.status = "error"
            status.error_message = str(e)
            self.db.commit()
            return {"status": "error", "message": str(e)}
    
    def get_concerts(self, limit: int = 50, skip: int = 0) -> List[Concert]:
        """Get upcoming concerts, sorted by date."""
        now = datetime.utcnow()
        return (
            self.db.query(Concert)
            .filter(Concert.event_date >= now)
            .order_by(Concert.event_date.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def delete_past_concerts(self) -> int:
        """Delete concerts that have already happened."""
        now = datetime.utcnow()
        deleted = self.db.query(Concert).filter(Concert.event_date < now).delete()
        self.db.commit()
        return deleted

