import { useState, useEffect, useRef, useCallback } from 'react';
import type { Album } from '../types';
import { getAlbums } from '../api';
import AlbumCard from './AlbumCard';

interface AlbumsViewProps {
  onAlbumClick: (albumId: number) => void;
}

const ALBUMS_PER_PAGE = 100;

export default function AlbumsView({ onAlbumClick }: AlbumsViewProps) {
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [search, setSearch] = useState('');
  const observerRef = useRef<IntersectionObserver | null>(null);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);

  // Fetch initial albums or when search changes
  useEffect(() => {
    const fetchAlbums = async () => {
      setLoading(true);
      try {
        const data = await getAlbums(search, 0, ALBUMS_PER_PAGE);
        setAlbums(data);
        setHasMore(data.length === ALBUMS_PER_PAGE);
      } catch (error) {
        console.error('Error fetching albums:', error);
      } finally {
        setLoading(false);
      }
    };

    const debounce = setTimeout(fetchAlbums, search ? 300 : 0);
    return () => clearTimeout(debounce);
  }, [search]);

  // Load more albums when scrolling
  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    
    setLoadingMore(true);
    try {
      const data = await getAlbums(search, albums.length, ALBUMS_PER_PAGE);
      setAlbums(prev => [...prev, ...data]);
      setHasMore(data.length === ALBUMS_PER_PAGE);
    } catch (error) {
      console.error('Error loading more albums:', error);
    } finally {
      setLoadingMore(false);
    }
  }, [albums.length, hasMore, loadingMore, search]);

  // Intersection observer for infinite scroll
  useEffect(() => {
    if (loading) return;

    observerRef.current = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loadingMore) {
          loadMore();
        }
      },
      { threshold: 0.1 }
    );

    if (loadMoreRef.current) {
      observerRef.current.observe(loadMoreRef.current);
    }

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect();
      }
    };
  }, [loading, hasMore, loadingMore, loadMore]);

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
          <>
            <div className="albums-grid">
              {albums.map((album) => (
                <AlbumCard
                  key={album.id}
                  album={album}
                  onClick={() => onAlbumClick(album.id)}
                />
              ))}
            </div>
            {/* Infinite scroll trigger */}
            <div ref={loadMoreRef} className="load-more-trigger">
              {loadingMore && (
                <div className="loading-more">
                  <div className="loading-spinner" />
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}

