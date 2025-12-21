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
  status: 'idle' | 'pending' | 'scanning' | 'completed' | 'error';
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
}

export interface NewReleasesScrapeStatus {
  id: number;
  status: 'idle' | 'scraping' | 'completed' | 'error';
  last_scrape_at: string | null;
  next_scrape_at: string | null;
  albums_found: number;
  error_message: string | null;
}

export type View = 'albums' | 'artists' | 'artist-detail' | 'wishlist' | 'new-releases';
