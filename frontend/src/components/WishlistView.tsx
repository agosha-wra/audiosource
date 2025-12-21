import { useState, useEffect } from 'react';
import type { Album } from '../types';
import { getWishlist, removeFromWishlist } from '../api';
import AlbumCard from './AlbumCard';

interface WishlistViewProps {
  onAlbumClick: (albumId: number) => void;
  onOpenSearch: () => void;
}

export default function WishlistView({ onAlbumClick, onOpenSearch }: WishlistViewProps) {
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);

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
  }, []);

  const handleRemove = async (e: React.MouseEvent, albumId: number) => {
    e.stopPropagation();
    try {
      await removeFromWishlist(albumId);
      setAlbums(albums.filter(a => a.id !== albumId));
    } catch (error) {
      console.error('Error removing from wishlist:', error);
    }
  };

  return (
    <>
      <header className="header">
        <h1>Wishlist</h1>
        <button className="search-albums-btn" onClick={onOpenSearch}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
          Search Albums
        </button>
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
            <p>Search for albums you want or add them from artist pages.</p>
            <button className="primary-btn" onClick={onOpenSearch}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8"/>
                <path d="M21 21l-4.35-4.35"/>
              </svg>
              Search MusicBrainz
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

