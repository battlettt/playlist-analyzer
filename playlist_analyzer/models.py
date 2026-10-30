"""Core data types."""

from dataclasses import dataclass, field
from typing import List, Optional

from .keys import CamelotKey


@dataclass
class Track:
    """One track in a playlist, after validation and key normalisation."""

    title: str
    artist: str
    key: CamelotKey
    bpm: float
    energy: float  # always on a 0-10 scale after parsing
    key_raw: str = ""
    duration: Optional[float] = None  # seconds
    genre: Optional[str] = None

    @property
    def label(self):
        return f"{self.artist} - {self.title}" if self.artist else self.title

    def to_dict(self):
        return {
            "title": self.title,
            "artist": self.artist,
            "key": self.key.code,
            "key_name": self.key.name,
            "key_raw": self.key_raw,
            "bpm": self.bpm,
            "energy": self.energy,
            "duration": self.duration,
            "genre": self.genre,
        }


@dataclass
class Playlist:
    """A parsed playlist plus anything the parser had to tell the user."""

    tracks: List[Track]
    name: str = "Playlist"
    source_format: str = ""
    energy_scale: str = "0-10"
    warnings: List[str] = field(default_factory=list)

    def __len__(self):
        return len(self.tracks)
