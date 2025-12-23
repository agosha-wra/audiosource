import { useState, useEffect, useCallback } from 'react';
import type { Album, SlskdStatus } from '../types';
import { getWishlist, removeFromWishlist, getSlskdStatus, startDownload, startWishlistDownload, getWishlistDownloadStatus, type WishlistDownloadStatus } from '../api';
import AlbumCard from './AlbumCard';

interface WishlistViewProps {
  onAlbumClick: (albumId: number) => void;
  onOpenSearch: () => void;
}

export default function WishlistView({ onAlbumClick, onOpenSearch }: WishlistViewProps) {
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const [slskdStatus, setSlskdStatus] = useState<SlskdStatus | null>(null);
  const [downloadingIds, setDownloadingIds] = useState<Set<number>>(new Set());
  const [wishlistStatus, setWishlistStatus] = useState<WishlistDownloadStatus | null>(null);
  const [startingWishlist, setStartingWishlist] = useState(false);

  const fetchWishlistStatus = useCallback(async () => {
    try {
      const status = await getWishlistDownloadStatus();
      setWishlistStatus(status);
    } catch (error) {
      console.error('Error fetching wishlist status:', error);
    }
  }, []);

  const fetchSlskdStatus = useCallback(async () => {
    try {
      const status = await getSlskdStatus();
      setSlskdStatus(status);
    } catch (error) {
      console.error('Error fetching slskd status:', error);
    }
  }, []);

  const fetchWishlist = async () => {
    try {
      const data = await getWishlist();
      setAlbums(data);
    } catch (error) {
      console.error('Error fetching wishlist:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWishlist();
    fetchSlskdStatus();
    fetchWishlistStatus();
  }, [fetchSlskdStatus, fetchWishlistStatus]);

  // Poll wishlist download status when running
  useEffect(() => {
    if (!wishlistStatus?.running) return;

    const interval = setInterval(() => {
      fetchWishlistStatus();
    }, 3000);

    return () => clearInterval(interval);
  }, [wishlistStatus?.running, fetchWishlistStatus]);

  const handleStartWishlistDownload = async () => {
    setStartingWishlist(true);
    try {
      await startWishlistDownload();
      fetchWishlistStatus();
    } catch (error) {
      console.error('Error starting wishlist download:', error);
    } finally {
      setStartingWishlist(false);
    }
  };

  const handleRemove = async (e: React.MouseEvent, albumId: number) => {
    e.stopPropagation();
    try {
      await removeFromWishlist(albumId);
      setAlbums(albums.filter(a => a.id !== albumId));
    } catch (error) {
      console.error('Error removing from wishlist:', error);
    }
  };

  const handleDownload = async (e: React.MouseEvent, albumId: number) => {
    e.stopPropagation();
    if (downloadingIds.has(albumId)) return;
    
    setDownloadingIds(prev => new Set(prev).add(albumId));
    
    try {
      await startDownload(albumId);
      // Keep the downloading state to show feedback
    } catch (error) {
      console.error('Error starting download:', error);
      setDownloadingIds(prev => {
        const next = new Set(prev);
        next.delete(albumId);
        return next;
      });
    }
  };

  // Check if album is upcoming (future release date)
  // Only works with ISO format dates (YYYY-MM-DD)
  const isUpcoming = (album: Album) => {
    if (!album.release_date) return false;
    // Only do comparison if it looks like an ISO date
    if (!/^\d{4}-\d{2}-\d{2}/.test(album.release_date)) return false;
    const today = new Date().toISOString().split('T')[0];
    return album.release_date > today;
  };

  const canDownload = slskdStatus?.enabled && slskdStatus?.available;

  return (
    <>
      <header className="header">
        <h1>Wishlist</h1>
        <div className="header-actions">
          {canDownload && albums.length > 0 && (
            wishlistStatus?.running ? (
              <div className="wishlist-download-progress">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="spin">
                  <path d="M21 12a9 9 0 11-6.219-8.56"/>
                </svg>
                <span>Downloading {wishlistStatus.processed_count}/{wishlistStatus.queued_count}</span>
              </div>
            ) : (
              <button 
                className="download-all-btn" 
                onClick={handleStartWishlistDownload}
                disabled={startingWishlist}
                title="Download all wishlist albums (one every 90 seconds)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="7 10 12 15 17 10"/>
                  <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                <span>{startingWishlist ? 'Starting...' : 'Download All'}</span>
              </button>
            )
          )}
          <button className="search-albums-btn" onClick={onOpenSearch}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"/>
              <path d="M21 21l-4.35-4.35"/>
            </svg>
            <span>Search Albums</span>
          </button>
        </div>
      </header>
      
      <div className="content">
        {loading ? (
          <div className="loading">
            <div className="loading-spinner" />
          </div>
        ) : albums.length === 0 ? (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
            </svg>
            <h2>Your wishlist is empty</h2>
            <p>Search for albums you want, add them from artist pages, or check for upcoming releases from the sidebar.</p>
            <button className="primary-btn" onClick={onOpenSearch}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8"/>
                <path d="M21 21l-4.35-4.35"/>
              </svg>
              <span>Search MusicBrainz</span>
            </button>
          </div>
        ) : (
          <div className="albums-grid wishlist-grid">
            {albums.map((album) => (
              <div key={album.id} className="wishlist-album-wrapper">
                <AlbumCard
                  album={album}
                  onClick={() => onAlbumClick(album.id)}
                  showWishlistButton={false}
                />
                {isUpcoming(album) && (
                  <div className="upcoming-icon" title={`Upcoming: ${album.release_date}`}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10"/>
                      <polyline points="12,6 12,12 16,14"/>
                    </svg>
                  </div>
                )}
                {canDownload && !isUpcoming(album) && (
                  <button 
                    className={`download-wishlist-btn ${downloadingIds.has(album.id) ? 'downloading' : ''}`}
                    onClick={(e) => handleDownload(e, album.id)}
                    title={downloadingIds.has(album.id) ? 'Download started...' : 'Download from Soulseek'}
                    disabled={downloadingIds.has(album.id)}
                  >
                    {downloadingIds.has(album.id) ? (
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="spin">
                        <path d="M21 12a9 9 0 11-6.219-8.56"/>
                      </svg>
                    ) : (
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                      </svg>
                    )}
                  </button>
                )}
                <button 
                  className="remove-wishlist-btn"
                  onClick={(e) => handleRemove(e, album.id)}
                  title="Remove from wishlist"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M18 6L6 18M6 6l12 12"/>
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
