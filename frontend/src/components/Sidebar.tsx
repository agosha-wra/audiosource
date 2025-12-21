import type { View, Stats, ScanStatus } from '../types';

interface SidebarProps {
  currentView: View;
  stats: Stats;
  scanStatus: ScanStatus | null;
  isScanning: boolean;
  onNavigate: (view: View) => void;
  onScan: () => void;
}

export default function Sidebar({ currentView, stats, scanStatus, isScanning, onNavigate, onScan }: SidebarProps) {
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
          Albums
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
          Artists
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
        
        {!isScanning ? (
          <button className="scan-btn" onClick={onScan}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
              <path d="M12 8v4l2 2"/>
            </svg>
            <span>Scan Library</span>
          </button>
        ) : (
          <div className="scan-status">
            <div className="scan-progress">
              <div className="scan-progress-bar" style={{ width: `${progress}%` }} />
            </div>
            <span className="scan-text">
              {scanStatus?.status === 'scanning'
                ? `Scanning ${scanStatus.scanned_folders}/${scanStatus.total_folders} folders...`
                : scanStatus?.status === 'completed'
                ? 'Scan completed!'
                : 'Starting scan...'}
            </span>
          </div>
        )}
      </div>
    </aside>
  );
}

