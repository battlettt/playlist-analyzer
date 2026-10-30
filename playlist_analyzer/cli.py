"""Command-line interface: ``python3 -m playlist_analyzer``."""

import argparse
import sys

from . import __version__
from .analysis import analyze
from .keys import KeyParseError, all_keys, classify_keys, compatible_keys, parse_key
from .parsers import PlaylistParseError, load, parse
from .reports import RENDERERS, render_json

COMMANDS = ("analyze", "reorder", "key")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python3 -m playlist_analyzer",
        description="Analyse the keys, tempos, energy curve and harmonic flow of an exported playlist.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    def add_input(p):
        p.add_argument("file", help="playlist file (.csv, .json, .txt) or '-' for stdin")
        p.add_argument("-f", "--format", default="auto", choices=["auto", "csv", "json", "text"],
                       help="input format (default: guess from extension/content)")
        p.add_argument("--name", help="playlist name to show in reports")
        p.add_argument("--lenient", action="store_true",
                       help="skip invalid rows (each one is listed as a warning) instead of failing")

    a = sub.add_parser("analyze", help="full analysis report (default command)")
    add_input(a)
    a.add_argument("-r", "--report", default="text", choices=sorted(RENDERERS),
                   help="report type: text, json or html (default: text)")
    a.add_argument("-o", "--output", help="write the report to this file instead of stdout")
    a.add_argument("--no-reorder", action="store_true", help="skip the suggested-order step")

    r = sub.add_parser("reorder", help="print only the suggested track order")
    add_input(r)
    r.add_argument("--json", action="store_true", help="output JSON")

    k = sub.add_parser("key", help="explain a key: Camelot code and safe moves")
    k.add_argument("key", nargs="+", help="a key such as 8A, 'A minor', Am, C; give two keys to classify a move")
    return parser


def _read(args):
    if args.file == "-":
        return parse(sys.stdin.read(), fmt=args.format, name=args.name or "Playlist", lenient=args.lenient)
    playlist = load(args.file, fmt=args.format, lenient=args.lenient)
    if args.name:
        playlist.name = args.name
    return playlist


def _cmd_analyze(args):
    playlist = _read(args)
    result = analyze(playlist, reorder=not args.no_reorder)
    report = RENDERERS[args.report](result)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(report)
        print(f"wrote {args.report} report to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(report)
    return 0


def _cmd_reorder(args):
    playlist = _read(args)
    so = analyze(playlist)["suggested_order"]
    if args.json:
        sys.stdout.write(render_json(so))
        return 0
    print(f"Flow score: {so['flow_before']} -> {so['flow_after']} ({so['improvement']:+d})")
    if so["kept_original"]:
        print("The current order already scores best; no change suggested.")
    for t in so["tracks"]:
        print(f"{t['new_position']:>3}. {t['artist']} - {t['title']}  "
              f"[{t['key']}, {t['bpm']:g} BPM, energy {t['energy']:g}]  (was #{t['original_position']})")
    return 0


def _cmd_key(args):
    if len(args.key) == 2 and all(_looks_like_single_key(k) for k in args.key):
        a, b = parse_key(args.key[0]), parse_key(args.key[1])
        category, rule = classify_keys(a, b)
        print(f"{a.code} ({a.name}) -> {b.code} ({b.name}): {category.replace('_', ' ')} ({rule})")
        return 0
    key = parse_key(" ".join(args.key))
    print(f"{' '.join(args.key)} = {key.code} ({key.name})")
    print("Compatible: " + ", ".join(f"{k.code} {k.name}" for k in compatible_keys(key)))
    print(f"Energy boost (+2): {key.shifted(2).code} {key.shifted(2).name}")
    print(f"Energy drop (-2):  {key.shifted(-2).code} {key.shifted(-2).name}")
    clashes = [k.code for k in all_keys() if classify_keys(key, k)[0] == "clash"]
    print(f"Clashes ({len(clashes)}): " + ", ".join(clashes))
    return 0


def _looks_like_single_key(text):
    try:
        parse_key(text)
        return True
    except KeyParseError:
        return False


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Allow the short form `python3 -m playlist_analyzer FILE [options]`.
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        argv.insert(0, "analyze")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    handler = {"analyze": _cmd_analyze, "reorder": _cmd_reorder, "key": _cmd_key}[args.command]
    try:
        return handler(args)
    except PlaylistParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
