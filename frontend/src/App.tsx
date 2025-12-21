import { useState, useEffect, useCallback } from 'react';
import type { View, Stats, ScanStatus } from './types';
import { getStats, getScanStatus, startScan } from './api';
import Sidebar from './components/Sidebar';
import AlbumsView from './components/AlbumsView';
import ArtistsView from './components/ArtistsView';
import ArtistDetailView from './components/ArtistDetailView';
import AlbumModal from './components/AlbumModal';

function App() {
  const [currentView, setCurrentView] = useState<View>('albums');
  const [currentArtistId, setCurrentArtistId] = useState<number | null>(null);
  const [selectedAlbumId, setSelectedAlbumId] = useState<number | null>(null);
  const [stats, setStats] = useState<Stats>({ album_count: 0, missing_album_count: 0, artist_count: 0 });
  const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null);
  const [isScanning, setIsScanning] = useState(false);

  const refreshStats = useCallback(async () => {
    try {
      const newStats = await getStats();
      setStats(newStats);
    } catch (error) {
      console.error('Error fetching stats:', error);
    }
  }, []);

  const checkScanStatus = useCallback(async () => {
    try {
      const status = await getScanStatus();
      setScanStatus(status);
      return status;
    } catch (error) {
      console.error('Error fetching scan status:', error);
      return null;
    }
  }, []);

  useEffect(() => {
    refreshStats();
    checkScanStatus();
  }, [refreshStats, checkScanStatus]);

  useEffect(() => {
    if (!isScanning) return;

    const interval = setInterval(async () => {
      const status = await checkScanStatus();
      if (status && (status.status === 'completed' || status.status === 'error' || status.status === 'idle')) {
        setIsScanning(false);
        refreshStats();
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [isScanning, checkScanStatus, refreshStats]);

  const handleScan = async () => {
    try {
      await startScan(false);
      setIsScanning(true);
    } catch (error) {
      console.error('Error starting scan:', error);
    }
  };

  const handleNavigate = (view: View) => {
    setCurrentView(view);
    setCurrentArtistId(null);
  };

  const handleArtistClick = (artistId: number) => {
    setCurrentArtistId(artistId);
    setCurrentView('artist-detail');
  };

  const handleAlbumClick = (albumId: number) => {
    setSelectedAlbumId(albumId);
  };

  const handleCloseModal = () => {
    setSelectedAlbumId(null);
  };

  const handleBackToArtists = () => {
    setCurrentView('artists');
    setCurrentArtistId(null);
  };

  return (
    <div className="app">
      <Sidebar
        currentView={currentView}
        stats={stats}
        scanStatus={scanStatus}
        isScanning={isScanning}
        onNavigate={handleNavigate}
        onScan={handleScan}
      />
      
      <main className="main">
        {currentView === 'albums' && (
          <AlbumsView onAlbumClick={handleAlbumClick} />
        )}
        
        {currentView === 'artists' && (
          <ArtistsView onArtistClick={handleArtistClick} />
        )}
        
        {currentView === 'artist-detail' && currentArtistId && (
          <ArtistDetailView
            artistId={currentArtistId}
            onBack={handleBackToArtists}
            onAlbumClick={handleAlbumClick}
          />
        )}
      </main>

      {selectedAlbumId !== null && (
        <AlbumModal albumId={selectedAlbumId} onClose={handleCloseModal} />
      )}
    </div>
  );
}

export default App;

