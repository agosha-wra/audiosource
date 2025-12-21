import type { Album } from '../types';

interface AlbumCardProps {
  album: Album;
  isMissing?: boolean;
  onClick: () => void;
}

export default function AlbumCard({ album, isMissing = false, onClick }: AlbumCardProps) {
  return (
    <div
      className={`album-card ${isMissing || !album.is_owned ? 'missing' : ''}`}
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

