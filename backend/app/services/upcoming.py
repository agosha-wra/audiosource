"""Service for scanning upcoming releases and fetching artist images."""
from datetime import datetime, date
from sqlalchemy.orm import Session
from typing import List

from app.models import Artist, Album, UpcomingReleasesStatus
from app.services.musicbrainz import MusicBrainzService


class UpcomingReleasesService:
    """Service for checking upcoming releases from artists with owned albums."""

    def __init__(self, db: Session):
        self.db = db

    def get_or_create_status(self) -> UpcomingReleasesStatus:
        """Get or create the upcoming releases status record."""
        status = self.db.query(UpcomingReleasesStatus).first()
        if not status:
            status = UpcomingReleasesStatus(status="idle")
            self.db.add(status)
            self.db.commit()
            self.db.refresh(status)
        return status

    def get_artists_with_owned_albums(self) -> List[Artist]:
        """Get all artists that have at least one owned album."""
        # Subquery to find artist IDs with owned albums
        from sqlalchemy import distinct, select
        
        artist_ids_with_owned = (
            self.db.query(distinct(Album.artist_id))
            .filter(Album.is_owned == True, Album.artist_id != None)
            .all()
        )
        
        artist_ids = [aid[0] for aid in artist_ids_with_owned]
        
        return self.db.query(Artist).filter(
            Artist.id.in_(artist_ids),
            Artist.musicbrainz_id != None
        ).all()

    def check_upcoming_releases(self) -> UpcomingReleasesStatus:
        """
        Check for upcoming releases from all artists with owned albums.
        Automatically adds upcoming releases to the wishlist.
        """
        status = self.get_or_create_status()
        
        # Check if already scanning
        if status.status == "scanning":
            return status
        
        # Start scanning
        status.status = "scanning"
        status.started_at = datetime.utcnow()
        status.completed_at = None
        status.error_message = None
        status.releases_found = 0
        status.artists_checked = 0
        self.db.commit()
        
        try:
            artists = self.get_artists_with_owned_albums()
            status.total_artists = len(artists)
            self.db.commit()
            
            today = date.today().isoformat()
            total_found = 0
            
            for i, artist in enumerate(artists):
                status.artists_checked = i + 1
                self.db.commit()
                
                if not artist.musicbrainz_id:
                    continue
                
                try:
                    # Also fetch artist image if we don't have one
                    if not artist.image_url:
                        image_url = MusicBrainzService.get_artist_image_url(artist.musicbrainz_id)
                        if image_url:
                            artist.image_url = image_url
                            self.db.commit()
                    
                    # Get upcoming releases
                    upcoming = MusicBrainzService.get_upcoming_releases(artist.musicbrainz_id)
                    
                    for release in upcoming:
                        mbid = release.get("musicbrainz_id")
                        if not mbid:
                            continue
                        
                        # Check if we already have this album
                        existing = self.db.query(Album).filter(
                            Album.musicbrainz_id == mbid
                        ).first()
                        
                        if existing:
                            # If exists but not wishlisted, add to wishlist
                            if not existing.is_owned and not existing.is_wishlisted:
                                existing.is_wishlisted = True
                                self.db.commit()
                                total_found += 1
                        else:
                            # Create new album and add to wishlist
                            new_album = Album(
                                title=release.get("title", "Unknown Album"),
                                musicbrainz_id=mbid,
                                artist_id=artist.id,
                                release_date=release.get("release_date"),
                                release_type=release.get("release_type"),
                                cover_art_url=release.get("cover_art_url"),
                                is_owned=False,
                                is_wishlisted=True,
                                is_scanned=True
                            )
                            self.db.add(new_album)
                            self.db.commit()
                            total_found += 1
                            print(f"Added upcoming release: {release.get('title')} by {artist.name} ({release.get('release_date')})")
                
                except Exception as e:
                    print(f"Error checking releases for {artist.name}: {e}")
                    continue
            
            status.releases_found = total_found
            status.status = "completed"
            status.completed_at = datetime.utcnow()
            status.last_check_at = datetime.utcnow()
            
        except Exception as e:
            status.status = "error"
            status.error_message = str(e)
            status.completed_at = datetime.utcnow()
        
        self.db.commit()
        return status

    def update_artist_images(self) -> int:
        """Update images for all artists that don't have one yet."""
        artists = self.db.query(Artist).filter(
            Artist.musicbrainz_id != None,
            Artist.image_url == None
        ).all()
        
        updated = 0
        for artist in artists:
            try:
                image_url = MusicBrainzService.get_artist_image_url(artist.musicbrainz_id)
                if image_url:
                    artist.image_url = image_url
                    self.db.commit()
                    updated += 1
                    print(f"Updated image for {artist.name}")
            except Exception as e:
                print(f"Error fetching image for {artist.name}: {e}")
        
        return updated

    def fetch_missing_albums_for_all_artists(self) -> UpcomingReleasesStatus:
        """
        Fetch all albums from MusicBrainz for each artist and add missing ones.
        This populates the 'missing albums' for each artist.
        Also cleans up duplicate 'missing' albums that match owned albums by title.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        status = self.get_or_create_status()
        
        # Check if already scanning
        if status.status == "scanning":
            return status
        
        # Start scanning
        status.status = "scanning"
        status.started_at = datetime.utcnow()
        status.completed_at = None
        status.error_message = None
        status.releases_found = 0
        status.artists_checked = 0
        self.db.commit()
        
        try:
            artists = self.get_artists_with_owned_albums()
            status.total_artists = len(artists)
            self.db.commit()
            
            # First pass: Clean up duplicate "missing" albums that match owned albums
            logger.info("[FETCH] Cleaning up duplicate missing albums...")
            duplicates_removed = 0
            for artist in artists:
                # Get owned albums for this artist
                owned_albums = self.db.query(Album).filter(
                    Album.artist_id == artist.id,
                    Album.is_owned == True
                ).all()
                
                # Get non-owned albums for this artist
                missing_albums = self.db.query(Album).filter(
                    Album.artist_id == artist.id,
                    Album.is_owned == False
                ).all()
                
                owned_titles = set()
                for owned in owned_albums:
                    owned_titles.add(owned.title.lower().strip())
                    # Also add cleaned version
                    owned_titles.add(owned.title.lower().strip().split('(')[0].strip())
                
                for missing in missing_albums:
                    missing_title = missing.title.lower().strip()
                    missing_clean = missing_title.split('(')[0].strip()
                    
                    if missing_title in owned_titles or (missing_clean in owned_titles and len(missing_clean) > 3):
                        logger.info(f"[FETCH] Removing duplicate: {missing.title} by {artist.name}")
                        self.db.delete(missing)
                        duplicates_removed += 1
                
                self.db.commit()
            
            logger.info(f"[FETCH] Removed {duplicates_removed} duplicate albums")
            
            total_added = 0
            
            for i, artist in enumerate(artists):
                status.artists_checked = i + 1
                self.db.commit()
                
                if not artist.musicbrainz_id:
                    continue
                
                try:
                    logger.info(f"[FETCH] Fetching albums for {artist.name} ({i+1}/{len(artists)})")
                    
                    # Also fetch artist image if we don't have one
                    if not artist.image_url:
                        image_url = MusicBrainzService.get_artist_image_url(artist.musicbrainz_id)
                        if image_url:
                            artist.image_url = image_url
                            self.db.commit()
                    
                    # Get ALL releases for this artist (albums and EPs)
                    releases = MusicBrainzService.get_artist_releases(artist.musicbrainz_id)
                    
                    for release in releases:
                        mbid = release.get("musicbrainz_id")
                        if not mbid:
                            continue
                        
                        release_title = release.get("title", "Unknown Album")
                        
                        # Check if we already have this album by musicbrainz_id
                        existing = self.db.query(Album).filter(
                            Album.musicbrainz_id == mbid
                        ).first()
                        
                        if existing:
                            continue
                        
                        # Also check by title similarity for this artist
                        # (in case local album has different/no musicbrainz_id)
                        artist_albums = self.db.query(Album).filter(
                            Album.artist_id == artist.id
                        ).all()
                        
                        title_match = False
                        release_title_lower = release_title.lower().strip()
                        for existing_album in artist_albums:
                            existing_title_lower = existing_album.title.lower().strip()
                            # Check for exact match or very close match
                            if existing_title_lower == release_title_lower:
                                title_match = True
                                break
                            # Also check without common suffixes like "(Deluxe)", "(Remaster)", etc.
                            clean_existing = existing_title_lower.split('(')[0].strip()
                            clean_release = release_title_lower.split('(')[0].strip()
                            if clean_existing == clean_release and len(clean_existing) > 3:
                                title_match = True
                                break
                        
                        if title_match:
                            continue
                        
                        # Create new album as NOT owned and NOT wishlisted
                        # This populates the "missing" albums
                        new_album = Album(
                            title=release_title,
                            musicbrainz_id=mbid,
                            artist_id=artist.id,
                            release_date=release.get("release_date"),
                            release_type=release.get("release_type"),
                            cover_art_url=release.get("cover_art_url"),
                            is_owned=False,
                            is_wishlisted=False,
                            is_scanned=True
                        )
                        self.db.add(new_album)
                        self.db.commit()
                        total_added += 1
                        logger.info(f"[FETCH] Added: {release_title} by {artist.name}")
                
                except Exception as e:
                    logger.error(f"[FETCH] Error fetching albums for {artist.name}: {e}")
                    continue
            
            status.releases_found = total_added
            status.status = "completed"
            status.completed_at = datetime.utcnow()
            status.last_check_at = datetime.utcnow()
            logger.info(f"[FETCH] Completed. Added {total_added} missing albums.")
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[FETCH] Failed: {e}")
            status.status = "error"
            status.error_message = str(e)
            status.completed_at = datetime.utcnow()
        
        self.db.commit()
        return status

