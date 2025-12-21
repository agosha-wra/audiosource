from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
import threading

from app.database import get_db, engine, Base, SessionLocal
from app.models import Album, Artist, ScanStatus
from app.schemas import (
    AlbumResponse,
    AlbumDetailResponse,
    ArtistResponse,
    ScanStatusResponse,
    ScanRequest,
)
from app.services.scanner import ScannerService

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


def run_scan_in_background(force_rescan: bool):
    """Run the library scan in a background thread."""
    db = SessionLocal()
    try:
        with _scan_lock:
            scanner = ScannerService(db)
            scanner.scan_library(force_rescan)
    finally:
        db.close()


@app.get("/")
def root():
    """Root endpoint."""
    return {"message": "AudioSource API", "version": "0.1.0"}


@app.get("/api/albums", response_model=List[AlbumResponse])
def list_albums(
    skip: int = 0,
    limit: int = 100,
    search: str = None,
    db: Session = Depends(get_db)
):
    """List all albums with optional search."""
    query = db.query(Album).order_by(Album.title)

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


@app.get("/api/artists", response_model=List[ArtistResponse])
def list_artists(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all artists."""
    artists = db.query(Artist).order_by(Artist.name).offset(skip).limit(limit).all()
    return artists


@app.get("/api/artists/{artist_id}", response_model=ArtistResponse)
def get_artist(artist_id: int, db: Session = Depends(get_db)):
    """Get a specific artist."""
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    return artist


@app.get("/api/artists/{artist_id}/albums", response_model=List[AlbumResponse])
def get_artist_albums(artist_id: int, db: Session = Depends(get_db)):
    """Get all albums for a specific artist."""
    artist = db.query(Artist).filter(Artist.id == artist_id).first()
    if not artist:
        raise HTTPException(status_code=404, detail="Artist not found")
    return artist.albums


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


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """Get library statistics."""
    album_count = db.query(Album).count()
    artist_count = db.query(Artist).count()

    return {
        "album_count": album_count,
        "artist_count": artist_count,
    }
