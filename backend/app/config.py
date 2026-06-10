from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql://audiosource:audiosource@db:5432/audiosource"
    music_folder: str = "/music"
    musicbrainz_app_name: str = "AudioSource"
    musicbrainz_app_version: str = "0.1"
    musicbrainz_contact: str = "audiosource@example.com"
    
    # Slskd integration settings
    slskd_enabled: bool = False
    slskd_url: str = ""
    slskd_api_key: str = ""
    slskd_download_dir: str = "/downloads"
    
    # Reddit API (optional — for vinyl releases scrape when public JSON is blocked)
    reddit_client_id: str = ""
    reddit_client_secret: str = ""

    # Concert city filter (only show concerts in this city/country)
    concert_city: str = "Paris"

    # Hour (0-23, UTC) at which nightly library and upcoming scans trigger.
    nightly_scan_hour_utc: int = 3

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()

