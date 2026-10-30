"""playlist-analyzer: keys, tempo, energy and harmonic flow of an exported playlist."""

from .analysis import analyze, flow_score
from .keys import CamelotKey, KeyParseError, classify_keys, parse_key
from .parsers import PlaylistParseError, load, parse
from .reorder import suggest_order
from .reports import render_html, render_json, render_text

__version__ = "1.0.0"

__all__ = [
    "analyze", "flow_score", "CamelotKey", "KeyParseError", "classify_keys",
    "parse_key", "PlaylistParseError", "load", "parse", "suggest_order",
    "render_html", "render_json", "render_text", "__version__",
]
