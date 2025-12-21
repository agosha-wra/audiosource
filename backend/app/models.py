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
    folder_path = Column(Text, nullable=False, unique=True)
    track_count = Column(Integer, nullable=True)
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

