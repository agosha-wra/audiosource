import { useState, useEffect, useCallback } from 'react';
import type { Download, SlskdStatus, BeetsCandidate } from '../types';
import { getDownloads, getSlskdStatus, getDownload, moveDownload, retryDownload, cancelDownload, deleteDownload, getDownloadCandidates, applyDownloadMatch } from '../api';

export default function DownloadsView() {
  const [downloads, setDownloads] = useState<Download[]>([]);
  const [slskdStatus, setSlskdStatus] = useState<SlskdStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [reviewingDownload, setReviewingDownload] = useState<Download | null>(null);
  const [candidates, setCandidates] = useState<BeetsCandidate[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [applyingMatch, setApplyingMatch] = useState(false);

  const fetchSlskdStatus = useCallback(async () => {
    try {
      const status = await getSlskdStatus();
      setSlskdStatus(status);
    } catch (error) {
      console.error('Error fetching slskd status:', error);
    }
  }, []);

  const fetchDownloads = useCallback(async () => {
    try {
      const data = await getDownloads();
      setDownloads(data);
    } catch (error) {
      console.error('Error fetching downloads:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSlskdStatus();
    fetchDownloads();
  }, [fetchSlskdStatus, fetchDownloads]);

  // Auto-refresh active downloads
  useEffect(() => {
    const hasActiveDownloads = downloads.some(d => 
      ['pending', 'searching', 'downloading'].includes(d.status)
    );

    if (!hasActiveDownloads) return;

    const interval = setInterval(async () => {
      const activeDownloads = downloads.filter(d => 
        ['pending', 'searching', 'downloading'].includes(d.status)
      );

      for (const download of activeDownloads) {
        try {
          const updated = await getDownload(download.id);
          setDownloads(prev => prev.map(d => d.id === updated.id ? updated : d));
        } catch (error) {
          console.error('Error updating download:', error);
        }
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [downloads]);

  const handleMove = async (downloadId: number) => {
    try {
      await moveDownload(downloadId);
      // Refresh after a short delay
      setTimeout(fetchDownloads, 1000);
    } catch (error) {
      console.error('Error moving download:', error);
    }
  };

  const handleDelete = async (downloadId: number) => {
    try {
      await deleteDownload(downloadId);
      setDownloads(prev => prev.filter(d => d.id !== downloadId));
    } catch (error) {
      console.error('Error deleting download:', error);
    }
  };

  const handleRetry = async (downloadId: number) => {
    try {
      const updated = await retryDownload(downloadId);
      setDownloads(prev => prev.map(d => d.id === downloadId ? updated : d));
    } catch (error) {
      console.error('Error retrying download:', error);
    }
  };

  const handleCancel = async (downloadId: number) => {
    try {
      const updated = await cancelDownload(downloadId);
      setDownloads(prev => prev.map(d => d.id === downloadId ? updated : d));
    } catch (error) {
      console.error('Error cancelling download:', error);
    }
  };

  const handleReviewTags = async (download: Download) => {
    setReviewingDownload(download);
    setLoadingCandidates(true);
    setCandidates([]);
    
    try {
      const fetchedCandidates = await getDownloadCandidates(download.id);
      setCandidates(fetchedCandidates);
    } catch (error) {
      console.error('Error fetching candidates:', error);
    } finally {
      setLoadingCandidates(false);
    }
  };

  const handleApplyMatch = async (matchId?: string, skipTagging: boolean = false) => {
    if (!reviewingDownload) return;
    
    setApplyingMatch(true);
    try {
      await applyDownloadMatch(reviewingDownload.id, matchId, skipTagging);
      setReviewingDownload(null);
      setCandidates([]);
      // Refresh downloads after a short delay
      setTimeout(fetchDownloads, 1000);
    } catch (error) {
      console.error('Error applying match:', error);
    } finally {
      setApplyingMatch(false);
    }
  };

  const closeReviewModal = () => {
    setReviewingDownload(null);
    setCandidates([]);
  };

  const getStatusColor = (status: Download['status']) => {
    switch (status) {
      case 'pending':
      case 'searching':
        return 'var(--accent-blue)';
      case 'downloading':
        return 'var(--accent-yellow)';
      case 'completed':
        return 'var(--accent-green)';
      case 'pending_review':
        return 'var(--accent-orange, #f97316)';
      case 'moved':
        return 'var(--accent-purple)';
      case 'failed':
        return 'var(--accent-red)';
      case 'cancelled':
        return 'var(--text-muted)';
      default:
        return 'var(--text-secondary)';
    }
  };

  const getStatusLabel = (status: Download['status']) => {
    switch (status) {
      case 'pending':
        return 'Pending';
      case 'searching':
        return 'Searching...';
      case 'downloading':
        return 'Downloading';
      case 'completed':
        return 'Completed';
      case 'pending_review':
        return 'Review Tags';
      case 'moved':
        return 'Moved to Library';
      case 'failed':
        return 'Failed';
      case 'cancelled':
        return 'Cancelled';
      default:
        return status;
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  if (loading) {
    return <div className="loading">Loading downloads...</div>;
  }

  return (
    <div className="downloads-view">
      <div className="downloads-header">
        <h2>Downloads</h2>
        
        <div className="slskd-status">
          {slskdStatus ? (
            <div className={`status-badge ${slskdStatus.available ? 'available' : 'unavailable'}`}>
              <span className="status-dot" style={{ 
                backgroundColor: slskdStatus.available ? 'var(--accent-green)' : 'var(--accent-red)' 
              }} />
              {slskdStatus.enabled ? (
                slskdStatus.available ? 'slskd Connected' : 'slskd Unavailable'
              ) : 'slskd Disabled'}
            </div>
          ) : (
            <div className="status-badge unavailable">
              <span className="status-dot" style={{ backgroundColor: 'var(--text-secondary)' }} />
              Checking...
            </div>
          )}
        </div>
      </div>

      {!slskdStatus?.enabled && (
        <div className="slskd-notice">
          <p>
            <strong>slskd Integration Disabled</strong>
          </p>
          <p>
            To enable album downloads from Soulseek, configure the following environment variables:
          </p>
          <ul>
            <li><code>SLSKD_ENABLED=true</code></li>
            <li><code>SLSKD_URL</code> - URL to your slskd instance (e.g., http://localhost:5030)</li>
            <li><code>SLSKD_API_KEY</code> - Your slskd API key</li>
            <li><code>SLSKD_DOWNLOAD_DIR</code> - Path to slskd downloads folder</li>
          </ul>
        </div>
      )}

      {downloads.length === 0 ? (
        <div className="empty-state">
          <p>No downloads yet.</p>
          <p className="hint">Go to your Wishlist and click the download button on albums you want to download.</p>
        </div>
      ) : (
        <div className="downloads-list">
          {downloads.map(download => (
            <div key={download.id} className="download-card">
              <div className="download-info">
                <div className="download-title">
                  <strong>{download.album_title}</strong>
                  <span className="download-artist">{download.artist_name}</span>
                </div>
                
                <div className="download-meta">
                  <span 
                    className="download-status"
                    style={{ color: getStatusColor(download.status) }}
                  >
                    {getStatusLabel(download.status)}
                  </span>
                  
                  {download.slskd_username && (
                    <span className="download-source">from {download.slskd_username}</span>
                  )}
                  
                  {download.total_files > 0 && (
                    <span className="download-files">
                      {download.completed_files}/{download.total_files} files
                    </span>
                  )}
                  
                  {download.total_bytes > 0 && (
                    <span className="download-size">
                      {formatBytes(download.completed_bytes)}/{formatBytes(download.total_bytes)}
                    </span>
                  )}
                </div>

                {download.status === 'downloading' && download.progress_percent > 0 && (
                  <div className="download-progress">
                    <div 
                      className="progress-bar"
                      style={{ width: `${download.progress_percent}%` }}
                    />
                    <span className="progress-text">{download.progress_percent}%</span>
                  </div>
                )}

                {download.error_message && (
                  <div className="download-error">
                    {download.error_message}
                  </div>
                )}

                <div className="download-time">
                  Added: {formatDate(download.created_at)}
                  {download.completed_at && (
                    <> • Completed: {formatDate(download.completed_at)}</>
                  )}
                </div>
              </div>

              <div className="download-actions">
                {['pending', 'searching', 'downloading'].includes(download.status) && (
                  <button 
                    className="btn btn-cancel"
                    onClick={() => handleCancel(download.id)}
                    title="Cancel download"
                  >
                    Cancel
                  </button>
                )}
                
                {download.status === 'completed' && (
                  <button 
                    className="btn btn-primary"
                    onClick={() => handleMove(download.id)}
                    title="Move to Music Library"
                  >
                    Move to Library
                  </button>
                )}
                
                {download.status === 'pending_review' && (
                  <button 
                    className="btn btn-review"
                    onClick={() => handleReviewTags(download)}
                    title="Review tag options"
                  >
                    Review Tags
                  </button>
                )}
                
                {['failed', 'cancelled'].includes(download.status) && (
                  <button 
                    className="btn btn-retry"
                    onClick={() => handleRetry(download.id)}
                    title="Retry download"
                  >
                    Retry
                  </button>
                )}
                
                {['completed', 'pending_review', 'failed', 'moved', 'cancelled'].includes(download.status) && (
                  <button 
                    className="btn btn-secondary"
                    onClick={() => handleDelete(download.id)}
                    title="Remove from list"
                  >
                    Remove
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tag Review Modal */}
      {reviewingDownload && (
        <div className="modal-overlay" onClick={closeReviewModal}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Review Album Tags</h3>
              <button className="modal-close" onClick={closeReviewModal}>&times;</button>
            </div>
            
            <div className="modal-body">
              <div className="review-album-info">
                <strong>{reviewingDownload.album_title}</strong>
                <span>{reviewingDownload.artist_name}</span>
              </div>
              
              {loadingCandidates ? (
                <div className="loading-candidates">Loading match candidates...</div>
              ) : candidates.length === 0 ? (
                <div className="no-candidates">
                  <p>No tag matches found for this album.</p>
                  <p>You can move it to your library without tagging.</p>
                </div>
              ) : (
                <div className="candidates-list">
                  <p className="candidates-intro">
                    Select the correct match for this album, or skip tagging to move as-is.
                  </p>
                  {candidates.map((candidate, index) => (
                    <div 
                      key={candidate.id || index} 
                      className={`candidate-card ${index === 0 ? 'best-match' : ''}`}
                    >
                      <div className="candidate-info">
                        <div className="candidate-title">
                          <strong>{candidate.album}</strong>
                          {index === 0 && <span className="best-badge">Best Match</span>}
                        </div>
                        <div className="candidate-artist">{candidate.artist}</div>
                        <div className="candidate-meta">
                          {candidate.year && <span>{candidate.year}</span>}
                          {candidate.tracks > 0 && <span>{candidate.tracks} tracks</span>}
                          <span className="confidence" style={{
                            color: candidate.confidence >= 95 ? 'var(--accent-green)' : 
                                   candidate.confidence >= 80 ? 'var(--accent-yellow)' : 
                                   'var(--accent-red)'
                          }}>
                            {candidate.confidence.toFixed(1)}% match
                          </span>
                        </div>
                      </div>
                      <button 
                        className="btn btn-apply"
                        onClick={() => handleApplyMatch(candidate.id)}
                        disabled={applyingMatch}
                      >
                        {applyingMatch ? 'Applying...' : 'Apply'}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            
            <div className="modal-footer">
              <button 
                className="btn btn-secondary"
                onClick={() => handleApplyMatch(undefined, true)}
                disabled={applyingMatch}
              >
                Skip Tagging
              </button>
              <button 
                className="btn btn-cancel"
                onClick={closeReviewModal}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        .downloads-view {
          padding: 32px;
        }

        .downloads-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 32px;
        }

        .downloads-header h2 {
          margin: 0;
          font-size: 28px;
          font-weight: 700;
        }

        .slskd-status .status-badge {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 14px 24px;
          border-radius: 24px;
          background: var(--bg-tertiary);
          font-size: 16px;
          font-weight: 500;
          margin-left: 24px;
        }

        .status-dot {
          width: 12px;
          height: 12px;
          border-radius: 50%;
        }

        .slskd-notice {
          background: var(--bg-tertiary);
          border-radius: 12px;
          padding: 20px;
          margin-bottom: 24px;
        }

        .slskd-notice p {
          margin: 0 0 12px;
        }

        .slskd-notice ul {
          margin: 0;
          padding-left: 20px;
        }

        .slskd-notice li {
          margin: 4px 0;
        }

        .slskd-notice code {
          background: var(--bg-secondary);
          padding: 2px 6px;
          border-radius: 4px;
          font-family: monospace;
        }

        .empty-state {
          text-align: center;
          padding: 60px 20px;
          color: var(--text-secondary);
        }

        .empty-state .hint {
          font-size: 14px;
          margin-top: 8px;
        }

        .downloads-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .download-card {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 16px;
          padding: 16px;
          background: var(--bg-tertiary);
          border-radius: 12px;
        }

        .download-info {
          flex: 1;
          min-width: 0;
        }

        .download-title {
          display: flex;
          flex-direction: column;
          gap: 4px;
          margin-bottom: 8px;
        }

        .download-title strong {
          font-size: 16px;
          color: var(--text-primary);
        }

        .download-artist {
          font-size: 14px;
          color: var(--text-secondary);
        }

        .download-meta {
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          font-size: 13px;
          color: var(--text-secondary);
          margin-bottom: 8px;
        }

        .download-status {
          font-weight: 500;
        }

        .download-progress {
          position: relative;
          height: 6px;
          background: var(--bg-secondary);
          border-radius: 3px;
          margin: 12px 0;
          overflow: hidden;
        }

        .progress-bar {
          height: 100%;
          background: var(--accent-primary);
          border-radius: 3px;
          transition: width 0.3s ease;
        }

        .progress-text {
          position: absolute;
          right: 0;
          top: -18px;
          font-size: 12px;
          color: var(--text-secondary);
        }

        .download-error {
          background: rgba(239, 68, 68, 0.1);
          color: var(--accent-red);
          padding: 8px 12px;
          border-radius: 6px;
          font-size: 13px;
          margin-top: 8px;
        }

        .download-time {
          font-size: 12px;
          color: var(--text-muted);
          margin-top: 8px;
        }

        .download-actions {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .btn {
          padding: 8px 16px;
          border-radius: 6px;
          border: none;
          cursor: pointer;
          font-size: 13px;
          font-weight: 500;
          transition: all 0.2s ease;
          white-space: nowrap;
        }

        .btn-primary {
          background: var(--accent-primary);
          color: white;
        }

        .btn-primary:hover {
          opacity: 0.9;
        }

        .btn-secondary {
          background: var(--bg-secondary);
          color: var(--text-primary);
        }

        .btn-secondary:hover {
          background: var(--bg-hover);
        }

        .btn-retry {
          background: var(--accent-yellow);
          color: #000;
        }

        .btn-retry:hover {
          opacity: 0.9;
        }

        .btn-cancel {
          background: var(--accent-red);
          color: white;
        }

        .btn-cancel:hover {
          opacity: 0.9;
        }

        .btn-review {
          background: var(--accent-orange, #f97316);
          color: white;
        }

        .btn-review:hover {
          opacity: 0.9;
        }

        .btn-apply {
          background: var(--accent-green);
          color: white;
        }

        .btn-apply:hover {
          opacity: 0.9;
        }

        .btn-apply:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        /* Modal Styles */
        .modal-overlay {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.7);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
          padding: 20px;
        }

        .modal-content {
          background: var(--bg-secondary);
          border-radius: 16px;
          max-width: 600px;
          width: 100%;
          max-height: 80vh;
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }

        .modal-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 20px 24px;
          border-bottom: 1px solid var(--bg-tertiary);
        }

        .modal-header h3 {
          margin: 0;
          font-size: 20px;
          font-weight: 600;
        }

        .modal-close {
          background: none;
          border: none;
          font-size: 24px;
          color: var(--text-secondary);
          cursor: pointer;
          padding: 0;
          line-height: 1;
        }

        .modal-close:hover {
          color: var(--text-primary);
        }

        .modal-body {
          padding: 24px;
          overflow-y: auto;
          flex: 1;
        }

        .review-album-info {
          display: flex;
          flex-direction: column;
          gap: 4px;
          padding: 16px;
          background: var(--bg-tertiary);
          border-radius: 8px;
          margin-bottom: 20px;
        }

        .review-album-info strong {
          font-size: 16px;
          color: var(--text-primary);
        }

        .review-album-info span {
          font-size: 14px;
          color: var(--text-secondary);
        }

        .loading-candidates,
        .no-candidates {
          text-align: center;
          padding: 40px 20px;
          color: var(--text-secondary);
        }

        .candidates-intro {
          margin: 0 0 16px;
          font-size: 14px;
          color: var(--text-secondary);
        }

        .candidates-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .candidate-card {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 16px;
          padding: 16px;
          background: var(--bg-tertiary);
          border-radius: 8px;
          border: 2px solid transparent;
          transition: border-color 0.2s;
        }

        .candidate-card.best-match {
          border-color: var(--accent-green);
        }

        .candidate-card:hover {
          border-color: var(--accent-primary);
        }

        .candidate-info {
          flex: 1;
          min-width: 0;
        }

        .candidate-title {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 4px;
        }

        .candidate-title strong {
          font-size: 15px;
          color: var(--text-primary);
        }

        .best-badge {
          background: var(--accent-green);
          color: white;
          padding: 2px 8px;
          border-radius: 4px;
          font-size: 11px;
          font-weight: 600;
        }

        .candidate-artist {
          font-size: 14px;
          color: var(--text-secondary);
          margin-bottom: 8px;
        }

        .candidate-meta {
          display: flex;
          gap: 12px;
          font-size: 13px;
          color: var(--text-muted);
        }

        .candidate-meta .confidence {
          font-weight: 500;
        }

        .modal-footer {
          display: flex;
          justify-content: flex-end;
          gap: 12px;
          padding: 16px 24px;
          border-top: 1px solid var(--bg-tertiary);
        }
      `}</style>
    </div>
  );
}

