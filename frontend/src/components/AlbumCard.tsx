import { useState } from 'react';
import type { Album } from '../types';
import { addToWishlist, removeFromWishlist } from '../api';

interface AlbumCardProps {
  album: Album;
  isMissing?: boolean;
  onClick: () => void;
  showWishlistButton?: boolean;
  onWishlistChange?: () => void;
}

export default function AlbumCard({ 
  album, 
  isMissing = false, 
  onClick,
  showWishlistButton = true,
  onWishlistChange
}: AlbumCardProps) {
  const [isWishlisted, setIsWishlisted] = useState(album.is_wishlisted);
  const [isUpdating, setIsUpdating] = useState(false);

  const handleWishlistClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isUpdating || album.is_owned) return;
    
    setIsUpdating(true);
    try {
      if (isWishlisted) {
        await removeFromWishlist(album.id);
        setIsWishlisted(false);
      } else {
        await addToWishlist({ album_id: album.id });
        setIsWishlisted(true);
      }
      onWishlistChange?.();
    } catch (error) {
      console.error('Error updating wishlist:', error);
    } finally {
      setIsUpdating(false);
    }
  };

  const showButton = showWishlistButton && !album.is_owned;

  return (
    <div
      className={`album-card ${isMissing || !album.is_owned ? 'missing' : ''} ${isWishlisted ? 'wishlisted' : ''}`}
      onClick={onClick}
    >
      <div className="album-cover">
        {album.cover_art_url ? (
          <img
            src={album.cover_art_url}
            alt={album.title}
            onError={(e) => {
              e.currentTarget.style.display = 'none';
              e.currentTarget.parentElement?.classList.add('show-placeholder');
            }}
          />
        ) : (
          <div className="album-cover-placeholder">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="10"/>
              <circle cx="12" cy="12" r="3"/>
            </svg>
          </div>
        )}
        {showButton && (
          <button 
            className={`wishlist-btn ${isWishlisted ? 'active' : ''} ${isUpdating ? 'updating' : ''}`}
            onClick={handleWishlistClick}
            title={isWishlisted ? 'Remove from wishlist' : 'Add to wishlist'}
          >
            <svg viewBox="0 0 24 24" fill={isWishlisted ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
            </svg>
          </button>
        )}
      </div>
      <div className="album-info">
        <div className="album-title">{album.title}</div>
        <div className="album-artist">{album.artist?.name || 'Unknown Artist'}</div>
        <div className="album-meta">
          {album.release_date && <span>{album.release_date.substring(0, 4)}</span>}
          {album.release_type && <span>{album.release_type}</span>}
        </div>
      </div>
    </div>
  );
}
