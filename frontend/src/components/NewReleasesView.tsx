import { useState, useEffect, useCallback } from 'react';
import type { NewRelease, NewReleasesScrapeStatus } from '../types';
import { getNewReleases, scrapeNewReleases, getNewReleasesScrapeStatus, addToWishlist } from '../api';

interface NewReleasesViewProps {
  onWishlistChange?: () => void;
}

// Get ISO week number and year for a given date
function getISOWeek(date: Date): { year: number; week: number } {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
  return { year: d.getUTCFullYear(), week: weekNo };
}

// Get date range for a given ISO week
function getWeekDateRange(year: number, week: number): { start: Date; end: Date } {
  const jan4 = new Date(year, 0, 4);
  const dayOfWeek = jan4.getDay() || 7;
  const firstMonday = new Date(jan4);
  firstMonday.setDate(jan4.getDate() - dayOfWeek + 1);
  
  const start = new Date(firstMonday);
  start.setDate(firstMonday.getDate() + (week - 1) * 7);
  
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  
  return { start, end };
}

// Format date range as "Dec 16 - Dec 22"
function formatWeekRange(year: number, week: number): string {
  const { start, end } = getWeekDateRange(year, week);
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${months[start.getMonth()]} ${start.getDate()} - ${months[end.getMonth()]} ${end.getDate()}`;
}

// Navigate to previous/next week
function navigateWeek(year: number, week: number, delta: number): { year: number; week: number } {
  const { start } = getWeekDateRange(year, week);
  start.setDate(start.getDate() + delta * 7);
  return getISOWeek(start);
}

export default function NewReleasesView({ onWishlistChange }: NewReleasesViewProps) {
  // Initialize with current week
  const currentWeek = getISOWeek(new Date());
  const [selectedYear, setSelectedYear] = useState(currentWeek.year);
  const [selectedWeek, setSelectedWeek] = useState(currentWeek.week);
  
  const [releases, setReleases] = useState<NewRelease[]>([]);
  const [loading, setLoading] = useState(true);
  const [scrapeStatus, setScrapeStatus] = useState<NewReleasesScrapeStatus | null>(null);
  const [isScraping, setIsScraping] = useState(false);
  const [failedImages, setFailedImages] = useState<Set<number>>(new Set());
  const [wishlisted, setWishlisted] = useState<Set<number>>(new Set());
  const [addingToWishlist, setAddingToWishlist] = useState<Set<number>>(new Set());

  const fetchReleases = useCallback(async (year: number, week: number) => {
    setLoading(true);
    try {
      const data = await getNewReleases(year, week);
      setReleases(data);
    } catch (error) {
      console.error('Error fetching releases:', error);
      setReleases([]);
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
    fetchReleases(selectedYear, selectedWeek);
    fetchScrapeStatus();
  }, [selectedYear, selectedWeek, fetchReleases, fetchScrapeStatus]);

  useEffect(() => {
    if (!isScraping) return;

    const interval = setInterval(async () => {
      const status = await fetchScrapeStatus();
      if (status && (status.status === 'completed' || status.status === 'error' || status.status === 'idle')) {
        setIsScraping(false);
        fetchReleases(selectedYear, selectedWeek);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [isScraping, fetchScrapeStatus, fetchReleases, selectedYear, selectedWeek]);

  const handleScrape = async () => {
    try {
      await scrapeNewReleases(selectedYear, selectedWeek);
      setIsScraping(true);
    } catch (error) {
      console.error('Error starting scrape:', error);
    }
  };

  const handlePrevWeek = () => {
    const prev = navigateWeek(selectedYear, selectedWeek, -1);
    setSelectedYear(prev.year);
    setSelectedWeek(prev.week);
  };

  const handleNextWeek = () => {
    const next = navigateWeek(selectedYear, selectedWeek, 1);
    // Don't allow navigating past current week
    if (next.year > currentWeek.year || (next.year === currentWeek.year && next.week > currentWeek.week)) {
      return;
    }
    setSelectedYear(next.year);
    setSelectedWeek(next.week);
  };

  const handleCurrentWeek = () => {
    setSelectedYear(currentWeek.year);
    setSelectedWeek(currentWeek.week);
  };

  const isCurrentWeek = selectedYear === currentWeek.year && selectedWeek === currentWeek.week;

  const handleImageError = (id: number) => {
    setFailedImages(prev => new Set(prev).add(id));
  };

  const handleAddToWishlist = async (e: React.MouseEvent, release: NewRelease) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (wishlisted.has(release.id) || addingToWishlist.has(release.id)) return;
    
    setAddingToWishlist(prev => new Set(prev).add(release.id));
    
    try {
      await addToWishlist({
        title: release.album_title,
        artist_name: release.artist_name,
        release_date: release.release_date || undefined,
        release_type: release.release_type || undefined,
        cover_art_url: release.cover_art_url || undefined,
      });
      
      setWishlisted(prev => new Set(prev).add(release.id));
      onWishlistChange?.();
    } catch (error) {
      console.error('Error adding to wishlist:', error);
    } finally {
      setAddingToWishlist(prev => {
        const next = new Set(prev);
        next.delete(release.id);
        return next;
      });
    }
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

  return (
    <>
      <header className="header">
        <div className="header-title-group">
          <h1>New Releases</h1>
          <span className="header-subtitle">
            Top albums by critic score from AOTY
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

      {/* Week Selector */}
      <div className="week-selector">
        <button 
          className="week-nav-btn" 
          onClick={handlePrevWeek}
          title="Previous week"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="15,18 9,12 15,6"/>
          </svg>
        </button>
        
        <div className="week-info">
          <span className="week-label">Week {selectedWeek}, {selectedYear}</span>
          <span className="week-dates">{formatWeekRange(selectedYear, selectedWeek)}</span>
        </div>
        
        <button 
          className="week-nav-btn" 
          onClick={handleNextWeek}
          disabled={isCurrentWeek}
          title={isCurrentWeek ? 'Already on current week' : 'Next week'}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="9,18 15,12 9,6"/>
          </svg>
        </button>
        
        {!isCurrentWeek && (
          <button 
            className="week-today-btn"
            onClick={handleCurrentWeek}
            title="Go to current week"
          >
            Today
          </button>
        )}
      </div>
      
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
            <h2>No releases for this week</h2>
            <p>Click refresh to fetch releases from Album of the Year.</p>
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
              <div key={release.id} className="new-release-row">
                <a
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
                <button
                  className={`new-release-wishlist-btn ${wishlisted.has(release.id) ? 'wishlisted' : ''}`}
                  onClick={(e) => handleAddToWishlist(e, release)}
                  disabled={wishlisted.has(release.id) || addingToWishlist.has(release.id)}
                  title={wishlisted.has(release.id) ? 'Added to wishlist' : 'Add to wishlist'}
                >
                  {addingToWishlist.has(release.id) ? (
                    <div className="btn-spinner" />
                  ) : (
                    <svg viewBox="0 0 24 24" fill={wishlisted.has(release.id) ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2">
                      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                    </svg>
                  )}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
