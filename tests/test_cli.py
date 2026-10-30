import json
import os
import subprocess
import sys
import tempfile
import unittest

from tests.helpers import ROOT, example


def run(*args, stdin=None):
    return subprocess.run([sys.executable, "-m", "playlist_analyzer", *args], cwd=ROOT,
                          input=stdin, capture_output=True, text=True, timeout=60)


class CliTest(unittest.TestCase):
    def test_short_form_defaults_to_text_analysis(self):
        proc = run(example("sunset-drive.csv"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PLAYLIST ANALYSIS: Sunset Drive", proc.stdout)

    def test_json_report(self):
        proc = run("analyze", example("mixed-bag.json"), "--report", "json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["playlist"]["name"], "Mixed Bag")

    def test_html_report_to_file(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "report.html")
            proc = run("analyze", example("mixed-bag.json"), "-r", "html", "-o", out)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out, encoding="utf-8") as handle:
                self.assertIn("<!DOCTYPE html>", handle.read())
            self.assertIn("wrote html report", proc.stderr)

    def test_stdin_with_format_and_name(self):
        proc = run("analyze", "-", "--format", "text", "--name", "Piped", "--no-reorder",
                   stdin="A - B | 8A | 120 | 5\nC - D | 9A | 122 | 6\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PLAYLIST ANALYSIS: Piped", proc.stdout)
        self.assertNotIn("SUGGESTED ORDER", proc.stdout)

    def test_reorder_command(self):
        proc = run("reorder", example("mixed-bag.json"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Flow score:", proc.stdout)
        self.assertEqual(proc.stdout.count("(was #"), 14)
        data = json.loads(run("reorder", example("mixed-bag.json"), "--json").stdout)
        self.assertEqual(sorted(data["order"]), list(range(1, 15)))

    def test_key_command(self):
        proc = run("key", "A", "minor")
        self.assertIn("= 8A (A minor)", proc.stdout)
        self.assertIn("Energy boost (+2): 10A", proc.stdout)
        proc = run("key", "8A", "3B")
        self.assertIn("clash", proc.stdout)

    def test_malformed_input_exits_2_with_row_details(self):
        proc = run("analyze", "-", "--format", "csv",
                   stdin="title,artist,key,bpm,energy\nA,B,8A,120,5\nC,D,Z,fast,5\n")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("row 3:", proc.stderr)
        self.assertIn("unrecognised key 'Z'", proc.stderr)

    def test_lenient_flag(self):
        proc = run("analyze", "-", "--format", "csv", "--lenient",
                   stdin="title,artist,key,bpm,energy\nA,B,8A,120,5\nC,D,Z,120,5\n")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("skipped row 3", proc.stdout)

    def test_missing_file_and_bad_key(self):
        self.assertEqual(run("analyze", "does-not-exist.csv").returncode, 1)
        proc = run("key", "H#")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unrecognised key", proc.stderr)

    def test_no_arguments_prints_help(self):
        proc = run()
        self.assertEqual(proc.returncode, 1)
        self.assertIn("usage:", proc.stdout)


if __name__ == "__main__":
    unittest.main()
