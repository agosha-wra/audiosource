import { useState, useEffect, useCallback } from 'react';
import type { Album, SlskdStatus } from '../types';
import { getWishlist, removeFromWishlist, getSlskdStatus, startDownload, startBatchDownload } from '../api';
import AlbumCard from './AlbumCard';

// Mirrors BATCH_DOWNLOAD_INTERVAL_SECONDS on the server. Only used for wording; the
// server is what actually enforces the spacing.
const BATCH_INTERVAL_MINUTES = 2;

interface WishlistViewProps {
  onAlbumClick: (albumId: number) => void;
  onOpenSearch: () => void;
  // Bump to refetch the wishlist in place (keeps search / sort / filters intact).
  refreshKey?: number;
}

const SORT_OPTIONS = [
  { value: 'date_added', label: 'Date added' },
  { value: 'release_date', label: 'Release date' },
  { value: 'artist', label: 'Artist' },
  { value: 'album', label: 'Album' },
] as const;

type WishlistSort = typeof SORT_OPTIONS[number]['value'];

function compareText(a: string, b: string) {
  return a.localeCompare(b, undefined, { sensitivity: 'base' });
}

export default function WishlistView({ onAlbumClick, onOpenSearch, refreshKey = 0 }: WishlistViewProps) {
  const [albums, setAlbums] = useState<Album[]>([]);
  const [loading, setLoading] = useState(true);
  const [slskdStatus, setSlskdStatus] = useState<SlskdStatus | null>(null);
  const [downloadingIds, setDownloadingIds] = useState<Set<number>>(new Set());
  const [hideUpcoming, setHideUpcoming] = useState(false);
  const [discogsOnly, setDiscogsOnly] = useState(false);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<WishlistSort>('date_added');
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [queueing, setQueueing] = useState(false);
  const [batchMessage, setBatchMessage] = useState<{ text: string; isError: boolean } | null>(null);

  const fetchSlskdStatus = useCallback(async () => {
    try {
      const status = await getSlskdStatus();
      setSlskdStatus(status);
    } catch (error) {
      console.error('Error fetching slskd status:', error);
    }
  }, []);

  useEffect(() => {
    fetchSlskdStatus();
  }, [fetchSlskdStatus]);

  // Initial load, and whenever the parent asks for a refresh. Only the album list is
  // replaced; search text, sort and filters live in this component's state and are
  // deliberately left alone.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getWishlist();
        if (!cancelled) setAlbums(data);
      } catch (error) {
        console.error('Error fetching wishlist:', error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const handleRemove = async (e: React.MouseEvent, albumId: number) => {
    e.stopPropagation();
    try {
      await removeFromWishlist(albumId);
      setAlbums(albums.filter(a => a.id !== albumId));
    } catch (error) {
      console.error('Error removing from wishlist:', error);
    }
  };

  const handleDownload = async (e: React.MouseEvent, albumId: number) => {
    e.stopPropagation();
    if (downloadingIds.has(albumId)) return;
    
    setDownloadingIds(prev => new Set(prev).add(albumId));
    
    try {
      await startDownload(albumId);
      // Keep the downloading state to show feedback
    } catch (error) {
      console.error('Error starting download:', error);
      setDownloadingIds(prev => {
        const next = new Set(prev);
        next.delete(albumId);
        return next;
      });
    }
  };

  const exitSelectMode = () => {
    setSelectMode(false);
    setSelectedIds(new Set());
  };

  const toggleSelected = (albumId: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(albumId)) next.delete(albumId);
      else next.add(albumId);
      return next;
    });
  };

  const handleQueueSelected = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0 || queueing) return;

    const totalMinutes = (ids.length - 1) * BATCH_INTERVAL_MINUTES;
    const confirmed = window.confirm(
      `Queue ${ids.length} album${ids.length > 1 ? 's' : ''} for download?\n\n` +
      `One download starts every ${BATCH_INTERVAL_MINUTES} minutes (Soulseek bans clients that ` +
      `search too fast), so the last one starts in about ${totalMinutes} min.`
    );
    if (!confirmed) return;

    setQueueing(true);
    setBatchMessage(null);
    try {
      const result = await startBatchDownload(ids);
      const everyMin = Math.round(result.interval_seconds / 60);
      let text = `${result.queued} album${result.queued === 1 ? '' : 's'} queued - one starts every ${everyMin} min. Follow progress in Downloads.`;
      if (result.skipped > 0) {
        text += ` Skipped ${result.skipped}: ${result.skipped_reasons.join('; ')}`;
      }
      setBatchMessage({ text, isError: result.queued === 0 });
      if (result.queued > 0) {
        setDownloadingIds(prev => {
          const next = new Set(prev);
          ids.forEach(id => next.add(id));
          return next;
        });
      }
      exitSelectMode();
    } catch (error) {
      console.error('Error queueing batch download:', error);
      setBatchMessage({ text: 'Could not queue the downloads. Is slskd reachable?', isError: true });
    } finally {
      setQueueing(false);
    }
  };

  // Check if album is upcoming (future release date)
  // Only works with ISO format dates (YYYY-MM-DD)
  const isUpcoming = (album: Album) => {
    if (!album.release_date) return false;
    // Only do comparison if it looks like an ISO date
    if (!/^\d{4}-\d{2}-\d{2}/.test(album.release_date)) return false;
    const today = new Date().toISOString().split('T')[0];
    return album.release_date > today;
  };

  const canDownload = slskdStatus?.enabled && slskdStatus?.available;

  // Filter albums based on hideUpcoming setting and search query
  const hasDiscogsAlbums = albums.some(a => a.from_discogs);
  const filteredByTag = discogsOnly ? albums.filter(a => a.from_discogs) : albums;
  const displayedAlbums = (hideUpcoming ? filteredByTag.filter(a => !isUpcoming(a)) : filteredByTag).filter(
    (album) => {
      const q = search.trim().toLowerCase();
      if (!q) return true;
      return (
        album.title.toLowerCase().includes(q) ||
        (album.artist?.name?.toLowerCase().includes(q) ?? false)
      );
    }
  ).sort((a, b) => {
    if (sort === 'release_date') {
      if (!a.release_date && !b.release_date) return compareText(a.title, b.title);
      if (!a.release_date) return 1;
      if (!b.release_date) return -1;
      const byDate = compareText(b.release_date, a.release_date);
      return byDate !== 0 ? byDate : compareText(a.title, b.title);
    }
    if (sort === 'artist') {
      const byArtist = compareText(a.artist?.name || '', b.artist?.name || '');
      return byArtist !== 0 ? byArtist : compareText(a.title, b.title);
    }
    if (sort === 'album') {
      return compareText(a.title, b.title);
    }
    const byAdded = compareText(b.created_at, a.created_at);
    return byAdded !== 0 ? byAdded : compareText(a.title, b.title);
  });

  // Albums that can go in a batch: released, and not already queued/started from here.
  const isSelectable = (album: Album) => !isUpcoming(album) && !downloadingIds.has(album.id);
  const selectableAlbums = displayedAlbums.filter(isSelectable);
  const allSelectableSelected =
    selectableAlbums.length > 0 && selectableAlbums.every(a => selectedIds.has(a.id));
  // "Select all Discogs" picks exactly the Discogs-tagged ones (replacing the selection).
  const selectableDiscogs = selectableAlbums.filter(a => a.from_discogs);
  const allDiscogsSelected =
    selectableDiscogs.length > 0 &&
    selectedIds.size === selectableDiscogs.length &&
    selectableDiscogs.every(a => selectedIds.has(a.id));

  return (
    <>
      <header className="header">
        <h1>Wishlist</h1>
        <div className="header-controls header-controls--stacked">
          <div className="search-box">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"/>
              <path d="M21 21l-4.35-4.35"/>
            </svg>
            <input
              type="text"
              placeholder="Search wishlist..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="header-controls-toolbar">
            <select
              className="sort-select"
              value={sort}
              onChange={(e) => setSort(e.target.value as WishlistSort)}
              aria-label="Sort wishlist"
            >
              {SORT_OPTIONS.map(option => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={hideUpcoming}
                onChange={(e) => setHideUpcoming(e.target.checked)}
              />
              <span>Hide upcoming</span>
            </label>
            {(hasDiscogsAlbums || discogsOnly) && (
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={discogsOnly}
                  onChange={(e) => setDiscogsOnly(e.target.checked)}
                />
                <span>Discogs only</span>
              </label>
            )}
            {canDownload && (
              <button
                className={`secondary-btn batch-select-btn ${selectMode ? 'active' : ''}`}
                onClick={() => (selectMode ? exitSelectMode() : setSelectMode(true))}
                title="Select several albums and download them one at a time"
              >
                <span>{selectMode ? 'Done selecting' : 'Select to download'}</span>
              </button>
            )}
            <button className="search-albums-btn" onClick={onOpenSearch}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8"/>
                <path d="M21 21l-4.35-4.35"/>
              </svg>
              <span>Add Album</span>
            </button>
          </div>
        </div>
      </header>
      
      <div className="content">
        {batchMessage && (
          <div className={`batch-message ${batchMessage.isError ? 'error' : ''}`}>
            <span>{batchMessage.text}</span>
            <button onClick={() => setBatchMessage(null)} aria-label="Dismiss">&times;</button>
          </div>
        )}

        {selectMode && (
          <div className="batch-bar">
            <div className="batch-bar-info">
              <strong>{selectedIds.size}</strong> selected
              <span className="batch-bar-hint">
                One download starts every {BATCH_INTERVAL_MINUTES} minutes to avoid a Soulseek ban.
              </span>
            </div>
            <div className="batch-bar-actions">
              <button
                className="secondary-btn"
                onClick={() =>
                  setSelectedIds(allSelectableSelected ? new Set() : new Set(selectableAlbums.map(a => a.id)))
                }
                disabled={selectableAlbums.length === 0}
              >
                <span>{allSelectableSelected ? 'Clear selection' : `Select all (${selectableAlbums.length})`}</span>
              </button>
              {selectableDiscogs.length > 0 && (
                <button
                  className="secondary-btn"
                  onClick={() =>
                    setSelectedIds(allDiscogsSelected ? new Set() : new Set(selectableDiscogs.map(a => a.id)))
                  }
                  title="Select every Discogs-tagged album currently shown (upcoming ones excluded)"
                >
                  <span>
                    {allDiscogsSelected ? 'Clear selection' : `Select all Discogs (${selectableDiscogs.length})`}
                  </span>
                </button>
              )}
              <button
                className="search-albums-btn"
                onClick={handleQueueSelected}
                disabled={selectedIds.size === 0 || queueing}
              >
                <span>
                  {queueing
                    ? 'Queueing...'
                    : `Queue ${selectedIds.size} download${selectedIds.size === 1 ? '' : 's'}`}
                </span>
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <div className="loading">
            <div className="loading-spinner" />
          </div>
        ) : displayedAlbums.length === 0 ? (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
            </svg>
            <h2>
              {search.trim()
                ? 'No matching albums'
                : hideUpcoming && albums.length > 0
                ? 'All albums are upcoming'
                : 'Your wishlist is empty'}
            </h2>
            <p>
              {search.trim()
                ? `No wishlist albums match "${search.trim()}".`
                : hideUpcoming && albums.length > 0
                ? `You have ${albums.length} upcoming album${albums.length > 1 ? 's' : ''} hidden. Uncheck "Hide upcoming" to see them.`
                : 'Search for albums you want, add them from artist pages, or check for upcoming releases from the sidebar.'}
            </p>
            {!hideUpcoming && !search.trim() && (
              <button className="primary-btn" onClick={onOpenSearch}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="11" cy="11" r="8"/>
                  <path d="M21 21l-4.35-4.35"/>
                </svg>
                <span>Search MusicBrainz</span>
              </button>
            )}
          </div>
        ) : (
          <div className="albums-grid wishlist-grid">
            {displayedAlbums.map((album) => (
              <div
                key={album.id}
                className={[
                  'wishlist-album-wrapper',
                  selectMode ? 'selecting' : '',
                  selectMode && !isSelectable(album) ? 'not-selectable' : '',
                  selectedIds.has(album.id) ? 'selected' : '',
                ].filter(Boolean).join(' ')}
              >
                <AlbumCard
                  album={album}
                  onClick={() => {
                    if (!selectMode) return onAlbumClick(album.id);
                    if (isSelectable(album)) toggleSelected(album.id);
                  }}
                  showWishlistButton={false}
                />
                {selectMode && isSelectable(album) && (
                  <div className="select-check" aria-hidden="true">
                    {selectedIds.has(album.id) && (
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <path d="M20 6L9 17l-5-5"/>
                      </svg>
                    )}
                  </div>
                )}
                {isUpcoming(album) && (
                  <div className="upcoming-icon" title={`Upcoming: ${album.release_date}`}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10"/>
                      <polyline points="12,6 12,12 16,14"/>
                    </svg>
                  </div>
                )}
                {canDownload && !selectMode && !isUpcoming(album) && (
                  <button 
                    className={`download-wishlist-btn ${downloadingIds.has(album.id) ? 'downloading' : ''}`}
                    onClick={(e) => handleDownload(e, album.id)}
                    title={downloadingIds.has(album.id) ? 'Download started...' : 'Download from Soulseek'}
                    disabled={downloadingIds.has(album.id)}
                  >
                    {downloadingIds.has(album.id) ? (
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="spin">
                        <path d="M21 12a9 9 0 11-6.219-8.56"/>
                      </svg>
                    ) : (
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
                      </svg>
                    )}
                  </button>
                )}
                {!selectMode && (
                  <button 
                    className="remove-wishlist-btn"
                    onClick={(e) => handleRemove(e, album.id)}
                    title="Remove from wishlist"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M18 6L6 18M6 6l12 12"/>
                    </svg>
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
