import { useState, useEffect } from 'react';
import type { Artist, Album } from '../types';
import { getArtist, getArtistAlbums } from '../api';
import AlbumCard from './AlbumCard';

interface ArtistDetailViewProps {
  artistId: number;
  onBack: () => void;
  onAlbumClick: (albumId: number) => void;
}

function getInitials(name: string): string {
  if (!name) return '?';
  return name.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();
}

export default function ArtistDetailView({ artistId, onBack, onAlbumClick }: ArtistDetailViewProps) {
  const [artist, setArtist] = useState<Artist | null>(null);
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [artistData, albumsData] = await Promise.all([
          getArtist(artistId),
          getArtistAlbums(artistId),
        ]);
        setArtist(artistData);
        setAlbums(albumsData);
      } catch (error) {
        console.error('Error fetching artist:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [artistId]);

  if (loading) {
    return (
      <div className="content">
        <div className="loading">
          <div className="loading-spinner" />
        </div>
      </div>
    );
  }

  if (!artist) {
    return (
      <div className="content">
        <div className="empty-state">
          <h2>Artist not found</h2>
        </div>
      </div>
    );
  }

  const ownedAlbums = albums.filter(a => a.is_owned);
  const missingAlbums = albums.filter(a => !a.is_owned);

  return (
    <>
      <header className="header">
        <h1>{artist.name}</h1>
      </header>
      
      <div className="content">
        <div className="artist-detail-header">
          <button className="back-btn" onClick={onBack}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
            Back to Artists
          </button>
          
          <div className="artist-detail-info">
            <div className="artist-detail-avatar">{getInitials(artist.name)}</div>
            <div>
              <h2>{artist.name}</h2>
              <div className="artist-detail-stats">
                <span className="owned-badge">{ownedAlbums.length} albums owned</span>
                <span className="missing-badge">{missingAlbums.length} albums missing</span>
              </div>
            </div>
          </div>
        </div>

        {ownedAlbums.length > 0 && (
          <div className="album-section">
            <h3 className="section-title owned">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
              Albums You Own ({ownedAlbums.length})
            </h3>
            <div className="albums-grid">
              {ownedAlbums.map((album) => (
                <AlbumCard
                  key={album.id}
                  album={album}
                  onClick={() => onAlbumClick(album.id)}
                />
              ))}
            </div>
          </div>
        )}

        {missingAlbums.length > 0 && (
          <div className="album-section missing-section">
            <h3 className="section-title missing">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <path d="M15 9l-6 6M9 9l6 6"/>
              </svg>
              Albums You're Missing ({missingAlbums.length})
            </h3>
            <div className="albums-grid">
              {missingAlbums.map((album) => (
                <AlbumCard
                  key={album.id}
                  album={album}
                  isMissing
                  onClick={() => onAlbumClick(album.id)}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

