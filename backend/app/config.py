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

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()

