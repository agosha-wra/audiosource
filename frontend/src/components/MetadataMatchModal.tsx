import { useState, useEffect } from 'react';
import type { MetadataMatchCandidate } from '../types';
import { getMetadataMatches, applyMetadata } from '../api';

interface MetadataMatchModalProps {
  albumId: number;
  albumTitle: string;
  artistName: string;
  onClose: () => void;
  onApplied: () => void;
}

export default function MetadataMatchModal({ 
  albumId, 
  albumTitle, 
  artistName,
  onClose, 
  onApplied 
}: MetadataMatchModalProps) {
  const [candidates, setCandidates] = useState<MetadataMatchCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchMatches = async () => {
      try {
        setLoading(true);
        setError(null);
        const matches = await getMetadataMatches(albumId);
        setCandidates(matches);
      } catch (err) {
        setError('Failed to search MusicBrainz');
        console.error('Error fetching matches:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchMatches();
  }, [albumId]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);

  const handleApply = async (candidate: MetadataMatchCandidate) => {
    try {
      setApplying(candidate.musicbrainz_id);
      await applyMetadata(albumId, candidate.musicbrainz_id);
      onApplied();
      onClose();
    } catch (err) {
      setError('Failed to apply metadata');
      console.error('Error applying metadata:', err);
    } finally {
      setApplying(null);
    }
  };

  const getMatchColor = (score: number) => {
    if (score >= 80) return 'var(--accent-green)';
    if (score >= 60) return 'var(--accent-yellow)';
    if (score >= 40) return 'var(--accent-orange, #f97316)';
    return 'var(--accent-red)';
  };

  return (
    <div className="modal active">
      <div className="modal-backdrop" onClick={onClose} />
      <div className="modal-content metadata-match-modal">
        <button className="modal-close" onClick={onClose}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>

        <div className="metadata-match-header">
          <h2>Fix Album Metadata</h2>
          <p className="current-info">
            Current: <strong>{artistName}</strong> — <strong>{albumTitle}</strong>
          </p>
        </div>

        {loading ? (
          <div className="loading" style={{ padding: '60px' }}>
            <div className="loading-spinner" />
            <p>Searching MusicBrainz...</p>
          </div>
        ) : error ? (
          <div className="error-state">
            <p>{error}</p>
            <button className="btn-retry" onClick={() => window.location.reload()}>
              Try Again
            </button>
          </div>
        ) : candidates.length === 0 ? (
          <div className="empty-state" style={{ padding: '40px' }}>
            <p>No matches found on MusicBrainz.</p>
            <p className="hint">Try editing the album title or artist name first.</p>
          </div>
        ) : (
          <div className="candidates-list">
            {candidates.map((candidate) => (
              <div key={candidate.musicbrainz_id} className="candidate-card">
                <div className="candidate-cover">
                  {candidate.cover_art_url ? (
                    <img 
                      src={candidate.cover_art_url} 
                      alt={candidate.title}
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                      }}
                    />
                  ) : (
                    <div className="cover-placeholder">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                        <circle cx="12" cy="12" r="10"/>
                        <circle cx="12" cy="12" r="3"/>
                      </svg>
                    </div>
                  )}
                </div>
                
                <div className="candidate-info">
                  <div className="candidate-title">{candidate.title}</div>
                  <div className="candidate-artist">{candidate.artist_name || 'Unknown Artist'}</div>
                  <div className="candidate-meta">
                    {candidate.release_type && <span>{candidate.release_type}</span>}
                    {candidate.release_date && <span>{candidate.release_date}</span>}
                    {candidate.track_count && <span>{candidate.track_count} tracks</span>}
                  </div>
                </div>

                <div className="candidate-match">
                  <div 
                    className="match-score"
                    style={{ 
                      backgroundColor: getMatchColor(candidate.match_score),
                      color: candidate.match_score >= 60 ? '#000' : '#fff'
                    }}
                  >
                    {candidate.match_score}%
                  </div>
                  <button
                    className="btn-apply"
                    onClick={() => handleApply(candidate)}
                    disabled={applying !== null}
                  >
                    {applying === candidate.musicbrainz_id ? (
                      <span className="spinner">⟳</span>
                    ) : (
                      'Apply'
                    )}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        <style>{`
          .metadata-match-modal {
            max-width: 700px;
            max-height: 80vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
          }

          .metadata-match-header {
            padding: 24px 24px 16px;
            border-bottom: 1px solid var(--border-color);
          }

          .metadata-match-header h2 {
            margin: 0 0 8px;
            font-size: 22px;
          }

          .metadata-match-header .current-info {
            margin: 0;
            color: var(--text-secondary);
            font-size: 14px;
          }

          .candidates-list {
            flex: 1;
            overflow-y: auto;
            padding: 16px 24px 24px;
          }

          .candidate-card {
            display: flex;
            align-items: center;
            gap: 16px;
            padding: 12px;
            background: var(--bg-tertiary);
            border-radius: 10px;
            margin-bottom: 10px;
            transition: background 0.15s ease;
          }

          .candidate-card:hover {
            background: var(--bg-hover);
          }

          .candidate-cover {
            width: 60px;
            height: 60px;
            border-radius: 6px;
            overflow: hidden;
            flex-shrink: 0;
            background: var(--bg-secondary);
          }

          .candidate-cover img {
            width: 100%;
            height: 100%;
            object-fit: cover;
          }

          .cover-placeholder {
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--text-muted);
          }

          .cover-placeholder svg {
            width: 30px;
            height: 30px;
          }

          .candidate-info {
            flex: 1;
            min-width: 0;
          }

          .candidate-title {
            font-weight: 600;
            font-size: 15px;
            color: var(--text-primary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }

          .candidate-artist {
            font-size: 13px;
            color: var(--text-secondary);
            margin-top: 2px;
          }

          .candidate-meta {
            display: flex;
            gap: 10px;
            margin-top: 4px;
            font-size: 12px;
            color: var(--text-muted);
          }

          .candidate-match {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 8px;
            flex-shrink: 0;
          }

          .match-score {
            font-size: 14px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 12px;
            min-width: 48px;
            text-align: center;
          }

          .btn-apply {
            padding: 6px 16px;
            border-radius: 6px;
            border: none;
            background: var(--accent-primary);
            color: white;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: opacity 0.15s ease;
          }

          .btn-apply:hover:not(:disabled) {
            opacity: 0.9;
          }

          .btn-apply:disabled {
            opacity: 0.6;
            cursor: not-allowed;
          }

          .btn-apply .spinner {
            display: inline-block;
            animation: spin 1s linear infinite;
          }

          @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }

          .error-state {
            padding: 40px;
            text-align: center;
          }

          .error-state p {
            color: var(--accent-red);
            margin-bottom: 16px;
          }

          .btn-retry {
            padding: 8px 20px;
            border-radius: 6px;
            border: none;
            background: var(--bg-tertiary);
            color: var(--text-primary);
            cursor: pointer;
          }

          .empty-state .hint {
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 8px;
          }
        `}</style>
      </div>
    </div>
  );
}

