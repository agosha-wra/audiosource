from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class ArtistBase(BaseModel):
    name: str
    musicbrainz_id: Optional[str] = None
    sort_name: Optional[str] = None
    country: Optional[str] = None


class ArtistResponse(ArtistBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ArtistDetailResponse(ArtistBase):
    id: int
    created_at: datetime
    owned_album_count: int = 0
    missing_album_count: int = 0

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
