import { useState, useEffect, useCallback } from 'react';
import type { Concert, ConcertScrapeStatus } from '../types';
import { getConcerts, scrapeConcerts, getConcertStatus, deleteConcert } from '../api';

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
}

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

export default function ConcertsView() {
  const [concerts, setConcerts] = useState<Concert[]>([]);
  const [loading, setLoading] = useState(true);
  const [scraping, setScraping] = useState(false);
  const [status, setStatus] = useState<ConcertScrapeStatus | null>(null);
  const [scrapeError, setScrapeError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Set<number>>(new Set());

  const fetchConcerts = useCallback(async () => {
    try {
      const data = await getConcerts();
      setConcerts(data);
    } catch (error) {
      console.error('Error fetching concerts:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getConcertStatus();
      setStatus(data);
      return data;
    } catch (error) {
      console.error('Error fetching status:', error);
      return null;
    }
  }, []);

  useEffect(() => {
    fetchConcerts();
    fetchStatus();
  }, [fetchConcerts, fetchStatus]);

  const handleScrape = async () => {
    setScraping(true);
    setScrapeError(null);
    try {
      await scrapeConcerts();
      await fetchStatus();
      await fetchConcerts();
    } catch (error: any) {
      console.error('Scrape error:', error);
      const errorMsg = error?.message || error?.detail || 'Scrape failed - check server logs';
      setScrapeError(errorMsg);
      await fetchStatus();
    } finally {
      setScraping(false);
    }
  };

  const handleDelete = async (concertId: number) => {
    setDeleting(prev => new Set(prev).add(concertId));
    try {
      await deleteConcert(concertId);
      setConcerts(concerts.filter(c => c.id !== concertId));
    } catch (error) {
      console.error('Error deleting concert:', error);
    } finally {
      setDeleting(prev => {
        const next = new Set(prev);
        next.delete(concertId);
        return next;
      });
    }
  };

  return (
    <>
      <header className="header">
        <h1>Upcoming Concerts</h1>
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
                  {status && status.total_artists > 0 
                    ? `Checking ${status.current_artist}/${status.total_artists}...`
                    : 'Checking...'}
                </span>
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                  <path d="M12 8v4l2 2"/>
                </svg>
                <span>Check Now</span>
              </>
            )}
          </button>
        </div>
      </header>

      <div className="content">
        {scrapeError && (
          <div className="concert-error-bar">
            <span>⚠️ {scrapeError}</span>
          </div>
        )}

        {status?.error_message && !scrapeError && (
          <div className="concert-error-bar">
            <span>⚠️ Last check error: {status.error_message}</span>
          </div>
        )}

        {status?.last_scrape_at && (
          <div className="concert-status-bar">
            <span>Last checked: {formatTimeAgo(status.last_scrape_at)}</span>
            {status.artists_checked > 0 && (
              <span> • Checked {status.artists_checked} artists, found {status.concerts_found} concerts</span>
            )}
            <span className="auto-note"> • Auto-checks daily</span>
          </div>
        )}

        {loading ? (
          <div className="loading">
            <div className="loading-spinner" />
          </div>
        ) : concerts.length === 0 ? (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2z"/>
            </svg>
            <h2>No upcoming concerts found</h2>
            <p>Click "Check Now" to search Bandsintown for concerts from your library artists.</p>
          </div>
        ) : (
          <div className="concerts-list">
            {concerts.map((concert) => (
              <div key={concert.id} className="concert-card">
                <div className="concert-date">
                  <div className="concert-month">
                    {new Date(concert.event_date).toLocaleDateString('en-US', { month: 'short' })}
                  </div>
                  <div className="concert-day">
                    {new Date(concert.event_date).getDate()}
                  </div>
                  <div className="concert-weekday">
                    {new Date(concert.event_date).toLocaleDateString('en-US', { weekday: 'short' })}
                  </div>
                </div>
                
                <div className="concert-content">
                  <div className="concert-artist">{concert.artist_name}</div>
                  
                  <div className="concert-venue">
                    {concert.venue_name && <span className="venue-name">{concert.venue_name}</span>}
                    <span className="venue-location">
                      {[concert.venue_city, concert.venue_region, concert.venue_country]
                        .filter(Boolean)
                        .join(', ')}
                    </span>
                  </div>
                  
                  {concert.lineup && concert.lineup !== concert.artist_name && (
                    <div className="concert-lineup">
                      with {concert.lineup}
                    </div>
                  )}
                </div>
                
                <div className="concert-actions">
                  {concert.ticket_url && (
                    <a 
                      href={concert.ticket_url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="ticket-btn"
                    >
                      Tickets
                    </a>
                  )}
                  
                  <button
                    className="concert-delete-btn"
                    onClick={() => handleDelete(concert.id)}
                    disabled={deleting.has(concert.id)}
                    title="Remove from list"
                  >
                    {deleting.has(concert.id) ? (
                      <div className="btn-spinner-small" />
                    ) : (
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M18 6L6 18M6 6l12 12"/>
                      </svg>
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <style>{`
        .concert-error-bar {
          background: rgba(239, 68, 68, 0.15);
          border: 1px solid rgba(239, 68, 68, 0.3);
          padding: 12px 16px;
          border-radius: var(--radius-md);
          margin-bottom: 12px;
          font-size: 13px;
          color: #ef4444;
        }

        .concert-status-bar {
          background: var(--bg-tertiary);
          padding: 12px 16px;
          border-radius: var(--radius-md);
          margin-bottom: 20px;
          font-size: 13px;
          color: var(--text-secondary);
        }

        .concert-status-bar .auto-note {
          color: var(--text-muted);
        }

        .concerts-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .concert-card {
          display: flex;
          align-items: stretch;
          gap: 16px;
          padding: 16px;
          background: var(--bg-tertiary);
          border-radius: var(--radius-md);
          transition: background var(--transition);
        }

        .concert-card:hover {
          background: var(--bg-hover);
        }

        .concert-date {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          min-width: 60px;
          padding: 8px 12px;
          background: var(--accent);
          border-radius: var(--radius-md);
          color: white;
          text-align: center;
        }

        .concert-month {
          font-size: 11px;
          text-transform: uppercase;
          font-weight: 600;
          opacity: 0.9;
        }

        .concert-day {
          font-size: 24px;
          font-weight: 700;
          line-height: 1.1;
        }

        .concert-weekday {
          font-size: 11px;
          opacity: 0.9;
        }

        .concert-content {
          flex: 1;
          min-width: 0;
          display: flex;
          flex-direction: column;
          justify-content: center;
          gap: 4px;
        }

        .concert-artist {
          font-size: 16px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .concert-venue {
          display: flex;
          flex-direction: column;
          gap: 2px;
          font-size: 14px;
        }

        .venue-name {
          color: var(--text-secondary);
        }

        .venue-location {
          color: var(--text-muted);
          font-size: 13px;
        }

        .concert-lineup {
          font-size: 13px;
          color: var(--text-muted);
          font-style: italic;
        }

        .concert-actions {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        .ticket-btn {
          padding: 8px 16px;
          background: var(--accent);
          color: white;
          border-radius: var(--radius-md);
          text-decoration: none;
          font-size: 13px;
          font-weight: 500;
          transition: opacity var(--transition);
        }

        .ticket-btn:hover {
          opacity: 0.9;
        }

        .concert-delete-btn {
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

        .concert-delete-btn:hover:not(:disabled) {
          background: rgba(239, 68, 68, 0.15);
          border-color: #ef4444;
          color: #ef4444;
        }

        .concert-delete-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .concert-delete-btn svg {
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

