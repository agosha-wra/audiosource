export interface Artist {
  id: number;
  name: string;
  musicbrainz_id: string | null;
  sort_name: string | null;
  country: string | null;
  image_url: string | null;
  created_at: string;
  owned_album_count?: number;
  missing_album_count?: number;  // Missing albums NOT in wishlist
  wishlisted_album_count?: number;  // Missing albums in wishlist
}

export interface Album {
  id: number;
  title: string;
  musicbrainz_id: string | null;
  folder_path: string | null;
  release_date: string | null;
  release_type: string | null;
  cover_art_url: string | null;
  track_count: number | null;
  is_owned: boolean;
  is_wishlisted: boolean;
  is_scanned: boolean;
  created_at: string;
  artist: Artist | null;
  tracks?: Track[];
}

export interface Track {
  id: number;
  title: string;
  track_number: number | null;
  disc_number: number;
  duration_seconds: number | null;
  file_path: string;
  file_format: string | null;
}

export interface ScanStatus {
  id: number;
  status: 'idle' | 'pending' | 'scanning' | 'completed' | 'error' | 'cancelled';
  current_folder: string | null;
  total_folders: number;
  scanned_folders: number;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}

export interface Stats {
  album_count: number;
  missing_album_count: number;
  wishlist_count: number;
  artist_count: number;
}

export interface UpcomingStatus {
  id: number;
  status: 'idle' | 'pending' | 'scanning' | 'completed' | 'error';
  artists_checked: number;
  total_artists: number;
  releases_found: number;
  started_at: string | null;
  completed_at: string | null;
  last_check_at: string | null;
  error_message: string | null;
}

export interface MusicBrainzSearchResult {
  musicbrainz_id: string;
  title: string;
  artist_name: string | null;
  artist_musicbrainz_id: string | null;
  release_date: string | null;
  release_type: string | null;
  cover_art_url: string | null;
  existing_album_id: number | null;
  is_owned: boolean;
  is_wishlisted: boolean;
}

export interface WishlistAddRequest {
  album_id?: number;
  musicbrainz_id?: string;
  title?: string;
  artist_name?: string;
  artist_musicbrainz_id?: string;
  release_date?: string;
  release_type?: string;
  cover_art_url?: string;
}

// New Releases from AOTY
export interface NewRelease {
  id: number;
  artist_name: string;
  album_title: string;
  release_date: string | null;
  release_type: string | null;
  aoty_url: string;
  cover_art_url: string | null;
  critic_score: number | null;
  num_critics: number | null;
  week_year: number;
  week_number: number;
  scraped_at: string;
  // Database status
  existing_album_id: number | null;
  is_owned: boolean;
  is_wishlisted: boolean;
}

export interface NewReleasesScrapeStatus {
  id: number;
  status: 'idle' | 'scraping' | 'completed' | 'error';
  last_scrape_at: string | null;
  next_scrape_at: string | null;
  albums_found: number;
  error_message: string | null;
}

// Downloads (slskd integration)
export interface Download {
  id: number;
  album_id: number | null;
  artist_name: string;
  album_title: string;
  slskd_username: string | null;
  total_files: number;
  completed_files: number;
  total_bytes: number;
  completed_bytes: number;
  status: 'pending' | 'searching' | 'downloading' | 'completed' | 'failed' | 'moved' | 'cancelled';
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  progress_percent: number;
}

export interface SlskdStatus {
  enabled: boolean;
  available: boolean;
  url: string | null;
}

export type View = 'albums' | 'artists' | 'artist-detail' | 'wishlist' | 'new-releases' | 'downloads' | 'vinyl-releases' | 'concerts' | 'settings';

export interface MetadataMatchCandidate {
  musicbrainz_id: string;
  title: string;
  artist_name: string | null;
  release_date: string | null;
  release_type: string | null;
  track_count: number | null;
  country: string | null;
  cover_art_url: string | null;
  match_score: number;
}

export interface AppSettings {
  music_folder: string;
  database_url: string;
  slskd: {
    enabled: boolean;
    url: string | null;
    download_dir: string | null;
    api_key_set: boolean;
  };
}

export interface VinylRelease {
  id: number;
  reddit_id: string;
  title: string;
  url: string;
  author: string | null;
  score: number;
  num_comments: number;
  flair: string | null;
  thumbnail: string | null;
  matched_artist_id: number | null;
  matched_artist_name: string | null;
  posted_at: string | null;
  scraped_at: string;
  created_at: string;
}

export interface VinylReleasesScrapeStatus {
  id: number;
  status: 'idle' | 'scraping' | 'completed' | 'error';
  last_scrape_at: string | null;
  posts_found: number;
  matches_found: number;
  current_post: number;
  total_posts: number;
  error_message: string | null;
}

export interface Concert {
  id: number;
  bandsintown_id: string;
  artist_id: number | null;
  artist_name: string;
  event_date: string;
  venue_name: string | null;
  venue_city: string | null;
  venue_region: string | null;
  venue_country: string | null;
  ticket_url: string | null;
  event_url: string | null;
  lineup: string | null;
  description: string | null;
  scraped_at: string;
}

export interface ConcertScrapeStatus {
  id: number;
  status: 'idle' | 'scraping' | 'completed' | 'error';
  last_scrape_at: string | null;
  artists_checked: number;
  total_artists: number;
  concerts_found: number;
  current_artist: number;
  error_message: string | null;
}
