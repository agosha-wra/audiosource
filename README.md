# AudioSource

A self-hosted music library management application that scans your music folder, fetches metadata from MusicBrainz, and provides a beautiful web interface to browse your collection.

## Features

- 🎵 **Automatic Library Scanning** - Discovers albums from your music folder
- 🔍 **MusicBrainz Integration** - Fetches album metadata, artist info, and cover art
- 💾 **PostgreSQL Database** - Persistent storage for your library data
- 🌐 **Modern Web Interface** - Browse albums and artists with a sleek UI
- 🐳 **Docker Deployment** - Easy deployment on any machine

## Quick Start

### Using Docker Compose (Recommended)

1. Clone this repository:
   ```bash
   git clone <repo-url>
   cd audiosource
   ```

2. Set your music folder path:
   ```bash
   export MUSIC_FOLDER=/path/to/your/music
   ```

3. Start the application:
   ```bash
   docker-compose up -d --build
   ```

4. Open your browser and navigate to:
   ```
   http://localhost:8080
   ```

5. Click **"Scan Library"** to scan your music folder.

### Configuration

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Edit the `.env` file to set your music folder path:

```env
MUSIC_FOLDER=/path/to/your/music
```

## Supported Audio Formats

- MP3 (.mp3)
- FLAC (.flac)
- AAC (.m4a, .aac)
- OGG Vorbis (.ogg)
- WAV (.wav)
- WMA (.wma)
- AIFF (.aiff)

## Development

### Running Locally

1. Start PostgreSQL:
   ```bash
   docker run -d --name audiosource-db \
     -e POSTGRES_USER=audiosource \
     -e POSTGRES_PASSWORD=audiosource \
     -e POSTGRES_DB=audiosource \
     -p 5432:5432 \
     postgres:15-alpine
   ```

2. Set up Python environment:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Set environment variables:
   ```bash
   export DATABASE_URL=postgresql://audiosource:audiosource@localhost:5432/audiosource
   export MUSIC_FOLDER=/path/to/your/music
   ```

4. Run the backend:
   ```bash
   cd backend
   uvicorn app.main:app --reload --port 8000
   ```

5. Serve the frontend (in another terminal):
   ```bash
   cd frontend
   python -m http.server 3000
   ```

6. Access at http://localhost:3000 (frontend will proxy API calls to :8000)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/albums` | GET | List all albums |
| `/api/albums/{id}` | GET | Get album details with tracks |
| `/api/artists` | GET | List all artists |
| `/api/artists/{id}` | GET | Get artist details |
| `/api/artists/{id}/albums` | GET | Get albums by artist |
| `/api/scan` | POST | Start library scan |
| `/api/scan/status` | GET | Get scan status |
| `/api/stats` | GET | Get library statistics |

## Architecture

```
audiosource/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI application
│   │   ├── models.py        # SQLAlchemy models
│   │   ├── schemas.py       # Pydantic schemas
│   │   ├── database.py      # Database configuration
│   │   ├── config.py        # App configuration
│   │   └── services/
│   │       ├── scanner.py   # Music folder scanner
│   │       └── musicbrainz.py # MusicBrainz API client
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
└── entrypoint.sh
```

## License

MIT

