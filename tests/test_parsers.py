import json
import os
import tempfile
import unittest

from playlist_analyzer.parsers import (
    PlaylistParseError, detect_delimiter, detect_format, load, normalise_energy,
    parse, parse_csv, parse_json, parse_text,
)
from tests.helpers import example, track

HEADER = "title,artist,key,bpm,energy\n"


class CsvParserTest(unittest.TestCase):
    def test_basic(self):
        p = parse_csv(HEADER + "Song,Band,8A,120,5\n")
        self.assertEqual(len(p), 1)
        t = p.tracks[0]
        self.assertEqual((t.title, t.artist, t.key.code, t.bpm, t.energy), ("Song", "Band", "8A", 120.0, 5.0))
        self.assertEqual(p.source_format, "csv")

    def test_extra_columns_and_any_order(self):
        text = "#,Energy,Comment,Artist,BPM,Title,Key,Rating\n1,7,great,Band,124,Song,Am,5\n"
        t = parse_csv(text).tracks[0]
        self.assertEqual((t.title, t.key.code, t.bpm, t.energy), ("Song", "8A", 124.0, 7.0))

    def test_header_aliases(self):
        text = "Track Name,Artist Name(s),Initial Key,Tempo,Energy Level,Length,Style\nSong,Band,C,99.5,3,3:30,House\n"
        t = parse_csv(text).tracks[0]
        self.assertEqual((t.title, t.artist, t.key.code, t.bpm, t.duration, t.genre),
                         ("Song", "Band", "8B", 99.5, 210.0, "House"))

    def test_quoted_fields_with_commas_and_quotes(self):
        text = HEADER + '"Hello, World","The ""Quoted"" Band",F# minor,110,6\n'
        t = parse_csv(text).tracks[0]
        self.assertEqual(t.title, "Hello, World")
        self.assertEqual(t.artist, 'The "Quoted" Band')

    def test_missing_optional_fields(self):
        text = "title,artist,key,bpm,energy,duration,genre\nSong,Band,8A,120,5,,\nTwo,Band,9A,121,5\n"
        p = parse_csv(text)
        self.assertIsNone(p.tracks[0].duration)
        self.assertIsNone(p.tracks[0].genre)
        self.assertIsNone(p.tracks[1].duration)

    def test_all_key_spellings_in_one_file(self):
        rows = ["8A", "A minor", "Am", "C major", "C", "1A"]
        text = HEADER + "".join(f"S{i},B,{k},120,5\n" for i, k in enumerate(rows))
        self.assertEqual([t.key.code for t in parse_csv(text).tracks], ["8A", "8A", "8A", "8B", "8B", "1A"])

    def test_bom_semicolons_crlf_and_blank_lines(self):
        text = "﻿title;artist;key;bpm;energy\r\n\r\nSong;Band;8A;120,5;5\r\n"
        t = parse_csv(text).tracks[0]
        self.assertEqual(t.bpm, 120.5)  # decimal comma

    def test_tab_delimited(self):
        self.assertEqual(detect_delimiter("a\tb\tc\n"), "\t")
        p = parse_csv("title\tartist\tkey\tbpm\tenergy\nSong\tBand\t8A\t120\t5\n")
        self.assertEqual(p.tracks[0].title, "Song")

    def test_duration_formats(self):
        text = ("title,artist,key,bpm,energy,duration\n"
                "A,B,8A,120,5,3:45\nC,D,8A,120,5,225\nE,F,8A,120,5,1:00:00\n")
        self.assertEqual([t.duration for t in parse_csv(text).tracks], [225.0, 225.0, 3600.0])
        ms = "title,artist,key,bpm,energy,duration_ms\nA,B,8A,120,5,225000\n"
        self.assertEqual(parse_csv(ms).tracks[0].duration, 225.0)

    def test_malformed_rows_report_row_number_and_reason(self):
        text = HEADER + "Good,Band,8A,120,5\nBadKey,Band,Q minor,120,5\nBadBpm,Band,8A,fast,5\n,Band,8A,120,5\n"
        with self.assertRaises(PlaylistParseError) as ctx:
            parse_csv(text)
        errors = ctx.exception.errors
        self.assertEqual([e.row for e in errors], [3, 4, 5])
        self.assertIn("unrecognised key 'Q minor'", errors[0].message)
        self.assertIn("bpm 'fast' is not a number", errors[1].message)
        self.assertIn("title is missing", errors[2].message)
        self.assertIn("row 3:", str(ctx.exception))
        self.assertIn("3 invalid row(s)", str(ctx.exception))

    def test_multiple_problems_in_one_row_are_all_reported(self):
        with self.assertRaises(PlaylistParseError) as ctx:
            parse_csv(HEADER + "Song,Band,,,\n")
        message = ctx.exception.errors[0].message
        for part in ("key is empty", "bpm is missing", "energy is missing"):
            self.assertIn(part, message)

    def test_out_of_range_values(self):
        with self.assertRaises(PlaylistParseError) as ctx:
            parse_csv(HEADER + "A,B,8A,500,5\nC,D,8A,120,-1\n")
        self.assertIn("bpm 500 is outside 20-300", ctx.exception.errors[0].message)
        self.assertIn("energy -1 is outside 0-100", ctx.exception.errors[1].message)

    def test_short_row_counts_as_missing_fields(self):
        with self.assertRaises(PlaylistParseError) as ctx:
            parse_csv(HEADER + "Song,Band,8A\n")
        self.assertIn("bpm is missing", ctx.exception.errors[0].message)

    def test_lenient_skips_but_reports(self):
        p = parse_csv(HEADER + "Good,Band,8A,120,5\nBad,Band,8A,abc,5\n", lenient=True)
        self.assertEqual(len(p), 1)
        self.assertEqual(p.warnings, ["skipped row 3: bpm 'abc' is not a number"])

    def test_lenient_with_no_valid_rows_still_fails(self):
        with self.assertRaisesRegex(PlaylistParseError, "no valid tracks"):
            parse_csv(HEADER + "Bad,Band,8A,abc,5\n", lenient=True)

    def test_missing_required_column(self):
        with self.assertRaisesRegex(PlaylistParseError, "missing required column\\(s\\): bpm, energy"):
            parse_csv("title,artist,key\nA,B,8A\n")

    def test_empty(self):
        with self.assertRaisesRegex(PlaylistParseError, "empty"):
            parse_csv("   \n")

    def test_sample_file(self):
        p = load(example("sunset-drive.csv"))
        self.assertEqual(len(p), 14)
        self.assertEqual(p.name, "Sunset Drive")
        self.assertEqual(p.tracks[5].artist, "Pocket Satellites, Ivo Brandt")
        self.assertEqual(p.warnings, [])


class JsonParserTest(unittest.TestCase):
    def test_list_of_tracks(self):
        data = [{"title": "A", "artist": "B", "key": "Am", "bpm": 120, "energy": 5}]
        p = parse_json(json.dumps(data))
        self.assertEqual(p.tracks[0].key.code, "8A")
        self.assertEqual(p.source_format, "json")

    def test_object_with_name_and_tracks(self):
        data = {"name": "My Mix", "tracks": [{"name": "A", "artists": ["X", "Y"], "key": "8B", "tempo": "121.5", "energy": 0.5}]}
        p = parse_json(json.dumps(data))
        self.assertEqual(p.name, "My Mix")
        t = p.tracks[0]
        self.assertEqual((t.title, t.artist, t.bpm), ("A", "X, Y", 121.5))

    def test_nulls_for_optional_fields(self):
        data = [{"title": "A", "artist": "B", "key": "8A", "bpm": 120, "energy": 5, "genre": None, "duration_ms": None}]
        t = parse_json(json.dumps(data)).tracks[0]
        self.assertIsNone(t.genre)
        self.assertIsNone(t.duration)

    def test_malformed_items(self):
        data = [{"title": "A", "artist": "B", "key": "8A", "bpm": 120, "energy": 5},
                "not a track",
                {"title": "C", "artist": "D", "key": "8A", "bpm": None, "energy": 5}]
        with self.assertRaises(PlaylistParseError) as ctx:
            parse_json(json.dumps(data))
        errors = ctx.exception.errors
        self.assertEqual([e.row for e in errors], [2, 3])
        self.assertIn("expected a track object, got str", errors[0].message)
        self.assertIn("bpm is missing", errors[1].message)

    def test_invalid_json_reports_position(self):
        with self.assertRaisesRegex(PlaylistParseError, "invalid JSON at line 2"):
            parse_json('[\n{"title": }]')

    def test_wrong_top_level_type(self):
        with self.assertRaisesRegex(PlaylistParseError, "list of tracks"):
            parse_json('{"foo": 1}')

    def test_sample_file(self):
        p = load(example("mixed-bag.json"))
        self.assertEqual(len(p), 14)
        self.assertEqual(p.name, "Mixed Bag")
        self.assertIsNone(p.tracks[4].duration)
        self.assertEqual(p.tracks[0].duration, 214.0)


class TextParserTest(unittest.TestCase):
    def test_basic_with_comments_and_blank_lines(self):
        text = "# my mix\n\nBand - Song | 8A | 120 | 5\nOther Band - Song - Remix | F#m | 98.5 | 7\n"
        p = parse_text(text)
        self.assertEqual(len(p), 2)
        self.assertEqual((p.tracks[1].artist, p.tracks[1].title), ("Other Band", "Song - Remix"))
        self.assertEqual(p.tracks[1].key.code, "11A")

    def test_wrong_field_count(self):
        with self.assertRaises(PlaylistParseError) as ctx:
            parse_text("Band - Song | 8A | 120\n")
        self.assertEqual(ctx.exception.errors[0].row, 1)
        self.assertIn("expected 4 fields", ctx.exception.errors[0].message)

    def test_missing_artist_separator(self):
        with self.assertRaises(PlaylistParseError) as ctx:
            parse_text("# header\nJust A Title | 8A | 120 | 5\n")
        self.assertEqual(ctx.exception.errors[0].row, 2)
        self.assertIn("expected 'Artist - Title'", ctx.exception.errors[0].message)

    def test_bad_values(self):
        with self.assertRaises(PlaylistParseError) as ctx:
            parse_text("A - B | Z | 120 | loud\n")
        self.assertIn("unrecognised key 'Z'", ctx.exception.errors[0].message)
        self.assertIn("energy 'loud' is not a number", ctx.exception.errors[0].message)

    def test_sample_file(self):
        self.assertEqual(len(load(example("quick-paste.txt"))), 6)


class FormatDetectionTest(unittest.TestCase):
    def test_by_extension(self):
        self.assertEqual(detect_format("", "a.csv"), "csv")
        self.assertEqual(detect_format("", "a.JSON"), "json")
        self.assertEqual(detect_format("", "a.txt"), "text")

    def test_by_content(self):
        self.assertEqual(detect_format('[{"title": 1}]'), "json")
        self.assertEqual(detect_format('  {"tracks": []}'), "json")
        self.assertEqual(detect_format("A - B | 8A | 120 | 5\n"), "text")
        self.assertEqual(detect_format(HEADER), "csv")

    def test_parse_dispatch_and_unknown(self):
        self.assertEqual(parse("A - B | 8A | 120 | 5").source_format, "text")
        with self.assertRaisesRegex(PlaylistParseError, "unknown format"):
            parse("x", fmt="xml")

    def test_load_from_file_name(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "late_night-set.csv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(HEADER + "A,B,8A,120,5\n")
            self.assertEqual(load(path).name, "Late Night Set")


class EnergyScaleTest(unittest.TestCase):
    def test_zero_to_one_is_scaled_up(self):
        p = parse_csv(HEADER + "A,B,8A,120,0.45\nC,D,8A,120,0.9\n")
        self.assertEqual([t.energy for t in p.tracks], [4.5, 9.0])
        self.assertEqual(p.energy_scale, "0-1")
        self.assertIn("rescaled", p.warnings[-1])

    def test_zero_to_hundred_is_scaled_down(self):
        p = parse_csv(HEADER + "A,B,8A,120,45\nC,D,8A,120,90\n")
        self.assertEqual([t.energy for t in p.tracks], [4.5, 9.0])
        self.assertEqual(p.energy_scale, "0-100")

    def test_zero_to_ten_unchanged(self):
        ts = [track(energy=3), track(energy=10)]
        self.assertEqual(normalise_energy(ts), "0-10")
        self.assertEqual([t.energy for t in ts], [3, 10])


if __name__ == "__main__":
    unittest.main()
