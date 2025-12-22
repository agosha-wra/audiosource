from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta
import threading
import asyncio

from app.database import get_db, engine, Base, SessionLocal
from app.models import Album, Artist, ScanStatus, ScanSchedule, UpcomingReleasesStatus
from app.schemas import (
    AlbumResponse,
    AlbumDetailResponse,
    ArtistResponse,
    ArtistDetailResponse,
    ScanStatusResponse,
    ScanRequest,
    ScanScheduleResponse,
    ScanScheduleUpdate,
    WishlistAddRequest,
    MusicBrainzSearchResult,
    UpcomingReleasesStatusResponse,
    NewReleaseResponse,
    NewReleasesScrapeStatusResponse,
)
from app.services.scanner import ScannerService
from app.services.musicbrainz import MusicBrainzService
from app.services.upcoming import UpcomingReleasesService
from app.services.aoty import AOTYService

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AudioSource",
    description="A music library management application",
    version="0.1.0",
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Background scan lock
_scan_lock = threading.Lock()
_scheduler_running = False


def run_scan_in_background(force_rescan: bool):
    """Run the library scan in a background thread."""
    db = SessionLocal()
    try:
        with _scan_lock:
            scanner = ScannerService(db)
            scanner.scan_library(force_rescan)
    finally:
        db.close()


async def scheduled_scan_loop():
    """Background loop that checks for scheduled scans and upcoming releases."""
    global _scheduler_running
    _scheduler_running = True
    
    while _scheduler_running:
        try:
            db = SessionLocal()
            try:
                schedule = db.query(ScanSchedule).first()
                if schedule and schedule.enabled:
                    now = datetime.utcnow()
                    
                    # Check if it's time for a scan
                    if schedule.next_scan_at and now >= schedule.next_scan_at:
                        # Check if not already scanning
                        status = db.query(ScanStatus).first()
                        if not status or status.status != "scanning":
                            print(f"Starting scheduled scan at {now}")
                            # Run scan in background thread
                            thread = threading.Thread(
                                target=run_scan_in_background,
                                args=(False,)
                            )
                            thread.start()
                            
                            # Update schedule
                            schedule.last_scan_at = now
                            schedule.next_scan_at = now + timedelta(hours=schedule.interval_hours)
                            db.commit()
                
                # Check for upcoming releases daily
                upcoming_status = db.query(UpcomingReleasesStatus).first()
                if upcoming_status:
                    # Run if never run or last check was more than 24 hours ago
                    should_check = (
                        upcoming_status.last_check_at is None or
                        (now - upcoming_status.last_check_at) > timedelta(hours=24)
                    )
                    if should_check and upcoming_status.status != "scanning":
                        print(f"Starting scheduled upcoming releases check at {now}")
                        thread = threading.Thread(target=run_upcoming_check_in_background)
                        thread.start()
            finally:
                db.close()
        except Exception as e:
            print(f"Scheduler error: {e}")
        
        # Check every minute
        await asyncio.sleep(60)


@app.on_event("startup")
async def startup_event():
    """Initialize scheduled scanning on startup."""
    # Create default schedule if it doesn't exist
    db = SessionLocal()
    try:
        schedule = db.query(ScanSchedule).first()
        if not schedule:
            schedule = ScanSchedule(
                enabled=True,
                interval_hours=24,
                next_scan_at=datetime.utcnow() + timedelta(hours=24)
            )
            db.add(schedule)
            db.commit()
    finally:
        db.close()
    
    # Start the scheduler
    asyncio.create_task(scheduled_scan_loop())


@app.on_event("shutdown")
async def shutdown_event():
    """Stop the scheduler on shutdown."""
    global _scheduler_running
    _scheduler_running = False


@app.get("/")
def root():
    """Root endpoint."""
    return {"message": "AudioSource API", "version": "0.1.0"}


@app.get("/api/albums", response_model=List[AlbumResponse])
def list_albums(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    owned_only: bool = True,
    db: Session = Depends(get_db)
):
    """List albums with optional search. By default only shows owned albums."""
    query = db.query(Album).order_by(Album.title)

    if owned_only:
        query = query.filter(Album.is_owned == True)

    if search:
        search_term = f"%{search}%"
        query = query.filter(Album.title.ilike(search_term))

    albums = query.offset(skip).limit(limit).all()
    return albums


@app.get("/api/albums/{album_id}", response_model=AlbumDetailResponse)
def get_album(album_id: int, db: Session = Depends(get_db)):
    """Get a specific album with its tracks."""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    return album


@app.get("/api/artists", response_model=List[ArtistDetailResponse])
def list_artists(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all artists with album counts."""
    artists = db.query(Artist).order_by(Artist.name).offset(skip).limit(limit).all()
    
    result = []
    for artist in artists:
        owned_count = db.query(Album).filter(
            Album.artist_id == artist.id,
            Album.is_owned == True
        ).count()
        # Missing albums NOT in wishlist
        missing_count = db.query(Album).filter(
            Album.artist_id == artist.id,
            Album.is_owned == False,
            Album.is_wishlisted == False
        ).count()
        # Missing albums in wishlist
        wishlisted_count = db.query(Album).filter(
            Album.artist_id == artist.id,
            Album.is_owned == False,
            Album.is_wishlisted == True
        ).count()
        
        artist_data = ArtistDetailResponse(
            id=artist.id,
            name=artist.name,
            musicbrainz_id=artist.musicbrainz_id,
            sort_name=artist.sort_name,
            country=artist.country,
            created_at=artist.created_at,
            owned_album_count=owned_count,
            missing_album_count=missing_count,
            wishlisted_album_count=wishlisted_count
        )
        result.append(artist_data)
    
    return result


@app.get("/api/artists/{artist_id}", response_model=ArtistDetailResponse)
def get_artist(artist_id: int, db: Session = Depends(get_db)):
    """Get a specific artist with album counts."""
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    
    owned_count = db.query(Album).filter(
        Album.artist_id == artist.id,
        Album.is_owned == True
    ).count()
    # Missing albums NOT in wishlist
    missing_count = db.query(Album).filter(
        Album.artist_id == artist.id,
        Album.is_owned == False,
        Album.is_wishlisted == False
    ).count()
    # Missing albums in wishlist
    wishlisted_count = db.query(Album).filter(
        Album.artist_id == artist.id,
        Album.is_owned == False,
        Album.is_wishlisted == True
    ).count()
    
    return ArtistDetailResponse(
        id=artist.id,
        name=artist.name,
        musicbrainz_id=artist.musicbrainz_id,
        sort_name=artist.sort_name,
        country=artist.country,
        created_at=artist.created_at,
        owned_album_count=owned_count,
        missing_album_count=missing_count,
        wishlisted_album_count=wishlisted_count
    )


@app.get("/api/artists/{artist_id}/albums", response_model=List[AlbumResponse])
def get_artist_albums(
    artist_id: int,
    owned: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """
    Get all albums for a specific artist.
    Use owned=true for owned albums, owned=false for missing albums, or omit for all.
    """
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    
    query = db.query(Album).filter(Album.artist_id == artist_id)
    
    if owned is not None:
        query = query.filter(Album.is_owned == owned)
    
    # Sort: owned albums first, then by release date
    albums = query.order_by(Album.is_owned.desc(), Album.release_date.desc()).all()
    return albums


@app.delete("/api/artists/{artist_id}")
def delete_artist(artist_id: int, db: Session = Depends(get_db)):
    """
    Delete an artist and all their non-owned albums.
    Cannot delete artists that have owned albums.
    """
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    
    # Check if artist has owned albums
    owned_count = db.query(Album).filter(
        Album.artist_id == artist_id,
        Album.is_owned == True
    ).count()
    
    if owned_count > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot delete artist with {owned_count} owned album(s)"
        )
    
    # Delete all non-owned albums for this artist
    db.query(Album).filter(Album.artist_id == artist_id).delete()
    
    # Delete the artist
    db.delete(artist)
    db.commit()
    
    return {"message": "Artist deleted"}


@app.post("/api/scan", response_model=ScanStatusResponse)
def start_scan(
    request: ScanRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Start a library scan."""
    scanner = ScannerService(db)
    status = scanner.get_or_create_scan_status()

    # If already scanning, return current status
    if status.status == "scanning":
        return status

    # Mark as pending to indicate scan is queued
    status.status = "pending"
    db.commit()
    db.refresh(status)

    # Start background scan - the scanner will set status to "scanning"
    background_tasks.add_task(run_scan_in_background, request.force_rescan)

    return status


@app.get("/api/scan/status", response_model=ScanStatusResponse)
def get_scan_status(db: Session = Depends(get_db)):
    """Get the current scan status."""
    scanner = ScannerService(db)
    return scanner.get_or_create_scan_status()


@app.get("/api/scan/schedule", response_model=ScanScheduleResponse)
def get_scan_schedule(db: Session = Depends(get_db)):
    """Get the scan schedule settings."""
    schedule = db.query(ScanSchedule).first()
    if not schedule:
        schedule = ScanSchedule(enabled=True, interval_hours=24)
        db.add(schedule)
        db.commit()
        db.refresh(schedule)
    return schedule


@app.put("/api/scan/schedule", response_model=ScanScheduleResponse)
def update_scan_schedule(
    update: ScanScheduleUpdate,
    db: Session = Depends(get_db)
):
    """Update the scan schedule settings."""
    schedule = db.query(ScanSchedule).first()
    if not schedule:
        schedule = ScanSchedule(enabled=True, interval_hours=24)
        db.add(schedule)
    
    if update.enabled is not None:
        schedule.enabled = update.enabled
    if update.interval_hours is not None:
        schedule.interval_hours = update.interval_hours
        # Update next scan time
        if schedule.enabled:
            schedule.next_scan_at = datetime.utcnow() + timedelta(hours=update.interval_hours)
    
    db.commit()
    db.refresh(schedule)
    return schedule


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """Get library statistics."""
    owned_album_count = db.query(Album).filter(Album.is_owned == True).count()
    missing_album_count = db.query(Album).filter(Album.is_owned == False).count()
    wishlisted_count = db.query(Album).filter(Album.is_wishlisted == True).count()
    artist_count = db.query(Artist).count()

    return {
        "album_count": owned_album_count,
        "missing_album_count": missing_album_count,
        "wishlist_count": wishlisted_count,
        "artist_count": artist_count,
    }


# ============ Wishlist Endpoints ============

@app.get("/api/wishlist", response_model=List[AlbumResponse])
def get_wishlist(db: Session = Depends(get_db)):
    """Get all wishlisted albums."""
    albums = db.query(Album).filter(Album.is_wishlisted == True).order_by(Album.title).all()
    return albums


@app.post("/api/wishlist", response_model=AlbumResponse)
def add_to_wishlist(request: WishlistAddRequest, db: Session = Depends(get_db)):
    """Add an album to the wishlist."""
    
    # If album_id is provided, just mark existing album as wishlisted
    if request.album_id:
        album = db.query(Album).filter(Album.id == request.album_id).first()
        if not album:
            raise HTTPException(status_code=404, detail="Album not found")
        album.is_wishlisted = True
        db.commit()
        db.refresh(album)
        return album
    
    # Check if album already exists by MusicBrainz ID
    if request.musicbrainz_id:
        existing = db.query(Album).filter(Album.musicbrainz_id == request.musicbrainz_id).first()
        if existing:
            existing.is_wishlisted = True
            db.commit()
            db.refresh(existing)
            return existing
    
    # Check if album exists by title + artist name (for AOTY releases without MusicBrainz ID)
    if request.title and request.artist_name:
        existing = db.query(Album).join(Artist).filter(
            func.lower(Album.title) == func.lower(request.title),
            func.lower(Artist.name) == func.lower(request.artist_name)
        ).first()
        if existing:
            existing.is_wishlisted = True
            db.commit()
            db.refresh(existing)
            return existing
    
    # Need at least a title to create a new album
    if not request.title:
        raise HTTPException(status_code=400, detail="Either album_id, musicbrainz_id, or title is required")
    
    # Get or create artist
    artist = None
    if request.artist_musicbrainz_id:
        artist = db.query(Artist).filter(Artist.musicbrainz_id == request.artist_musicbrainz_id).first()
        if not artist and request.artist_name:
            artist = Artist(
                name=request.artist_name,
                musicbrainz_id=request.artist_musicbrainz_id
            )
            db.add(artist)
            db.commit()
            db.refresh(artist)
    elif request.artist_name:
        artist = db.query(Artist).filter(func.lower(Artist.name) == func.lower(request.artist_name)).first()
        if not artist:
            artist = Artist(name=request.artist_name)
            db.add(artist)
            db.commit()
            db.refresh(artist)
    
    # Create new album
    album = Album(
        title=request.title,
        musicbrainz_id=request.musicbrainz_id,
        artist_id=artist.id if artist else None,
        release_date=request.release_date,
        release_type=request.release_type,
        cover_art_url=request.cover_art_url,
        is_owned=False,
        is_wishlisted=True,
        is_scanned=True
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    
    return album


@app.delete("/api/wishlist/{album_id}")
def remove_from_wishlist(album_id: int, db: Session = Depends(get_db)):
    """Remove an album from the wishlist. Cleans up orphaned artists."""
    album = db.query(Album).filter(Album.id == album_id).first()
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    artist_id = album.artist_id
    
    # If album is not owned, delete it entirely
    if not album.is_owned:
        db.delete(album)
    else:
        album.is_wishlisted = False
    
    db.commit()
    
    # Clean up orphaned artist (no owned or wishlisted albums)
    if artist_id:
        remaining_albums = db.query(Album).filter(Album.artist_id == artist_id).count()
        if remaining_albums == 0:
            artist = db.query(Artist).filter(Artist.id == artist_id).first()
            if artist:
                db.delete(artist)
                db.commit()
    
    return {"message": "Removed from wishlist"}


# ============ MusicBrainz Search ============

@app.get("/api/search/musicbrainz", response_model=List[MusicBrainzSearchResult])
def search_musicbrainz(q: str, db: Session = Depends(get_db)):
    """Search MusicBrainz for albums."""
    if not q or len(q) < 2:
        return []
    
    # Search MusicBrainz
    results = MusicBrainzService.search_releases_multi(q, limit=20)
    
    # Check which ones we already have
    response = []
    for result in results:
        mbid = result.get("musicbrainz_id")
        existing = None
        if mbid:
            existing = db.query(Album).filter(Album.musicbrainz_id == mbid).first()
        
        response.append(MusicBrainzSearchResult(
            musicbrainz_id=result.get("musicbrainz_id", ""),
            title=result.get("title", "Unknown"),
            artist_name=result.get("artist_name"),
            artist_musicbrainz_id=result.get("artist_musicbrainz_id"),
            release_date=result.get("release_date"),
            release_type=result.get("release_type"),
            cover_art_url=result.get("cover_art_url"),
            existing_album_id=existing.id if existing else None,
            is_owned=existing.is_owned if existing else False,
            is_wishlisted=existing.is_wishlisted if existing else False,
        ))
    
    return response


# ============ Upcoming Releases ============

# Background task lock for upcoming releases
_upcoming_lock = threading.Lock()


def run_upcoming_check_in_background():
    """Run the upcoming releases check in a background thread."""
    db = SessionLocal()
    try:
        with _upcoming_lock:
            service = UpcomingReleasesService(db)
            service.check_upcoming_releases()
    finally:
        db.close()


@app.post("/api/upcoming/check", response_model=UpcomingReleasesStatusResponse)
def check_upcoming_releases(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Start checking for upcoming releases from artists with owned albums.
    Upcoming releases are automatically added to the wishlist.
    """
    service = UpcomingReleasesService(db)
    status = service.get_or_create_status()
    
    # If already scanning, return current status
    if status.status == "scanning":
        return status
    
    # Mark as pending
    status.status = "pending"
    db.commit()
    db.refresh(status)
    
    # Start background check
    background_tasks.add_task(run_upcoming_check_in_background)
    
    return status


@app.get("/api/upcoming/status", response_model=UpcomingReleasesStatusResponse)
def get_upcoming_status(db: Session = Depends(get_db)):
    """Get the current upcoming releases check status."""
    service = UpcomingReleasesService(db)
    return service.get_or_create_status()


@app.get("/api/upcoming/albums", response_model=List[AlbumResponse])
def get_upcoming_albums(db: Session = Depends(get_db)):
    """Get all upcoming albums (future release dates) that are in the wishlist."""
    from datetime import date
    today = date.today().isoformat()
    
    albums = db.query(Album).filter(
        Album.is_wishlisted == True,
        Album.release_date > today
    ).order_by(Album.release_date).all()
    
    return albums


# ============ New Releases (AOTY Scraping) ============

# Background task lock for AOTY scraping
_aoty_lock = threading.Lock()


def run_aoty_scrape_in_background(year: int = None, week: int = None):
    """Run the AOTY scrape in a background thread."""
    db = SessionLocal()
    try:
        with _aoty_lock:
            service = AOTYService(db)
            service.scrape_weekly_releases(year, week)
    finally:
        db.close()


@app.post("/api/new-releases/scrape", response_model=NewReleasesScrapeStatusResponse)
def scrape_new_releases(
    background_tasks: BackgroundTasks,
    year: Optional[int] = None,
    week: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Start scraping new releases from Album of the Year (AOTY).
    Scrapes the weekly releases sorted by critic score.
    """
    service = AOTYService(db)
    status = service.get_or_create_scrape_status()
    
    # If already scraping, return current status
    if status.status == "scraping":
        return status
    
    # Mark as pending
    status.status = "scraping"
    db.commit()
    db.refresh(status)
    
    # Start background scrape
    background_tasks.add_task(run_aoty_scrape_in_background, year, week)
    
    return status


@app.get("/api/new-releases/status", response_model=NewReleasesScrapeStatusResponse)
def get_new_releases_scrape_status(db: Session = Depends(get_db)):
    """Get the current AOTY scrape status."""
    service = AOTYService(db)
    return service.get_or_create_scrape_status()


@app.get("/api/new-releases", response_model=List[NewReleaseResponse])
def get_new_releases(
    year: Optional[int] = None,
    week: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    Get new releases from AOTY.
    If year/week not specified, returns the latest week's releases.
    Results are sorted by critic score descending.
    """
    service = AOTYService(db)
    
    if year and week:
        releases = service.get_releases(year, week, limit)
    else:
        releases = service.get_latest_releases(limit)
    
    # Enrich with database status (owned/wishlisted)
    result = []
    for release in releases:
        # Try to find matching album in database by title and artist name
        # Use case-insensitive matching
        matching_album = db.query(Album).join(Artist).filter(
            func.lower(Album.title) == func.lower(release.album_title),
            func.lower(Artist.name) == func.lower(release.artist_name)
        ).first()
        
        result.append(NewReleaseResponse(
            id=release.id,
            artist_name=release.artist_name,
            album_title=release.album_title,
            release_date=release.release_date,
            release_type=release.release_type,
            aoty_url=release.aoty_url,
            cover_art_url=release.cover_art_url,
            critic_score=release.critic_score,
            num_critics=release.num_critics,
            week_year=release.week_year,
            week_number=release.week_number,
            scraped_at=release.scraped_at,
            existing_album_id=matching_album.id if matching_album else None,
            is_owned=matching_album.is_owned if matching_album else False,
            is_wishlisted=matching_album.is_wishlisted if matching_album else False,
        ))
    
    return result
