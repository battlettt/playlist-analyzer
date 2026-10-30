"""Copy the shared stylesheet and example playlists into the static demo.

The demo in docs/ must work from file:// with no fetch() calls, so it carries
its own copies. Run this after editing playlist_analyzer/style.css,
docs/index.template.html or anything in examples/:

    python3 tools/sync_demo.py

tests/test_demo.py fails if the copies drift.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = ("sunset-drive.csv", "mixed-bag.json")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


def build_index():
    template = read("docs", "index.template.html")
    return template.replace("@@STYLE@@", read("playlist_analyzer", "style.css").rstrip("\n"))


def embed_examples(app_js):
    for name in EXAMPLES:
        content = read("examples", name)
        if "`" in content or "${" in content:
            raise SystemExit(f"{name} contains characters that cannot go in a JS template literal")
        pattern = re.compile(
            r'(// BEGIN EXAMPLE {0}\n\s*"{0}": String\.raw`).*?(`,?\n\s*// END EXAMPLE {0})'.format(re.escape(name)),
            re.S,
        )
        app_js, count = pattern.subn(lambda m: m.group(1) + content + m.group(2), app_js)
        if count != 1:
            raise SystemExit(f"could not find the embed markers for {name} in docs/app.js")
    return app_js


def main():
    index = build_index()
    app = embed_examples(read("docs", "app.js"))
    with open(os.path.join(ROOT, "docs", "index.html"), "w", encoding="utf-8") as handle:
        handle.write(index)
    with open(os.path.join(ROOT, "docs", "app.js"), "w", encoding="utf-8") as handle:
        handle.write(app)
    print("docs/index.html and docs/app.js are in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
