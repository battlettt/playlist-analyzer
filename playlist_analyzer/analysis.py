"""Playlist analysis: keys, tempo, energy, transitions and flow score.

Everything returns plain dicts/lists so the result can be dumped to JSON
directly and rendered by any of the report generators.
"""

import math
import statistics

from .keys import (
    CLASH, COMPATIBLE, ENERGY_BOOST, ENERGY_DROP, all_keys, classify_keys,
)

# --- tempo -----------------------------------------------------------------

TEMPO_BUCKETS = [
    ("<90", None, 90),
    ("90-100", 90, 100),
    ("100-110", 100, 110),
    ("110-120", 110, 120),
    ("120-130", 120, 130),
    ("130+", 130, None),
]

# A BPM gap above SMOOTH is tricky to beatmatch; above HARD it is a hard jump.
TEMPO_SMOOTH_MAX = 6.0
TEMPO_HARD_MIN = 10.0

# --- energy ----------------------------------------------------------------

FLAT_RANGE = 2.0       # energy range (0-10 scale) below which a curve is "flat"
TREND_CORRELATION = 0.6  # |Pearson r| needed to call a curve rising/falling
ENERGY_SMOOTH_MAX = 2.0
ENERGY_ROUGH_MAX = 4.0

# --- flow score weights -----------------------------------------------------

KEY_POINTS = {COMPATIBLE: 1.0, ENERGY_BOOST: 0.75, ENERGY_DROP: 0.75, CLASH: 0.0}
WEIGHT_KEY, WEIGHT_TEMPO, WEIGHT_ENERGY = 0.5, 0.3, 0.2


def round_half_up(value, digits=0):
    """Round halves away from zero for positives (2.5 -> 3), matching JavaScript's
    Math.round so the browser demo and the CLI print identical numbers."""
    scale = 10 ** digits
    result = math.floor(value * scale + 0.5) / scale
    return int(result) if digits == 0 else result


def key_distribution(tracks):
    """Counts and percentages per key, major/minor split and most common key(s)."""
    total = len(tracks)
    counts = {}
    for t in tracks:
        counts[t.key] = counts.get(t.key, 0) + 1
    order = {k: i for i, k in enumerate(all_keys())}
    keys = sorted(counts, key=lambda k: order[k])
    rows = [
        {
            "key": k.code,
            "name": k.name,
            "mode": k.mode,
            "count": counts[k],
            "percent": _pct(counts[k], total),
        }
        for k in keys
    ]
    minor = sum(c for k, c in counts.items() if k.is_minor)
    major = total - minor
    top = max(counts.values()) if counts else 0
    most_common = [k for k in keys if counts[k] == top]
    return {
        "total": total,
        "distinct": len(keys),
        "keys": rows,
        "major": {"count": major, "percent": _pct(major, total)},
        "minor": {"count": minor, "percent": _pct(minor, total)},
        "most_common": {
            "key": most_common[0].code if most_common else None,
            "name": most_common[0].name if most_common else None,
            "count": top,
            "tied_with": [k.code for k in most_common[1:]],
        },
    }


def tempo_bucket(bpm):
    """Label of the histogram bucket a BPM falls in. Lower bounds are inclusive."""
    for label, low, high in TEMPO_BUCKETS:
        if (low is None or bpm >= low) and (high is None or bpm < high):
            return label
    raise AssertionError("buckets cover every BPM")


def tempo_histogram(tracks):
    """BPM histogram plus min, max, mean and median."""
    bpms = [t.bpm for t in tracks]
    counts = {label: 0 for label, _, _ in TEMPO_BUCKETS}
    for b in bpms:
        counts[tempo_bucket(b)] += 1
    total = len(bpms)
    return {
        "buckets": [
            {"label": label, "count": counts[label], "percent": _pct(counts[label], total)}
            for label, _, _ in TEMPO_BUCKETS
        ],
        "min": min(bpms) if bpms else None,
        "max": max(bpms) if bpms else None,
        "mean": round_half_up(sum(bpms) / len(bpms), 2) if bpms else None,
        "median": round_half_up(statistics.median(bpms), 2) if bpms else None,
    }


def classify_shape(energies):
    """Name the overall shape of an energy curve.

    * ``flat``            - max minus min is under 2 points (0-10 scale)
    * ``rising``          - Pearson correlation of energy with position >= 0.6
    * ``falling``         - correlation <= -0.6
    * ``peak-and-valley`` - anything else: it moves a lot but not one way
    """
    if len(energies) < 2 or max(energies) - min(energies) < FLAT_RANGE:
        return "flat"
    r = _correlation(list(range(len(energies))), energies)
    if r >= TREND_CORRELATION:
        return "rising"
    if r <= -TREND_CORRELATION:
        return "falling"
    return "peak-and-valley"


def describe_shape(shape, energies, peak):
    """One plain-English sentence about the curve."""
    if not energies:
        return "No tracks, so no energy curve."
    n = len(energies)
    if shape == "flat":
        return f"Energy stays level (between {min(energies):g} and {max(energies):g}) the whole way through."
    if shape == "rising":
        return f"Energy builds from {energies[0]:g} to {energies[-1]:g} across the playlist."
    if shape == "falling":
        return f"Energy winds down from {energies[0]:g} to {energies[-1]:g} across the playlist."
    where = peak + 1
    if 0.25 * n <= peak < 0.85 * n and energies[0] < energies[peak] and energies[-1] < energies[peak]:
        return f"An arc: energy climbs to a peak of {energies[peak]:g} at track {where} of {n}, then eases off."
    return "Energy swings up and down rather than following one direction."


def energy_curve(tracks, jumps=3):
    """Per-track energy in order, shape summary, extremes and biggest jumps."""
    energies = [t.energy for t in tracks]
    points = [
        {"position": i + 1, "title": t.title, "artist": t.artist, "energy": t.energy}
        for i, t in enumerate(tracks)
    ]
    deltas = []
    for i in range(1, len(tracks)):
        deltas.append({
            "from_position": i,
            "to_position": i + 1,
            "from": tracks[i - 1].label,
            "to": tracks[i].label,
            "change": round_half_up(energies[i] - energies[i - 1], 2),
        })
    ups = sorted((d for d in deltas if d["change"] > 0), key=lambda d: (-d["change"], d["from_position"]))
    downs = sorted((d for d in deltas if d["change"] < 0), key=lambda d: (d["change"], d["from_position"]))
    peak = max(range(len(tracks)), key=lambda i: (energies[i], -i)) if tracks else None
    low = min(range(len(tracks)), key=lambda i: (energies[i], i)) if tracks else None
    shape = classify_shape(energies) if tracks else "flat"
    return {
        "points": points,
        "shape": shape,
        "description": describe_shape(shape, energies, peak),
        "mean": round_half_up(sum(energies) / len(energies), 2) if energies else None,
        "peak": _extreme(tracks, peak),
        "lowest": _extreme(tracks, low),
        "biggest_rises": ups[:jumps],
        "biggest_drops": downs[:jumps],
    }


def tempo_flag(delta):
    """``ok`` (<= 6 BPM), ``tricky`` (> 6 and <= 10) or ``hard`` (> 10)."""
    gap = abs(delta)
    if gap > TEMPO_HARD_MIN:
        return "hard"
    if gap > TEMPO_SMOOTH_MAX:
        return "tricky"
    return "ok"


def transition_score(category, bpm_delta, energy_delta):
    """Score one transition 0-1. See :func:`flow_score` for the formula."""
    key_points = KEY_POINTS[category]
    tempo_points = {"ok": 1.0, "tricky": 0.5, "hard": 0.0}[tempo_flag(bpm_delta)]
    gap = abs(energy_delta)
    energy_points = 1.0 if gap <= ENERGY_SMOOTH_MAX else 0.5 if gap <= ENERGY_ROUGH_MAX else 0.0
    return WEIGHT_KEY * key_points + WEIGHT_TEMPO * tempo_points + WEIGHT_ENERGY * energy_points


def analyze_transition(a, b, position):
    """Full description of the move from track ``a`` to track ``b``."""
    category, rule = classify_keys(a.key, b.key)
    bpm_delta = round_half_up(b.bpm - a.bpm, 2)
    energy_delta = round_half_up(b.energy - a.energy, 2)
    return {
        "position": position,
        "from": a.label,
        "to": b.label,
        "from_key": a.key.code,
        "to_key": b.key.code,
        "category": category,
        "rule": rule,
        "bpm_from": a.bpm,
        "bpm_to": b.bpm,
        "bpm_delta": bpm_delta,
        "tempo_flag": tempo_flag(bpm_delta),
        "energy_delta": energy_delta,
        "score": round_half_up(transition_score(category, bpm_delta, energy_delta), 3),
    }


def transitions(tracks):
    return [analyze_transition(tracks[i], tracks[i + 1], i + 1) for i in range(len(tracks) - 1)]


def flow_score(tracks):
    """Playlist flow score, 0-100.

    For each consecutive pair::

        pair = 0.5 * key + 0.3 * tempo + 0.2 * energy

        key    = 1.0 compatible, 0.75 energy boost/drop, 0.0 clash
        tempo  = 1.0 if |BPM gap| <= 6, 0.5 if <= 10, 0.0 above 10
        energy = 1.0 if |energy change| <= 2, 0.5 if <= 4, 0.0 above 4

    flow = round(100 * mean(pair scores)), halves rounded up. A playlist
    with fewer than two tracks has no transitions and scores 100.
    """
    if len(tracks) < 2:
        return 100
    scores = [
        transition_score(classify_keys(a.key, b.key)[0], b.bpm - a.bpm, b.energy - a.energy)
        for a, b in zip(tracks, tracks[1:])
    ]
    return round_half_up(100 * sum(scores) / len(scores))


def transition_summary(items):
    counts = {COMPATIBLE: 0, ENERGY_BOOST: 0, ENERGY_DROP: 0, CLASH: 0}
    tempo = {"ok": 0, "tricky": 0, "hard": 0}
    for t in items:
        counts[t["category"]] += 1
        tempo[t["tempo_flag"]] += 1
    return {"categories": counts, "tempo_flags": tempo, "total": len(items)}


def analyze(playlist, reorder=True):
    """Run every analysis on a :class:`Playlist` and return one JSON-ready dict."""
    from .reorder import suggest_order  # local import: reorder depends on this module

    tracks = playlist.tracks
    items = transitions(tracks)
    result = {
        "playlist": {
            "name": playlist.name,
            "source_format": playlist.source_format,
            "track_count": len(tracks),
            "total_duration": _total_duration(tracks),
            "energy_scale": playlist.energy_scale,
            "warnings": list(playlist.warnings),
        },
        "tracks": [dict(t.to_dict(), position=i + 1) for i, t in enumerate(tracks)],
        "keys": key_distribution(tracks),
        "tempo": tempo_histogram(tracks),
        "energy": energy_curve(tracks),
        "transitions": items,
        "transition_summary": transition_summary(items),
        "flow_score": flow_score(tracks),
    }
    if reorder:
        result["suggested_order"] = suggest_order(tracks)
    return result


def _total_duration(tracks):
    if not tracks or any(t.duration is None for t in tracks):
        return None
    return round_half_up(sum(t.duration for t in tracks), 1)


def _extreme(tracks, index):
    if index is None:
        return None
    t = tracks[index]
    return {"position": index + 1, "title": t.title, "artist": t.artist, "energy": t.energy}


def _pct(part, total):
    return round_half_up(100.0 * part / total, 1) if total else 0.0


def _correlation(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return 0.0
    return sxy / (sxx * syy) ** 0.5
