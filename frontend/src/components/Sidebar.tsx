import type { View, Stats, ScanStatus, UpcomingStatus } from '../types';

interface SidebarProps {
  currentView: View;
  stats: Stats;
  scanStatus: ScanStatus | null;
  upcomingStatus: UpcomingStatus | null;
  isScanning: boolean;
  isCheckingUpcoming: boolean;
  onNavigate: (view: View) => void;
  onScan: () => void;
  onCheckUpcoming: () => void;
  onCancelScan?: () => void;
}

export default function Sidebar({ 
  currentView, 
  stats, 
  scanStatus, 
  upcomingStatus,
  isScanning, 
  isCheckingUpcoming,
  onNavigate, 
  onScan,
  onCheckUpcoming,
  onCancelScan
}: SidebarProps) {
  const progress = scanStatus && scanStatus.total_folders > 0
    ? (scanStatus.scanned_folders / scanStatus.total_folders) * 100
    : 0;

  return (
    <aside className="sidebar">
      <div className="logo">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10"/>
          <circle cx="12" cy="12" r="3"/>
          <path d="M12 2v4M12 18v4"/>
        </svg>
        <span>AudioSource</span>
      </div>
      
      <nav className="nav">
        <a
          href="#"
          className={`nav-item ${currentView === 'albums' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('albums'); }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="7" height="7" rx="1"/>
            <rect x="14" y="3" width="7" height="7" rx="1"/>
            <rect x="3" y="14" width="7" height="7" rx="1"/>
            <rect x="14" y="14" width="7" height="7" rx="1"/>
          </svg>
          <span>Albums</span>
        </a>
        <a
          href="#"
          className={`nav-item ${currentView === 'artists' || currentView === 'artist-detail' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('artists'); }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="8" r="4"/>
            <path d="M4 20c0-4 4-6 8-6s8 2 8 6"/>
          </svg>
          <span>Artists</span>
        </a>
        <a
          href="#"
          className={`nav-item ${currentView === 'wishlist' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('wishlist'); }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
          </svg>
          <span>Wishlist</span>
          {stats.wishlist_count > 0 && (
            <span className="nav-badge">{stats.wishlist_count}</span>
          )}
        </a>
        <a
          href="#"
          className={`nav-item ${currentView === 'new-releases' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('new-releases'); }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
          </svg>
          <span>New Releases</span>
        </a>
        <a
          href="#"
          className={`nav-item ${currentView === 'downloads' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('downloads'); }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          <span>Downloads</span>
        </a>
        <a
          href="#"
          className={`nav-item ${currentView === 'vinyl-releases' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('vinyl-releases'); }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <circle cx="12" cy="12" r="3"/>
            <circle cx="12" cy="12" r="6"/>
          </svg>
          <span>Vinyl Releases</span>
        </a>
        <a
          href="#"
          className={`nav-item ${currentView === 'settings' ? 'active' : ''}`}
          onClick={(e) => { e.preventDefault(); onNavigate('settings'); }}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          <span>Settings</span>
        </a>
      </nav>
      
      <div className="sidebar-footer">
        <div className="stats">
          <div className="stat">
            <span className="stat-value">{stats.album_count}</span>
            <span className="stat-label">Albums</span>
          </div>
          <div className="stat">
            <span className="stat-value">{stats.artist_count}</span>
            <span className="stat-label">Artists</span>
          </div>
        </div>
        
        {isScanning ? (
          <div className="scan-status">
            <div className="scan-progress">
              <div className="scan-progress-bar" style={{ width: `${progress}%` }} />
            </div>
            <div className="scan-status-row">
              <span className="scan-text">
                {scanStatus?.status === 'scanning'
                  ? `Scanning ${scanStatus.scanned_folders}/${scanStatus.total_folders}...`
                  : scanStatus?.status === 'completed'
                  ? 'Scan completed!'
                  : scanStatus?.status === 'cancelled'
                  ? 'Scan cancelled'
                  : 'Starting scan...'}
              </span>
              {onCancelScan && scanStatus?.status === 'scanning' && (
                <button className="cancel-scan-btn" onClick={onCancelScan} title="Cancel scan">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M18 6L6 18M6 6l12 12"/>
                  </svg>
                </button>
              )}
            </div>
          </div>
        ) : isCheckingUpcoming ? (
          <div className="scan-status">
            <div className="scan-progress">
              <div 
                className="scan-progress-bar upcoming" 
                style={{ 
                  width: upcomingStatus?.total_artists 
                    ? `${(upcomingStatus.artists_checked / upcomingStatus.total_artists) * 100}%` 
                    : '0%' 
                }} 
              />
            </div>
            <span className="scan-text">
              Checking {upcomingStatus?.artists_checked || 0}/{upcomingStatus?.total_artists || 0} artists...
            </span>
          </div>
        ) : (
          <div className="sidebar-buttons">
            <button className="scan-btn" onClick={onScan}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                <path d="M12 8v4l2 2"/>
              </svg>
              <span>Scan Library</span>
            </button>
            <button className="upcoming-sidebar-btn" onClick={onCheckUpcoming}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/>
                <polyline points="12,6 12,12 16,14"/>
              </svg>
              <span>Check Upcoming</span>
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
