import { useState, useEffect, useRef, useCallback } from 'react';
import type { Artist } from '../types';
import { getArtists, deleteArtist } from '../api';

interface ArtistsViewProps {
  onArtistClick: (artistId: number) => void;
}

const ARTISTS_PER_PAGE = 100;

const SORT_OPTIONS = [
  { value: 'name', label: 'Name (A-Z)' },
  { value: 'name_desc', label: 'Name (Z-A)' },
  { value: 'date_added', label: 'Recently Added' },
];

function getInitials(name: string): string {
  if (!name) return '?';
  return name.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();
}

export default function ArtistsView({ onArtistClick }: ArtistsViewProps) {
  const [artists, setArtists] = useState<Artist[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [sort, setSort] = useState('name');
  const [deleting, setDeleting] = useState<Set<number>>(new Set());
  const observerRef = useRef<IntersectionObserver | null>(null);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);

  // Fetch initial artists or when sort changes
  useEffect(() => {
    const fetchArtists = async () => {
      setLoading(true);
      try {
        const data = await getArtists(0, ARTISTS_PER_PAGE, sort);
        setArtists(data);
        setHasMore(data.length === ARTISTS_PER_PAGE);
      } catch (error) {
        console.error('Error fetching artists:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchArtists();
  }, [sort]);

  // Load more artists when scrolling
  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    
    setLoadingMore(true);
    try {
      const data = await getArtists(artists.length, ARTISTS_PER_PAGE, sort);
      setArtists(prev => [...prev, ...data]);
      setHasMore(data.length === ARTISTS_PER_PAGE);
    } catch (error) {
      console.error('Error loading more artists:', error);
    } finally {
      setLoadingMore(false);
    }
  }, [artists.length, hasMore, loadingMore, sort]);

  // Intersection observer for infinite scroll
  useEffect(() => {
    if (loading) return;

    observerRef.current = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loadingMore) {
          loadMore();
        }
      },
      { threshold: 0.1 }
    );

    if (loadMoreRef.current) {
      observerRef.current.observe(loadMoreRef.current);
    }

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
      }
    };
  }, [loading, hasMore, loadingMore, loadMore]);

  const handleDelete = async (e: React.MouseEvent, artistId: number) => {
    e.stopPropagation();
    
    if (deleting.has(artistId)) return;
    
    setDeleting(prev => new Set(prev).add(artistId));
    
    try {
      await deleteArtist(artistId);
      setArtists(artists.filter(a => a.id !== artistId));
    } catch (error) {
      console.error('Error deleting artist:', error);
    } finally {
      setDeleting(prev => {
        const next = new Set(prev);
        next.delete(artistId);
        return next;
      });
    }
  };

  const canDelete = (artist: Artist) => {
    return (artist.owned_album_count || 0) === 0;
  };

  return (
    <>
      <header className="header">
        <h1>Artists</h1>
        <div className="header-controls">
          <select 
            className="sort-select" 
            value={sort} 
            onChange={(e) => setSort(e.target.value)}
          >
            {SORT_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
      </header>
      
      <div className="content">
        {loading ? (
          <div className="loading">
            <div className="loading-spinner" />
          </div>
        ) : artists.length === 0 ? (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="8" r="4"/>
              <path d="M4 20c0-4 4-6 8-6s8 2 8 6"/>
            </svg>
            <h2>No artists found</h2>
            <p>Scan your library to discover artists.</p>
          </div>
        ) : (
          <>
            <div className="artists-grid">
              {artists.map((artist) => (
                <div
                  key={artist.id}
                  className="artist-card"
                  onClick={() => onArtistClick(artist.id)}
                >
                  {canDelete(artist) && (
                    <button
                      className="artist-delete-btn"
                      onClick={(e) => handleDelete(e, artist.id)}
                      disabled={deleting.has(artist.id)}
                      title="Delete artist"
                    >
                      {deleting.has(artist.id) ? (
                        <div className="btn-spinner-small" />
                      ) : (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M18 6L6 18M6 6l12 12"/>
                        </svg>
                      )}
                    </button>
                  )}
                  {artist.image_url ? (
                    <div className="artist-image">
                      <img 
                        src={artist.image_url} 
                        alt={artist.name}
                        onError={(e) => {
                          e.currentTarget.style.display = 'none';
                          e.currentTarget.parentElement?.classList.add('show-fallback');
                        }}
                      />
                      <span className="artist-initials">{getInitials(artist.name)}</span>
                    </div>
                  ) : (
                    <div className="artist-avatar">{getInitials(artist.name)}</div>
                  )}
                  <div className="artist-name">{artist.name}</div>
                  <div className="artist-album-counts">
                    <span className="owned-count">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M20 6L9 17l-5-5"/>
                      </svg>
                      {artist.owned_album_count || 0}
                    </span>
                    {(artist.missing_album_count || 0) > 0 && (
                      <span className="missing-count">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="12" cy="12" r="10"/>
                          <path d="M15 9l-6 6M9 9l6 6"/>
                        </svg>
                        {artist.missing_album_count}
                      </span>
                    )}
                    {(artist.wishlisted_album_count || 0) > 0 && (
                      <span className="wishlisted-count">
                        <svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="2">
                          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                        </svg>
                        {artist.wishlisted_album_count}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <div ref={loadMoreRef} className="load-more-trigger">
              {loadingMore && (
                <div className="loading-more">
                  <div className="loading-spinner" />
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
