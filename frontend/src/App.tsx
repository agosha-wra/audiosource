import { useState, useEffect, useCallback } from 'react';
import type { View, Stats, ScanStatus, UpcomingStatus } from './types';
import { getStats, getScanStatus, startScan, checkUpcomingReleases, getUpcomingStatus } from './api';
import Sidebar from './components/Sidebar';
import AlbumsView from './components/AlbumsView';
import ArtistsView from './components/ArtistsView';
import ArtistDetailView from './components/ArtistDetailView';
import WishlistView from './components/WishlistView';
import AlbumModal from './components/AlbumModal';
import SearchModal from './components/SearchModal';

function App() {
  const [currentView, setCurrentView] = useState<View>('albums');
  const [currentArtistId, setCurrentArtistId] = useState<number | null>(null);
  const [selectedAlbumId, setSelectedAlbumId] = useState<number | null>(null);
  const [showSearchModal, setShowSearchModal] = useState(false);
  const [stats, setStats] = useState<Stats>({ album_count: 0, missing_album_count: 0, wishlist_count: 0, artist_count: 0 });
  const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null);
  const [upcomingStatus, setUpcomingStatus] = useState<UpcomingStatus | null>(null);
  const [isScanning, setIsScanning] = useState(false);
  const [isCheckingUpcoming, setIsCheckingUpcoming] = useState(false);
  const [wishlistKey, setWishlistKey] = useState(0);

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

  const fetchUpcomingStatus = useCallback(async () => {
    try {
      const status = await getUpcomingStatus();
      setUpcomingStatus(status);
      return status;
    } catch (error) {
      console.error('Error fetching upcoming status:', error);
      return null;
    }
  }, []);

  useEffect(() => {
    refreshStats();
    checkScanStatus();
    fetchUpcomingStatus();
  }, [refreshStats, checkScanStatus, fetchUpcomingStatus]);

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

  useEffect(() => {
    if (!isCheckingUpcoming) return;

    const interval = setInterval(async () => {
      const status = await fetchUpcomingStatus();
      if (status && (status.status === 'completed' || status.status === 'error' || status.status === 'idle')) {
        setIsCheckingUpcoming(false);
        refreshStats();
        setWishlistKey(prev => prev + 1);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [isCheckingUpcoming, fetchUpcomingStatus, refreshStats]);

  const handleScan = async () => {
    try {
      await startScan(false);
      setIsScanning(true);
    } catch (error) {
      console.error('Error starting scan:', error);
    }
  };

  const handleCheckUpcoming = async () => {
    try {
      await checkUpcomingReleases();
      setIsCheckingUpcoming(true);
    } catch (error) {
      console.error('Error starting upcoming check:', error);
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

  const handleOpenSearch = () => {
    setShowSearchModal(true);
  };

  const handleCloseSearch = () => {
    setShowSearchModal(false);
  };

  const handleAlbumAddedToWishlist = () => {
    refreshStats();
    setWishlistKey(prev => prev + 1);
  };

  return (
    <div className="app">
      <Sidebar
        currentView={currentView}
        stats={stats}
        scanStatus={scanStatus}
        upcomingStatus={upcomingStatus}
        isScanning={isScanning}
        isCheckingUpcoming={isCheckingUpcoming}
        onNavigate={handleNavigate}
        onScan={handleScan}
        onCheckUpcoming={handleCheckUpcoming}
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

        {currentView === 'wishlist' && (
          <WishlistView 
            key={wishlistKey}
            onAlbumClick={handleAlbumClick}
            onOpenSearch={handleOpenSearch}
          />
        )}
      </main>

      {selectedAlbumId !== null && (
        <AlbumModal albumId={selectedAlbumId} onClose={handleCloseModal} />
      )}

      {showSearchModal && (
        <SearchModal 
          onClose={handleCloseSearch}
          onAlbumAdded={handleAlbumAddedToWishlist}
        />
      )}
    </div>
  );
}

export default App;
