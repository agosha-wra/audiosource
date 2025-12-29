import { useState, useEffect, useCallback } from 'react';
import type { View, Stats, ScanStatus, UpcomingStatus } from './types';
import { getStats, getScanStatus, startScan, cancelScan, checkUpcomingReleases, getUpcomingStatus } from './api';
import Sidebar from './components/Sidebar';
import AlbumsView from './components/AlbumsView';
import ArtistsView from './components/ArtistsView';
import ArtistDetailView from './components/ArtistDetailView';
import WishlistView from './components/WishlistView';
import NewReleasesView from './components/NewReleasesView';
import DownloadsView from './components/DownloadsView';
import VinylReleasesView from './components/VinylReleasesView';
import ConcertsView from './components/ConcertsView';
import SettingsView from './components/SettingsView';
import AlbumModal from './components/AlbumModal';
import SearchModal from './components/SearchModal';

// Parse URL to get current state
function getStateFromURL(): { view: View; artistId: number | null; year?: number; week?: number } {
  const params = new URLSearchParams(window.location.search);
  const path = window.location.pathname;
  
  // Parse view from path
  let view: View = 'albums';
  let artistId: number | null = null;
  
  if (path === '/artists' || path.startsWith('/artists')) {
    const artistMatch = path.match(/\/artists\/(\d+)/);
    if (artistMatch) {
      view = 'artist-detail';
      artistId = parseInt(artistMatch[1], 10);
    } else {
      view = 'artists';
    }
  } else if (path === '/wishlist') {
    view = 'wishlist';
  } else if (path === '/new-releases') {
    view = 'new-releases';
  } else if (path === '/downloads') {
    view = 'downloads';
  } else if (path === '/vinyl-releases') {
    view = 'vinyl-releases';
  } else if (path === '/concerts') {
    view = 'concerts';
  } else if (path === '/settings') {
    view = 'settings';
  } else {
    view = 'albums';
  }
  
  // Parse year/week from query params
  const year = params.get('year') ? parseInt(params.get('year')!, 10) : undefined;
  const week = params.get('week') ? parseInt(params.get('week')!, 10) : undefined;
  
  return { view, artistId, year, week };
}

// Update URL without reload
function updateURL(view: View, artistId?: number | null, year?: number, week?: number) {
  let path = '/';
  const params = new URLSearchParams();
  
  switch (view) {
    case 'albums':
      path = '/';
      break;
    case 'artists':
      path = '/artists';
      break;
    case 'artist-detail':
      path = artistId ? `/artists/${artistId}` : '/artists';
      break;
    case 'wishlist':
      path = '/wishlist';
      break;
    case 'new-releases':
      path = '/new-releases';
      if (year) params.set('year', year.toString());
      if (week) params.set('week', week.toString());
      break;
    case 'downloads':
      path = '/downloads';
      break;
    case 'vinyl-releases':
      path = '/vinyl-releases';
      break;
    case 'concerts':
      path = '/concerts';
      break;
    case 'settings':
      path = '/settings';
      break;
  }
  
  const search = params.toString();
  const url = search ? `${path}?${search}` : path;
  window.history.pushState({}, '', url);
}

function App() {
  // Initialize from URL
  const initialState = getStateFromURL();
  
  const [currentView, setCurrentView] = useState<View>(initialState.view);
  const [currentArtistId, setCurrentArtistId] = useState<number | null>(initialState.artistId);
  const [initialYear] = useState<number | undefined>(initialState.year);
  const [initialWeek] = useState<number | undefined>(initialState.week);
  
  const [selectedAlbumId, setSelectedAlbumId] = useState<number | null>(null);
  const [showSearchModal, setShowSearchModal] = useState(false);
  const [stats, setStats] = useState<Stats>({ album_count: 0, missing_album_count: 0, wishlist_count: 0, artist_count: 0 });
  const [scanStatus, setScanStatus] = useState<ScanStatus | null>(null);
  const [upcomingStatus, setUpcomingStatus] = useState<UpcomingStatus | null>(null);
  const [isScanning, setIsScanning] = useState(false);
  const [isCheckingUpcoming, setIsCheckingUpcoming] = useState(false);
  const [wishlistKey, setWishlistKey] = useState(0);

  // Handle browser back/forward
  useEffect(() => {
    const handlePopState = () => {
      const state = getStateFromURL();
      setCurrentView(state.view);
      setCurrentArtistId(state.artistId);
    };
    
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

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
      if (status && (status.status === 'completed' || status.status === 'error' || status.status === 'idle' || status.status === 'cancelled')) {
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

  const handleCancelScan = async () => {
    try {
      await cancelScan();
      setIsScanning(false);
      refreshStats();
    } catch (error) {
      console.error('Error cancelling scan:', error);
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
    updateURL(view);
  };

  const handleArtistClick = (artistId: number) => {
    setCurrentArtistId(artistId);
    setCurrentView('artist-detail');
    updateURL('artist-detail', artistId);
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
    updateURL('artists');
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

  // Callback for NewReleasesView to update URL when week changes
  const handleWeekChange = (year: number, week: number) => {
    updateURL('new-releases', null, year, week);
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
        onCancelScan={handleCancelScan}
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

        {currentView === 'new-releases' && (
          <NewReleasesView 
            onWishlistChange={handleAlbumAddedToWishlist}
            initialYear={initialYear}
            initialWeek={initialWeek}
            onWeekChange={handleWeekChange}
          />
        )}

        {currentView === 'downloads' && (
          <DownloadsView />
        )}

        {currentView === 'vinyl-releases' && (
          <VinylReleasesView />
        )}

        {currentView === 'concerts' && (
          <ConcertsView />
        )}

        {currentView === 'settings' && (
          <SettingsView />
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
