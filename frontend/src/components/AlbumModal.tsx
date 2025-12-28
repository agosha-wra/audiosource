import { useState, useEffect } from 'react';
import type { Album, Track } from '../types';
import { getAlbum } from '../api';
import MetadataMatchModal from './MetadataMatchModal';

interface AlbumModalProps {
  albumId: number;
  onClose: () => void;
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes} min`;
}

function formatTrackDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export default function AlbumModal({ albumId, onClose }: AlbumModalProps) {
  const [album, setAlbum] = useState<Album | null>(null);
  const [loading, setLoading] = useState(true);
  const [showMetadataMatch, setShowMetadataMatch] = useState(false);

  useEffect(() => {
    const fetchAlbum = async () => {
      try {
        const data = await getAlbum(albumId);
        setAlbum(data);
      } catch (error) {
        console.error('Error fetching album:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchAlbum();
  }, [albumId]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  const tracks = album?.tracks || [];
  const totalDuration = tracks.reduce((sum, t) => sum + (t.duration_seconds || 0), 0);
  const sortedTracks = [...tracks].sort((a, b) => 
    (a.disc_number - b.disc_number) || ((a.track_number || 0) - (b.track_number || 0))
  );

  const handleMetadataApplied = async () => {
    // Refresh album data
    try {
      const data = await getAlbum(albumId);
      setAlbum(data);
    } catch (error) {
      console.error('Error refreshing album:', error);
    }
  };

  return (
    <div className="modal active">
      <div className="modal-backdrop" onClick={onClose} />
      <div className="modal-content">
        <button className="modal-close" onClick={onClose}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
        
        {loading ? (
          <div className="loading" style={{ padding: '80px' }}>
            <div className="loading-spinner" />
          </div>
        ) : album ? (
          <div className="album-detail">
            <div className="album-detail-cover">
              {album.cover_art_url ? (
                <img
                  src={album.cover_art_url.replace('-250', '-500')}
                  alt={album.title}
                  onError={(e) => {
                    e.currentTarget.src = album.cover_art_url || '';
                  }}
                />
              ) : (
                <div className="album-cover-placeholder" style={{ height: '100%' }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <circle cx="12" cy="12" r="10"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                </div>
              )}
            </div>
            
            <div className="album-detail-info">
              <div className="album-header-row">
                <div className={`album-ownership-status ${album.is_owned ? 'owned' : 'missing'}`}>
                  {album.is_owned ? '✓ In Your Library' : '✗ Not In Library'}
                </div>
                {album.is_owned && (
                  <button 
                    className="fix-metadata-btn"
                    onClick={() => setShowMetadataMatch(true)}
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                    Fix Metadata
                  </button>
                )}
              </div>
              
              <h2>{album.title}</h2>
              <div className="album-detail-artist">
                {album.artist?.name || 'Unknown Artist'}
              </div>
              
              <div className="album-detail-meta">
                {album.release_type && (
                  <span>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10"/>
                    </svg>
                    {album.release_type}
                  </span>
                )}
                {album.release_date && (
                  <span>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="3" y="4" width="18" height="18" rx="2"/>
                      <path d="M16 2v4M8 2v4M3 10h18"/>
                    </svg>
                    {album.release_date}
                  </span>
                )}
                {tracks.length > 0 && (
                  <span>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M9 18V5l12-2v13"/>
                      <circle cx="6" cy="18" r="3"/>
                      <circle cx="18" cy="16" r="3"/>
                    </svg>
                    {tracks.length} tracks
                  </span>
                )}
                {totalDuration > 0 && (
                  <span>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10"/>
                      <path d="M12 6v6l4 2"/>
                    </svg>
                    {formatDuration(totalDuration)}
                  </span>
                )}
              </div>

              {tracks.length > 0 ? (
                <div className="tracks-list">
                  <h3>Tracklist</h3>
                  {sortedTracks.map((track) => (
                    <TrackItem key={track.id} track={track} />
                  ))}
                </div>
              ) : (
                <div className="no-tracks">
                  <p>No track information available for this album.</p>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="empty-state" style={{ padding: '40px' }}>
            <h2>Album not found</h2>
          </div>
        )}
      </div>

      {showMetadataMatch && album && (
        <MetadataMatchModal
          albumId={album.id}
          albumTitle={album.title}
          artistName={album.artist?.name || 'Unknown Artist'}
          onClose={() => setShowMetadataMatch(false)}
          onApplied={handleMetadataApplied}
        />
      )}
    </div>
  );
}

function TrackItem({ track }: { track: Track }) {
  return (
    <div className="track-item">
      <span className="track-number">{track.track_number || '-'}</span>
      <span className="track-title">{track.title}</span>
      <span className="track-duration">
        {track.duration_seconds ? formatTrackDuration(track.duration_seconds) : '--:--'}
      </span>
    </div>
  );
}

