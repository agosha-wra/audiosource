"""Service for fetching concerts by scraping Songkick."""

import cloudscraper
import re
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy import distinct

from app.models import Artist, Album, Concert, ConcertScrapeStatus


class BandsintownService:
    """Service for fetching concerts from Songkick."""
    
    BASE_URL = "https://www.songkick.com"
    
    def __init__(self, db: Session):
        self.db = db
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
        )
    
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
        """Fetch upcoming events for an artist by scraping Songkick."""
        import urllib.parse
        
        # First, search for the artist to get their Songkick URL
        search_url = f"{self.BASE_URL}/search?query={urllib.parse.quote(artist_name)}&type=artists"
        
        try:
            response = self.scraper.get(search_url, timeout=30)
            
            if response.status_code != 200:
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the first artist result in the search component
            search_component = soup.select_one('.component.search')
            if not search_component:
                return []
            
            artist_link = search_component.select_one('a[href*="/artists/"]')
            if not artist_link:
                return []
            
            artist_url = artist_link.get('href')
            if not artist_url.startswith('http'):
                artist_url = f"{self.BASE_URL}{artist_url}"
            
            # Fetch the artist's calendar page
            calendar_url = f"{artist_url}/calendar"
            response = self.scraper.get(calendar_url, timeout=30)
            if response.status_code != 200:
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            events = []
            now = datetime.utcnow()
            
            # Parse event listings
            event_elements = soup.select('.event-listings li.event-listing')
            
            for event_el in event_elements[:20]:  # Limit to 20 events per artist
                try:
                    # Get event link and ID
                    event_link = event_el.select_one('a[href*="/concerts/"]') or event_el.select_one('a[href*="/festivals/"]')
                    if not event_link:
                        continue
                    
                    event_url = event_link.get('href', '')
                    if not event_url.startswith('http'):
                        event_url = f"{self.BASE_URL}{event_url}"
                    
                    # Extract event ID from URL
                    id_match = re.search(r'/(?:concerts|festivals)/(\d+)', event_url)
                    event_id = id_match.group(1) if id_match else None
                    if not event_id:
                        continue
                    
                    # Get date from time element
                    date_el = event_el.select_one('time')
                    event_date = None
                    if date_el:
                        datetime_str = date_el.get('datetime')
                        if datetime_str:
                            try:
                                # Parse the datetime string
                                event_date = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                                # Remove timezone for comparison
                                event_date = event_date.replace(tzinfo=None)
                            except:
                                pass
                    
                    if not event_date:
                        continue
                    
                    # Only include future events
                    if event_date < now:
                        continue
                    
                    # Get venue and location from the event text
                    event_text = event_el.get_text(strip=True)
                    # Text format: "Dec16Copenhagen, DenmarkRoyal Arena"
                    # Try to extract location
                    location_parts = []
                    for part in event_text.split(','):
                        part = re.sub(r'^[A-Za-z]{3}\d+', '', part).strip()
                        if part:
                            location_parts.append(part)
                    
                    city = location_parts[0] if len(location_parts) > 0 else None
                    country = location_parts[1].split()[0] if len(location_parts) > 1 else None
                    venue_name = location_parts[-1] if len(location_parts) > 1 else None
                    
                    events.append({
                        'id': f"sk-{event_id}",
                        'datetime': event_date.isoformat(),
                        'url': event_url,
                        'venue': {
                            'name': venue_name,
                            'city': city,
                            'country': country
                        }
                    })
                    
                except Exception as e:
                    continue
            
            return events
            
        except Exception as e:
            print(f"[CONCERTS] Error fetching events for '{artist_name}': {e}")
            return []
    
    def scrape_concerts(self) -> Dict[str, Any]:
        """Scrape concerts for all library artists."""
        status = self.get_or_create_scrape_status()
        
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
                        
                        # Create new concert
                        concert = Concert(
                            bandsintown_id=event_id,
                            artist_id=artist.id,
                            artist_name=artist.name,
                            event_date=event_datetime,
                            venue_name=venue.get("name"),
                            venue_city=venue.get("city"),
                            venue_country=venue.get("country"),
                            ticket_url=event.get("url"),
                            event_url=event.get("url")
                        )
                        self.db.add(concert)
                        concerts_added += 1
                        
                    except Exception as e:
                        print(f"[CONCERTS] Error processing event: {e}")
                        continue
                
                # Rate limiting for Songkick
                time.sleep(2)
            
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
    
    def get_concerts(self, limit: int = 50, skip: int = 0, city_filter: str = None) -> List[Concert]:
        """Get upcoming concerts, sorted by date, optionally filtered by city."""
        now = datetime.utcnow()
        query = self.db.query(Concert).filter(Concert.event_date >= now)
        
        if city_filter:
            # Case-insensitive city matching
            city_lower = city_filter.lower()
            query = query.filter(
                Concert.venue_city.ilike(f"%{city_lower}%") |
                Concert.venue_country.ilike(f"%{city_lower}%")
            )
        
        return query.order_by(Concert.event_date.asc()).offset(skip).limit(limit).all()
    
    def delete_past_concerts(self) -> int:
        """Delete concerts that have already happened."""
        now = datetime.utcnow()
        deleted = self.db.query(Concert).filter(Concert.event_date < now).delete()
        self.db.commit()
        return deleted

