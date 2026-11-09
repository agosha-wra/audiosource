import { useState, useEffect, useCallback } from 'react';
import type { Album, DownloadFolderListing } from '../types';
import { getDownloadFolders, startManualDownload } from '../api';

interface ManualDownloadModalProps {
  album: Album;
  onClose: () => void;
  // Called once the server accepted the folder (tag matching continues in Downloads).
  onStarted: (albumId: number) => void;
}

export default function ManualDownloadModal({ album, onClose, onStarted }: ManualDownloadModalProps) {
  const [path, setPath] = useState('');
  const [listing, setListing] = useState<DownloadFolderListing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const artistName = album.artist?.name || 'Unknown Artist';

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getDownloadFolders(path)
      .then((data) => {
        if (!cancelled) setListing(data);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  const navigate = (next: string) => {
    setFilter('');
    setPath(next);
  };

  const handleSelect = useCallback(
    async (folderPath: string, label: string) => {
      if (submitting) return;
      const confirmed = window.confirm(
        `Use "${label}" as ${artistName} - ${album.title}?\n\n` +
        `Its audio files will be tag-matched and moved into your library.`
      );
      if (!confirmed) return;

      setSubmitting(true);
      setError(null);
      try {
        await startManualDownload(album.id, folderPath);
        onStarted(album.id);
        onClose();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Could not start the manual download');
        setSubmitting(false);
      }
    },
    [submitting, artistName, album.id, album.title, onStarted, onClose]
  );

  // Breadcrumb segments: "a/b/c" -> [a, a/b, a/b/c]
  const segments = path ? path.split('/') : [];
  const visibleFolders = (listing?.folders ?? []).filter(
    (f) => !filter.trim() || f.name.toLowerCase().includes(filter.trim().toLowerCase())
  );

  return (
    <div className="modal active">
      <div className="modal-backdrop" onClick={onClose} />
      <div className="modal-content manual-download-modal">
        <button className="modal-close" onClick={onClose}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>

        <div className="manual-download-header">
          <h2>Pick a downloaded folder</h2>
          <p className="manual-download-album">
            This folder is <strong>{artistName}</strong> — <strong>{album.title}</strong>
          </p>
        </div>

        <div className="manual-download-toolbar">
          <div className="manual-download-breadcrumb">
            <button onClick={() => navigate('')} disabled={!path}>downloads</button>
            {segments.map((seg, i) => {
              const segPath = segments.slice(0, i + 1).join('/');
              const isLast = i === segments.length - 1;
              return (
                <span key={segPath}>
                  <span className="sep">/</span>
                  <button onClick={() => navigate(segPath)} disabled={isLast}>{seg}</button>
                </span>
              );
            })}
          </div>
          <input
            type="text"
            className="manual-download-filter"
            placeholder="Filter folders..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>

        {error && <div className="manual-download-error">{error}</div>}

        <div className="manual-download-list">
          {loading ? (
            <div className="loading" style={{ padding: '40px' }}>
              <div className="loading-spinner" />
            </div>
          ) : (
            <>
              {listing && path && listing.audio_count > 0 && (
                <div className="manual-download-row current">
                  <div className="manual-download-row-info">
                    <span className="manual-download-row-name">This folder</span>
                    <span className="manual-download-row-meta">{listing.audio_count} audio files</span>
                  </div>
                  <button
                    className="manual-download-select"
                    disabled={submitting}
                    onClick={() => handleSelect(listing.path, segments[segments.length - 1])}
                  >
                    Use this folder
                  </button>
                </div>
              )}

              {listing && listing.parent !== null && (
                <button className="manual-download-row up" onClick={() => navigate(listing.parent as string)}>
                  <span className="manual-download-row-name">.. (up)</span>
                </button>
              )}

              {visibleFolders.length === 0 ? (
                <div className="manual-download-empty">
                  {listing?.folders.length ? 'No folder matches the filter.' : 'No subfolders here.'}
                </div>
              ) : (
                visibleFolders.map((folder) => (
                  <div key={folder.path} className="manual-download-row">
                    <button
                      className="manual-download-row-info manual-download-row-link"
                      onClick={() => navigate(folder.path)}
                      title={folder.has_subfolders ? 'Open folder' : folder.name}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                      </svg>
                      <span className="manual-download-row-name">{folder.name}</span>
                      <span className="manual-download-row-meta">
                        {folder.audio_count > 0 ? `${folder.audio_count} audio files` : 'no audio'}
                      </span>
                    </button>
                    <button
                      className="manual-download-select"
                      disabled={submitting || folder.audio_count === 0}
                      title={folder.audio_count === 0 ? 'No audio files in this folder' : 'Use this folder'}
                      onClick={() => handleSelect(folder.path, folder.name)}
                    >
                      Select
                    </button>
                  </div>
                ))
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
