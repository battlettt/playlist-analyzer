import random
import unittest

from playlist_analyzer.analysis import flow_score
from playlist_analyzer.keys import all_keys
from playlist_analyzer.parsers import load
from playlist_analyzer.reorder import arc_deviation, best_order, suggest_order, target_arc
from tests.helpers import example, track, tracks


def random_playlist(rng, n):
    keys = [k.code for k in all_keys()]
    return [track(f"T{i}", rng.choice(keys), rng.randint(70, 150), rng.randint(0, 10)) for i in range(n)]


class ReorderTest(unittest.TestCase):
    def assertPermutation(self, order, n):
        self.assertEqual(len(order), n, "a track was dropped or duplicated")
        self.assertEqual(sorted(order), list(range(n)), "order is not a permutation")

    def test_never_drops_or_duplicates_on_samples(self):
        for name in ("sunset-drive.csv", "mixed-bag.json", "quick-paste.txt"):
            ts = load(example(name)).tracks
            so = suggest_order(ts)
            self.assertEqual(sorted(so["order"]), list(range(1, len(ts) + 1)), name)
            self.assertEqual(len(so["tracks"]), len(ts))
            labels = sorted((t["artist"], t["title"]) for t in so["tracks"])
            self.assertEqual(labels, sorted((t.artist, t.title) for t in ts))

    def test_never_drops_or_duplicates_random(self):
        rng = random.Random(1234)
        for n in list(range(0, 12)) + [25, 40]:
            ts = random_playlist(rng, n)
            self.assertPermutation(best_order(ts), n)

    def test_duplicate_tracks_are_both_kept(self):
        ts = [track("Same", "8A", 120, 5), track("Same", "8A", 120, 5), track("Other", "3B", 90, 2)]
        self.assertPermutation(best_order(ts), 3)

    def test_score_never_gets_worse(self):
        rng = random.Random(99)
        for _ in range(60):
            ts = random_playlist(rng, rng.randint(2, 16))
            so = suggest_order(ts)
            self.assertGreaterEqual(so["flow_after"], so["flow_before"])

    def test_improves_mixed_bag(self):
        ts = load(example("mixed-bag.json")).tracks
        so = suggest_order(ts)
        self.assertGreater(so["flow_after"], so["flow_before"])
        self.assertGreaterEqual(so["improvement"], 30)
        self.assertFalse(so["kept_original"])
        reordered = [ts[i - 1] for i in so["order"]]
        self.assertEqual(flow_score(reordered), so["flow_after"])
        self.assertEqual(len(so["transitions"]), len(ts) - 1)

    def test_keeps_an_already_good_order(self):
        so = suggest_order(load(example("sunset-drive.csv")).tracks)
        self.assertTrue(so["kept_original"])
        self.assertEqual(so["flow_after"], so["flow_before"])

    def test_fixes_an_obvious_clash(self):
        ts = tracks(("8A", 120, 3), ("3B", 120, 5), ("9A", 121, 4))
        so = suggest_order(ts)
        self.assertGreater(so["flow_after"], so["flow_before"])

    def test_tiny_playlists_unchanged(self):
        self.assertEqual(best_order([]), [])
        self.assertEqual(best_order([track()]), [0])
        self.assertEqual(best_order(tracks(("8A", 120, 5), ("3B", 90, 1))), [0, 1])

    def test_deterministic(self):
        ts = load(example("mixed-bag.json")).tracks
        self.assertEqual(best_order(ts), best_order(ts))

    def test_target_arc_peaks_late_and_lands_lower(self):
        ts = tracks(*[("8A", 120, e) for e in (2, 4, 6, 8, 10, 3, 5, 7, 9, 1, 6)])
        arc = target_arc(ts)
        peak = arc.index(max(arc))
        self.assertEqual(peak, 7)  # 70% of the way through 11 slots
        self.assertEqual(arc[0], 1)
        self.assertAlmostEqual(arc[-1], 1 + 0.6 * 9)
        self.assertEqual(arc_deviation(tracks(("8A", 1, 5), ("8A", 1, 5))), 0.0)


if __name__ == "__main__":
    unittest.main()
