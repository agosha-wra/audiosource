"""Service for fetching concerts by scraping Songkick."""

import cloudscraper
import re
import time
import unicodedata
from datetime import datetime
from typing import List, Dict, Any, Optional, Set
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy import distinct

from app.models import Artist, Album, Concert, ConcertScrapeStatus
from app.config import get_settings


class BandsintownService:
    """Service for fetching concerts from Songkick."""
    
    BASE_URL = "https://www.songkick.com"
    
    # Mapping of city names to Songkick metro area URLs
    CITY_URLS = {
        "paris": "/metro-areas/28909-france-paris",
        "london": "/metro-areas/24426-uk-london",
        "new york": "/metro-areas/7644-us-new-york-metro-area",
        "los angeles": "/metro-areas/17835-us-los-angeles-metro-area",
        "berlin": "/metro-areas/28443-germany-berlin",
        "tokyo": "/metro-areas/30181-japan-tokyo",
        "sydney": "/metro-areas/26794-australia-sydney",
        "amsterdam": "/metro-areas/31366-netherlands-amsterdam",
        "barcelona": "/metro-areas/28714-spain-barcelona",
        "montreal": "/metro-areas/27376-canada-montreal",
        "toronto": "/metro-areas/27396-canada-toronto",
        "chicago": "/metro-areas/9426-us-chicago-metro-area",
        "san francisco": "/metro-areas/26330-us-sf-bay-area",
        "seattle": "/metro-areas/2846-us-seattle-metro-area",
        "melbourne": "/metro-areas/26791-australia-melbourne",
        "manchester": "/metro-areas/24475-uk-manchester",
        "dublin": "/metro-areas/29314-ireland-dublin",
        "brussels": "/metro-areas/28519-belgium-brussels",
        "lyon": "/metro-areas/28948-france-lyon",
        "marseille": "/metro-areas/28963-france-marseille",
    }
    
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
    
    def _normalize_name(self, name: str) -> str:
        """Normalize artist name for matching."""
        if not name:
            return ""
        name = name.lower()
        name = unicodedata.normalize('NFKD', name)
        name = name.encode('ascii', 'ignore').decode('ascii')
        name = re.sub(r'^the\s+', '', name)
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', ' ', name).strip()
        return name
    
    def _build_artist_lookup(self) -> Dict[str, Artist]:
        """Build a lookup dict of normalized artist names to Artist objects."""
        artists = self.get_library_artists()
        lookup = {}
        for artist in artists:
            normalized = self._normalize_name(artist.name)
            if normalized:
                lookup[normalized] = artist
        return lookup
    
    def _find_matching_artist(self, concert_artist: str, artist_lookup: Dict[str, Artist]) -> Optional[Artist]:
        """Find a matching artist in the library."""
        normalized = self._normalize_name(concert_artist)
        if not normalized:
            return None
        
        # Exact match
        if normalized in artist_lookup:
            return artist_lookup[normalized]
        
        # Check if library artist is contained in concert artist name (for "Artist + Guest" formats)
        for lib_name, artist in artist_lookup.items():
            if lib_name in normalized or normalized in lib_name:
                return artist
        
        return None
    
    def fetch_city_concerts(self, city: str) -> List[Dict[str, Any]]:
        """Fetch all upcoming concerts in a city from Songkick."""
        city_lower = city.lower().strip()
        
        # Get the metro area URL for this city
        metro_url = self.CITY_URLS.get(city_lower)
        
        if not metro_url:
            # Try searching for the city
            import urllib.parse
            search_url = f"{self.BASE_URL}/search?query={urllib.parse.quote(city)}&type=locations"
            print(f"[CONCERTS] City '{city}' not in predefined list, searching...")
            
            try:
                response = self.scraper.get(search_url, timeout=30)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    location_link = soup.select_one('a[href*="/metro-areas/"]')
                    if location_link:
                        metro_url = location_link.get('href')
                        print(f"[CONCERTS] Found metro area: {metro_url}")
            except Exception as e:
                print(f"[CONCERTS] Error searching for city: {e}")
        
        if not metro_url:
            print(f"[CONCERTS] Could not find metro area for '{city}'")
            return []
        
        # Fetch the metro area concerts page
        full_url = f"{self.BASE_URL}{metro_url}" if not metro_url.startswith('http') else metro_url
        print(f"[CONCERTS] Fetching concerts from {full_url}")
        
        all_events = []
        now = datetime.utcnow()
        
        try:
            # Fetch multiple pages of upcoming concerts
            for page in range(1, 4):  # Get first 3 pages
                page_url = f"{full_url}?page={page}" if page > 1 else full_url
                response = self.scraper.get(page_url, timeout=30)
                
                if response.status_code != 200:
                    break
                
                soup = BeautifulSoup(response.text, 'html.parser')
                event_elements = soup.select('.event-listings li.event-listing')
                
                if not event_elements:
                    break
                
                print(f"[CONCERTS] Page {page}: found {len(event_elements)} events")
                
                for event_el in event_elements:
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
                                    event_date = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                                    event_date = event_date.replace(tzinfo=None)
                                except:
                                    pass
                        
                        if not event_date or event_date < now:
                            continue
                        
                        # Get artist name - look for the headline artist
                        artist_el = event_el.select_one('.artists strong, .headliners a, .artists a')
                        artist_name = artist_el.get_text(strip=True) if artist_el else None
                        
                        if not artist_name:
                            # Try to get from event text
                            title_el = event_el.select_one('.artists, .event-title')
                            if title_el:
                                artist_name = title_el.get_text(strip=True).split(' at ')[0].strip()
                        
                        if not artist_name:
                            continue
                        
                        # Get venue info
                        venue_el = event_el.select_one('.venue-name, .location a')
                        venue_name = venue_el.get_text(strip=True) if venue_el else None
                        
                        all_events.append({
                            'id': f"sk-{event_id}",
                            'artist_name': artist_name,
                            'datetime': event_date.isoformat(),
                            'url': event_url,
                            'venue_name': venue_name,
                            'venue_city': city
                        })
                        
                    except Exception as e:
                        continue
                
                time.sleep(1)  # Rate limiting between pages
            
            return all_events
            
        except Exception as e:
            print(f"[CONCERTS] Error fetching city concerts: {e}")
            return []
    
    def scrape_concerts(self) -> Dict[str, Any]:
        """Scrape concerts in the configured city and match against library artists."""
        status = self.get_or_create_scrape_status()
        settings = get_settings()
        city = settings.concert_city
        
        if not city:
            status.status = "error"
            status.error_message = "No CONCERT_CITY configured"
            self.db.commit()
            return {"status": "error", "message": "No CONCERT_CITY configured"}
        
        # Update status
        status.status = "scraping"
        status.last_scrape_at = datetime.utcnow()
        status.error_message = None
        self.db.commit()
        
        try:
            # Build artist lookup
            print(f"[CONCERTS] Building artist lookup from library...")
            artist_lookup = self._build_artist_lookup()
            print(f"[CONCERTS] Found {len(artist_lookup)} artists in library")
            
            # Fetch all concerts in the city
            print(f"[CONCERTS] Fetching concerts in {city}...")
            city_events = self.fetch_city_concerts(city)
            print(f"[CONCERTS] Found {len(city_events)} upcoming concerts in {city}")
            
            status.total_artists = len(city_events)
            status.artists_checked = 0
            status.current_artist = 0
            status.concerts_found = 0
            self.db.commit()
            
            concerts_added = 0
            
            for idx, event in enumerate(city_events, 1):
                status.current_artist = idx
                status.artists_checked = idx
                
                if idx % 20 == 0:
                    self.db.commit()
                    print(f"[CONCERTS] Processing event {idx}/{len(city_events)}")
                
                # Check if this artist is in our library
                concert_artist = event.get('artist_name', '')
                matched_artist = self._find_matching_artist(concert_artist, artist_lookup)
                
                if not matched_artist:
                    continue
                
                print(f"[CONCERTS] MATCH: {concert_artist} -> {matched_artist.name}")
                
                event_id = str(event.get("id", ""))
                if not event_id:
                    continue
                
                # Check if we already have this concert
                existing = self.db.query(Concert).filter(
                    Concert.bandsintown_id == event_id
                ).first()
                
                if existing:
                    existing.ticket_url = event.get("url")
                    continue
                
                # Parse event date
                event_datetime = None
                if event.get("datetime"):
                    try:
                        event_datetime = datetime.fromisoformat(event["datetime"])
                    except:
                        pass
                
                if not event_datetime:
                    continue
                
                # Create new concert
                concert = Concert(
                    bandsintown_id=event_id,
                    artist_id=matched_artist.id,
                    artist_name=matched_artist.name,
                    event_date=event_datetime,
                    venue_name=event.get("venue_name"),
                    venue_city=event.get("venue_city"),
                    ticket_url=event.get("url"),
                    event_url=event.get("url")
                )
                self.db.add(concert)
                concerts_added += 1
            
            self.db.commit()
            
            # Update status
            status.status = "completed"
            status.concerts_found = concerts_added
            self.db.commit()
            
            print(f"[CONCERTS] Scrape completed: {len(city_events)} events checked, {concerts_added} matches found for library artists")
            
            return {
                "status": "completed",
                "events_checked": len(city_events),
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
        """Get upcoming concerts, sorted by date, optionally filtered by city (excluding dismissed)."""
        now = datetime.utcnow()
        query = self.db.query(Concert).filter(
            Concert.event_date >= now,
            Concert.dismissed == False
        )
        
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

