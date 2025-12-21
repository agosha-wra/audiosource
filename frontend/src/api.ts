import type { Album, Artist, ScanStatus, Stats, MusicBrainzSearchResult, WishlistAddRequest, UpcomingStatus } from './types';

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

export async function getAlbums(search = ''): Promise<Album[]> {
  const params = search ? `?search=${encodeURIComponent(search)}` : '';
  return fetchApi<Album[]>(`/albums${params}`);
}

export async function getAlbum(id: number): Promise<Album> {
  return fetchApi<Album>(`/albums/${id}`);
}

export async function getArtists(): Promise<Artist[]> {
  return fetchApi<Artist[]>('/artists');
}

export async function getArtist(id: number): Promise<Artist> {
  return fetchApi<Artist>(`/artists/${id}`);
}

export async function getArtistAlbums(artistId: number): Promise<Album[]> {
  return fetchApi<Album[]>(`/artists/${artistId}/albums`);
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

