import { useState, useEffect } from 'react';
import type { Album } from '../types';
import { getAlbums } from '../api';
import AlbumCard from './AlbumCard';

interface AlbumsViewProps {
  onAlbumClick: (albumId: number) => void;
}

export default function AlbumsView({ onAlbumClick }: AlbumsViewProps) {
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  useEffect(() => {
    const fetchAlbums = async () => {
      try {
        const data = await getAlbums(search);
        setAlbums(data);
      } catch (error) {
        console.error('Error fetching albums:', error);
      } finally {
        setLoading(false);
      }
    };

    const debounce = setTimeout(fetchAlbums, search ? 300 : 0);
    return () => clearTimeout(debounce);
  }, [search]);

  return (
    <>
      <header className="header">
        <h1>Albums</h1>
        <div className="search-box">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
          <input
            type="text"
            placeholder="Search albums..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
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
              <circle cx="12" cy="12" r="10"/>
              <circle cx="12" cy="12" r="3"/>
              <path d="M12 2v4M12 18v4"/>
            </svg>
            <h2>No albums found</h2>
            <p>Click "Scan Library" to discover albums in your music folder.</p>
          </div>
        ) : (
          <div className="albums-grid">
            {albums.map((album) => (
              <AlbumCard
                key={album.id}
                album={album}
                onClick={() => onAlbumClick(album.id)}
              />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

