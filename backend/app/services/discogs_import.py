"""
Import a Discogs collection CSV export into the wishlist.

Every album in the CSV that isn't already in AudioSource (owned or wishlisted) is added
to the wishlist.

MusicBrainz is the expensive part: it allows ~1 request/second, and a collection can be
hundreds of rows. So:
  * rows are matched against the local database first - anything we already have costs
    no MusicBrainz request at all;
  * the remaining rows get ONE search each, paced slower than MusicBrainz's limit and
    funnelled through the shared MusicBrainzService limiter;
  * the work runs in a background thread (a request would time out), with progress;
  * if MusicBrainz starts failing we back off, then stop the import rather than keep
    hammering it. Re-running is safe: whatever was already added is skipped.
"""

import csv
import io
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import musicbrainzngs
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Album, Artist
from app.services.musicbrainz import MusicBrainzService

# Safety cap so a wrong file can't queue thousands of MusicBrainz searches.
MAX_ROWS = 3000

# Minimum gap between this importer's MusicBrainz searches. MusicBrainz asks for at most
# 1 request/second on average; the shared limiter already enforces 1.1s, this is the
# extra politeness for a bulk job that runs for many minutes.
IMPORT_MB_MIN_INTERVAL_SECONDS = 1.5

# MusicBrainz problems: pause this long between attempts, then give up on the whole
# import (the library's own retries have already been exhausted by then).
_MB_RETRY_WAITS_SECONDS = (15, 45)

# Matching thresholds for accepting a MusicBrainz result for a Discogs row.
_TITLE_ACCEPT = 0.85
_ARTIST_ACCEPT = 0.80
# Fuzzy match against albums we already have (same artist, near-identical title).
_LOCAL_TITLE_FUZZY = 0.92

_REPORT_LIST_CAP = 300


class ImportAlreadyRunning(Exception):
    pass


class MusicBrainzUnavailable(Exception):
    pass


# --------------------------------------------------------------------------
# Parsing / normalisation
# --------------------------------------------------------------------------

@dataclass
class DiscogsRow:
    artist: str          # cleaned artist name
    title: str           # cleaned title
    year: Optional[str]  # Discogs "Released" year (of that pressing, so only a fallback)

    @property
    def label(self) -> str:
        return f"{self.artist} - {self.title}"


_DISCOGS_DISAMBIGUATION = re.compile(r"\s*\(\d+\)")


def clean_artist(raw: str) -> str:
    """'Grimes (4)' -> 'Grimes', 'Beatles, The' -> 'The Beatles', 'Various' -> 'Various Artists'."""
    artist = _DISCOGS_DISAMBIGUATION.sub("", raw or "").strip()
    artist = re.sub(r"\s+", " ", artist)
    match = re.match(r"^(.*),\s*The$", artist, flags=re.IGNORECASE)
    if match:
        artist = f"The {match.group(1)}"
    if artist.lower() == "various":
        artist = "Various Artists"
    return artist


def clean_title(raw: str) -> str:
    return re.sub(r"\s+", " ", raw or "").strip()


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def norm(s: str) -> str:
    """Lowercase, accent-free, punctuation-free, single-spaced."""
    s = _strip_accents(s or "").lower().replace("&", " and ")
    s = re.sub(r"[^\w\s]|_", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_artist(s: str) -> str:
    n = norm(s)
    return n[4:] if n.startswith("the ") else n


def loose_title(s: str) -> str:
    """Title without (bracketed) edition notes and a trailing 'EP' - for local matching only."""
    s = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", s or "")
    n = norm(s)
    n = re.sub(r"\s+ep$", "", n)
    return n


def _artist_keys(artist: str) -> List[str]:
    """Full name first, then the first credited artist ('A, B' / 'A & B' / 'A feat. B')."""
    keys = [norm_artist(artist)]
    first = re.split(r",|\s&\s|\sand\s|\sfeat\.?\s|\sfeaturing\s|\s/\s|\sx\s", artist, maxsplit=1,
                     flags=re.IGNORECASE)[0]
    first_key = norm_artist(first)
    if first_key and first_key not in keys:
        keys.append(first_key)
    return [k for k in keys if k]


def parse_discogs_csv(text: str) -> List[DiscogsRow]:
    """Parse a Discogs collection export. Duplicate artist+title rows are collapsed."""
    text = text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(text))
    fields = {f.strip().lower(): f for f in (reader.fieldnames or []) if f}
    if "artist" not in fields or "title" not in fields:
        raise ValueError(
            "This doesn't look like a Discogs collection export: "
            "the CSV needs 'Artist' and 'Title' columns."
        )

    artist_col, title_col = fields["artist"], fields["title"]
    year_col = fields.get("released")

    rows: List[DiscogsRow] = []
    seen = set()
    for record in reader:
        artist = clean_artist(record.get(artist_col) or "")
        title = clean_title(record.get(title_col) or "")
        if not artist or not title:
            continue

        key = (norm_artist(artist), norm(title))
        if key in seen:
            continue
        seen.add(key)

        year = None
        if year_col:
            m = re.match(r"^\s*((?:19|20)\d{2})", record.get(year_col) or "")
            year = m.group(1) if m else None
        rows.append(DiscogsRow(artist=artist, title=title, year=year))

        if len(rows) > MAX_ROWS:
            raise ValueError(f"Too many albums (more than {MAX_ROWS}); split the file and import it in parts.")

    return rows


# --------------------------------------------------------------------------
# Matching against what we already have
# --------------------------------------------------------------------------

def _status_rank(album: Album) -> int:
    if album.is_owned:
        return 0
    if album.is_wishlisted:
        return 1
    return 2


class LocalIndex:
    """All albums already in the database, indexed for cheap in-memory matching."""

    def __init__(self, albums: List[Album]):
        self.by_artist: Dict[str, List[Tuple[Album, str, str]]] = {}
        self.by_mbid: Dict[str, Album] = {}
        for album in albums:
            self.add(album)

    def add(self, album: Album) -> None:
        if album.musicbrainz_id:
            self.by_mbid[album.musicbrainz_id] = album
        if album.artist is None:
            return
        for key in _artist_keys(album.artist.name):
            self.by_artist.setdefault(key, []).append(
                (album, norm(album.title), loose_title(album.title))
            )

    def find(self, artist: str, title: str) -> Optional[Album]:
        nt, lt = norm(title), loose_title(title)
        candidates: List[Album] = []
        fuzzy: List[Tuple[float, Album]] = []

        for key in _artist_keys(artist):
            for album, n, l in self.by_artist.get(key, []):
                if n == nt or (lt and l == lt):
                    candidates.append(album)
                elif nt and SequenceMatcher(None, n, nt).ratio() >= _LOCAL_TITLE_FUZZY:
                    fuzzy.append((SequenceMatcher(None, n, nt).ratio(), album))

        if candidates:
            return min(candidates, key=_status_rank)
        if fuzzy:
            return min((a for _, a in fuzzy), key=_status_rank)
        return None


# --------------------------------------------------------------------------
# Job state (single job at a time, kept in memory; the UI polls it)
# --------------------------------------------------------------------------

_state_lock = threading.Lock()
_cancel_event = threading.Event()
_state: Dict[str, Any] = {}


def _fresh_state() -> Dict[str, Any]:
    return {
        "status": "idle",          # idle | running | completed | cancelled | error
        "message": None,
        "filename": None,
        "started_at": None,
        "finished_at": None,
        "total_rows": 0,           # unique albums in the CSV
        "already_owned": 0,
        "already_wishlisted": 0,
        "tagged_existing": 0,      # already-wishlisted albums that got the Discogs tag
        "to_lookup": 0,            # rows that need a MusicBrainz search
        "processed": 0,            # of those, how many are done
        "added": 0,                # newly wishlisted
        "added_unmatched": 0,      # ...of which have no MusicBrainz match
        "failed": 0,
        "current": None,
        "estimated_seconds_left": None,
        "unmatched": [],           # "Artist - Title" added without a MusicBrainz match
        "failed_items": [],
    }


_state = _fresh_state()


def get_status() -> Dict[str, Any]:
    with _state_lock:
        snap = dict(_state)
        snap["unmatched"] = list(_state["unmatched"])
        snap["failed_items"] = list(_state["failed_items"])
        return snap


def _update(**kwargs) -> None:
    with _state_lock:
        _state.update(kwargs)


def _incr(field: str, by: int = 1) -> None:
    with _state_lock:
        _state[field] += by


def _append_capped(field: str, value: str) -> None:
    with _state_lock:
        if len(_state[field]) < _REPORT_LIST_CAP:
            _state[field].append(value)


def request_cancel() -> bool:
    with _state_lock:
        running = _state["status"] == "running"
    if running:
        _cancel_event.set()
    return running


def start_import(rows: List[DiscogsRow], filename: Optional[str] = None) -> Dict[str, Any]:
    """
    Classify rows against the local database (instant, no MusicBrainz) and start the
    background job for whatever is left. Returns the initial status.
    """
    with _state_lock:
        if _state["status"] == "running":
            raise ImportAlreadyRunning()
        _cancel_event.clear()
        _state.clear()
        _state.update(_fresh_state())
        _state.update(status="running", filename=filename, started_at=datetime.utcnow().isoformat(),
                      total_rows=len(rows), message="Matching against your library...")

    try:
        db = SessionLocal()
        try:
            importer = DiscogsImporter(db)
            plan = importer.classify(rows)
        finally:
            db.close()
    except Exception as e:
        _update(status="error", message=f"Could not read the library: {e}",
                finished_at=datetime.utcnow().isoformat())
        raise

    _update(
        already_owned=plan.owned,
        already_wishlisted=plan.already_wishlisted,
        to_lookup=len(plan.to_lookup),
        message=None,
    )

    thread = threading.Thread(target=_run_job, args=(plan,), daemon=True, name="discogs-import")
    thread.start()
    return get_status()


@dataclass
class Plan:
    owned: int
    already_wishlisted: int
    existing_missing: List[Tuple[DiscogsRow, int]]   # (row, album_id) already in DB, just not wishlisted
    to_lookup: List[DiscogsRow]
    wishlisted_ids: List[int]                        # already on the wishlist: only need the Discogs tag


def _run_job(plan: Plan) -> None:
    db = SessionLocal()
    try:
        DiscogsImporter(db).run(plan)
    except Exception as e:
        import traceback
        traceback.print_exc()
        _update(status="error", message=f"Import failed: {e}", finished_at=datetime.utcnow().isoformat(),
                current=None)
    finally:
        db.close()


# --------------------------------------------------------------------------
# The importer
# --------------------------------------------------------------------------

def _lucene_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _title_similarity(a: str, b: str) -> float:
    return max(_similar(norm(a), norm(b)), _similar(loose_title(a), loose_title(b)))


def _artist_similarity(row_artist: str, mb_artist: str) -> float:
    target = norm_artist(mb_artist)
    return max(_similar(key, target) for key in _artist_keys(row_artist) + [norm_artist(row_artist)])


def pick_best_match(row: DiscogsRow, candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Best MusicBrainz release group for a Discogs row, or None if nothing is convincing."""
    various = norm(row.artist) == "various artists"
    best, best_score = None, 0.0
    for cand in candidates:
        if not cand.get("musicbrainz_id") or not cand.get("title"):
            continue
        title_sim = _title_similarity(row.title, cand["title"])
        artist_sim = 1.0 if various else _artist_similarity(row.artist, cand.get("artist_name") or "")
        if title_sim < _TITLE_ACCEPT or artist_sim < _ARTIST_ACCEPT:
            continue
        score = title_sim * 0.6 + artist_sim * 0.4
        if score > best_score:   # strict > keeps MusicBrainz's own ordering on ties
            best, best_score = cand, score
    return best


def _http_status(exc: Exception) -> Optional[int]:
    return getattr(getattr(exc, "cause", None), "code", None)


class DiscogsImporter:
    def __init__(self, db: Session):
        self.db = db
        self._last_mb_call = 0.0
        self.index: Optional[LocalIndex] = None
        self._artists_by_name: Dict[str, Artist] = {}
        self._artists_by_mbid: Dict[str, Artist] = {}

    # ---- local classification ------------------------------------------------

    def _load_index(self) -> LocalIndex:
        if self.index is None:
            self.index = LocalIndex(self.db.query(Album).all())
        return self.index

    def classify(self, rows: List[DiscogsRow]) -> Plan:
        index = self._load_index()
        owned = already_wishlisted = 0
        existing_missing: List[Tuple[DiscogsRow, int]] = []
        to_lookup: List[DiscogsRow] = []
        wishlisted_ids: List[int] = []

        for row in rows:
            album = index.find(row.artist, row.title)
            if album is None:
                to_lookup.append(row)
            elif album.is_owned:
                owned += 1
            elif album.is_wishlisted:
                already_wishlisted += 1
                wishlisted_ids.append(album.id)
            else:
                existing_missing.append((row, album.id))

        return Plan(owned, already_wishlisted, existing_missing, to_lookup, wishlisted_ids)

    # ---- the job ---------------------------------------------------------------

    def run(self, plan: Plan) -> None:
        index = self._load_index()

        # Tag albums that were already on the wishlist as coming from Discogs. Done up
        # front (one UPDATE, no MusicBrainz) so it takes effect immediately, even if the
        # slow lookups below get cancelled. Owned albums are left alone.
        if plan.wishlisted_ids:
            tagged = (
                self.db.query(Album)
                .filter(Album.id.in_(plan.wishlisted_ids),
                        Album.is_owned == False,  # noqa: E712
                        Album.is_wishlisted == True)  # noqa: E712
                .update({Album.from_discogs: True}, synchronize_session=False)
            )
            self.db.commit()
            _update(tagged_existing=tagged)

        # Albums we already know about (e.g. from a discography fetch) just need the
        # wishlist flag (+ tag): no MusicBrainz request.
        for row, album_id in plan.existing_missing:
            album = self.db.query(Album).filter(Album.id == album_id).first()
            if album and not album.is_owned and not album.is_wishlisted:
                album.is_wishlisted = True
                album.from_discogs = True
                _incr("added")
        self.db.commit()

        total = len(plan.to_lookup)
        started = time.time()

        for i, row in enumerate(plan.to_lookup):
            if _cancel_event.is_set():
                _update(status="cancelled", current=None, finished_at=datetime.utcnow().isoformat(),
                        message=f"Cancelled after {i} of {total} lookups. Run the import again to continue.")
                return

            _update(current=row.label)
            try:
                candidates = self._search_musicbrainz(row)
            except MusicBrainzUnavailable as e:
                _update(status="error", current=None, finished_at=datetime.utcnow().isoformat(),
                        message=(f"MusicBrainz stopped responding ({e}) after {i} of {total} lookups. "
                                 f"Nothing was lost - run the import again later to continue."))
                return
            except _Cancelled:
                continue  # loop head reports the cancellation

            try:
                self._add_row(row, pick_best_match(row, candidates), index)
            except Exception as e:
                self.db.rollback()
                # The artist cache may hold an object from the rolled-back transaction.
                self._artists_by_name.clear()
                self._artists_by_mbid.clear()
                print(f"Discogs import: failed to add {row.label}: {e}")
                _incr("failed")
                _append_capped("failed_items", row.label)

            done = i + 1
            _update(processed=done)
            elapsed = time.time() - started
            _update(estimated_seconds_left=int(elapsed / done * (total - done)) if done else None)

        _update(status="completed", current=None, estimated_seconds_left=0,
                finished_at=datetime.utcnow().isoformat(), message=None)

    # ---- MusicBrainz -----------------------------------------------------------

    def _pace(self) -> None:
        wait = IMPORT_MB_MIN_INTERVAL_SECONDS - (time.time() - self._last_mb_call)
        if wait > 0 and _cancel_event.wait(wait):
            raise _Cancelled()
        # Shared limiter: also spaces us from every other MusicBrainz user in the app.
        MusicBrainzService._rate_limit()
        self._last_mb_call = time.time()

    def _search_musicbrainz(self, row: DiscogsRow) -> List[Dict[str, Any]]:
        """
        One release-group search for the row. Errors are *not* treated as "no match":
        we back off and retry, and raise MusicBrainzUnavailable if it keeps failing.
        """
        query = f'releasegroup:"{_lucene_escape(row.title)}"'
        if norm(row.artist) != "various artists":
            query += f' AND artist:"{_lucene_escape(row.artist)}"'

        last_error: Optional[Exception] = None
        for attempt in range(len(_MB_RETRY_WAITS_SECONDS) + 1):
            self._pace()
            try:
                result = musicbrainzngs.search_release_groups(query=query, limit=5)
                return [self._candidate(rg) for rg in result.get("release-group-list", [])]
            except musicbrainzngs.ResponseError as e:
                # A rejected query (bad syntax / odd characters) won't improve on retry.
                if _http_status(e) in (400, 404):
                    return []
                last_error = e
            except (musicbrainzngs.NetworkError, musicbrainzngs.WebServiceError) as e:
                last_error = e

            if attempt < len(_MB_RETRY_WAITS_SECONDS):
                wait = _MB_RETRY_WAITS_SECONDS[attempt]
                print(f"Discogs import: MusicBrainz error ({last_error}); waiting {wait}s")
                _update(message=f"MusicBrainz is struggling; pausing {wait}s before retrying...")
                if _cancel_event.wait(wait):
                    raise _Cancelled()
                _update(message=None)

        raise MusicBrainzUnavailable(str(last_error))

    @staticmethod
    def _candidate(rg: Dict[str, Any]) -> Dict[str, Any]:
        artist_name = artist_mbid = None
        credit = rg.get("artist-credit", [])
        if credit and isinstance(credit[0], dict):
            artist = credit[0].get("artist", credit[0])
            artist_name, artist_mbid = artist.get("name"), artist.get("id")
        rg_id = rg.get("id")
        return {
            "musicbrainz_id": rg_id,
            "title": rg.get("title"),
            "artist_name": artist_name,
            "artist_musicbrainz_id": artist_mbid,
            "release_date": rg.get("first-release-date") or None,
            "release_type": rg.get("primary-type") or None,
            "cover_art_url": MusicBrainzService.get_release_group_cover_art_url(rg_id) if rg_id else None,
        }

    # ---- writing to the wishlist --------------------------------------------------

    def _add_row(self, row: DiscogsRow, match: Optional[Dict[str, Any]], index: LocalIndex) -> None:
        if match:
            # The MusicBrainz id may already belong to an album we have (different
            # spelling locally, or two CSV rows that resolve to the same release group).
            existing = index.by_mbid.get(match["musicbrainz_id"])
            if existing is not None:
                if existing.is_owned:
                    _incr("already_owned")
                elif existing.is_wishlisted:
                    # Already wishlisted (by the user, or earlier in this very import).
                    if not existing.from_discogs:
                        existing.from_discogs = True
                        self.db.commit()
                        _incr("tagged_existing")
                    _incr("already_wishlisted")
                else:
                    existing.is_wishlisted = True
                    existing.from_discogs = True
                    self.db.commit()
                    _incr("added")
                return

            artist = self._get_or_create_artist(
                match.get("artist_name") or row.artist, match.get("artist_musicbrainz_id")
            )
            album = Album(
                title=match["title"],
                musicbrainz_id=match["musicbrainz_id"],
                artist_id=artist.id,
                release_date=match.get("release_date"),
                release_type=match.get("release_type"),
                cover_art_url=match.get("cover_art_url"),
                is_owned=False, is_wishlisted=True, is_scanned=True, from_discogs=True,
            )
        else:
            # No convincing MusicBrainz match: keep the Discogs data so it still lands
            # on the wishlist (no cover art / MusicBrainz id).
            artist = self._get_or_create_artist(row.artist, None)
            album = Album(
                title=row.title,
                artist_id=artist.id,
                release_date=row.year,
                is_owned=False, is_wishlisted=True, is_scanned=True, from_discogs=True,
            )

        self.db.add(album)
        self.db.commit()
        self.db.refresh(album)
        index.add(album)
        _incr("added")
        if not match:
            _incr("added_unmatched")
            _append_capped("unmatched", row.label)

    def _get_or_create_artist(self, name: str, mbid: Optional[str]) -> Artist:
        if not self._artists_by_name:
            for a in self.db.query(Artist).all():
                self._artists_by_name[a.name.lower()] = a
                if a.musicbrainz_id:
                    self._artists_by_mbid[a.musicbrainz_id] = a

        artist = self._artists_by_mbid.get(mbid) if mbid else None
        if artist is None:
            artist = self._artists_by_name.get(name.lower())
            # Name match without an id yet: adopt the MusicBrainz id (it is unique, so
            # only if nobody else holds it).
            if artist is not None and mbid and not artist.musicbrainz_id and mbid not in self._artists_by_mbid:
                artist.musicbrainz_id = mbid
                self._artists_by_mbid[mbid] = artist
        if artist is None:
            artist = Artist(name=name, musicbrainz_id=mbid if mbid not in self._artists_by_mbid else None)
            self.db.add(artist)
            self.db.flush()
            self._artists_by_name[name.lower()] = artist
            if mbid:
                self._artists_by_mbid[mbid] = artist
        return artist


class _Cancelled(Exception):
    pass
