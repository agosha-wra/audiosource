"""Service for scraping r/vinylreleases from Reddit."""

import httpx
import re
import unicodedata
import logging
from datetime import datetime
from typing import List, Dict, Any, Set
from sqlalchemy.orm import Session

from app.models import Artist, VinylRelease, VinylReleasesScrapeStatus

logger = logging.getLogger(__name__)


class RedditService:
    """Service for scraping r/vinylreleases."""
    
    SUBREDDIT_URL = "https://www.reddit.com/r/VinylReleases/new.json"
    HEADERS = {
        "User-Agent": "AudioSource/1.0 (Music Library Manager)"
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_or_create_scrape_status(self) -> VinylReleasesScrapeStatus:
        """Get or create the scrape status record."""
        status = self.db.query(VinylReleasesScrapeStatus).first()
        if not status:
            status = VinylReleasesScrapeStatus(status="idle")
            self.db.add(status)
            self.db.commit()
            self.db.refresh(status)
        return status
    
    @staticmethod
    def normalize_name(name: str) -> str:
        """
        Normalize an artist name for comparison.
        Removes punctuation, extra spaces, converts to lowercase.
        """
        if not name:
            return ""
        
        # Convert to lowercase
        name = name.lower()
        
        # Normalize unicode characters
        name = unicodedata.normalize('NFKD', name)
        name = name.encode('ascii', 'ignore').decode('ascii')
        
        # Remove common prefixes/suffixes
        name = re.sub(r'^the\s+', '', name)
        
        # Remove punctuation and special characters
        name = re.sub(r'[^\w\s]', '', name)
        
        # Collapse multiple spaces
        name = re.sub(r'\s+', ' ', name).strip()
        
        return name
    
    def get_library_artists(self) -> Dict[str, Artist]:
        """
        Get all artists with owned albums and return a dict mapping
        normalized names to Artist objects.
        """
        from sqlalchemy import distinct
        from app.models import Album
        
        # Get artist IDs that have at least one owned album
        artist_ids_with_owned = (
            self.db.query(distinct(Album.artist_id))
            .filter(Album.is_owned == True, Album.artist_id != None)
            .all()
        )
        artist_ids = [aid[0] for aid in artist_ids_with_owned]
        
        artists = self.db.query(Artist).filter(Artist.id.in_(artist_ids)).all()
        
        # Build lookup dict with normalized names
        artist_lookup = {}
        for artist in artists:
            normalized = self.normalize_name(artist.name)
            if normalized:
                artist_lookup[normalized] = artist
                
                # Also add without "the" prefix if present
                if artist.name.lower().startswith("the "):
                    alt_normalized = self.normalize_name(artist.name[4:])
                    if alt_normalized:
                        artist_lookup[alt_normalized] = artist
        
        return artist_lookup
    
    def find_artist_in_title(self, title: str, artist_lookup: Dict[str, Artist]) -> Artist | None:
        """
        Try to find a matching artist in the post title.
        Returns the matched Artist or None.
        """
        normalized_title = self.normalize_name(title)
        
        # Check each artist name
        for artist_name, artist in artist_lookup.items():
            if not artist_name:
                continue
            
            # Check if artist name appears in title
            # Use word boundary matching to avoid partial matches
            pattern = r'\b' + re.escape(artist_name) + r'\b'
            if re.search(pattern, normalized_title):
                return artist
        
        return None
    
    def scrape_vinyl_releases(self, limit: int = 100, is_background: bool = False) -> Dict[str, Any]:
        """
        Scrape r/vinylreleases and match posts against library artists.
        
        Args:
            limit: Maximum number of posts to fetch
            is_background: If True, skip the "already scraping" check (used by background tasks)
        
        Returns:
            Dict with scrape results
        """
        status = self.get_or_create_scrape_status()
        
        # If already scraping (and not a background task continuation), return current status
        if not is_background and status.status == "scraping":
            return {"status": "already_scraping", "message": "Scrape already in progress"}
        
        # Update status to scraping
        status.status = "scraping"
        status.last_scrape_at = datetime.utcnow()
        status.error_message = None
        self.db.commit()
        
        try:
            # Get library artists
            print(f"[VINYL] Getting library artists...")
            artist_lookup = self.get_library_artists()
            print(f"[VINYL] Found {len(artist_lookup)} artist names to match against")
            
            if len(artist_lookup) == 0:
                print("[VINYL] No artists with owned albums found - nothing to match against")
                status.status = "completed"
                status.posts_found = 0
                status.matches_found = 0
                status.error_message = "No artists with owned albums to match against"
                self.db.commit()
                return {"status": "completed", "posts_found": 0, "matches_found": 0}
            
            # Fetch posts from Reddit
            print(f"[VINYL] Fetching posts from Reddit...")
            posts = self._fetch_reddit_posts(limit)
            print(f"[VINYL] Fetched {len(posts)} posts from r/vinylreleases")
            
            posts_found = len(posts)
            matches_found = 0
            
            for post in posts:
                reddit_id = post.get("id")
                if not reddit_id:
                    continue
                
                # Check if we already have this post
                existing = self.db.query(VinylRelease).filter(
                    VinylRelease.reddit_id == reddit_id
                ).first()
                
                if existing:
                    # Update score and comments
                    existing.score = post.get("score", 0)
                    existing.num_comments = post.get("num_comments", 0)
                    continue
                
                # Try to match against library artists
                title = post.get("title", "")
                matched_artist = self.find_artist_in_title(title, artist_lookup)
                
                if matched_artist:
                    # Create new vinyl release entry
                    posted_at = None
                    if post.get("created_utc"):
                        posted_at = datetime.utcfromtimestamp(post["created_utc"])
                    
                    vinyl_release = VinylRelease(
                        reddit_id=reddit_id,
                        title=title,
                        url=f"https://reddit.com{post.get('permalink', '')}",
                        author=post.get("author"),
                        score=post.get("score", 0),
                        num_comments=post.get("num_comments", 0),
                        flair=post.get("link_flair_text"),
                        thumbnail=post.get("thumbnail") if post.get("thumbnail", "").startswith("http") else None,
                        matched_artist_id=matched_artist.id,
                        matched_artist_name=matched_artist.name,
                        posted_at=posted_at
                    )
                    self.db.add(vinyl_release)
                    matches_found += 1
                    print(f"[VINYL] Matched: '{title}' -> {matched_artist.name}")
            
            self.db.commit()
            
            # Update status
            status.status = "completed"
            status.posts_found = posts_found
            status.matches_found = matches_found
            self.db.commit()
            
            print(f"[VINYL] Scrape completed: {posts_found} posts, {matches_found} matches")
            
            return {
                "status": "completed",
                "posts_found": posts_found,
                "matches_found": matches_found
            }
            
        except Exception as e:
            import traceback
            print(f"[VINYL] Scrape failed: {e}")
            print(f"[VINYL] Traceback: {traceback.format_exc()}")
            status.status = "error"
            status.error_message = str(e)
            self.db.commit()
            return {"status": "error", "message": str(e)}
    
    def _fetch_reddit_posts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch posts from r/vinylreleases."""
        posts = []
        after = None
        
        print(f"[VINYL] Starting to fetch up to {limit} posts from Reddit...")
        
        while len(posts) < limit:
            try:
                params = {"limit": min(100, limit - len(posts))}
                if after:
                    params["after"] = after
                
                print(f"[VINYL] Making request to {self.SUBREDDIT_URL} with params {params}")
                
                response = httpx.get(
                    self.SUBREDDIT_URL,
                    headers=self.HEADERS,
                    params=params,
                    timeout=30
                )
                
                print(f"[VINYL] Reddit response status: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"[VINYL] Reddit returned non-200: {response.text[:500]}")
                    break
                
                response.raise_for_status()
                
                data = response.json()
                children = data.get("data", {}).get("children", [])
                
                print(f"[VINYL] Got {len(children)} posts in this batch")
                
                if not children:
                    break
                
                for child in children:
                    post_data = child.get("data", {})
                    posts.append(post_data)
                
                after = data.get("data", {}).get("after")
                if not after:
                    break
                    
            except httpx.TimeoutException:
                print(f"[VINYL] Timeout fetching Reddit posts")
                break
            except Exception as e:
                import traceback
                print(f"[VINYL] Error fetching Reddit posts: {e}")
                print(f"[VINYL] Traceback: {traceback.format_exc()}")
                break
        
        print(f"[VINYL] Total posts fetched: {len(posts)}")
        return posts
    
    def get_vinyl_releases(self, limit: int = 50, skip: int = 0) -> List[VinylRelease]:
        """Get vinyl releases from the database, sorted by posted_at."""
        return self.db.query(VinylRelease).order_by(
            VinylRelease.posted_at.desc().nullslast()
        ).offset(skip).limit(limit).all()

