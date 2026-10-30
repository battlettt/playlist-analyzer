"""The static demo in docs/ must stay in sync with the Python package."""

import json
import os
import re
import shutil
import subprocess
import unittest

from playlist_analyzer.analysis import analyze
from playlist_analyzer.parsers import load, parse
from playlist_analyzer.reports import render_html_body, stylesheet
from tests.helpers import ROOT, example

DOCS = os.path.join(ROOT, "docs")
NODE = shutil.which("node")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as handle:
        return handle.read()


def node(script):
    proc = subprocess.run([NODE, "-e", script], cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return proc.stdout


class DemoFilesTest(unittest.TestCase):
    def test_index_embeds_the_shared_stylesheet(self):
        self.assertIn(stylesheet().rstrip("\n"), read(DOCS, "index.html"))

    def test_examples_are_embedded_verbatim(self):
        app = read(DOCS, "app.js")
        for name in ("sunset-drive.csv", "mixed-bag.json"):
            m = re.search(r'// BEGIN EXAMPLE {0}\n\s*"{0}": String\.raw`(.*?)`'.format(re.escape(name)), app, re.S)
            self.assertIsNotNone(m, name)
            self.assertEqual(m.group(1), read(ROOT, "examples", name), f"{name} drifted: run tools/sync_demo.py")

    def test_no_external_assets_or_network_calls(self):
        index, app = read(DOCS, "index.html"), read(DOCS, "app.js")
        self.assertNotRegex(index + app, r"https?://")
        self.assertNotRegex(app, r"\b(fetch|XMLHttpRequest|WebSocket|EventSource|importScripts|sendBeacon)\s*\(")
        refs = re.findall(r'(?:src|href)="([^"]+)"', index)
        self.assertEqual(sorted(refs), ["#pa-input", "app.js", "theory.md"])
        for ref in refs:
            if not ref.startswith("#"):
                self.assertTrue(os.path.exists(os.path.join(DOCS, ref)), ref)

    def test_one_click_example_buttons_exist(self):
        index = read(DOCS, "index.html")
        self.assertIn('id="pa-example-sunset"', index)
        self.assertIn('id="pa-example-mixed"', index)


@unittest.skipUnless(NODE, "node is not installed; JavaScript parity checks skipped")
class DemoParityTest(unittest.TestCase):
    """Run docs/app.js under Node and compare with the Python implementation."""

    def js_analyze(self, text, fmt="auto", name="Playlist", lenient=False):
        script = ("const PA=require('./docs/app.js');"
                  f"const r=PA.analyze(PA.parse({json.dumps(text)},{json.dumps(fmt)},{json.dumps(name)},{json.dumps(lenient)}));"
                  "process.stdout.write(JSON.stringify({result:r, body:PA.renderBody(r)}));")
        return json.loads(node(script))

    def test_examples_match_python_exactly(self):
        for name, title in (("sunset-drive.csv", "Sunset Drive"), ("mixed-bag.json", "Mixed Bag"),
                            ("quick-paste.txt", "Quick Paste")):
            py = analyze(load(example(name)))
            js = self.js_analyze(read(ROOT, "examples", name), name=title)
            # json round-trip normalises 120.0 vs 120
            self.assertEqual(json.loads(json.dumps(py)), js["result"], name)
            body = render_html_body(py)
            self.assertEqual(body[:body.index("<footer")], js["body"], name)

    def test_messy_input_matches(self):
        text = ('﻿Track Name;Artist;Initial Key;Tempo;Energy;Length\r\n'
                '"Semi; colon";"A ""B""";E flat minor;98,5;0.4;3:21\r\n'
                'Two;C;A MINOR;104;0.9;\r\n'
                'Three;D;8A;111;0.35;201\r\n')
        py = analyze(parse(text, name="Messy"))
        js = self.js_analyze(text, name="Messy")
        self.assertEqual(json.loads(json.dumps(py)), js["result"])

    def test_error_messages_match(self):
        text = "title,artist,key,bpm,energy\nA,B,8A,120,5\nC,D,Q,fast,\n,E,9A,500,5\n"
        try:
            parse(text)
        except Exception as exc:  # noqa: BLE001
            py_message = str(exc)
        js_message = node("const PA=require('./docs/app.js');"
                          f"try{{PA.parse({json.dumps(text)})}}catch(e){{process.stdout.write(e.message)}}")
        self.assertEqual(py_message, js_message)

    def test_reorder_matches_on_random_playlists(self):
        import random
        rng = random.Random(7)
        keys = ["8A", "Am", "C", "F#m", "3B", "12A", "1A", "6B", "Bbm", "E", "10A", "5A"]
        for _ in range(8):
            rows = [f"T{i},A{i},{rng.choice(keys)},{rng.randint(80, 140)},{rng.randint(1, 10)}"
                    for i in range(rng.randint(3, 14))]
            text = "title,artist,key,bpm,energy\n" + "\n".join(rows) + "\n"
            py = analyze(parse(text))["suggested_order"]
            js = self.js_analyze(text)["result"]["suggested_order"]
            self.assertEqual(py["order"], js["order"])
            self.assertEqual(py["flow_after"], js["flow_after"])

    def test_page_script_runs_against_a_minimal_dom(self):
        # A tiny stand-in DOM: enough to check the buttons are wired and the
        # one-click example renders a report without throwing.
        script = r"""
        const listeners = {}; const els = {};
        function el(id) {
          return els[id] || (els[id] = { id, value: "", checked: false, disabled: false, innerHTML: "",
            textContent: "", className: "", files: [],
            addEventListener(type, fn) { listeners[id + ":" + type] = fn; },
            scrollIntoView() {}, focus() {} });
        }
        el("pa-format").value = "auto";
        global.document = { readyState: "complete", getElementById: el, addEventListener() {} };
        global.window = { matchMedia: () => ({ matches: true }) };
        require("./docs/app.js");
        listeners["pa-example-mixed:click"]();
        const mixed = { status: els["pa-status"].textContent, html: els["pa-output"].innerHTML };
        el("pa-input").value = "title,artist,key,bpm,energy\nA,B,ZZ,120,5\n";
        listeners["pa-analyze:click"]();
        process.stdout.write(JSON.stringify({ mixed, error: els["pa-status"].textContent,
          errorClass: els["pa-status"].className, cleared: els["pa-output"].innerHTML }));
        """
        out = json.loads(node(script))
        self.assertIn("Analysed 14 tracks from JSON", out["mixed"]["status"])
        self.assertIn('<h1 class="pa-title">Mixed Bag</h1>', out["mixed"]["html"])
        self.assertIn("row 2: unrecognised key 'ZZ'", out["error"])
        self.assertIn("error", out["errorClass"])
        self.assertEqual(out["cleared"], "")


if __name__ == "__main__":
    unittest.main()
