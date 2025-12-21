import { useState, useEffect } from 'react';
import type { Album, UpcomingStatus } from '../types';
import { getWishlist, removeFromWishlist, checkUpcomingReleases, getUpcomingStatus } from '../api';
import AlbumCard from './AlbumCard';

interface WishlistViewProps {
  onAlbumClick: (albumId: number) => void;
  onOpenSearch: () => void;
}

export default function WishlistView({ onAlbumClick, onOpenSearch }: WishlistViewProps) {
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const [upcomingStatus, setUpcomingStatus] = useState<UpcomingStatus | null>(null);
  const [isCheckingUpcoming, setIsCheckingUpcoming] = useState(false);

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

  const fetchUpcomingStatus = async () => {
    try {
      const status = await getUpcomingStatus();
      setUpcomingStatus(status);
      return status;
    } catch (error) {
      console.error('Error fetching upcoming status:', error);
      return null;
    }
  };

  useEffect(() => {
    fetchWishlist();
    fetchUpcomingStatus();
  }, []);

  useEffect(() => {
    if (!isCheckingUpcoming) return;

    const interval = setInterval(async () => {
      const status = await fetchUpcomingStatus();
      if (status && (status.status === 'completed' || status.status === 'error' || status.status === 'idle')) {
        setIsCheckingUpcoming(false);
        fetchWishlist();
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [isCheckingUpcoming]);

  const handleCheckUpcoming = async () => {
    try {
      await checkUpcomingReleases();
      setIsCheckingUpcoming(true);
    } catch (error) {
      console.error('Error starting upcoming check:', error);
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

  // Separate upcoming from regular wishlist items
  const today = new Date().toISOString().split('T')[0];
  const upcomingAlbums = albums.filter(a => a.release_date && a.release_date > today);
  const regularAlbums = albums.filter(a => !a.release_date || a.release_date <= today);

  return (
    <>
      <header className="header">
        <h1>Wishlist</h1>
        <div className="header-actions">
          <button 
            className="upcoming-btn"
            onClick={handleCheckUpcoming}
            disabled={isCheckingUpcoming}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12,6 12,12 16,14"/>
            </svg>
            {isCheckingUpcoming 
              ? `Checking ${upcomingStatus?.artists_checked || 0}/${upcomingStatus?.total_artists || 0}...`
              : 'Check Upcoming'}
          </button>
          <button className="search-albums-btn" onClick={onOpenSearch}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"/>
              <path d="M21 21l-4.35-4.35"/>
            </svg>
            Search Albums
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
            <p>Search for albums you want, add them from artist pages, or check for upcoming releases.</p>
            <div className="empty-state-actions">
              <button className="primary-btn" onClick={onOpenSearch}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8"/>
                  <path d="M21 21l-4.35-4.35"/>
                </svg>
                Search MusicBrainz
              </button>
              <button className="secondary-btn" onClick={handleCheckUpcoming} disabled={isCheckingUpcoming}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"/>
                  <polyline points="12,6 12,12 16,14"/>
                </svg>
                {isCheckingUpcoming ? 'Checking...' : 'Check Upcoming Releases'}
              </button>
            </div>
          </div>
        ) : (
          <>
            {upcomingAlbums.length > 0 && (
              <div className="wishlist-section">
                <h2 className="section-header upcoming">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10"/>
                    <polyline points="12,6 12,12 16,14"/>
                  </svg>
                  Upcoming Releases ({upcomingAlbums.length})
                </h2>
                <div className="albums-grid wishlist-grid">
                  {upcomingAlbums.map((album) => (
                    <div key={album.id} className="wishlist-album-wrapper upcoming-album">
                      <AlbumCard
                        album={album}
                        onClick={() => onAlbumClick(album.id)}
                        showWishlistButton={false}
                      />
                      <div className="upcoming-badge">
                        {album.release_date}
                      </div>
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
              </div>
            )}

            {regularAlbums.length > 0 && (
              <div className="wishlist-section">
                {upcomingAlbums.length > 0 && (
                  <h2 className="section-header">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                    </svg>
                    Wishlist ({regularAlbums.length})
                  </h2>
                )}
                <div className="albums-grid wishlist-grid">
                  {regularAlbums.map((album) => (
                    <div key={album.id} className="wishlist-album-wrapper">
                      <AlbumCard
                        album={album}
                        onClick={() => onAlbumClick(album.id)}
                        showWishlistButton={false}
                      />
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
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
