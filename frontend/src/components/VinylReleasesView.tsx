import { useState, useEffect, useCallback } from 'react';
import type { VinylRelease, VinylReleasesScrapeStatus } from '../types';
import { getVinylReleases, scrapeVinylReleases, getVinylReleasesStatus, deleteVinylRelease } from '../api';

function formatTimeAgo(dateString: string | null): string {
  if (!dateString) return '';
  
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export default function VinylReleasesView() {
  const [releases, setReleases] = useState<VinylRelease[]>([]);
  const [loading, setLoading] = useState(true);
  const [scraping, setScraping] = useState(false);
  const [status, setStatus] = useState<VinylReleasesScrapeStatus | null>(null);
  const [deleting, setDeleting] = useState<Set<number>>(new Set());

  const fetchReleases = useCallback(async () => {
    try {
      const data = await getVinylReleases();
      setReleases(data);
    } catch (error) {
      console.error('Error fetching vinyl releases:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getVinylReleasesStatus();
      setStatus(data);
      return data;
    } catch (error) {
      console.error('Error fetching status:', error);
      return null;
    }
  }, []);

  useEffect(() => {
    fetchReleases();
    fetchStatus();
  }, [fetchReleases, fetchStatus]);

  // Poll while scraping
  useEffect(() => {
    if (!scraping) return;

    const interval = setInterval(async () => {
      const newStatus = await fetchStatus();
      if (newStatus && (newStatus.status === 'completed' || newStatus.status === 'error' || newStatus.status === 'idle')) {
        setScraping(false);
        fetchReleases();
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [scraping, fetchStatus, fetchReleases]);

  const handleScrape = async () => {
    try {
      setScraping(true);
      await scrapeVinylReleases();
    } catch (error) {
      console.error('Error starting scrape:', error);
      setScraping(false);
    }
  };

  const handleDelete = async (releaseId: number) => {
    setDeleting(prev => new Set(prev).add(releaseId));
    try {
      await deleteVinylRelease(releaseId);
      setReleases(releases.filter(r => r.id !== releaseId));
    } catch (error) {
      console.error('Error deleting release:', error);
    } finally {
      setDeleting(prev => {
        const next = new Set(prev);
        next.delete(releaseId);
        return next;
      });
    }
  };

  return (
    <>
      <header className="header">
        <h1>Vinyl Releases</h1>
        <div className="header-controls">
          <button 
            className="scrape-btn"
            onClick={handleScrape}
            disabled={scraping}
          >
            {scraping ? (
              <>
                <div className="btn-spinner-small" />
                <span>
                  {status && status.total_posts > 0 
                    ? `Scraping ${status.current_post}/${status.total_posts}...`
                    : 'Scraping...'}
                </span>
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                  <path d="M12 8v4l2 2"/>
                </svg>
                <span>Scrape Now</span>
              </>
            )}
          </button>
        </div>
      </header>

      <div className="content">
        {status?.last_scrape_at && (
          <div className="vinyl-status-bar">
            <span>Last scraped: {formatTimeAgo(status.last_scrape_at)}</span>
            {status.posts_found > 0 && (
              <span> • {status.matches_found} matches from {status.posts_found} posts</span>
            )}
            <span className="auto-note"> • Auto-scrapes every hour</span>
          </div>
        )}

        {loading ? (
          <div className="loading">
            <div className="loading-spinner" />
          </div>
        ) : releases.length === 0 ? (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="10"/>
              <circle cx="12" cy="12" r="3"/>
              <path d="M12 2v4M12 18v4"/>
            </svg>
            <h2>No vinyl releases found</h2>
            <p>Click "Scrape Now" to check r/vinylreleases for posts matching your library artists.</p>
          </div>
        ) : (
          <div className="vinyl-releases-list">
            {releases.map((release) => (
              <div key={release.id} className="vinyl-release-card">
                <div className="vinyl-release-content">
                  <div className="vinyl-release-header">
                    <span className="vinyl-artist-badge">
                      {release.matched_artist_name}
                    </span>
                    {release.flair && (
                      <span className="vinyl-flair">{release.flair}</span>
                    )}
                  </div>
                  
                  <a 
                    href={release.url} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="vinyl-release-title"
                  >
                    {release.title}
                  </a>
                  
                  <div className="vinyl-release-meta">
                    <span className="vinyl-score">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M12 19V5M5 12l7-7 7 7"/>
                      </svg>
                      {release.score}
                    </span>
                    <span className="vinyl-comments">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
                      </svg>
                      {release.num_comments}
                    </span>
                    <span className="vinyl-time">
                      {formatTimeAgo(release.posted_at)}
                    </span>
                    {release.author && (
                      <span className="vinyl-author">
                        by u/{release.author}
                      </span>
                    )}
                  </div>
                </div>
                
                <button
                  className="vinyl-delete-btn"
                  onClick={() => handleDelete(release.id)}
                  disabled={deleting.has(release.id)}
                  title="Remove from list"
                >
                  {deleting.has(release.id) ? (
                    <div className="btn-spinner-small" />
                  ) : (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M18 6L6 18M6 6l12 12"/>
                    </svg>
                  )}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <style>{`
        .vinyl-status-bar {
          background: var(--bg-tertiary);
          padding: 12px 16px;
          border-radius: var(--radius-md);
          margin-bottom: 20px;
          font-size: 13px;
          color: var(--text-secondary);
        }

        .vinyl-status-bar .auto-note {
          color: var(--text-muted);
        }

        .vinyl-releases-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .vinyl-release-card {
          display: flex;
          align-items: flex-start;
          gap: 16px;
          padding: 16px;
          background: var(--bg-tertiary);
          border-radius: var(--radius-md);
          transition: background var(--transition);
        }

        .vinyl-release-card:hover {
          background: var(--bg-hover);
        }

        .vinyl-release-content {
          flex: 1;
          min-width: 0;
        }

        .vinyl-release-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
        }

        .vinyl-artist-badge {
          background: var(--accent);
          color: white;
          padding: 4px 10px;
          border-radius: 12px;
          font-size: 12px;
          font-weight: 600;
        }

        .vinyl-flair {
          background: var(--bg-primary);
          color: var(--text-secondary);
          padding: 4px 8px;
          border-radius: 4px;
          font-size: 11px;
          text-transform: uppercase;
        }

        .vinyl-release-title {
          display: block;
          font-size: 15px;
          font-weight: 500;
          color: var(--text-primary);
          text-decoration: none;
          line-height: 1.4;
          margin-bottom: 8px;
        }

        .vinyl-release-title:hover {
          color: var(--accent);
        }

        .vinyl-release-meta {
          display: flex;
          align-items: center;
          gap: 16px;
          font-size: 13px;
          color: var(--text-muted);
        }

        .vinyl-release-meta span {
          display: flex;
          align-items: center;
          gap: 4px;
        }

        .vinyl-release-meta svg {
          width: 14px;
          height: 14px;
        }

        .vinyl-score svg {
          color: var(--accent);
        }

        .vinyl-delete-btn {
          width: 32px;
          height: 32px;
          padding: 0;
          background: transparent;
          border: 1px solid var(--border-color);
          border-radius: 50%;
          color: var(--text-muted);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all var(--transition);
          flex-shrink: 0;
        }

        .vinyl-delete-btn:hover:not(:disabled) {
          background: rgba(239, 68, 68, 0.15);
          border-color: #ef4444;
          color: #ef4444;
        }

        .vinyl-delete-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .vinyl-delete-btn svg {
          width: 14px;
          height: 14px;
        }

        .scrape-btn {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 16px;
          background: var(--accent);
          border: none;
          color: white;
          border-radius: var(--radius-md);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all var(--transition);
        }

        .scrape-btn:hover:not(:disabled) {
          opacity: 0.9;
        }

        .scrape-btn:disabled {
          opacity: 0.7;
          cursor: not-allowed;
        }

        .scrape-btn svg {
          width: 16px;
          height: 16px;
        }
      `}</style>
    </>
  );
}

