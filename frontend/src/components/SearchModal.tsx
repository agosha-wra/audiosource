import { useState, useEffect, useRef } from 'react';
import type { MusicBrainzSearchResult, SlskdStatus } from '../types';
import { searchMusicBrainz, addToWishlist, startDownload, getSlskdStatus } from '../api';

interface SearchModalProps {
  onClose: () => void;
  onAlbumAdded: () => void;
}

export default function SearchModal({ onClose, onAlbumAdded }: SearchModalProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<MusicBrainzSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [pendingAction, setPendingAction] = useState<Record<string, 'add' | 'download'>>({});
  const [slskdStatus, setSlskdStatus] = useState<SlskdStatus | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const canDownload = Boolean(slskdStatus?.enabled && slskdStatus?.available);

  // The parent re-renders on every status poll and hands us a new onClose each time.
  // Keep the latest one in a ref so the setup effect below runs once, instead of
  // re-focusing the input and refetching slskd status on every poll tick.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    inputRef.current?.focus();
    
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCloseRef.current();
    };
    document.addEventListener('keydown', handleEscape);
    getSlskdStatus().then(setSlskdStatus).catch(() => setSlskdStatus(null));
    return () => document.removeEventListener('keydown', handleEscape);
  }, []);

  useEffect(() => {
    if (query.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }

    // MusicBrainz responses can arrive out of order. Once the query changes, the
    // cleanup marks this run stale so its results are never applied.
    let stale = false;
    const debounce = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await searchMusicBrainz(query);
        if (!stale) setResults(data);
      } catch (error) {
        console.error('Search error:', error);
      } finally {
        if (!stale) setLoading(false);
      }
    }, 400);

    return () => {
      stale = true;
      clearTimeout(debounce);
    };
  }, [query]);

  const wishlistPayload = (result: MusicBrainzSearchResult) => ({
    album_id: result.existing_album_id || undefined,
    musicbrainz_id: result.musicbrainz_id,
    title: result.title,
    artist_name: result.artist_name || undefined,
    artist_musicbrainz_id: result.artist_musicbrainz_id || undefined,
    release_date: result.release_date || undefined,
    release_type: result.release_type || undefined,
    cover_art_url: result.cover_art_url || undefined,
  });

  const markWishlisted = (musicbrainzId: string) => {
    setResults(prev => prev.map(r =>
      r.musicbrainz_id === musicbrainzId
        ? { ...r, is_wishlisted: true }
        : r
    ));
  };

  const withPending = async (
    musicbrainzId: string,
    actionName: 'add' | 'download',
    action: () => Promise<void>
  ) => {
    if (pendingAction[musicbrainzId]) return;
    setPendingAction(prev => ({ ...prev, [musicbrainzId]: actionName }));
    try {
      await action();
    } finally {
      setPendingAction(prev => {
        const next = { ...prev };
        delete next[musicbrainzId];
        return next;
      });
    }
  };

  const handleAdd = (result: MusicBrainzSearchResult) => {
    void withPending(result.musicbrainz_id, 'add', async () => {
      try {
        await addToWishlist(wishlistPayload(result));
        markWishlisted(result.musicbrainz_id);
        onAlbumAdded();
      } catch (error) {
        console.error('Error adding to wishlist:', error);
      }
    });
  };

  const handleAddAndDownload = (result: MusicBrainzSearchResult) => {
    void withPending(result.musicbrainz_id, 'download', async () => {
      try {
        const album = await addToWishlist(wishlistPayload(result));
        markWishlisted(result.musicbrainz_id);
        onAlbumAdded();
        await startDownload(album.id);
      } catch (error) {
        console.error('Error adding album and starting download:', error);
      }
    });
  };

  return (
    <div className="modal active search-modal">
      <div className="modal-backdrop" onClick={onClose} />
      <div className="modal-content search-modal-content">
        <button className="modal-close" onClick={onClose}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
        
        <div className="search-modal-header">
          <h2>Search Albums</h2>
          <p>Search MusicBrainz to find albums and add them to your wishlist</p>
        </div>
        
        <div className="search-modal-input">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/>
            <path d="M21 21l-4.35-4.35"/>
          </svg>
          <input
            ref={inputRef}
            type="text"
            placeholder="Search for albums, artists..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {loading && <div className="search-spinner" />}
        </div>
        
        <div className="search-results">
          {query.length < 2 ? (
            <div className="search-hint">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="12" r="10"/>
                <path d="M12 16v-4M12 8h.01"/>
              </svg>
              <p>Type at least 2 characters to search</p>
            </div>
          ) : results.length === 0 && !loading ? (
            <div className="search-hint">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="12" r="10"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
              <p>No albums found for "{query}"</p>
            </div>
          ) : (
            results.map((result) => (
              <div key={result.musicbrainz_id} className="search-result-item">
                <div className="search-result-cover">
                  {result.cover_art_url ? (
                    <img
                      src={result.cover_art_url}
                      alt={result.title}
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                      }}
                    />
                  ) : (
                    <div className="cover-placeholder">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <circle cx="12" cy="12" r="10"/>
                        <circle cx="12" cy="12" r="3"/>
                      </svg>
                    </div>
                  )}
                </div>
                
                <div className="search-result-info">
                  <div className="search-result-title">{result.title}</div>
                  <div className="search-result-artist">{result.artist_name || 'Unknown Artist'}</div>
                  <div className="search-result-meta">
                    {result.release_date && <span>{result.release_date.substring(0, 4)}</span>}
                    {result.release_type && <span>{result.release_type}</span>}
                  </div>
                </div>
                
                <div className="search-result-actions">
                  {result.is_owned ? (
                    <span className="status-badge owned">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M20 6L9 17l-5-5"/>
                      </svg>
                      Owned
                    </span>
                  ) : result.is_wishlisted ? (
                    <span className="status-badge wishlisted">
                      <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                      </svg>
                      Wishlisted
                    </span>
                  ) : (
                    <>
                      <button
                        className="add-wishlist-btn"
                        onClick={() => handleAdd(result)}
                        disabled={Boolean(pendingAction[result.musicbrainz_id])}
                        aria-label={`Add ${result.title} to wishlist`}
                        title="Add to wishlist"
                      >
                        {pendingAction[result.musicbrainz_id] === 'add' ? (
                          <div className="btn-spinner" />
                        ) : (
                          <>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                            </svg>
                            <span className="add-wishlist-btn-label">Add to Wishlist</span>
                          </>
                        )}
                      </button>
                      {canDownload && (
                        <button
                          className="add-wishlist-btn add-download-btn"
                          onClick={() => handleAddAndDownload(result)}
                          disabled={Boolean(pendingAction[result.musicbrainz_id])}
                          aria-label={`Add ${result.title} and start download`}
                          title="Add album and launch download"
                        >
                          {pendingAction[result.musicbrainz_id] === 'download' ? (
                            <div className="btn-spinner" />
                          ) : (
                          <>
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                            <polyline points="7 10 12 15 17 10"/>
                            <line x1="12" y1="15" x2="12" y2="3"/>
                          </svg>
                          <span className="add-wishlist-btn-label">Add album and launch download</span>
                          </>
                          )}
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

