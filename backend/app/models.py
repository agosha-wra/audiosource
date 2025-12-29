from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Artist(Base):
    __tablename__ = "artists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(500), nullable=False, index=True)
    musicbrainz_id = Column(String(36), unique=True, nullable=True, index=True)
    sort_name = Column(String(500), nullable=True)
    disambiguation = Column(Text, nullable=True)
    country = Column(String(100), nullable=True)
    image_url = Column(Text, nullable=True)  # Artist photo URL
    discography_fetched = Column(Boolean, default=False)  # True if we've fetched all albums
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    albums = relationship("Album", back_populates="artist")


class Album(Base):
    __tablename__ = "albums"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    musicbrainz_id = Column(String(36), unique=True, nullable=True, index=True)
    artist_id = Column(Integer, ForeignKey("artists.id"), nullable=True)
    release_date = Column(String(50), nullable=True)
    release_type = Column(String(100), nullable=True)  # Album, EP, Single, etc.
    cover_art_url = Column(Text, nullable=True)
    folder_path = Column(Text, nullable=True, unique=True)  # NULL for missing albums
    track_count = Column(Integer, nullable=True)
    is_owned = Column(Boolean, default=True)  # True if we have it locally
    is_wishlisted = Column(Boolean, default=False)  # True if user wants this album
    is_scanned = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    artist = relationship("Artist", back_populates="albums")
    tracks = relationship("Track", back_populates="album", cascade="all, delete-orphan")


class Track(Base):
    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    album_id = Column(Integer, ForeignKey("albums.id"), nullable=False)
    track_number = Column(Integer, nullable=True)
    disc_number = Column(Integer, default=1)
    duration_seconds = Column(Integer, nullable=True)
    file_path = Column(Text, nullable=False, unique=True)
    file_format = Column(String(20), nullable=True)
    musicbrainz_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    album = relationship("Album", back_populates="tracks")


class ScanStatus(Base):
    __tablename__ = "scan_status"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(50), default="idle")  # idle, scanning, completed, error
    current_folder = Column(Text, nullable=True)
    total_folders = Column(Integer, default=0)
    scanned_folders = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)


class ScanSchedule(Base):
    __tablename__ = "scan_schedule"

    id = Column(Integer, primary_key=True, index=True)
    enabled = Column(Boolean, default=True)
    interval_hours = Column(Integer, default=24)  # Scan every N hours
    last_scan_at = Column(DateTime, nullable=True)
    next_scan_at = Column(DateTime, nullable=True)


class UpcomingReleasesStatus(Base):
    __tablename__ = "upcoming_releases_status"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(50), default="idle")  # idle, scanning, completed, error
    artists_checked = Column(Integer, default=0)
    total_artists = Column(Integer, default=0)
    releases_found = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    last_check_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)


class NewRelease(Base):
    """New releases scraped from Album of the Year (AOTY)."""
    __tablename__ = "new_releases"

    id = Column(Integer, primary_key=True, index=True)
    artist_name = Column(String(500), nullable=False)
    album_title = Column(String(500), nullable=False)
    release_date = Column(String(50), nullable=True)  # e.g., "Oct 31"
    release_type = Column(String(100), nullable=True)  # LP, EP, etc.
    aoty_url = Column(Text, nullable=False, unique=True)  # Full album page URL
    cover_art_url = Column(Text, nullable=True)
    critic_score = Column(Integer, nullable=True)  # 0-100
    num_critics = Column(Integer, nullable=True)
    week_year = Column(Integer, nullable=False)  # e.g., 2025
    week_number = Column(Integer, nullable=False)  # e.g., 44
    scraped_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class NewReleasesScrapeStatus(Base):
    """Status of the AOTY scraping."""
    __tablename__ = "new_releases_scrape_status"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(50), default="idle")  # idle, scraping, completed, error
    last_scrape_at = Column(DateTime, nullable=True)
    next_scrape_at = Column(DateTime, nullable=True)
    albums_found = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)


class Download(Base):
    """Tracks downloads from slskd."""
    __tablename__ = "downloads"

    id = Column(Integer, primary_key=True, index=True)
    album_id = Column(Integer, ForeignKey("albums.id"), nullable=True)
    
    # Album info (for display even if album is deleted)
    artist_name = Column(String(500), nullable=False)
    album_title = Column(String(500), nullable=False)
    
    # slskd info
    slskd_username = Column(String(255), nullable=True)  # User we're downloading from
    total_files = Column(Integer, default=0)
    completed_files = Column(Integer, default=0)
    total_bytes = Column(Integer, default=0)
    completed_bytes = Column(Integer, default=0)
    
    # Status
    status = Column(String(50), default="pending")  # pending, searching, downloading, completed, failed, moved
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationship
    album = relationship("Album")


class VinylRelease(Base):
    """Vinyl releases from r/vinylreleases that match library artists."""
    __tablename__ = "vinyl_releases"

    id = Column(Integer, primary_key=True, index=True)
    reddit_id = Column(String(50), unique=True, nullable=False, index=True)
    title = Column(Text, nullable=False)
    url = Column(Text, nullable=False)
    author = Column(String(100), nullable=True)
    score = Column(Integer, default=0)
    num_comments = Column(Integer, default=0)
    flair = Column(String(100), nullable=True)
    thumbnail = Column(Text, nullable=True)
    
    # Matched artist info
    matched_artist_id = Column(Integer, ForeignKey("artists.id"), nullable=True)
    matched_artist_name = Column(String(500), nullable=True)
    
    # Timestamps
    posted_at = Column(DateTime, nullable=True)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    matched_artist = relationship("Artist")


class VinylReleasesScrapeStatus(Base):
    """Status of the Reddit vinyl releases scraping."""
    __tablename__ = "vinyl_releases_scrape_status"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(50), default="idle")  # idle, scraping, completed, error
    last_scrape_at = Column(DateTime, nullable=True)
    posts_found = Column(Integer, default=0)
    matches_found = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
