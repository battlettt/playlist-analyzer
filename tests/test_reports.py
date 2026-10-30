import json
import re
import unittest
import xml.dom.minidom

from playlist_analyzer.analysis import analyze
from playlist_analyzer.parsers import load, parse_csv
from playlist_analyzer.reports import render_html, render_json, render_text, stylesheet
from tests.helpers import example


def result_for(name):
    return analyze(load(example(name)))


class JsonReportTest(unittest.TestCase):
    def test_round_trips_and_has_every_section(self):
        r = result_for("mixed-bag.json")
        data = json.loads(render_json(r))
        for key in ("playlist", "tracks", "keys", "tempo", "energy", "transitions",
                    "transition_summary", "flow_score", "suggested_order"):
            self.assertIn(key, data)
        self.assertEqual(data, json.loads(json.dumps(r)))
        self.assertEqual(data["flow_score"], r["flow_score"])
        self.assertEqual(len(data["transitions"]), 13)


class TextReportTest(unittest.TestCase):
    def test_sections_and_values(self):
        r = result_for("mixed-bag.json")
        text = render_text(r)
        for heading in ("PLAYLIST ANALYSIS: Mixed Bag", "KEYS", "TEMPO (BPM)", "ENERGY CURVE",
                        "TRANSITIONS", "SUGGESTED ORDER"):
            self.assertIn(heading, text)
        self.assertIn(f"Flow score: {r['flow_score']}/100", text)
        self.assertIn("Clash", text)
        self.assertIn("[HARD JUMP]", text)
        self.assertIn("[TRICKY]", text)
        so = r["suggested_order"]
        self.assertIn(f"Flow score {so['flow_before']} -> {so['flow_after']}", text)

    def test_kept_original_message_and_warnings(self):
        p = parse_csv("title,artist,key,bpm,energy\nA,B,8A,100,4\nC,D,9A,102,5\nE,F,9B,104,6\nG,H,8A,x,6\n",
                      name="Tiny", lenient=True)
        text = render_text(analyze(p))
        self.assertIn("already scores best", text)
        self.assertIn("! skipped row 5: bpm 'x' is not a number", text)


class HtmlReportTest(unittest.TestCase):
    def setUp(self):
        self.result = result_for("mixed-bag.json")
        self.html = render_html(self.result)

    def test_is_a_complete_document(self):
        self.assertTrue(self.html.startswith("<!DOCTYPE html>"))
        self.assertIn("<title>Mixed Bag - playlist analysis</title>", self.html)
        self.assertIn(stylesheet().strip()[:200], self.html)

    def test_self_contained(self):
        self.assertNotRegex(self.html, r"(?i)(src|href)\s*=")
        self.assertNotIn("<script", self.html)
        self.assertNotIn("<link", self.html)
        self.assertNotRegex(self.html, r"https?://")
        self.assertNotIn("@import", self.html)

    def test_contains_all_charts_and_tables(self):
        svgs = re.findall(r"<svg.*?</svg>", self.html, re.S)
        self.assertEqual(len(svgs), 4)  # key wheel, tempo, energy, energy after reorder
        for svg in svgs:
            xml.dom.minidom.parseString(svg)  # well-formed
        self.assertIn("Camelot wheel", self.html)
        self.assertIn("Tempo histogram", self.html)
        self.assertIn("Energy per track", self.html)
        self.assertEqual(self.html.count('<path class="pa-wheel-seg'), 24)
        self.assertIn('id="pa-trans"', self.html)
        self.assertEqual(self.html.count('<td class="pa-num pa-muted">'), 13 + 14)  # transition rows + "was" column

    def test_badges_carry_text_not_just_colour(self):
        self.assertIn('<span class="pa-badge critical"><span aria-hidden="true">✕</span>Clash</span>', self.html)
        self.assertIn("Hard jump</span>", self.html)
        self.assertIn("Tricky</span>", self.html)
        self.assertIn("Energy boost</span>", self.html)

    def test_escapes_user_data(self):
        p = parse_csv('title,artist,key,bpm,energy\n<script>alert(1)</script>,"A & B",8A,120,5\nOK,"<b>x</b>",9A,121,6\n')
        html = render_html(analyze(p))
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("A &amp; B", html)
        self.assertNotIn("<b>x</b>", html)

    def test_kept_original_and_single_track(self):
        html = render_html(result_for("sunset-drive.csv"))
        self.assertIn("No reordering suggested", html)
        single = parse_csv("title,artist,key,bpm,energy\nOnly,One,8A,120,5\n")
        html = render_html(analyze(single))
        self.assertIn("Flow score", html)
        for svg in re.findall(r"<svg.*?</svg>", html, re.S):
            xml.dom.minidom.parseString(svg)


if __name__ == "__main__":
    unittest.main()
