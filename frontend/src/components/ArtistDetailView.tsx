import { useState, useEffect } from 'react';
import type { Artist, Album } from '../types';
import { getArtist, getArtistAlbums, enrichArtistAoty } from '../api';
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
  const [enriching, setEnriching] = useState(false);
  const [enrichResult, setEnrichResult] = useState<string | null>(null);

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

  useEffect(() => {
    fetchData();
  }, [artistId]);

  const handleEnrichAoty = async () => {
    if (enriching) return;
    setEnriching(true);
    setEnrichResult(null);
    
    try {
      const result = await enrichArtistAoty(artistId);
      setEnrichResult(`✓ Enriched ${result.enriched} albums with AOTY scores`);
      // Refresh the albums to show the new scores
      await fetchData();
    } catch (error) {
      console.error('Error enriching with AOTY:', error);
      setEnrichResult('✗ Failed to fetch AOTY data');
    } finally {
      setEnriching(false);
      // Clear the message after 5 seconds
      setTimeout(() => setEnrichResult(null), 5000);
    }
  };

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
                  showScore={false}
                />
              ))}
            </div>
          </div>
        )}

        {missingAlbums.length > 0 && (
          <div className="album-section missing-section">
            <div className="section-header-row">
              <h3 className="section-title missing">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"/>
                  <path d="M15 9l-6 6M9 9l6 6"/>
                </svg>
                Albums You're Missing ({missingAlbums.length})
              </h3>
              <button 
                className={`aoty-enrich-btn ${enriching ? 'loading' : ''}`}
                onClick={handleEnrichAoty}
                disabled={enriching}
                title="Fetch critic scores from Album of the Year"
              >
                {enriching ? (
                  <>
                    <div className="loading-spinner-small" />
                    Fetching...
                  </>
                ) : (
                  <>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/>
                    </svg>
                    Get AOTY Scores
                  </>
                )}
              </button>
            </div>
            {enrichResult && (
              <div className={`enrich-result ${enrichResult.startsWith('✓') ? 'success' : 'error'}`}>
                {enrichResult}
              </div>
            )}
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

