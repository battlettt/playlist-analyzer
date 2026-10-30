"""Suggest a better track order.

Algorithm (greedy walk over the Camelot wheel):

1. Build a target energy arc for the set: a warm-up that climbs to the
   playlist's highest energy about 70% of the way through, then eases off to
   60% of the range for the landing. The arc uses the playlist's own min/max
   energy, so it never asks for energy the tracks don't have.
2. From a starting track, repeatedly step to the unused track with the lowest
   cost::

       cost = (1 - pair score) + ARC_WEIGHT * |energy - target energy| / range

   where ``pair score`` is the same 0-1 transition score used by the flow
   score (key compatibility, BPM gap, energy change). Ties are broken by the
   original playlist position so results are deterministic.
3. Run step 2 from every possible starting track (or the lowest-energy
   starts for very long playlists) and keep the walk with the best
   ``flow score - ARC_WEIGHT * arc deviation``.
4. The original order is always a candidate and any walk whose flow score is
   lower than the original's is discarded, so the suggestion can never score
   worse than what you started with.

Every walk is a permutation of the input: each track is placed exactly once.
"""

from .analysis import energy_curve, flow_score, transition_score, transitions
from .keys import classify_keys

ARC_WEIGHT = 0.3
PEAK_AT = 0.7
LANDING = 0.6
MAX_STARTS = 24


def target_arc(tracks):
    """Target energy for each slot in a set of ``len(tracks)`` tracks."""
    n = len(tracks)
    if n == 0:
        return []
    low = min(t.energy for t in tracks)
    high = max(t.energy for t in tracks)
    targets = []
    for i in range(n):
        p = i / (n - 1) if n > 1 else 0.0
        if p <= PEAK_AT:
            shape = p / PEAK_AT
        else:
            shape = 1.0 - (1.0 - LANDING) * (p - PEAK_AT) / (1.0 - PEAK_AT)
        targets.append(low + shape * (high - low))
    return targets


def arc_deviation(tracks, targets=None):
    """Mean distance from the target arc, normalised by the energy range (0-1)."""
    if len(tracks) < 2:
        return 0.0
    targets = targets or target_arc(tracks)
    spread = max(t.energy for t in tracks) - min(t.energy for t in tracks)
    if spread == 0:
        return 0.0
    return sum(abs(t.energy - g) for t, g in zip(tracks, targets)) / (len(tracks) * spread)


def _pair_score(a, b):
    return transition_score(classify_keys(a.key, b.key)[0], b.bpm - a.bpm, b.energy - a.energy)


def greedy_walk(tracks, start, targets):
    """Greedy order starting at index ``start``. Returns a list of indexes."""
    spread = (max(t.energy for t in tracks) - min(t.energy for t in tracks)) or 1.0
    remaining = [i for i in range(len(tracks)) if i != start]
    order = [start]
    while remaining:
        current = tracks[order[-1]]
        slot = len(order)

        def cost(i):
            t = tracks[i]
            return (
                (1.0 - _pair_score(current, t))
                + ARC_WEIGHT * abs(t.energy - targets[slot]) / spread,
                i,
            )

        best = min(remaining, key=cost)
        order.append(best)
        remaining.remove(best)
    return order


def _objective(ordered, targets):
    return flow_score(ordered) - 100 * ARC_WEIGHT * arc_deviation(ordered, targets)


def best_order(tracks):
    """Return the chosen order as a list of indexes into ``tracks``."""
    n = len(tracks)
    original = list(range(n))
    if n < 3:
        return original
    targets = target_arc(tracks)
    starts = sorted(range(n), key=lambda i: (tracks[i].energy, i))[:MAX_STARTS]
    baseline_flow = flow_score(tracks)
    best, best_value = original, _objective(tracks, targets)
    for start in starts:
        order = greedy_walk(tracks, start, targets)
        ordered = [tracks[i] for i in order]
        if flow_score(ordered) < baseline_flow:
            continue
        value = _objective(ordered, targets)
        if value > best_value + 1e-9:
            best, best_value = order, value
    return best


def suggest_order(tracks):
    """Suggested order plus before/after flow scores, as a JSON-ready dict."""
    order = best_order(tracks)
    ordered = [tracks[i] for i in order]
    before, after = flow_score(tracks), flow_score(ordered)
    return {
        "order": [i + 1 for i in order],
        "tracks": [
            {
                "new_position": n + 1,
                "original_position": i + 1,
                "title": tracks[i].title,
                "artist": tracks[i].artist,
                "key": tracks[i].key.code,
                "bpm": tracks[i].bpm,
                "energy": tracks[i].energy,
            }
            for n, i in enumerate(order)
        ],
        "flow_before": before,
        "flow_after": after,
        "improvement": after - before,
        "kept_original": order == list(range(len(tracks))),
        "energy_shape_after": energy_curve(ordered)["shape"],
        "transitions": transitions(ordered),
        "method": "greedy Camelot walk with energy-arc target (see reorder.py)",
    }
