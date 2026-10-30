"""Musical key parsing and Camelot wheel logic.

Every key the analyzer understands is normalised to a Camelot code such as
``8A`` (A minor) or ``8B`` (C major). The Camelot wheel is the circle of
fifths relabelled with numbers 1-12 (one step = one fifth) and a letter:
``A`` for minor keys on the inner ring, ``B`` for major keys on the outer ring.
"""

import re
from dataclasses import dataclass

# Pitch classes: C=0, C#/Db=1, ... B=11.
_NOTE_BASE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Conventional display names, indexed by Camelot number 1..12.
MAJOR_NAMES = {
    1: "B major", 2: "F# major", 3: "Db major", 4: "Ab major",
    5: "Eb major", 6: "Bb major", 7: "F major", 8: "C major",
    9: "G major", 10: "D major", 11: "A major", 12: "E major",
}
MINOR_NAMES = {
    1: "Ab minor", 2: "Eb minor", 3: "Bb minor", 4: "F minor",
    5: "C minor", 6: "G minor", 7: "D minor", 8: "A minor",
    9: "E minor", 10: "B minor", 11: "F# minor", 12: "C# minor",
}

# Transition classes, from best to worst.
COMPATIBLE = "compatible"
ENERGY_BOOST = "energy_boost"
ENERGY_DROP = "energy_drop"
CLASH = "clash"

_CAMELOT_RE = re.compile(r"^0?(1[0-2]|[1-9])\s*([AaBb])$")
_MINOR_WORDS = ("m", "-", "min", "minor", "moll")
_MAJOR_WORDS = ("", "M", "maj", "major", "dur")


class KeyParseError(ValueError):
    """Raised when a key string cannot be understood."""


@dataclass(frozen=True, order=True)
class CamelotKey:
    """A position on the Camelot wheel: number 1-12 and letter A (minor) / B (major)."""

    number: int
    letter: str

    def __post_init__(self):
        if not 1 <= self.number <= 12:
            raise KeyParseError(f"Camelot number must be 1-12, got {self.number}")
        if self.letter not in ("A", "B"):
            raise KeyParseError(f"Camelot letter must be A or B, got {self.letter!r}")

    @property
    def code(self):
        return f"{self.number}{self.letter}"

    @property
    def is_minor(self):
        return self.letter == "A"

    @property
    def mode(self):
        return "minor" if self.is_minor else "major"

    @property
    def name(self):
        return (MINOR_NAMES if self.is_minor else MAJOR_NAMES)[self.number]

    def shifted(self, steps):
        """Move ``steps`` positions clockwise (negative = anticlockwise) on the wheel."""
        return CamelotKey((self.number - 1 + steps) % 12 + 1, self.letter)

    def swapped(self):
        """The relative major/minor: same number, other letter."""
        return CamelotKey(self.number, "B" if self.letter == "A" else "A")

    def __str__(self):
        return self.code


def from_pitch_class(pitch_class, minor):
    """Convert a pitch class (0=C .. 11=B) and mode into a Camelot key.

    Walking the circle of fifths means multiplying the pitch class by 7 (a
    fifth is 7 semitones) modulo 12. C major sits at 8B, so we offset by 7.
    A minor key has the same number as its relative major, which is three
    semitones above it (A minor -> C major).
    """
    major_pc = (pitch_class + 3) % 12 if minor else pitch_class % 12
    fifths = (major_pc * 7) % 12
    return CamelotKey((fifths + 7) % 12 + 1, "A" if minor else "B")


def parse_key(text):
    """Parse a key written in any common notation into a :class:`CamelotKey`.

    Accepted spellings include Camelot codes (``8A``, ``08a``, ``12B``),
    full names (``A minor``, ``C major``, ``F# Minor``, ``Bb major``),
    short names (``Am``, ``F#m``, ``Bbm``, ``Cmaj``, ``Amin``), bare roots
    (``C`` means C major), unicode accidentals (``B♭``), spelled-out
    accidentals (``E flat minor``, ``C sharp``) and any capitalisation of the
    mode words (``A MINOR``). A lone capital ``M`` suffix means major.
    """
    if text is None:
        raise KeyParseError("key is missing")
    raw = str(text).strip()
    if not raw:
        raise KeyParseError("key is empty")

    match = _CAMELOT_RE.match(raw)
    if match:
        return CamelotKey(int(match.group(1)), match.group(2).upper())

    bad = KeyParseError(f"unrecognised key {raw!r} (expected e.g. '8A', 'A minor', 'Am', 'C')")
    root = raw[0].upper()
    if root not in _NOTE_BASE:
        raise bad
    pitch_class = _NOTE_BASE[root]
    rest = raw[1:].strip()
    lowered = rest.lower()
    for words, shift in ((("#", "\u266f", "-sharp", "sharp"), 1), (("\u266d", "-flat", "flat", "b"), -1)):
        word = next((w for w in words if lowered.startswith(w)), None)
        if word:
            pitch_class += shift
            rest = rest[len(word):].strip()
            break
    # Mode: a lone capital "M" means major, a lone "m" minor; words are case-insensitive.
    if rest in ("m", "M"):
        minor = rest == "m"
    elif rest.lower() in _MINOR_WORDS:
        minor = True
    elif rest.lower() in _MAJOR_WORDS:
        minor = False
    else:
        raise bad
    return from_pitch_class(pitch_class % 12, minor)


def all_keys():
    """All 24 keys in wheel order: 1A, 1B, 2A, 2B, ... 12A, 12B."""
    return [CamelotKey(n, letter) for n in range(1, 13) for letter in ("A", "B")]


def wheel_distance(a, b):
    """Shortest number of steps around the wheel between two Camelot numbers (0-6)."""
    diff = abs(a.number - b.number) % 12
    return min(diff, 12 - diff)


def classify_keys(a, b):
    """Classify the harmonic move from key ``a`` to key ``b``.

    Rules (exactly these, nothing else):

    * ``compatible`` - same code (8A -> 8A); one step either way on the same
      ring (8A -> 7A or 9A); or same number with the letter swapped, i.e. the
      relative major/minor (8A -> 8B).
    * ``energy_boost`` - two steps clockwise on the same ring (8A -> 10A).
      This is a whole tone up and lifts the mood.
    * ``energy_drop`` - two steps anticlockwise on the same ring (8A -> 6A).
    * ``clash`` - anything else (e.g. 8A -> 3B, or 8A -> 9B diagonals).

    Returns ``(category, rule)`` where ``rule`` is a short human description.
    """
    if a == b:
        return COMPATIBLE, "same key"
    if a.letter == b.letter:
        if b == a.shifted(1):
            return COMPATIBLE, "+1 on the wheel (up a fifth)"
        if b == a.shifted(-1):
            return COMPATIBLE, "-1 on the wheel (down a fifth)"
        if b == a.shifted(2):
            return ENERGY_BOOST, "+2 on the wheel (up a whole tone)"
        if b == a.shifted(-2):
            return ENERGY_DROP, "-2 on the wheel (down a whole tone)"
    elif a.number == b.number:
        return COMPATIBLE, "relative major/minor (letter swap)"
    return CLASH, f"{wheel_distance(a, b)} steps apart" + (
        "" if a.letter == b.letter else " and a mode change"
    )


def compatible_keys(key):
    """Keys you can safely mix into from ``key`` (the 'compatible' set)."""
    return [key, key.shifted(-1), key.shifted(1), key.swapped()]
