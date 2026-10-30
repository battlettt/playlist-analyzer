import os

from playlist_analyzer.keys import parse_key
from playlist_analyzer.models import Track

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")


def example(name):
    return os.path.join(EXAMPLES, name)


def track(title="T", key="8A", bpm=120, energy=5, artist="A"):
    return Track(title=title, artist=artist, key=parse_key(key), bpm=float(bpm), energy=float(energy), key_raw=key)


def tracks(*specs):
    """specs: (key, bpm, energy) tuples -> numbered tracks."""
    return [track(f"Track {i + 1}", k, b, e) for i, (k, b, e) in enumerate(specs)]
