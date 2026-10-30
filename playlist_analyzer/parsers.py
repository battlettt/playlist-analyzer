"""Import playlists from CSV, JSON and a plain-text paste format.

All three parsers feed the same row validator, so a track is accepted or
rejected by identical rules whatever format it arrived in. Bad rows are never
dropped silently: by default any bad row raises :class:`PlaylistParseError`
listing every problem (row number and what is wrong). With ``lenient=True``
bad rows are skipped but each one is recorded in ``Playlist.warnings``.
"""

import csv
import io
import json
import os
import re

from .analysis import round_half_up
from .keys import KeyParseError, parse_key
from .models import Playlist, Track

# Header aliases seen in real exports (Rekordbox, Serato, Mixed In Key,
# Exportify-style Spotify dumps, hand-made spreadsheets). Matching is done on
# a normalised header: lowercase, with spaces/underscores/dashes removed.
FIELD_ALIASES = {
    "title": ["title", "name", "track", "trackname", "tracktitle", "song", "songname"],
    "artist": ["artist", "artists", "artistname", "artistnames", "performer", "by"],
    "key": ["key", "musicalkey", "initialkey", "camelot", "camelotkey", "keycamelot", "tonality"],
    "bpm": ["bpm", "tempo", "beatsperminute"],
    "energy": ["energy", "energylevel", "energyscore", "intensity"],
    "duration": ["duration", "length", "time", "durationms", "durationseconds"],
    "genre": ["genre", "genres", "style"],
}
REQUIRED_FIELDS = ("title", "artist", "key", "bpm", "energy")
MIN_BPM, MAX_BPM = 20.0, 300.0
MAX_ENERGY = 100.0
_NUMBER_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


class RowError:
    """One problem with one input row."""

    def __init__(self, row, message):
        self.row = row
        self.message = message

    def __str__(self):
        return f"row {self.row}: {self.message}"

    def __repr__(self):
        return f"RowError({self.row!r}, {self.message!r})"


class PlaylistParseError(ValueError):
    """Raised when input cannot be turned into a playlist. Carries every row error."""

    def __init__(self, message, errors=None):
        self.errors = list(errors or [])
        detail = "".join(f"\n  - {e}" for e in self.errors)
        super().__init__(message + detail)


def _norm_header(name):
    return re.sub(r"[\s_\-()]+", "", str(name).strip().lower().lstrip("﻿"))


def _map_headers(headers):
    """Map our field names to column indexes. Unknown extra columns are ignored."""
    lookup = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            lookup.setdefault(alias, field)
    mapping = {}
    for index, header in enumerate(headers):
        field = lookup.get(_norm_header(header))
        if field and field not in mapping:
            mapping[field] = (index, _norm_header(header))
    return mapping


def _parse_number(value, what):
    text = str(value).strip().replace(",", ".") if value is not None else ""
    if not text:
        raise ValueError(f"{what} is missing")
    if not _NUMBER_RE.match(text):
        raise ValueError(f"{what} {value!r} is not a number")
    return float(text)


def _parse_duration(value, header=""):
    """Parse '3:45', '1:02:03', '225' (seconds) or a duration_ms column."""
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    if ":" in text:
        parts = text.split(":")
        try:
            numbers = [float(p) for p in parts]
        except ValueError:
            raise ValueError(f"duration {value!r} is not like 3:45") from None
        seconds = 0.0
        for n in numbers:
            seconds = seconds * 60 + n
        return seconds
    number = _parse_number(text, "duration")
    if number < 0:
        raise ValueError(f"duration {value!r} is negative")
    if header == "durationms" or number > 10000:
        return number / 1000.0
    return number


def build_track(raw, row):
    """Validate one raw row dict (string values) into a Track, or raise ValueError.

    ``energy`` is kept as given here; scale normalisation happens per playlist.
    """
    problems = []
    title = str(raw.get("title") or "").strip()
    artist = str(raw.get("artist") or "").strip()
    if not title:
        problems.append("title is missing")
    key = None
    key_raw = raw.get("key")
    try:
        key = parse_key(key_raw)
    except KeyParseError as exc:
        problems.append(str(exc))
    bpm = energy = None
    try:
        bpm = _parse_number(raw.get("bpm"), "bpm")
        if not MIN_BPM <= bpm <= MAX_BPM:
            problems.append(f"bpm {bpm:g} is outside {MIN_BPM:g}-{MAX_BPM:g}")
    except ValueError as exc:
        problems.append(str(exc))
    try:
        energy = _parse_number(raw.get("energy"), "energy")
        if not 0 <= energy <= MAX_ENERGY:
            problems.append(f"energy {energy:g} is outside 0-{MAX_ENERGY:g}")
    except ValueError as exc:
        problems.append(str(exc))
    duration = None
    try:
        duration = _parse_duration(raw.get("duration"), raw.get("_duration_header", ""))
    except ValueError as exc:
        problems.append(str(exc))
    if problems:
        raise ValueError("; ".join(problems))
    genre = str(raw.get("genre") or "").strip() or None
    return Track(
        title=title, artist=artist, key=key, bpm=bpm, energy=energy,
        key_raw=str(key_raw).strip(), duration=duration, genre=genre,
    )


def normalise_energy(tracks):
    """Bring energy onto a 0-10 scale, deciding the source scale per playlist.

    * every value <= 1   -> treated as 0-1 (Spotify style), multiplied by 10
    * any value  > 10    -> treated as 0-100, divided by 10
    * otherwise          -> already 0-10 (Mixed In Key style), unchanged
    Returns the detected scale label.
    """
    if not tracks:
        return "0-10"
    top = max(t.energy for t in tracks)
    if top <= 1.0:
        factor, scale = 10.0, "0-1"
    elif top > 10.0:
        factor, scale = 0.1, "0-100"
    else:
        return "0-10"
    for t in tracks:
        t.energy = round_half_up(t.energy * factor, 2)
    return scale


def _finish(rows, name, source_format, lenient, empty_message):
    """Shared tail of every parser: validate rows, collect errors, normalise."""
    tracks, errors = [], []
    for row_number, raw in rows:
        if isinstance(raw, RowError):
            errors.append(raw)
            continue
        try:
            tracks.append(build_track(raw, row_number))
        except ValueError as exc:
            errors.append(RowError(row_number, str(exc)))
    if errors and not lenient:
        raise PlaylistParseError(
            f"{len(errors)} invalid row(s) in {source_format} input", errors
        )
    if not tracks:
        raise PlaylistParseError(empty_message, errors)
    scale = normalise_energy(tracks)
    warnings = [f"skipped {e}" for e in errors]
    if scale != "0-10":
        warnings.append(f"energy values looked like a {scale} scale and were rescaled to 0-10")
    return Playlist(tracks=tracks, name=name, source_format=source_format,
                    energy_scale=scale, warnings=warnings)


def detect_delimiter(text):
    """Pick ',', ';' or tab: whichever appears most in the first non-blank line."""
    first = next((line for line in text.splitlines() if line.strip()), "")
    counts = [(first.count(d), -i, d) for i, d in enumerate((",", ";", "\t"))]
    best = max(counts)
    return best[2] if best[0] else ","


def parse_csv(text, name="Playlist", lenient=False):
    """Parse CSV with a header row. Row numbers in errors are file line numbers."""
    text = text.lstrip("﻿")
    if not text.strip():
        raise PlaylistParseError("CSV input is empty")
    reader = csv.reader(io.StringIO(text), delimiter=detect_delimiter(text))
    header = None
    for header in reader:
        if any(cell.strip() for cell in header):
            break
    mapping = _map_headers(header or [])
    missing = [f for f in REQUIRED_FIELDS if f not in mapping]
    if missing:
        raise PlaylistParseError(
            "CSV header is missing required column(s): " + ", ".join(missing)
            + f" (found: {', '.join(h.strip() for h in header or []) or 'nothing'})"
        )

    def rows():
        while True:
            try:
                cells = next(reader)
            except StopIteration:
                return
            except csv.Error as exc:
                yield reader.line_num, RowError(reader.line_num, f"unreadable CSV ({exc})")
                continue
            if not any(c.strip() for c in cells):
                continue  # blank line, not data
            raw = {}
            for field, (index, header_norm) in mapping.items():
                raw[field] = cells[index] if index < len(cells) else ""
                if field == "duration":
                    raw["_duration_header"] = header_norm
            yield reader.line_num, raw

    return _finish(rows(), name, "csv", lenient, "CSV contains no valid tracks")


def parse_json(text, name="Playlist", lenient=False):
    """Parse a JSON list of track objects, or ``{"name": ..., "tracks": [...]}``.

    Row numbers in errors are 1-based positions in the track list.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlaylistParseError(
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from None
    if isinstance(data, dict):
        name = str(data.get("name") or data.get("title") or name)
        data = data.get("tracks", data.get("items"))
    if not isinstance(data, list):
        raise PlaylistParseError(
            "JSON must be a list of tracks or an object with a 'tracks' list"
        )

    def rows():
        for number, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                yield number, RowError(number, f"expected a track object, got {type(item).__name__}")
                continue
            mapping = _map_headers(list(item.keys()))
            keys = list(item.keys())
            raw = {}
            for field, (index, header_norm) in mapping.items():
                value = item[keys[index]]
                if isinstance(value, list):  # e.g. "artists": ["A", "B"]
                    value = ", ".join(str(v) for v in value)
                raw[field] = "" if value is None else value
                if field == "duration":
                    raw["_duration_header"] = header_norm
            yield number, raw

    return _finish(rows(), name, "json", lenient, "JSON contains no valid tracks")


def parse_text(text, name="Playlist", lenient=False):
    """Parse the quick-paste format: ``Artist - Title | key | bpm | energy``.

    Blank lines and lines starting with ``#`` are ignored. Row numbers in
    errors are line numbers.
    """
    def rows():
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = [p.strip() for p in stripped.split("|")]
            if len(parts) != 4:
                yield number, RowError(
                    number,
                    f"expected 4 fields separated by '|' (Artist - Title | key | bpm | energy), got {len(parts)}",
                )
                continue
            who, key, bpm, energy = parts
            if " - " in who:
                artist, title = (s.strip() for s in who.split(" - ", 1))
            else:
                yield number, RowError(number, f"expected 'Artist - Title' but got {who!r}")
                continue
            yield number, {"title": title, "artist": artist, "key": key, "bpm": bpm, "energy": energy}

    if not text.strip():
        raise PlaylistParseError("text input is empty")
    return _finish(rows(), name, "text", lenient, "text input contains no valid tracks")


PARSERS = {"csv": parse_csv, "json": parse_json, "text": parse_text}


def detect_format(text, filename=None):
    """Guess the format from the file extension, falling back to the content."""
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".csv" or ext == ".tsv":
            return "csv"
        if ext == ".json":
            return "json"
        if ext == ".txt":
            return "text"
    stripped = text.lstrip("﻿").lstrip()
    if stripped.startswith(("[", "{")):
        return "json"
    lines = [l for l in stripped.splitlines() if l.strip() and not l.strip().startswith("#")]
    if lines and all(l.count("|") == 3 for l in lines[:5]):
        return "text"
    return "csv"


def parse(text, fmt="auto", filename=None, name=None, lenient=False):
    """Parse ``text`` in format ``fmt`` (csv, json, text or auto)."""
    if fmt == "auto":
        fmt = detect_format(text, filename)
    if fmt not in PARSERS:
        raise PlaylistParseError(f"unknown format {fmt!r} (use csv, json, text or auto)")
    if name is None:
        name = _name_from_filename(filename) if filename else "Playlist"
    return PARSERS[fmt](text, name=name, lenient=lenient)


def _name_from_filename(filename):
    base = os.path.splitext(os.path.basename(filename))[0]
    return re.sub(r"[-_]+", " ", base).strip().title() or "Playlist"


def load(path, fmt="auto", lenient=False):
    """Read and parse a playlist file."""
    with open(path, encoding="utf-8-sig") as handle:
        text = handle.read()
    return parse(text, fmt=fmt, filename=path, lenient=lenient)
