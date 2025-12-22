import { useState, useEffect, useCallback } from 'react';
import type { NewRelease, NewReleasesScrapeStatus } from '../types';
import { getNewReleases, scrapeNewReleases, getNewReleasesScrapeStatus } from '../api';

export default function NewReleasesView() {
  const [releases, setReleases] = useState<NewRelease[]>([]);
  const [loading, setLoading] = useState(true);
  const [scrapeStatus, setScrapeStatus] = useState<NewReleasesScrapeStatus | null>(null);
  const [isScraping, setIsScraping] = useState(false);
  const [failedImages, setFailedImages] = useState<Set<number>>(new Set());

  const fetchReleases = useCallback(async () => {
    try {
      const data = await getNewReleases();
      setReleases(data);
    } catch (error) {
      console.error('Error fetching releases:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchScrapeStatus = useCallback(async () => {
    try {
      const status = await getNewReleasesScrapeStatus();
      setScrapeStatus(status);
      return status;
    } catch (error) {
      console.error('Error fetching scrape status:', error);
      return null;
    }
  }, []);

  useEffect(() => {
    fetchReleases();
    fetchScrapeStatus();
  }, [fetchReleases, fetchScrapeStatus]);

  useEffect(() => {
    if (!isScraping) return;

    const interval = setInterval(async () => {
      const status = await fetchScrapeStatus();
      if (status && (status.status === 'completed' || status.status === 'error' || status.status === 'idle')) {
        setIsScraping(false);
        fetchReleases();
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [isScraping, fetchScrapeStatus, fetchReleases]);

  const handleScrape = async () => {
    try {
      await scrapeNewReleases();
      setIsScraping(true);
    } catch (error) {
      console.error('Error starting scrape:', error);
    }
  };

  const handleImageError = (id: number) => {
    setFailedImages(prev => new Set(prev).add(id));
  };

  const getScoreColor = (score: number | null) => {
    if (score === null) return 'var(--text-muted)';
    if (score >= 80) return '#22c55e';
    if (score >= 70) return '#84cc16';
    if (score >= 60) return '#eab308';
    if (score >= 50) return '#f97316';
    return '#ef4444';
  };

  const formatLastScrape = (date: string | null) => {
    if (!date) return 'Never';
    const d = new Date(date);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const hours = Math.floor(diff / (1000 * 60 * 60));
    if (hours < 1) return 'Just now';
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  // Get week info from releases
  const weekInfo = releases.length > 0 
    ? `Week ${releases[0].week_number}, ${releases[0].week_year}`
    : 'No data';

  return (
    <>
      <header className="header">
        <div className="header-title-group">
          <h1>New Releases</h1>
          <span className="header-subtitle">
            {weekInfo} • {releases.length} albums
          </span>
        </div>
        <div className="header-actions">
          <span className="scrape-info">
            Last updated: {formatLastScrape(scrapeStatus?.last_scrape_at ?? null)}
          </span>
          <button 
            className="refresh-btn"
            onClick={handleScrape}
            disabled={isScraping}
          >
            <svg 
              viewBox="0 0 24 24" 
              fill="none" 
              stroke="currentColor" 
              strokeWidth="2"
              className={isScraping ? 'spinning' : ''}
            >
              <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
              <path d="M12 8v4l2 2"/>
            </svg>
            <span>{isScraping ? 'Refreshing...' : 'Refresh'}</span>
          </button>
        </div>
      </header>
      
      <div className="content">
        {loading ? (
          <div className="loading">
            <div className="loading-spinner" />
          </div>
        ) : releases.length === 0 ? (
          <div className="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M9 19V6l12-3v13"/>
              <circle cx="6" cy="18" r="3"/>
              <circle cx="18" cy="16" r="3"/>
            </svg>
            <h2>No new releases yet</h2>
            <p>Click refresh to fetch this week's releases from Album of the Year.</p>
            <button className="primary-btn" onClick={handleScrape} disabled={isScraping}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                <path d="M12 8v4l2 2"/>
              </svg>
              <span>{isScraping ? 'Fetching...' : 'Fetch Releases'}</span>
            </button>
          </div>
        ) : (
          <div className="new-releases-grid">
            {releases.map((release, index) => (
              <a
                key={release.id}
                href={release.aoty_url}
                target="_blank"
                rel="noopener noreferrer"
                className="new-release-card"
              >
                <div className="new-release-rank">#{index + 1}</div>
                <div className="new-release-cover">
                  {release.cover_art_url && !failedImages.has(release.id) ? (
                    <img 
                      src={release.cover_art_url} 
                      alt={release.album_title}
                      loading="lazy"
                      referrerPolicy="no-referrer"
                      onError={() => handleImageError(release.id)}
                    />
                  ) : (
                    <div className="cover-placeholder">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <circle cx="12" cy="12" r="10"/>
                        <circle cx="12" cy="12" r="3"/>
                      </svg>
                    </div>
                  )}
                  {release.critic_score !== null && (
                    <div 
                      className="critic-score"
                      style={{ backgroundColor: getScoreColor(release.critic_score) }}
                    >
                      {release.critic_score}
                    </div>
                  )}
                </div>
                <div className="new-release-info">
                  <div className="new-release-title">{release.album_title}</div>
                  <div className="new-release-artist">{release.artist_name}</div>
                  <div className="new-release-meta">
                    <span className="release-type">{release.release_type || 'LP'}</span>
                    <span className="meta-separator">•</span>
                    <span className="release-date">{release.release_date || 'TBA'}</span>
                    {release.num_critics !== null && release.num_critics > 0 && (
                      <>
                        <span className="meta-separator">•</span>
                        <span className="num-critics">{release.num_critics} reviews</span>
                      </>
                    )}
                  </div>
                </div>
                <div className="aoty-link">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
                    <polyline points="15,3 21,3 21,9"/>
                    <line x1="10" y1="14" x2="21" y2="3"/>
                  </svg>
                </div>
              </a>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
