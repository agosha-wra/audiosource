import { useState, useEffect } from 'react';
import type { AppSettings } from '../types';
import { getAppSettings } from '../api';

// Preset accent colors
const ACCENT_COLORS = [
  { name: 'Orange', value: '#f97316', hover: '#ea580c' },
  { name: 'Blue', value: '#3b82f6', hover: '#2563eb' },
  { name: 'Green', value: '#22c55e', hover: '#16a34a' },
  { name: 'Purple', value: '#a855f7', hover: '#9333ea' },
  { name: 'Pink', value: '#ec4899', hover: '#db2777' },
  { name: 'Red', value: '#ef4444', hover: '#dc2626' },
  { name: 'Cyan', value: '#06b6d4', hover: '#0891b2' },
  { name: 'Yellow', value: '#eab308', hover: '#ca8a04' },
];

export default function SettingsView() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [accentColor, setAccentColor] = useState(() => {
    return localStorage.getItem('accentColor') || '#f97316';
  });

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const data = await getAppSettings();
        setSettings(data);
      } catch (error) {
        console.error('Error fetching settings:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchSettings();
  }, []);

  const handleColorChange = (color: string, hoverColor: string) => {
    setAccentColor(color);
    localStorage.setItem('accentColor', color);
    localStorage.setItem('accentHoverColor', hoverColor);
    
    // Apply to CSS variables
    document.documentElement.style.setProperty('--accent', color);
    document.documentElement.style.setProperty('--accent-hover', hoverColor);
    document.documentElement.style.setProperty('--accent-glow', `${color}26`);
  };

  return (
    <>
      <header className="header">
        <h1>Settings</h1>
      </header>

      <div className="content">
        <div className="settings-container">
          {/* Appearance Section */}
          <section className="settings-section">
            <h2>Appearance</h2>
            
            <div className="setting-item">
              <label>Accent Color</label>
              <div className="color-picker">
                {ACCENT_COLORS.map((color) => (
                  <button
                    key={color.value}
                    className={`color-option ${accentColor === color.value ? 'active' : ''}`}
                    style={{ backgroundColor: color.value }}
                    onClick={() => handleColorChange(color.value, color.hover)}
                    title={color.name}
                  >
                    {accentColor === color.value && (
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <polyline points="20 6 9 17 4 12"/>
                      </svg>
                    )}
                  </button>
                ))}
              </div>
            </div>
          </section>

          {/* Environment Configuration Section */}
          <section className="settings-section">
            <h2>Configuration</h2>
            <p className="section-description">
              These values are read from environment variables and cannot be changed from the UI.
            </p>

            {loading ? (
              <div className="loading">
                <div className="loading-spinner" />
              </div>
            ) : settings ? (
              <div className="config-grid">
                <div className="config-item">
                  <span className="config-label">Music Folder</span>
                  <span className="config-value">{settings.music_folder}</span>
                </div>

                <div className="config-item">
                  <span className="config-label">Database</span>
                  <span className="config-value">{settings.database_url}</span>
                </div>

                <div className="config-item">
                  <span className="config-label">slskd Integration</span>
                  <span className={`config-value ${settings.slskd.enabled ? 'enabled' : 'disabled'}`}>
                    {settings.slskd.enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </div>

                {settings.slskd.enabled && (
                  <>
                    <div className="config-item">
                      <span className="config-label">slskd URL</span>
                      <span className="config-value">{settings.slskd.url}</span>
                    </div>

                    <div className="config-item">
                      <span className="config-label">slskd Download Dir</span>
                      <span className="config-value">{settings.slskd.download_dir}</span>
                    </div>

                    <div className="config-item">
                      <span className="config-label">slskd API Key</span>
                      <span className={`config-value ${settings.slskd.api_key_set ? 'enabled' : 'disabled'}`}>
                        {settings.slskd.api_key_set ? '••••••••' : 'Not Set'}
                      </span>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="error-state">Failed to load settings</div>
            )}
          </section>

          {/* About Section */}
          <section className="settings-section">
            <h2>About</h2>
            <div className="about-info">
              <p><strong>AudioSource</strong></p>
              <p className="muted">A personal music library manager with MusicBrainz integration and Soulseek downloads.</p>
            </div>
          </section>
        </div>
      </div>

      <style>{`
        .settings-container {
          max-width: 700px;
          margin: 0 auto;
        }

        .settings-section {
          background: var(--bg-tertiary);
          border-radius: 12px;
          padding: 24px;
          margin-bottom: 20px;
        }

        .settings-section h2 {
          font-size: 18px;
          font-weight: 600;
          margin-bottom: 16px;
          color: var(--text-primary);
        }

        .section-description {
          font-size: 13px;
          color: var(--text-muted);
          margin-bottom: 16px;
        }

        .setting-item {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .setting-item label {
          font-size: 14px;
          font-weight: 500;
          color: var(--text-secondary);
        }

        .color-picker {
          display: flex;
          gap: 10px;
          flex-wrap: wrap;
        }

        .color-option {
          width: 40px;
          height: 40px;
          border-radius: 10px;
          border: 3px solid transparent;
          cursor: pointer;
          transition: all 0.15s ease;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .color-option:hover {
          transform: scale(1.1);
        }

        .color-option.active {
          border-color: var(--text-primary);
        }

        .color-option svg {
          width: 20px;
          height: 20px;
          color: white;
          filter: drop-shadow(0 1px 2px rgba(0,0,0,0.5));
        }

        .config-grid {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .config-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px 16px;
          background: var(--bg-secondary);
          border-radius: 8px;
        }

        .config-label {
          font-size: 14px;
          color: var(--text-secondary);
        }

        .config-value {
          font-size: 14px;
          font-family: 'SF Mono', Monaco, monospace;
          color: var(--text-primary);
        }

        .config-value.enabled {
          color: var(--success);
        }

        .config-value.disabled {
          color: var(--text-muted);
        }

        .about-info {
          font-size: 14px;
          color: var(--text-secondary);
        }

        .about-info p {
          margin-bottom: 8px;
        }

        .about-info .muted {
          color: var(--text-muted);
          font-size: 13px;
        }

        .error-state {
          color: var(--accent-red);
          text-align: center;
          padding: 20px;
        }
      `}</style>
    </>
  );
}

