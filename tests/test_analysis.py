import unittest

from playlist_analyzer.analysis import (
    analyze, analyze_transition, classify_shape, energy_curve, flow_score, key_distribution,
    round_half_up, tempo_bucket, tempo_flag, tempo_histogram, transition_score, transitions,
)
from playlist_analyzer.parsers import load
from tests.helpers import example, track, tracks


class KeyDistributionTest(unittest.TestCase):
    def test_counts_percentages_and_mode_split(self):
        d = key_distribution(tracks(("8A", 120, 5), ("8A", 120, 5), ("9A", 120, 5), ("8B", 120, 5)))
        self.assertEqual([(k["key"], k["count"], k["percent"]) for k in d["keys"]],
                         [("8A", 2, 50.0), ("8B", 1, 25.0), ("9A", 1, 25.0)])
        self.assertEqual(d["minor"], {"count": 3, "percent": 75.0})
        self.assertEqual(d["major"], {"count": 1, "percent": 25.0})
        self.assertEqual(d["most_common"]["key"], "8A")
        self.assertEqual(d["most_common"]["name"], "A minor")
        self.assertEqual(d["most_common"]["tied_with"], [])
        self.assertEqual(d["distinct"], 3)

    def test_spellings_of_the_same_key_are_merged(self):
        ts = [track(key=k) for k in ("8A", "Am", "A minor")]
        self.assertEqual(key_distribution(ts)["keys"][0]["count"], 3)

    def test_ties_in_wheel_order(self):
        d = key_distribution(tracks(("10B", 120, 5), ("2A", 120, 5)))
        self.assertEqual(d["most_common"]["key"], "2A")
        self.assertEqual(d["most_common"]["tied_with"], ["10B"])

    def test_empty(self):
        d = key_distribution([])
        self.assertIsNone(d["most_common"]["key"])
        self.assertEqual(d["major"]["percent"], 0.0)


class TempoTest(unittest.TestCase):
    def test_bucket_boundaries(self):
        cases = {60: "<90", 89.99: "<90", 90: "90-100", 99.9: "90-100", 100: "100-110",
                 110: "110-120", 119.5: "110-120", 120: "120-130", 129.99: "120-130", 130: "130+", 174: "130+"}
        for bpm, label in cases.items():
            self.assertEqual(tempo_bucket(bpm), label, bpm)

    def test_histogram_and_stats(self):
        h = tempo_histogram(tracks(("8A", 85, 5), ("8A", 95, 5), ("8A", 96, 5), ("8A", 128, 5), ("8A", 140, 5)))
        self.assertEqual([b["count"] for b in h["buckets"]], [1, 2, 0, 0, 1, 1])
        self.assertEqual([b["label"] for b in h["buckets"]], ["<90", "90-100", "100-110", "110-120", "120-130", "130+"])
        self.assertEqual(h["buckets"][1]["percent"], 40.0)
        self.assertEqual((h["min"], h["max"], h["mean"], h["median"]), (85, 140, 108.8, 96))

    def test_even_count_median(self):
        h = tempo_histogram(tracks(("8A", 100, 5), ("8A", 110, 5), ("8A", 120, 5), ("8A", 125, 5)))
        self.assertEqual(h["median"], 115)

    def test_tempo_flags(self):
        self.assertEqual(tempo_flag(0), "ok")
        self.assertEqual(tempo_flag(6), "ok")
        self.assertEqual(tempo_flag(-6), "ok")
        self.assertEqual(tempo_flag(6.5), "tricky")
        self.assertEqual(tempo_flag(10), "tricky")
        self.assertEqual(tempo_flag(-10.01), "hard")
        self.assertEqual(tempo_flag(32), "hard")


class EnergyCurveTest(unittest.TestCase):
    def test_shapes(self):
        self.assertEqual(classify_shape([5, 5, 6, 5, 6]), "flat")
        self.assertEqual(classify_shape([2, 3, 4, 6, 7, 9]), "rising")
        self.assertEqual(classify_shape([9, 8, 6, 5, 3, 2]), "falling")
        self.assertEqual(classify_shape([2, 5, 9, 5, 2]), "peak-and-valley")
        self.assertEqual(classify_shape([8, 2, 9, 1, 8]), "peak-and-valley")
        self.assertEqual(classify_shape([4]), "flat")

    def test_rising_tolerates_small_dips(self):
        self.assertEqual(classify_shape([2, 4, 3, 5, 7, 6, 9]), "rising")

    def test_peak_lowest_and_jumps(self):
        ts = tracks(("8A", 120, 3), ("8A", 120, 8), ("8A", 120, 6), ("8A", 120, 9), ("8A", 120, 2))
        c = energy_curve(ts)
        self.assertEqual([p["energy"] for p in c["points"]], [3, 8, 6, 9, 2])
        self.assertEqual(c["peak"]["position"], 4)
        self.assertEqual(c["lowest"]["position"], 5)
        self.assertEqual([(d["from_position"], d["change"]) for d in c["biggest_rises"]], [(1, 5), (3, 3)])
        self.assertEqual([(d["from_position"], d["change"]) for d in c["biggest_drops"]], [(4, -7), (2, -2)])
        self.assertEqual(c["mean"], 5.6)

    def test_first_occurrence_wins_ties(self):
        c = energy_curve(tracks(("8A", 120, 9), ("8A", 120, 2), ("8A", 120, 9), ("8A", 120, 2)))
        self.assertEqual((c["peak"]["position"], c["lowest"]["position"]), (1, 2))

    def test_descriptions(self):
        arc = tracks(("8A", 100, 2), ("8A", 100, 5), ("8A", 100, 9), ("8A", 100, 5))
        self.assertIn("climbs to a peak of 9 at track 3 of 4", energy_curve(arc)["description"])
        self.assertIn("builds from 2 to 9", energy_curve(tracks(("8A", 100, 2), ("8A", 100, 5), ("8A", 100, 9)))["description"])
        self.assertIn("stays level", energy_curve(tracks(("8A", 100, 5), ("8A", 100, 5)))["description"])


class TransitionTest(unittest.TestCase):
    def test_classification_and_tempo(self):
        t = analyze_transition(track("A", "8A", 120, 5), track("B", "10A", 128, 7), 1)
        self.assertEqual(t["category"], "energy_boost")
        self.assertEqual(t["bpm_delta"], 8)
        self.assertEqual(t["tempo_flag"], "tricky")
        self.assertEqual(t["energy_delta"], 2)
        self.assertEqual((t["from_key"], t["to_key"]), ("8A", "10A"))

    def test_every_category_appears(self):
        ts = tracks(("8A", 120, 5), ("9A", 121, 5), ("11A", 122, 6), ("9A", 123, 5), ("3B", 140, 5))
        self.assertEqual([t["category"] for t in transitions(ts)],
                         ["compatible", "energy_boost", "energy_drop", "clash"])
        self.assertEqual(transitions(ts)[-1]["tempo_flag"], "hard")

    def test_transition_score_formula(self):
        self.assertAlmostEqual(transition_score("compatible", 0, 0), 1.0)
        self.assertAlmostEqual(transition_score("energy_boost", 0, 0), 0.875)
        self.assertAlmostEqual(transition_score("clash", 0, 0), 0.5)
        self.assertAlmostEqual(transition_score("compatible", 8, 3), 0.5 + 0.15 + 0.1)
        self.assertAlmostEqual(transition_score("clash", 20, 6), 0.0)


class FlowScoreTest(unittest.TestCase):
    def test_perfect_and_terrible(self):
        self.assertEqual(flow_score(tracks(("8A", 120, 5), ("9A", 122, 6), ("9B", 124, 6))), 100)
        self.assertEqual(flow_score(tracks(("8A", 80, 1), ("3B", 140, 9), ("10A", 80, 1))), 0)

    def test_mean_of_pairs(self):
        # compatible+smooth (1.0) then clash with smooth tempo/energy (0.5) -> 75
        self.assertEqual(flow_score(tracks(("8A", 120, 5), ("9A", 120, 5), ("3B", 120, 5))), 75)

    def test_short_playlists(self):
        self.assertEqual(flow_score([]), 100)
        self.assertEqual(flow_score([track()]), 100)

    def test_round_half_up(self):
        self.assertEqual(round_half_up(62.5), 63)
        self.assertEqual(round_half_up(0.125, 2), 0.13)
        self.assertEqual(round_half_up(-2.5), -2)


class AnalyzeTest(unittest.TestCase):
    def test_sunset_drive_flows(self):
        r = analyze(load(example("sunset-drive.csv")))
        self.assertEqual(r["playlist"]["track_count"], 14)
        self.assertEqual(r["transition_summary"]["categories"]["clash"], 0)
        self.assertEqual(r["transition_summary"]["tempo_flags"]["hard"], 0)
        self.assertGreaterEqual(r["flow_score"], 90)
        self.assertEqual(r["energy"]["shape"], "peak-and-valley")
        self.assertIn("climbs to a peak", r["energy"]["description"])
        self.assertEqual(r["playlist"]["total_duration"], sum(
            int(m) * 60 + int(s) for m, s in (d.split(":") for d in
            "3:52 4:10 3:41 4:25 3:58 4:02 3:47 4:33 5:01 4:12 3:55 4:18 3:36 4:44".split())))

    def test_mixed_bag_has_problems(self):
        r = analyze(load(example("mixed-bag.json")))
        s = r["transition_summary"]
        self.assertGreaterEqual(s["categories"]["clash"], 5)
        self.assertGreaterEqual(s["tempo_flags"]["hard"], 5)
        self.assertGreaterEqual(s["tempo_flags"]["tricky"], 1)
        self.assertGreaterEqual(s["categories"]["energy_boost"], 1)
        self.assertLess(r["flow_score"], 50)
        self.assertIsNone(r["playlist"]["total_duration"])  # one track has no duration

    def test_without_reorder(self):
        self.assertNotIn("suggested_order", analyze(load(example("quick-paste.txt")), reorder=False))


if __name__ == "__main__":
    unittest.main()
