import { useState, useEffect } from 'react';
import type { Artist } from '../types';
import { getArtists } from '../api';

interface ArtistsViewProps {
  onArtistClick: (artistId: number) => void;
}

function getInitials(name: string): string {
  if (!name) return '?';
  return name.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();
}

export default function ArtistsView({ onArtistClick }: ArtistsViewProps) {
  const [artists, setArtists] = useState<Artist[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchArtists = async () => {
      try {
        const data = await getArtists();
        setArtists(data);
      } catch (error) {
        console.error('Error fetching artists:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchArtists();
  }, []);

  return (
    <>
      <header className="header">
        <h1>Artists</h1>
        <div className="search-box">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
          <input type="text" placeholder="Search artists..." />
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
          <div className="artists-grid">
            {artists.map((artist) => (
              <div
                key={artist.id}
                className="artist-card"
                onClick={() => onArtistClick(artist.id)}
              >
                <div className="artist-avatar">{getInitials(artist.name)}</div>
                <div className="artist-name">{artist.name}</div>
                <div className="artist-album-counts">
                  <span className="owned-count">{artist.owned_album_count || 0} owned</span>
                  {(artist.missing_album_count || 0) > 0 && (
                    <span className="missing-count">{artist.missing_album_count} missing</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

