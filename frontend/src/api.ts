import type { Album, Artist, ScanStatus, Stats, MusicBrainzSearchResult, WishlistAddRequest, UpcomingStatus, NewRelease, NewReleasesScrapeStatus, Download, SlskdStatus, MetadataMatchCandidate, AppSettings, VinylRelease, VinylReleasesScrapeStatus } from './types';

const API_BASE = '/api';

async function fetchApi<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
    },
    ...options,
  });
  
  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }
  
  return response.json();
}

export async function getAlbums(search = '', skip = 0, limit = 100, sort = 'title'): Promise<Album[]> {
  const params = new URLSearchParams();
  if (search) params.set('search', search);
  params.set('skip', skip.toString());
  params.set('limit', limit.toString());
  params.set('sort', sort);
  return fetchApi<Album[]>(`/albums?${params.toString()}`);
}

export async function getAlbum(id: number): Promise<Album> {
  return fetchApi<Album>(`/albums/${id}`);
}

export async function getArtists(skip = 0, limit = 100, sort = 'name'): Promise<Artist[]> {
  const params = new URLSearchParams();
  params.set('skip', skip.toString());
  params.set('limit', limit.toString());
  params.set('sort', sort);
  return fetchApi<Artist[]>(`/artists?${params.toString()}`);
}

export async function getArtist(id: number): Promise<Artist> {
  return fetchApi<Artist>(`/artists/${id}`);
}

export async function getArtistAlbums(artistId: number): Promise<Album[]> {
  return fetchApi<Album[]>(`/artists/${artistId}/albums`);
}

export async function deleteArtist(artistId: number): Promise<void> {
  await fetchApi(`/artists/${artistId}`, { method: 'DELETE' });
}

export async function getStats(): Promise<Stats> {
  return fetchApi<Stats>('/stats');
}

export async function startScan(forceRescan = false): Promise<ScanStatus> {
  return fetchApi<ScanStatus>('/scan', {
    method: 'POST',
    body: JSON.stringify({ force_rescan: forceRescan }),
  });
}

export async function getScanStatus(): Promise<ScanStatus> {
  return fetchApi<ScanStatus>('/scan/status');
}

// Wishlist
export async function getWishlist(): Promise<Album[]> {
  return fetchApi<Album[]>('/wishlist');
}

export async function addToWishlist(request: WishlistAddRequest): Promise<Album> {
  return fetchApi<Album>('/wishlist', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function removeFromWishlist(albumId: number): Promise<void> {
  await fetchApi<void>(`/wishlist/${albumId}`, {
    method: 'DELETE',
  });
}

// MusicBrainz Search
export async function searchMusicBrainz(query: string): Promise<MusicBrainzSearchResult[]> {
  if (!query || query.length < 2) return [];
  return fetchApi<MusicBrainzSearchResult[]>(`/search/musicbrainz?q=${encodeURIComponent(query)}`);
}

// Upcoming Releases
export async function checkUpcomingReleases(): Promise<UpcomingStatus> {
  return fetchApi<UpcomingStatus>('/upcoming/check', { method: 'POST' });
}

export async function getUpcomingStatus(): Promise<UpcomingStatus> {
  return fetchApi<UpcomingStatus>('/upcoming/status');
}

export async function getUpcomingAlbums(): Promise<Album[]> {
  return fetchApi<Album[]>('/upcoming/albums');
}

export async function fetchMissingAlbums(): Promise<UpcomingStatus> {
  return fetchApi<UpcomingStatus>('/artists/fetch-missing', { method: 'POST' });
}

// New Releases (AOTY)
export async function getNewReleases(year?: number, week?: number): Promise<NewRelease[]> {
  const params = new URLSearchParams();
  if (year) params.append('year', year.toString());
  if (week) params.append('week', week.toString());
  const queryString = params.toString();
  return fetchApi<NewRelease[]>(`/new-releases${queryString ? `?${queryString}` : ''}`);
}

export async function scrapeNewReleases(year?: number, week?: number): Promise<NewReleasesScrapeStatus> {
  const params = new URLSearchParams();
  if (year) params.append('year', year.toString());
  if (week) params.append('week', week.toString());
  const queryString = params.toString();
  return fetchApi<NewReleasesScrapeStatus>(`/new-releases/scrape${queryString ? `?${queryString}` : ''}`, {
    method: 'POST',
  });
}

export async function getNewReleasesScrapeStatus(): Promise<NewReleasesScrapeStatus> {
  return fetchApi<NewReleasesScrapeStatus>('/new-releases/status');
}

// Downloads (slskd integration)
export async function getSlskdStatus(): Promise<SlskdStatus> {
  return fetchApi<SlskdStatus>('/downloads/slskd-status');
}

export async function getDownloads(): Promise<Download[]> {
  return fetchApi<Download[]>('/downloads');
}

export async function getDownload(downloadId: number): Promise<Download> {
  return fetchApi<Download>(`/downloads/${downloadId}`);
}

export async function startDownload(albumId: number): Promise<Download> {
  return fetchApi<Download>(`/downloads/${albumId}`, { method: 'POST' });
}

export async function moveDownload(downloadId: number): Promise<void> {
  await fetchApi(`/downloads/${downloadId}/move`, { method: 'POST' });
}

export async function retryDownload(downloadId: number): Promise<Download> {
  return fetchApi<Download>(`/downloads/${downloadId}/retry`, { method: 'POST' });
}

export async function cancelDownload(downloadId: number): Promise<Download> {
  return fetchApi<Download>(`/downloads/${downloadId}/cancel`, { method: 'POST' });
}

export async function deleteDownload(downloadId: number): Promise<void> {
  await fetchApi(`/downloads/${downloadId}`, { method: 'DELETE' });
}

// Cancel scan
export async function cancelScan(): Promise<ScanStatus> {
  return fetchApi<ScanStatus>('/scan/cancel', { method: 'POST' });
}

// Metadata matching
export async function getMetadataMatches(albumId: number): Promise<MetadataMatchCandidate[]> {
  return fetchApi<MetadataMatchCandidate[]>(`/albums/${albumId}/metadata-matches`);
}

export async function applyMetadata(albumId: number, musicbrainzId: string): Promise<Album> {
  return fetchApi<Album>(`/albums/${albumId}/apply-metadata`, {
    method: 'POST',
    body: JSON.stringify({ musicbrainz_id: musicbrainzId }),
  });
}

// Settings
export async function getAppSettings(): Promise<AppSettings> {
  return fetchApi<AppSettings>('/settings');
}

// Vinyl Releases
export async function getVinylReleases(skip = 0, limit = 50): Promise<VinylRelease[]> {
  return fetchApi<VinylRelease[]>(`/vinyl-releases?skip=${skip}&limit=${limit}`);
}

export async function scrapeVinylReleases(): Promise<VinylReleasesScrapeStatus> {
  return fetchApi<VinylReleasesScrapeStatus>('/vinyl-releases/scrape', { method: 'POST' });
}

export async function getVinylReleasesStatus(): Promise<VinylReleasesScrapeStatus> {
  return fetchApi<VinylReleasesScrapeStatus>('/vinyl-releases/status');
}

export async function deleteVinylRelease(releaseId: number): Promise<void> {
  await fetchApi(`/vinyl-releases/${releaseId}`, { method: 'DELETE' });
}

// Concerts
import type { Concert, ConcertScrapeStatus } from './types';

export async function getConcerts(skip = 0, limit = 50): Promise<Concert[]> {
  return fetchApi<Concert[]>(`/concerts?skip=${skip}&limit=${limit}`);
}

export async function scrapeConcerts(): Promise<ConcertScrapeStatus> {
  return fetchApi<ConcertScrapeStatus>('/concerts/scrape', { method: 'POST' });
}

export async function getConcertStatus(): Promise<ConcertScrapeStatus> {
  return fetchApi<ConcertScrapeStatus>('/concerts/status');
}

export async function deleteConcert(concertId: number): Promise<void> {
  await fetchApi(`/concerts/${concertId}`, { method: 'DELETE' });
}
