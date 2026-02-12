import { useState, useEffect, useCallback } from 'react';
import type { View, Stats, ScanStatus, UpcomingStatus, Artist } from './types';
import { getStats, getScanStatus, startScan, cancelScan, checkUpcomingReleases, getUpcomingStatus, getArtists } from './api';
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
  const [sidebarOpen, setSidebarOpen] = useState(false);
  
  // Artists state - persisted across navigation
  const [artists, setArtists] = useState<Artist[]>([]);
  const [artistsLoaded, setArtistsLoaded] = useState(false);
  const [artistsSort, setArtistsSort] = useState('name');
  const [artistsSearch, setArtistsSearch] = useState('');
  const [artistsHasMore, setArtistsHasMore] = useState(true);
  const [artistsScrollPos, setArtistsScrollPos] = useState(0);
  const [shouldRestoreScroll, setShouldRestoreScroll] = useState(false);

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
    setSidebarOpen(false); // Close sidebar on mobile after navigation
  };

  const handleArtistClick = (artistId: number) => {
    // Save scroll position before navigating (window is the scroll container)
    setArtistsScrollPos(window.scrollY);
    setShouldRestoreScroll(true);
    setCurrentArtistId(artistId);
    setCurrentView('artist-detail');
    updateURL('artist-detail', artistId);
  };
  
  // Load artists (initial or when sort/search changes)
  const loadArtists = useCallback(async () => {
    try {
      const data = await getArtists(0, 100, artistsSort, artistsSearch);
      setArtists(data);
      setArtistsHasMore(data.length === 100);
      setArtistsLoaded(true);
    } catch (error) {
      console.error('Error fetching artists:', error);
    }
  }, [artistsSort, artistsSearch]);
  
  // Load more artists for infinite scroll
  const loadMoreArtists = useCallback(async () => {
    try {
      const data = await getArtists(artists.length, 100, artistsSort, artistsSearch);
      setArtists(prev => [...prev, ...data]);
      setArtistsHasMore(data.length === 100);
    } catch (error) {
      console.error('Error loading more artists:', error);
    }
  }, [artists.length, artistsSort, artistsSearch]);
  
  // Handle artist sort change
  const handleArtistsSortChange = useCallback((newSort: string) => {
    setArtistsSort(newSort);
    setArtistsLoaded(false); // Force reload
  }, []);
  
  // Handle artist search change
  const handleArtistsSearchChange = useCallback((newSearch: string) => {
    setArtistsSearch(newSearch);
    setArtistsLoaded(false); // Force reload
  }, []);
  
  // Update artists list (called after delete, etc.)
  const updateArtistsList = useCallback((newArtists: Artist[]) => {
    setArtists(newArtists);
  }, []);

  const handleAlbumClick = (albumId: number) => {
    setSelectedAlbumId(albumId);
  };

  const handleCloseModal = () => {
    setSelectedAlbumId(null);
  };

  const handleAlbumDeleted = () => {
    refreshStats();
    // Reload artists if we're on the artists view (album counts may have changed)
    if (currentView === 'artists' || currentView === 'artist-detail') {
      setArtistsLoaded(false); // Force reload of artists list
    }
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
      {/* Mobile menu button */}
      <button 
        className="mobile-menu-btn"
        onClick={() => setSidebarOpen(!sidebarOpen)}
        aria-label="Toggle menu"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          {sidebarOpen ? (
            <path d="M18 6L6 18M6 6l12 12"/>
          ) : (
            <path d="M3 12h18M3 6h18M3 18h18"/>
          )}
        </svg>
      </button>

      {/* Overlay for mobile */}
      {sidebarOpen && (
        <div 
          className="sidebar-overlay"
          onClick={() => setSidebarOpen(false)}
        />
      )}

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
        isOpen={sidebarOpen}
      />
      
      <main className="main">
        {currentView === 'albums' && (
          <AlbumsView onAlbumClick={handleAlbumClick} />
        )}
        
        {currentView === 'artists' && (
          <ArtistsView 
            onArtistClick={handleArtistClick}
            artists={artists}
            setArtists={updateArtistsList}
            loaded={artistsLoaded}
            loadArtists={loadArtists}
            loadMoreArtists={loadMoreArtists}
            hasMore={artistsHasMore}
            sort={artistsSort}
            onSortChange={handleArtistsSortChange}
            search={artistsSearch}
            onSearchChange={handleArtistsSearchChange}
            savedScrollPos={artistsScrollPos}
            shouldRestoreScroll={shouldRestoreScroll}
            onScrollRestored={() => setShouldRestoreScroll(false)}
          />
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
        <AlbumModal 
          albumId={selectedAlbumId} 
          onClose={handleCloseModal} 
          onDeleted={handleAlbumDeleted}
        />
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
