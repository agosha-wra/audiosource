import { useEffect, useRef, useState } from 'react';
import type { DiscogsImportStatus } from '../types';
import { cancelDiscogsImport, getDiscogsImportStatus, startDiscogsImport } from '../api';

interface Props {
  onWishlistChange?: () => void;
}

function formatEta(seconds: number | null): string {
  if (seconds === null || seconds <= 0) return '';
  if (seconds < 60) return 'less than a minute left';
  return `about ${Math.round(seconds / 60)} min left`;
}

export default function DiscogsImport({ onWishlistChange }: Props) {
  const [status, setStatus] = useState<DiscogsImportStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const wasRunning = useRef(false);
  const onChangeRef = useRef(onWishlistChange);
  onChangeRef.current = onWishlistChange;

  const running = status?.status === 'running';

  // Load whatever the server knows (an import may already be running / just finished).
  useEffect(() => {
    let stale = false;
    getDiscogsImportStatus()
      .then(s => { if (!stale) setStatus(s); })
      .catch(() => { /* status is optional */ });
    return () => { stale = true; };
  }, []);

  // Poll while running. The interval depends only on the boolean, so it isn't recreated per update.
  useEffect(() => {
    if (!running) return;
    let stale = false;
    let inFlight = false;
    const tick = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const s = await getDiscogsImportStatus();
        if (!stale) setStatus(s);
      } catch {
        /* transient; try again next tick */
      } finally {
        inFlight = false;
      }
    };
    const id = setInterval(tick, 2000);
    return () => { stale = true; clearInterval(id); };
  }, [running]);

  // Tell the app the wishlist changed once a run we were watching ends.
  useEffect(() => {
    if (running) {
      wasRunning.current = true;
    } else if (wasRunning.current) {
      wasRunning.current = false;
      setCancelling(false);
      onChangeRef.current?.();
    }
  }, [running]);

  const handleFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    setError(null);
    setStarting(true);
    try {
      const content = await file.text();
      const s = await startDiscogsImport(content, file.name);
      setStatus(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import failed');
    } finally {
      setStarting(false);
    }
  };

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await cancelDiscogsImport();
    } catch {
      setCancelling(false);
    }
  };

  const percent = status && status.to_lookup > 0
    ? Math.min(100, Math.round((status.processed / status.to_lookup) * 100))
    : status && status.status !== 'running' ? 100 : 0;

  const hasReport = status && status.status !== 'idle';

  return (
    <div className="discogs-import">
      <input
        ref={fileInput}
        type="file"
        accept=".csv,text/csv"
        onChange={handleFile}
        style={{ display: 'none' }}
      />

      <div className="discogs-actions">
        <button
          className="discogs-btn"
          onClick={() => fileInput.current?.click()}
          disabled={running || starting}
        >
          {starting ? 'Reading file...' : 'Choose Discogs CSV...'}
        </button>
        {running && (
          <button className="discogs-btn secondary" onClick={handleCancel} disabled={cancelling}>
            {cancelling ? 'Stopping...' : 'Cancel import'}
          </button>
        )}
      </div>

      {error && <p className="discogs-error">{error}</p>}

      {hasReport && status && (
        <div className="discogs-report">
          {status.filename && <div className="discogs-filename">{status.filename}</div>}

          {status.status === 'running' && (
            <>
              <div className="discogs-progress">
                <div className="discogs-progress-bar" style={{ width: `${percent}%` }} />
              </div>
              <div className="discogs-progress-text">
                {status.to_lookup > 0
                  ? `Looking up ${status.processed} / ${status.to_lookup} on MusicBrainz ${formatEta(status.estimated_seconds_left)}`
                  : 'Matching against your library...'}
              </div>
              {status.current && <div className="discogs-current">{status.current}</div>}
            </>
          )}

          {status.message && (
            <p className={status.status === 'error' ? 'discogs-error' : 'discogs-note'}>{status.message}</p>
          )}
          {status.status === 'completed' && <p className="discogs-done">Import finished.</p>}

          <ul className="discogs-stats">
            <li><strong>{status.total_rows}</strong> albums in the CSV</li>
            <li><strong>{status.already_owned}</strong> already in your library</li>
            <li><strong>{status.already_wishlisted}</strong> already on your wishlist</li>
            <li><strong>{status.added}</strong> added to your wishlist</li>
            {status.tagged_existing > 0 && (
              <li><strong>{status.tagged_existing}</strong> already on your wishlist, now tagged "Discogs"</li>
            )}
            {status.added_unmatched > 0 && (
              <li><strong>{status.added_unmatched}</strong> of those not found on MusicBrainz (no cover art)</li>
            )}
            {status.failed > 0 && <li><strong>{status.failed}</strong> failed</li>}
          </ul>

          {status.unmatched.length > 0 && (
            <details className="discogs-details">
              <summary>Added without a MusicBrainz match ({status.added_unmatched})</summary>
              <ul>{status.unmatched.map(item => <li key={item}>{item}</li>)}</ul>
            </details>
          )}
          {status.failed_items.length > 0 && (
            <details className="discogs-details">
              <summary>Failed ({status.failed})</summary>
              <ul>{status.failed_items.map(item => <li key={item}>{item}</li>)}</ul>
            </details>
          )}
        </div>
      )}

      <style>{`
        .discogs-actions { display: flex; gap: 10px; flex-wrap: wrap; }
        .discogs-btn {
          padding: 8px 16px; border-radius: 8px; border: none; cursor: pointer;
          background: var(--accent); color: white; font-size: 14px; font-weight: 500;
        }
        .discogs-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .discogs-btn.secondary { background: var(--bg-secondary); color: var(--text-primary); }
        .discogs-report { margin-top: 16px; display: flex; flex-direction: column; gap: 8px; }
        .discogs-filename { font-size: 12px; color: var(--text-muted); font-family: 'SF Mono', Monaco, monospace; }
        .discogs-progress { height: 8px; border-radius: 4px; background: var(--bg-secondary); overflow: hidden; }
        .discogs-progress-bar { height: 100%; background: var(--accent); transition: width 0.4s ease; }
        .discogs-progress-text { font-size: 13px; color: var(--text-secondary); }
        .discogs-current { font-size: 12px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .discogs-error { color: var(--accent-red); font-size: 13px; margin: 8px 0 0; }
        .discogs-note { color: var(--text-secondary); font-size: 13px; margin: 0; }
        .discogs-done { color: var(--success); font-size: 13px; margin: 0; }
        .discogs-stats { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 4px; font-size: 14px; color: var(--text-secondary); }
        .discogs-stats strong { color: var(--text-primary); }
        .discogs-details { font-size: 13px; color: var(--text-secondary); }
        .discogs-details summary { cursor: pointer; }
        .discogs-details ul { max-height: 220px; overflow-y: auto; margin: 8px 0 0; padding-left: 18px; }
      `}</style>
    </div>
  );
}
