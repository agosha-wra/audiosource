// AudioSource Frontend Application

const API_BASE = '/api';

// State
let currentView = 'albums';
let currentArtistId = null;
let albums = [];
let artists = [];
let scanStatusInterval = null;

// DOM Elements
const content = document.getElementById('content');
const pageTitle = document.getElementById('page-title');
const searchInput = document.getElementById('search-input');
const scanBtn = document.getElementById('scan-btn');
const scanStatus = document.getElementById('scan-status');
const scanProgressBar = document.getElementById('scan-progress-bar');
const scanText = document.getElementById('scan-text');
const albumModal = document.getElementById('album-modal');
const albumDetail = document.getElementById('album-detail');
const modalClose = document.getElementById('modal-close');
const albumCount = document.getElementById('album-count');
const artistCount = document.getElementById('artist-count');

// API Functions
async function fetchApi(endpoint, options = {}) {
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            headers: {
                'Content-Type': 'application/json',
            },
            ...options,
        });
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

async function getAlbums(search = '') {
    const params = search ? `?search=${encodeURIComponent(search)}` : '';
    return await fetchApi(`/albums${params}`);
}

async function getAlbum(id) {
    return await fetchApi(`/albums/${id}`);
}

async function getArtists() {
    return await fetchApi('/artists');
}

async function getArtist(id) {
    return await fetchApi(`/artists/${id}`);
}

async function getArtistAlbums(artistId) {
    return await fetchApi(`/artists/${artistId}/albums`);
}

async function getStats() {
    return await fetchApi('/stats');
}

async function startScan(forceRescan = false) {
    return await fetchApi('/scan', {
        method: 'POST',
        body: JSON.stringify({ force_rescan: forceRescan }),
    });
}

async function getScanStatus() {
    return await fetchApi('/scan/status');
}

// Render Functions
function renderAlbumsGrid(albumsList, showOwnershipBadge = false) {
    const grid = document.getElementById('albums-grid');
    if (!grid) return;
    
    if (albumsList.length === 0) {
        grid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="12" cy="12" r="10"/>
                    <circle cx="12" cy="12" r="3"/>
                    <path d="M12 2v4M12 18v4"/>
                </svg>
                <h2>No albums found</h2>
                <p>Click "Scan Library" to discover albums in your music folder.</p>
            </div>
        `;
        return;
    }

    grid.innerHTML = albumsList.map(album => `
        <div class="album-card ${album.is_owned ? '' : 'missing'}" data-album-id="${album.id}">
            ${showOwnershipBadge ? `
                <div class="album-badge ${album.is_owned ? 'owned' : 'missing'}">
                    ${album.is_owned ? '✓ Owned' : '✗ Missing'}
                </div>
            ` : ''}
            <div class="album-cover">
                ${album.cover_art_url 
                    ? `<img src="${album.cover_art_url}" alt="${escapeHtml(album.title)}" onerror="this.parentElement.innerHTML = getPlaceholderSvg()">`
                    : `<div class="album-cover-placeholder">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <circle cx="12" cy="12" r="10"/>
                            <circle cx="12" cy="12" r="3"/>
                        </svg>
                    </div>`
                }
            </div>
            <div class="album-info">
                <div class="album-title">${escapeHtml(album.title)}</div>
                <div class="album-artist">${album.artist ? escapeHtml(album.artist.name) : 'Unknown Artist'}</div>
                <div class="album-meta">
                    ${album.release_date ? `<span>${album.release_date.substring(0, 4)}</span>` : ''}
                    ${album.track_count ? `<span>${album.track_count} tracks</span>` : ''}
                    ${album.release_type ? `<span>${album.release_type}</span>` : ''}
                </div>
            </div>
        </div>
    `).join('');

    // Add click handlers
    document.querySelectorAll('.album-card').forEach(card => {
        card.addEventListener('click', () => {
            const albumId = card.dataset.albumId;
            showAlbumDetail(albumId);
        });
    });
}

function renderArtistsGrid(artistsList) {
    content.innerHTML = `<div class="artists-grid" id="artists-grid"></div>`;
    const artistsGrid = document.getElementById('artists-grid');

    if (artistsList.length === 0) {
        artistsGrid.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <circle cx="12" cy="8" r="4"/>
                    <path d="M4 20c0-4 4-6 8-6s8 2 8 6"/>
                </svg>
                <h2>No artists found</h2>
                <p>Scan your library to discover artists.</p>
            </div>
        `;
        return;
    }

    artistsGrid.innerHTML = artistsList.map(artist => `
        <div class="artist-card" data-artist-id="${artist.id}">
            <div class="artist-avatar">${getInitials(artist.name)}</div>
            <div class="artist-name">${escapeHtml(artist.name)}</div>
            <div class="artist-album-counts">
                <span class="owned-count" title="Albums you own">${artist.owned_album_count || 0} owned</span>
                ${artist.missing_album_count > 0 ? `
                    <span class="missing-count" title="Albums you're missing">${artist.missing_album_count} missing</span>
                ` : ''}
            </div>
        </div>
    `).join('');

    // Add click handlers to show artist detail
    document.querySelectorAll('.artist-card').forEach(card => {
        card.addEventListener('click', () => {
            const artistId = card.dataset.artistId;
            showArtistDetail(artistId);
        });
    });
}

async function showArtistDetail(artistId) {
    currentArtistId = artistId;
    currentView = 'artist-detail';
    
    content.innerHTML = `<div class="loading"><div class="loading-spinner"></div></div>`;
    
    try {
        const [artist, albums] = await Promise.all([
            getArtist(artistId),
            getArtistAlbums(artistId)
        ]);
        
        const ownedAlbums = albums.filter(a => a.is_owned);
        const missingAlbums = albums.filter(a => !a.is_owned);
        
        pageTitle.textContent = artist.name;
        
        content.innerHTML = `
            <div class="artist-detail-header">
                <button class="back-btn" id="back-to-artists">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M19 12H5M12 19l-7-7 7-7"/>
                    </svg>
                    Back to Artists
                </button>
                <div class="artist-detail-info">
                    <div class="artist-detail-avatar">${getInitials(artist.name)}</div>
                    <div>
                        <h2>${escapeHtml(artist.name)}</h2>
                        <div class="artist-detail-stats">
                            <span class="owned-badge">${ownedAlbums.length} albums owned</span>
                            <span class="missing-badge">${missingAlbums.length} albums missing</span>
                        </div>
                    </div>
                </div>
            </div>
            
            ${ownedAlbums.length > 0 ? `
                <div class="album-section">
                    <h3 class="section-title owned">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M20 6L9 17l-5-5"/>
                        </svg>
                        Albums You Own (${ownedAlbums.length})
                    </h3>
                    <div class="albums-grid" id="owned-albums-grid"></div>
                </div>
            ` : ''}
            
            ${missingAlbums.length > 0 ? `
                <div class="album-section missing-section">
                    <h3 class="section-title missing">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"/>
                            <path d="M15 9l-6 6M9 9l6 6"/>
                        </svg>
                        Albums You're Missing (${missingAlbums.length})
                    </h3>
                    <div class="albums-grid" id="missing-albums-grid"></div>
                </div>
            ` : ''}
        `;
        
        // Render owned albums
        if (ownedAlbums.length > 0) {
            const ownedGrid = document.getElementById('owned-albums-grid');
            ownedGrid.innerHTML = ownedAlbums.map(album => renderAlbumCard(album, false)).join('');
        }
        
        // Render missing albums
        if (missingAlbums.length > 0) {
            const missingGrid = document.getElementById('missing-albums-grid');
            missingGrid.innerHTML = missingAlbums.map(album => renderAlbumCard(album, true)).join('');
        }
        
        // Add click handlers
        document.querySelectorAll('.album-card').forEach(card => {
            card.addEventListener('click', () => {
                const albumId = card.dataset.albumId;
                showAlbumDetail(albumId);
            });
        });
        
        // Back button handler
        document.getElementById('back-to-artists').addEventListener('click', () => {
            navigateTo('artists');
        });
        
    } catch (error) {
        console.error('Error loading artist:', error);
        content.innerHTML = `
            <div class="empty-state">
                <h2>Error loading artist</h2>
                <p>Could not load artist details.</p>
            </div>
        `;
    }
}

function renderAlbumCard(album, isMissing = false) {
    return `
        <div class="album-card ${isMissing ? 'missing' : ''}" data-album-id="${album.id}">
            <div class="album-cover">
                ${album.cover_art_url 
                    ? `<img src="${album.cover_art_url}" alt="${escapeHtml(album.title)}" onerror="this.parentElement.innerHTML = getPlaceholderSvg()">`
                    : `<div class="album-cover-placeholder">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <circle cx="12" cy="12" r="10"/>
                            <circle cx="12" cy="12" r="3"/>
                        </svg>
                    </div>`
                }
            </div>
            <div class="album-info">
                <div class="album-title">${escapeHtml(album.title)}</div>
                <div class="album-meta">
                    ${album.release_date ? `<span>${album.release_date.substring(0, 4)}</span>` : ''}
                    ${album.release_type ? `<span>${album.release_type}</span>` : ''}
                </div>
            </div>
        </div>
    `;
}

async function showAlbumDetail(albumId) {
    try {
        const album = await getAlbum(albumId);
        
        const totalDuration = album.tracks ? album.tracks.reduce((sum, t) => sum + (t.duration_seconds || 0), 0) : 0;
        const durationStr = formatDuration(totalDuration);

        albumDetail.innerHTML = `
            <div class="album-detail-cover">
                ${album.cover_art_url 
                    ? `<img src="${album.cover_art_url.replace('-250', '-500')}" alt="${escapeHtml(album.title)}" onerror="this.src='${album.cover_art_url}'">`
                    : `<div class="album-cover-placeholder" style="height: 100%;">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <circle cx="12" cy="12" r="10"/>
                            <circle cx="12" cy="12" r="3"/>
                        </svg>
                    </div>`
                }
            </div>
            <div class="album-detail-info">
                <div class="album-ownership-status ${album.is_owned ? 'owned' : 'missing'}">
                    ${album.is_owned ? '✓ In Your Library' : '✗ Not In Library'}
                </div>
                <h2>${escapeHtml(album.title)}</h2>
                <div class="album-detail-artist">${album.artist ? escapeHtml(album.artist.name) : 'Unknown Artist'}</div>
                <div class="album-detail-meta">
                    ${album.release_type ? `
                        <span>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="12" cy="12" r="10"/>
                            </svg>
                            ${album.release_type}
                        </span>
                    ` : ''}
                    ${album.release_date ? `
                        <span>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <rect x="3" y="4" width="18" height="18" rx="2"/>
                                <path d="M16 2v4M8 2v4M3 10h18"/>
                            </svg>
                            ${album.release_date}
                        </span>
                    ` : ''}
                    ${album.tracks && album.tracks.length ? `
                        <span>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M9 18V5l12-2v13"/>
                                <circle cx="6" cy="18" r="3"/>
                                <circle cx="18" cy="16" r="3"/>
                            </svg>
                            ${album.tracks.length} tracks
                        </span>
                    ` : ''}
                    ${totalDuration ? `
                        <span>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="12" cy="12" r="10"/>
                                <path d="M12 6v6l4 2"/>
                            </svg>
                            ${durationStr}
                        </span>
                    ` : ''}
                </div>
                ${album.tracks && album.tracks.length > 0 ? `
                    <div class="tracks-list">
                        <h3>Tracklist</h3>
                        ${album.tracks.sort((a, b) => (a.disc_number - b.disc_number) || (a.track_number - b.track_number)).map(track => `
                            <div class="track-item">
                                <span class="track-number">${track.track_number || '-'}</span>
                                <span class="track-title">${escapeHtml(track.title)}</span>
                                <span class="track-duration">${track.duration_seconds ? formatTrackDuration(track.duration_seconds) : '--:--'}</span>
                            </div>
                        `).join('')}
                    </div>
                ` : `
                    <div class="no-tracks">
                        <p>No track information available for this album.</p>
                    </div>
                `}
            </div>
        `;

        albumModal.classList.add('active');
    } catch (error) {
        console.error('Error loading album:', error);
    }
}

// Helper Functions
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getInitials(name) {
    if (!name) return '?';
    return name.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();
}

function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
        return `${hours}h ${minutes}m`;
    }
    return `${minutes} min`;
}

function formatTrackDuration(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function getPlaceholderSvg() {
    return `<div class="album-cover-placeholder">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="10"/>
            <circle cx="12" cy="12" r="3"/>
        </svg>
    </div>`;
}

// Navigation
async function navigateTo(view) {
    currentView = view;
    currentArtistId = null;
    
    // Update nav
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.view === view);
    });

    // Update title and search placeholder
    if (view === 'albums') {
        pageTitle.textContent = 'Albums';
        searchInput.placeholder = 'Search albums...';
        content.innerHTML = `
            <div class="loading"><div class="loading-spinner"></div></div>
        `;
        
        try {
            albums = await getAlbums();
            content.innerHTML = `<div class="albums-grid" id="albums-grid"></div>`;
            renderAlbumsGrid(albums);
        } catch (error) {
            content.innerHTML = `
                <div class="empty-state">
                    <h2>Error loading albums</h2>
                    <p>Could not connect to the server. Make sure the backend is running.</p>
                </div>
            `;
        }
    } else if (view === 'artists') {
        pageTitle.textContent = 'Artists';
        searchInput.placeholder = 'Search artists...';
        content.innerHTML = `
            <div class="loading"><div class="loading-spinner"></div></div>
        `;
        
        try {
            artists = await getArtists();
            renderArtistsGrid(artists);
        } catch (error) {
            content.innerHTML = `
                <div class="empty-state">
                    <h2>Error loading artists</h2>
                    <p>Could not connect to the server. Make sure the backend is running.</p>
                </div>
            `;
        }
    }
}

// Scan Functions
async function handleScan() {
    try {
        scanBtn.disabled = true;
        await startScan(false);
        startScanPolling();
    } catch (error) {
        console.error('Error starting scan:', error);
        scanBtn.disabled = false;
    }
}

function startScanPolling() {
    scanStatus.style.display = 'block';
    scanBtn.style.display = 'none';
    
    scanStatusInterval = setInterval(async () => {
        try {
            const status = await getScanStatus();
            updateScanStatus(status);
            
            if (status.status === 'completed' || status.status === 'error' || status.status === 'idle') {
                stopScanPolling();
                await refreshData();
            }
        } catch (error) {
            console.error('Error polling scan status:', error);
        }
    }, 1000);
}

function stopScanPolling() {
    if (scanStatusInterval) {
        clearInterval(scanStatusInterval);
        scanStatusInterval = null;
    }
    
    setTimeout(() => {
        scanStatus.style.display = 'none';
        scanBtn.style.display = 'flex';
        scanBtn.disabled = false;
    }, 2000);
}

function updateScanStatus(status) {
    const progress = status.total_folders > 0 
        ? (status.scanned_folders / status.total_folders) * 100 
        : 0;
    
    scanProgressBar.style.width = `${progress}%`;
    
    if (status.status === 'scanning') {
        scanText.textContent = `Scanning ${status.scanned_folders}/${status.total_folders} folders...`;
    } else if (status.status === 'completed') {
        scanText.textContent = 'Scan completed!';
        scanProgressBar.style.width = '100%';
    } else if (status.status === 'error') {
        scanText.textContent = `Error: ${status.error_message || 'Unknown error'}`;
    }
}

async function refreshData() {
    try {
        const stats = await getStats();
        albumCount.textContent = stats.album_count;
        artistCount.textContent = stats.artist_count;
    } catch (error) {
        console.error('Error refreshing stats:', error);
    }
    
    // Refresh current view
    if (currentView === 'artist-detail' && currentArtistId) {
        showArtistDetail(currentArtistId);
    } else {
        navigateTo(currentView);
    }
}

// Search
let searchTimeout;
searchInput.addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(async () => {
        if (currentView === 'albums') {
            try {
                const searchResults = await getAlbums(e.target.value);
                renderAlbumsGrid(searchResults);
            } catch (error) {
                console.error('Search error:', error);
            }
        }
    }, 300);
});

// Event Listeners
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        navigateTo(item.dataset.view);
    });
});

scanBtn.addEventListener('click', handleScan);

modalClose.addEventListener('click', () => {
    albumModal.classList.remove('active');
});

document.querySelector('.modal-backdrop').addEventListener('click', () => {
    albumModal.classList.remove('active');
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        albumModal.classList.remove('active');
    }
});

// Initialize
async function init() {
    try {
        // Check initial scan status
        const status = await getScanStatus();
        if (status.status === 'scanning') {
            startScanPolling();
        }
    } catch (error) {
        console.log('Could not check scan status');
    }
    
    // Load initial data
    refreshData();
}

init();
