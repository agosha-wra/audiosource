from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class ArtistBase(BaseModel):
    name: str
    musicbrainz_id: Optional[str] = None
    sort_name: Optional[str] = None
    country: Optional[str] = None
    image_url: Optional[str] = None


class ArtistResponse(ArtistBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ArtistDetailResponse(ArtistBase):
    id: int
    created_at: datetime
    owned_album_count: int = 0
    missing_album_count: int = 0  # Missing albums NOT in wishlist
    wishlisted_album_count: int = 0  # Missing albums in wishlist

    class Config:
        from_attributes = True


class TrackBase(BaseModel):
    title: str
    track_number: Optional[int] = None
    disc_number: int = 1
    duration_seconds: Optional[int] = None
    file_format: Optional[str] = None


class TrackResponse(TrackBase):
    id: int
    file_path: str

    class Config:
        from_attributes = True


class AlbumBase(BaseModel):
    title: str
    release_date: Optional[str] = None
    release_type: Optional[str] = None
    track_count: Optional[int] = None


class AlbumResponse(AlbumBase):
    id: int
    musicbrainz_id: Optional[str] = None
    folder_path: Optional[str] = None
    cover_art_url: Optional[str] = None
    is_owned: bool = True
    is_wishlisted: bool = False
    is_scanned: bool
    created_at: datetime
    artist: Optional[ArtistResponse] = None

    class Config:
        from_attributes = True


class AlbumDetailResponse(AlbumResponse):
    tracks: List[TrackResponse] = []

    class Config:
        from_attributes = True


class ScanStatusResponse(BaseModel):
    id: int
    status: str
    current_folder: Optional[str] = None
    total_folders: int
    scanned_folders: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class ScanRequest(BaseModel):
    force_rescan: bool = False


class ScanScheduleResponse(BaseModel):
    id: int
    enabled: bool
    interval_hours: int
    last_scan_at: Optional[datetime] = None
    next_scan_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ScanScheduleUpdate(BaseModel):
    enabled: Optional[bool] = None
    interval_hours: Optional[int] = None


# Wishlist schemas
class WishlistAddRequest(BaseModel):
    album_id: Optional[int] = None  # For existing albums
    # For new albums from MusicBrainz search
    musicbrainz_id: Optional[str] = None
    title: Optional[str] = None
    artist_name: Optional[str] = None
    artist_musicbrainz_id: Optional[str] = None
    release_date: Optional[str] = None
    release_type: Optional[str] = None
    cover_art_url: Optional[str] = None


# MusicBrainz search schemas
class MusicBrainzSearchResult(BaseModel):
    musicbrainz_id: str
    title: str
    artist_name: Optional[str] = None
    artist_musicbrainz_id: Optional[str] = None
    release_date: Optional[str] = None
    release_type: Optional[str] = None
    cover_art_url: Optional[str] = None
    # Check if already in our DB
    existing_album_id: Optional[int] = None
    is_owned: bool = False
    is_wishlisted: bool = False


# Upcoming releases schemas
class UpcomingReleasesStatusResponse(BaseModel):
    id: int
    status: str
    artists_checked: int
    total_artists: int
    releases_found: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_check_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


# New Releases (AOTY) schemas
class NewReleaseResponse(BaseModel):
    id: int
    artist_name: str
    album_title: str
    release_date: Optional[str] = None
    release_type: Optional[str] = None
    aoty_url: str
    cover_art_url: Optional[str] = None
    critic_score: Optional[int] = None
    num_critics: Optional[int] = None
    week_year: int
    week_number: int
    scraped_at: datetime
    # Database status
    existing_album_id: Optional[int] = None
    is_owned: bool = False
    is_wishlisted: bool = False

    class Config:
        from_attributes = True


class NewReleasesScrapeStatusResponse(BaseModel):
    id: int
    status: str
    last_scrape_at: Optional[datetime] = None
    next_scrape_at: Optional[datetime] = None
    albums_found: int
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


# ============ Download Schemas ============

class DownloadResponse(BaseModel):
    id: int
    album_id: Optional[int] = None
    artist_name: str
    album_title: str
    slskd_username: Optional[str] = None
    total_files: int
    completed_files: int
    total_bytes: int
    completed_bytes: int
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress_percent: float = 0

    class Config:
        from_attributes = True


class SlskdStatusResponse(BaseModel):
    enabled: bool
    available: bool
    url: Optional[str] = None


# ============ Metadata Match Schemas ============

class MetadataMatchCandidate(BaseModel):
    musicbrainz_id: str
    title: str
    artist_name: Optional[str] = None
    release_date: Optional[str] = None
    release_type: Optional[str] = None
    track_count: Optional[int] = None
    country: Optional[str] = None
    cover_art_url: Optional[str] = None
    match_score: int = 0


class ApplyMetadataRequest(BaseModel):
    musicbrainz_id: str


# ============ App Settings Schemas ============

class SlskdSettingsResponse(BaseModel):
    enabled: bool
    url: Optional[str] = None
    download_dir: Optional[str] = None
    api_key_set: bool = False


class AppSettingsResponse(BaseModel):
    music_folder: str
    database_url: str
    slskd: SlskdSettingsResponse


# ============ Vinyl Releases Schemas ============

class VinylReleaseResponse(BaseModel):
    id: int
    reddit_id: str
    title: str
    url: str
    author: Optional[str] = None
    score: int
    num_comments: int
    flair: Optional[str] = None
    thumbnail: Optional[str] = None
    matched_artist_id: Optional[int] = None
    matched_artist_name: Optional[str] = None
    posted_at: Optional[datetime] = None
    scraped_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class VinylReleasesScrapeStatusResponse(BaseModel):
    id: int
    status: str
    last_scrape_at: Optional[datetime] = None
    posts_found: int
    matches_found: int
    current_post: int = 0
    total_posts: int = 0
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class ConcertResponse(BaseModel):
    id: int
    bandsintown_id: str
    artist_id: Optional[int] = None
    artist_name: str
    event_date: datetime
    venue_name: Optional[str] = None
    venue_city: Optional[str] = None
    venue_region: Optional[str] = None
    venue_country: Optional[str] = None
    ticket_url: Optional[str] = None
    event_url: Optional[str] = None
    lineup: Optional[str] = None
    description: Optional[str] = None
    scraped_at: datetime
    
    class Config:
        from_attributes = True


class ConcertScrapeStatusResponse(BaseModel):
    id: int
    status: str
    last_scrape_at: Optional[datetime] = None
    artists_checked: int = 0
    total_artists: int = 0
    concerts_found: int = 0
    current_artist: int = 0
    error_message: Optional[str] = None

    class Config:
        from_attributes = True
