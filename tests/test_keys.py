import unittest

from playlist_analyzer.keys import (
    CLASH, COMPATIBLE, ENERGY_BOOST, ENERGY_DROP, CamelotKey, KeyParseError,
    all_keys, classify_keys, compatible_keys, from_pitch_class, parse_key, wheel_distance,
)


class ParseKeyTest(unittest.TestCase):
    def assertKey(self, text, code):
        self.assertEqual(parse_key(text).code, code, text)

    def test_camelot_codes(self):
        for text, code in [("8A", "8A"), ("8a", "8A"), ("08A", "8A"), ("12B", "12B"),
                           ("1A", "1A"), ("1b", "1B"), (" 5A ", "5A"), ("8 A", "8A")]:
            self.assertKey(text, code)

    def test_every_camelot_code_round_trips(self):
        for key in all_keys():
            self.assertEqual(parse_key(key.code), key)

    def test_full_names(self):
        for text, code in [("A minor", "8A"), ("C major", "8B"), ("F# minor", "11A"),
                           ("Bb major", "6B"), ("Eb minor", "2A"), ("A Minor", "8A"),
                           ("C MAJOR", "8B"), ("f# minor", "11A"), ("E  flat   minor", "2A")]:
            self.assertKey(text, code)

    def test_short_names(self):
        for text, code in [("Am", "8A"), ("am", "8A"), ("F#m", "11A"), ("Bbm", "3A"),
                           ("C#m", "12A"), ("G#m", "1A"), ("Abm", "1A"), ("Cmaj", "8B"),
                           ("Amin", "8A"), ("Ebmaj", "5B"), ("A-", "8A"), ("AM", "11B"), ("bm", "10A")]:
            self.assertKey(text, code)

    def test_bare_root_is_major(self):
        for text, code in [("C", "8B"), ("G", "9B"), ("D", "10B"), ("A", "11B"), ("E", "12B"),
                           ("B", "1B"), ("F#", "2B"), ("Db", "3B"), ("Ab", "4B"), ("Eb", "5B"),
                           ("Bb", "6B"), ("F", "7B")]:
            self.assertKey(text, code)

    def test_accidental_spellings(self):
        for text, code in [("B♭", "6B"), ("F♯ minor", "11A"), ("C sharp", "3B"),
                           ("f-sharp minor", "11A"), ("E flat", "5B"), ("Cb", "1B"), ("E#", "7B")]:
            self.assertKey(text, code)

    def test_enharmonic_equivalents_match(self):
        pairs = [("C#", "Db"), ("F#", "Gb"), ("G#m", "Abm"), ("D#m", "Ebm"), ("A#", "Bb")]
        for a, b in pairs:
            self.assertEqual(parse_key(a), parse_key(b), (a, b))

    def test_all_24_note_names_cover_the_wheel(self):
        roots = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
        codes = {parse_key(r + " major").code for r in roots} | {parse_key(r + " minor").code for r in roots}
        self.assertEqual(codes, {k.code for k in all_keys()})

    def test_relative_minor_shares_number(self):
        for major, minor in [("C", "Am"), ("G", "Em"), ("Eb", "Cm"), ("E", "C#m")]:
            self.assertEqual(parse_key(major).number, parse_key(minor).number)

    def test_names(self):
        self.assertEqual(parse_key("8A").name, "A minor")
        self.assertEqual(parse_key("8B").name, "C major")
        self.assertEqual(parse_key("Gb").name, "F# major")

    def test_invalid_keys(self):
        for bad in ["", "   ", None, "H minor", "13A", "0B", "8C", "A mixolydian", "?", "C##", "8AA"]:
            with self.assertRaises(KeyParseError, msg=repr(bad)):
                parse_key(bad)

    def test_error_message_mentions_input(self):
        with self.assertRaisesRegex(KeyParseError, "unrecognised key 'X minor'"):
            parse_key("X minor")

    def test_from_pitch_class(self):
        self.assertEqual(from_pitch_class(0, False).code, "8B")
        self.assertEqual(from_pitch_class(9, True).code, "8A")

    def test_camelot_key_validation(self):
        with self.assertRaises(KeyParseError):
            CamelotKey(13, "A")
        with self.assertRaises(KeyParseError):
            CamelotKey(1, "C")


class CamelotRulesTest(unittest.TestCase):
    def cls(self, a, b):
        return classify_keys(parse_key(a), parse_key(b))[0]

    def test_same_key_is_compatible(self):
        self.assertEqual(self.cls("8A", "8A"), COMPATIBLE)

    def test_plus_minus_one_same_letter(self):
        self.assertEqual(self.cls("8A", "9A"), COMPATIBLE)
        self.assertEqual(self.cls("8A", "7A"), COMPATIBLE)
        self.assertEqual(self.cls("8B", "9B"), COMPATIBLE)

    def test_wraps_around_the_wheel(self):
        self.assertEqual(self.cls("12A", "1A"), COMPATIBLE)
        self.assertEqual(self.cls("1B", "12B"), COMPATIBLE)
        self.assertEqual(self.cls("12A", "2A"), ENERGY_BOOST)
        self.assertEqual(self.cls("1A", "11A"), ENERGY_DROP)

    def test_letter_swap(self):
        self.assertEqual(self.cls("8A", "8B"), COMPATIBLE)
        self.assertEqual(self.cls("Am", "C"), COMPATIBLE)

    def test_energy_boost_and_drop(self):
        self.assertEqual(self.cls("8A", "10A"), ENERGY_BOOST)
        self.assertEqual(self.cls("8A", "6A"), ENERGY_DROP)
        self.assertEqual(self.cls("5B", "7B"), ENERGY_BOOST)

    def test_clashes(self):
        for a, b in [("8A", "9B"), ("8A", "7B"), ("8A", "11A"), ("8A", "2A"), ("8A", "3B"), ("8B", "10A")]:
            self.assertEqual(self.cls(a, b), CLASH, (a, b))

    def test_rule_descriptions(self):
        self.assertEqual(classify_keys(parse_key("8A"), parse_key("8B"))[1], "relative major/minor (letter swap)")
        self.assertIn("mode change", classify_keys(parse_key("8A"), parse_key("3B"))[1])

    def test_every_key_has_4_compatible_1_boost_1_drop_18_clashes(self):
        for key in all_keys():
            results = [classify_keys(key, other)[0] for other in all_keys()]
            self.assertEqual(results.count(COMPATIBLE), 4)
            self.assertEqual(results.count(ENERGY_BOOST), 1)
            self.assertEqual(results.count(ENERGY_DROP), 1)
            self.assertEqual(results.count(CLASH), 18)

    def test_compatible_keys_list(self):
        self.assertEqual([k.code for k in compatible_keys(parse_key("8A"))], ["8A", "7A", "9A", "8B"])

    def test_wheel_distance(self):
        self.assertEqual(wheel_distance(parse_key("1A"), parse_key("12A")), 1)
        self.assertEqual(wheel_distance(parse_key("1A"), parse_key("7B")), 6)


if __name__ == "__main__":
    unittest.main()
