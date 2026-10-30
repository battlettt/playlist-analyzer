"""Render one analysis result as text, JSON or a self-contained HTML page."""

import json
import math
import os
from html import escape

from .analysis import round_half_up
from .keys import CamelotKey

CATEGORY_LABELS = {
    "compatible": ("Compatible", "good", "✓"),
    "energy_boost": ("Energy boost", "info", "▲"),
    "energy_drop": ("Energy drop", "info", "▼"),
    "clash": ("Clash", "critical", "✕"),
}
TEMPO_LABELS = {
    "ok": ("Smooth", "good", "✓"),
    "tricky": ("Tricky", "warning", "!"),
    "hard": ("Hard jump", "critical", "✕"),
}

_STYLE_PATH = os.path.join(os.path.dirname(__file__), "style.css")


def stylesheet():
    with open(_STYLE_PATH, encoding="utf-8") as handle:
        return handle.read()


# --------------------------------------------------------------------- JSON

def render_json(result, indent=2):
    return json.dumps(result, indent=indent, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------- text

def _fmt(n):
    if n is None:
        return "-"
    return f"{n:g}" if isinstance(n, float) else str(n)


def _duration(seconds):
    if seconds is None:
        return None
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _bar(value, top, width=24):
    if top <= 0 or value <= 0:
        return ""
    return "█" * max(1, int(round(width * value / top)))


def _cut(text, width):
    return text if len(text) <= width else text[: width - 1] + "…"


def render_text(result):
    p = result["playlist"]
    keys, tempo, energy = result["keys"], result["tempo"], result["energy"]
    out = []
    add = out.append
    title = f"PLAYLIST ANALYSIS: {p['name']}"
    add(title)
    add("=" * len(title))
    meta = [f"{p['track_count']} tracks", f"from {p['source_format']}"]
    if p.get("total_duration"):
        meta.append(f"running time {_duration(p['total_duration'])}")
    add(" | ".join(meta))
    add(f"Flow score: {result['flow_score']}/100")
    if p["warnings"]:
        add("")
        add("Warnings:")
        for w in p["warnings"]:
            add(f"  ! {w}")

    add("")
    add("KEYS")
    add("----")
    mc = keys["most_common"]
    if mc["key"]:
        tie = f" (tied with {', '.join(mc['tied_with'])})" if mc["tied_with"] else ""
        add(f"Most common key: {mc['key']} ({mc['name']}), {mc['count']} track(s){tie}")
    add(f"Major {keys['major']['count']} ({keys['major']['percent']}%)  |  "
        f"Minor {keys['minor']['count']} ({keys['minor']['percent']}%)  |  "
        f"{keys['distinct']} distinct key(s)")
    top = max((k["count"] for k in keys["keys"]), default=0)
    for k in keys["keys"]:
        add(f"  {k['key']:>3}  {k['name']:<9} {_bar(k['count'], top, 20):<20} {k['count']:>2}  {k['percent']:>5}%")

    add("")
    add("TEMPO (BPM)")
    add("-----------")
    add(f"min {_fmt(tempo['min'])}  max {_fmt(tempo['max'])}  "
        f"mean {_fmt(tempo['mean'])}  median {_fmt(tempo['median'])}")
    top = max(b["count"] for b in tempo["buckets"])
    for b in tempo["buckets"]:
        add(f"  {b['label']:>8}  {_bar(b['count'], top, 20):<20} {b['count']:>2}")

    add("")
    add("ENERGY CURVE (0-10)")
    add("-------------------")
    add(f"Shape: {energy['shape']}. {energy['description']}")
    for pt in energy["points"]:
        add(f"  {pt['position']:>2}  {_bar(pt['energy'], 10, 20):<20} {_fmt(pt['energy']):>4}  "
            f"{_cut(pt['title'], 40)}")
    if energy["peak"]:
        add(f"Peak: #{energy['peak']['position']} {energy['peak']['title']} ({_fmt(energy['peak']['energy'])})")
        add(f"Lowest: #{energy['lowest']['position']} {energy['lowest']['title']} ({_fmt(energy['lowest']['energy'])})")
    for label, items in (("Biggest rises", energy["biggest_rises"]), ("Biggest drops", energy["biggest_drops"])):
        if items:
            add(label + ":")
            for d in items:
                add(f"  {d['from_position']}->{d['to_position']}  {d['change']:+g}  ({_cut(d['to'], 50)})")

    add("")
    add("TRANSITIONS")
    add("-----------")
    s = result["transition_summary"]
    c = s["categories"]
    add(f"{c['compatible']} compatible, {c['energy_boost']} energy boost, "
        f"{c['energy_drop']} energy drop, {c['clash']} clash  |  "
        f"tempo: {s['tempo_flags']['ok']} smooth, {s['tempo_flags']['tricky']} tricky, "
        f"{s['tempo_flags']['hard']} hard")
    for t in result["transitions"]:
        cat = CATEGORY_LABELS[t["category"]][0]
        flag = "" if t["tempo_flag"] == "ok" else f"  [{TEMPO_LABELS[t['tempo_flag']][0].upper()}]"
        add(f"  {t['position']:>2}->{t['position'] + 1:<2} {t['from_key']:>3} -> {t['to_key']:<3}  "
            f"{cat:<12}  {t['bpm_delta']:+6g} BPM{flag}")
        add(f"         {_cut(t['from'], 34)}  ->  {_cut(t['to'], 34)}")

    if "suggested_order" in result:
        so = result["suggested_order"]
        add("")
        add("SUGGESTED ORDER")
        add("---------------")
        if so["kept_original"]:
            add(f"The current order already scores best ({so['flow_before']}/100); no change suggested.")
        else:
            add(f"Flow score {so['flow_before']} -> {so['flow_after']} ({so['improvement']:+d}); "
                f"energy shape becomes {so['energy_shape_after']}.")
            for t in so["tracks"]:
                add(f"  {t['new_position']:>2}. (was {t['original_position']:>2})  {t['key']:>3}  "
                    f"{_fmt(t['bpm']):>5} BPM  E{_fmt(t['energy']):<4} {_cut(t['artist'] + ' - ' + t['title'], 50)}")
    add("")
    add("Key, tempo and energy values come from your export; this tool does not listen to audio.")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------- HTML

def _signed(n):
    """'+3', '-2' or '0' (no sign on zero), like the JS demo."""
    return f"+{n:g}" if n > 0 else f"{n:g}"


def _badge(kind, labels):
    text, tone, icon = labels[kind]
    return f'<span class="pa-badge {tone}"><span aria-hidden="true">{icon}</span>{escape(text)}</span>'


def _n1(value):
    """Coordinate with one decimal, halves rounded up (matches the JS demo)."""
    return f"{round_half_up(value, 1):.1f}"


def _n2(value):
    return f"{round_half_up(value, 2):.2f}"


def _arc_path(cx, cy, r0, r1, a0, a1):
    """Annular sector between radii r0<r1 and angles a0<a1 (degrees, 0 = up, clockwise)."""
    def pt(r, a):
        rad = math.radians(a)
        return cx + r * math.sin(rad), cy - r * math.cos(rad)

    x0, y0 = pt(r1, a0)
    x1, y1 = pt(r1, a1)
    x2, y2 = pt(r0, a1)
    x3, y3 = pt(r0, a0)
    return (f"M{_n2(x0)},{_n2(y0)} A{r1},{r1} 0 0 1 {_n2(x1)},{_n2(y1)} "
            f"L{_n2(x2)},{_n2(y2)} A{r0},{r0} 0 0 0 {_n2(x3)},{_n2(y3)} Z")


def svg_key_wheel(keys):
    """Camelot wheel: outer ring major (B), inner ring minor (A), shaded by count."""
    counts = {k["key"]: k for k in keys["keys"]}
    top = max((k["count"] for k in keys["keys"]), default=0)
    cx = cy = 160
    rings = {"B": (102, 150), "A": (56, 100)}
    parts = [f'<svg class="pa-chart" viewBox="0 0 320 320" role="img" '
             f'aria-label="Camelot wheel showing how many tracks are in each key">']
    for number in range(1, 13):
        center = (number % 12) * 30
        for letter, (r0, r1) in rings.items():
            key = CamelotKey(number, letter)
            row = counts.get(key.code)
            count = row["count"] if row else 0
            step = 0 if not count else max(1, min(7, int(math.ceil(7 * count / top))))
            label_r = (r0 + r1) / 2
            rad = math.radians(center)
            tx, ty = cx + label_r * math.sin(rad), cy - label_r * math.cos(rad)
            tip = f"{key.code} · {key.name} · {count} track{'s' if count != 1 else ''}"
            if row:
                tip += f" ({row['percent']:g}%)"
            parts.append(
                f'<g class="pa-wheel-g"><title>{escape(tip)}</title>'
                f'<path class="pa-wheel-seg c{step}" d="{_arc_path(cx, cy, r0, r1, center - 15, center + 15)}"/>'
                f'<text class="pa-wheel-text t{step}" x="{_n1(tx)}" y="{_n1(ty)}">{key.code}</text></g>'
            )
    parts.append(f'<text class="pa-wheel-center" x="{cx}" y="{cy - 4}">inner: minor</text>')
    parts.append(f'<text class="pa-wheel-center" x="{cx}" y="{cy + 12}">outer: major</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_tempo_histogram(tempo):
    buckets = tempo["buckets"]
    width, height = 420, 220
    left, right, top_pad, bottom = 28, 8, 20, 30
    plot_h = height - top_pad - bottom
    band = (width - left - right) / len(buckets)
    top = max(b["count"] for b in buckets) or 1
    ticks = _nice_ticks(top)
    y_max = ticks[-1]
    base_y = top_pad + plot_h
    summary = "; ".join(f'{b["label"]} BPM: {b["count"]}' for b in buckets)
    parts = [f'<svg class="pa-chart" viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="Tempo histogram. {escape(summary)}">']
    for t in ticks:
        y = base_y - plot_h * t / y_max
        cls = "pa-baseline" if t == 0 else "pa-grid-line"
        parts.append(f'<line class="{cls}" x1="{left}" x2="{width - right}" y1="{_n1(y)}" y2="{_n1(y)}"/>')
        parts.append(f'<text class="pa-axis-label" x="{left - 6}" y="{_n1(y + 4)}" text-anchor="end">{t}</text>')
    bar_w = min(24.0, band * 0.6)
    for i, b in enumerate(buckets):
        x = left + band * i + band / 2
        h = plot_h * b["count"] / y_max
        parts.append(f'<g class="pa-bar-group"><title>{escape(b["label"])} BPM: {b["count"]} track'
                     f'{"s" if b["count"] != 1 else ""} ({b["percent"]:g}%)</title>'
                     f'<rect class="pa-bar-hit" x="{_n1(x - band / 2)}" y="{top_pad}" width="{_n1(band)}" height="{plot_h}"/>')
        if b["count"]:
            parts.append(f'<path class="pa-bar" d="{_column_path(x - bar_w / 2, base_y, bar_w, h)}"/>'
                         f'<text class="pa-value-label" x="{_n1(x)}" y="{_n1(base_y - h - 6)}" text-anchor="middle">{b["count"]}</text>')
        parts.append("</g>")
        parts.append(f'<text class="pa-axis-label" x="{_n1(x)}" y="{base_y + 18}" text-anchor="middle">{escape(b["label"])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_energy_curve(points, label="Energy per track in playlist order"):
    width, height = 680, 240
    left, right, top_pad, bottom = 28, 16, 16, 30
    plot_w, plot_h = width - left - right, height - top_pad - bottom
    n = len(points)
    base_y = top_pad + plot_h

    def xy(i, e):
        x = left + (plot_w * i / (n - 1) if n > 1 else plot_w / 2)
        return x, base_y - plot_h * e / 10.0

    values = ", ".join(f'{p["position"]}: {p["energy"]:g}' for p in points)
    parts = [f'<svg class="pa-chart" viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="{escape(label)} (track: energy out of 10). {values}">']
    for t in (0, 2.5, 5, 7.5, 10):
        y = base_y - plot_h * t / 10
        cls = "pa-baseline" if t == 0 else "pa-grid-line"
        parts.append(f'<line class="{cls}" x1="{left}" x2="{width - right}" y1="{_n1(y)}" y2="{_n1(y)}"/>')
        parts.append(f'<text class="pa-axis-label" x="{left - 6}" y="{_n1(y + 4)}" text-anchor="end">{t:g}</text>')
    coords = [xy(i, p["energy"]) for i, p in enumerate(points)]
    if coords:
        line = " ".join(f"{_n1(x)},{_n1(y)}" for x, y in coords)
        area = f"{_n1(coords[0][0])},{base_y} {line} {_n1(coords[-1][0])},{base_y}"
        parts.append(f'<polygon class="pa-area" points="{area}"/>')
        parts.append(f'<polyline class="pa-line" points="{line}"/>')
    energies = [p["energy"] for p in points]
    peak = energies.index(max(energies)) if energies else -1
    low = energies.index(min(energies)) if energies else -1
    step = max(1, int(math.ceil(n / 16)))
    for i, (p, (x, y)) in enumerate(zip(points, coords)):
        who = f"{p['artist']} - {p['title']}" if p.get("artist") else p["title"]
        parts.append(f'<g class="pa-dot-group"><title>#{p["position"]} {escape(who)}: energy {p["energy"]:g}</title>'
                     f'<circle class="pa-dot-hit" cx="{_n1(x)}" cy="{_n1(y)}" r="12"/>'
                     f'<circle class="pa-dot" cx="{_n1(x)}" cy="{_n1(y)}" r="4.5"/></g>')
        if i in (peak, low) and n > 1:
            tag = "peak" if i == peak else "low"
            ly = y - 12 if i == peak else min(y + 20, base_y - 4)
            anchor = "start" if i == 0 else "end" if i == n - 1 else "middle"
            parts.append(f'<text class="pa-value-label" x="{_n1(x)}" y="{_n1(ly)}" text-anchor="{anchor}">{tag} {p["energy"]:g}</text>')
        if i % step == 0 or i == n - 1:
            parts.append(f'<text class="pa-axis-label" x="{_n1(x)}" y="{base_y + 18}" text-anchor="middle">{p["position"]}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _column_path(x, base_y, w, h):
    """Column with 4px rounded top, square at the baseline."""
    r = min(4.0, w / 2, h)
    top = base_y - h
    return (f"M{_n1(x)},{_n1(base_y)} L{_n1(x)},{_n1(top + r)} Q{_n1(x)},{_n1(top)} {_n1(x + r)},{_n1(top)} "
            f"L{_n1(x + w - r)},{_n1(top)} Q{_n1(x + w)},{_n1(top)} {_n1(x + w)},{_n1(top + r)} "
            f"L{_n1(x + w)},{_n1(base_y)} Z")


def _nice_ticks(top):
    step = 1 if top <= 5 else 2 if top <= 10 else 5 if top <= 25 else 10
    end = int(math.ceil(top / step) * step)
    return list(range(0, end + 1, step))


def _track_cell(title, artist):
    return (f'<div class="pa-track">{escape(title)}</div>'
            f'<div class="pa-artist">{escape(artist)}</div>')


def _transition_rows(items, track_lookup):
    rows = []
    for t in items:
        a, b = track_lookup(t)
        rows.append(
            "<tr>"
            f'<td class="pa-num pa-muted">{t["position"]}&rarr;{t["position"] + 1}</td>'
            f"<td>{_track_cell(*a)}</td><td>{_track_cell(*b)}</td>"
            f'<td class="pa-num">{escape(t["from_key"])} &rarr; {escape(t["to_key"])}</td>'
            f'<td>{_badge(t["category"], CATEGORY_LABELS)}<div class="pa-artist">{escape(t["rule"])}</div></td>'
            f'<td class="pa-num">{_signed(t["bpm_delta"])}</td>'
            f'<td>{_badge(t["tempo_flag"], TEMPO_LABELS)}</td>'
            f'<td class="pa-num">{_signed(t["energy_delta"])}</td>'
            f'<td class="pa-num">{round_half_up(t["score"] * 100)}</td>'
            "</tr>"
        )
    return "".join(rows)


_TRANSITION_HEAD = (
    '<tr><th class="pa-num">#</th><th>From</th><th>To</th><th class="pa-num">Keys</th>'
    '<th>Harmony</th><th class="pa-num">BPM &Delta;</th><th>Tempo</th>'
    '<th class="pa-num">Energy &Delta;</th><th class="pa-num">Score</th></tr>'
)


def _tile(label, value, note=""):
    note_html = f'<p class="pa-tile-note">{escape(note)}</p>' if note else ""
    return (f'<div class="pa-tile"><p class="pa-tile-label">{escape(label)}</p>'
            f'<p class="pa-tile-value">{value}</p>{note_html}</div>')


def render_html_body(result):
    """The report markup without the surrounding document (shared with the demo layout)."""
    p, keys, tempo, energy = result["playlist"], result["keys"], result["tempo"], result["energy"]
    tracks = result["tracks"]
    by_pos = {t["position"]: (t["title"], t["artist"]) for t in tracks}
    summary = result["transition_summary"]
    cats = summary["categories"]
    mc = keys["most_common"]
    out = []
    add = out.append

    add('<header class="pa-header"><p class="pa-eyebrow">Playlist analysis</p>'
        f'<h1 class="pa-title">{escape(p["name"])}</h1>')
    meta = [f'{p["track_count"]} tracks', f'imported from {escape(p["source_format"])}']
    if p.get("total_duration"):
        meta.append(f'running time {_duration(p["total_duration"])}')
    add(f'<p class="pa-sub">{" &middot; ".join(meta)}</p></header>')

    if p["warnings"]:
        add('<div class="pa-warn" role="note"><strong>Import notes</strong><ul>'
            + "".join(f"<li>{escape(w)}</li>" for w in p["warnings"]) + "</ul></div>")

    flow = result["flow_score"]
    add('<section class="pa-tiles" aria-label="Summary">')
    add('<div class="pa-tile"><p class="pa-tile-label">Flow score</p>'
        f'<p class="pa-tile-value">{flow}<span class="pa-muted" style="font-size:16px">/100</span></p>'
        f'<div class="pa-score-bar" aria-hidden="true"><div class="pa-score-fill" style="width:{flow}%"></div></div>'
        f'<p class="pa-tile-note">{cats["compatible"]} of {summary["total"]} transitions compatible</p></div>')
    add(_tile("Most common key", escape(mc["key"] or "-"), mc["name"] or ""))
    add(_tile("Median tempo", f'{tempo["median"]:g}<span class="pa-muted" style="font-size:16px"> BPM</span>',
              f'range {tempo["min"]:g}-{tempo["max"]:g}' ))
    add(_tile("Energy shape", escape(energy["shape"]), f'mean energy {energy["mean"]:g} / 10'))
    if "suggested_order" in result:
        so = result["suggested_order"]
        add(_tile("Suggested order", f'{so["flow_after"]}<span class="pa-muted" style="font-size:16px">/100</span>',
                  "current order already best" if so["kept_original"] else f'{_signed(so["improvement"])} vs current'))
    add("</section>")

    # Keys
    add('<section class="pa-card" aria-labelledby="pa-keys"><h2 id="pa-keys">Keys</h2>'
        f'<p class="pa-card-sub">{keys["distinct"]} distinct keys &middot; '
        f'major {keys["major"]["count"]} ({keys["major"]["percent"]:g}%) &middot; '
        f'minor {keys["minor"]["count"]} ({keys["minor"]["percent"]:g}%). '
        'Darker segments hold more tracks; neighbours on the wheel mix smoothly.</p>'
        '<div class="pa-grid-2"><div>' + svg_key_wheel(keys) +
        '<div class="pa-legend"><span>fewer</span>'
        + "".join(f'<span class="pa-swatch" style="background:var(--seq-{i})"></span>' for i in range(1, 8))
        + '<span>more tracks</span></div></div>'
        '<div class="pa-table-wrap"><table class="pa-table"><thead><tr><th>Camelot</th><th>Key</th>'
        '<th class="pa-num">Tracks</th><th class="pa-num">Share</th></tr></thead><tbody>'
        + "".join(f'<tr><td>{k["key"]}</td><td>{escape(k["name"])}</td><td class="pa-num">{k["count"]}</td>'
                  f'<td class="pa-num">{k["percent"]:g}%</td></tr>' for k in keys["keys"])
        + "</tbody></table></div></div></section>")

    # Tempo + energy
    add('<section class="pa-card" aria-labelledby="pa-tempo"><h2 id="pa-tempo">Tempo</h2>'
        f'<p class="pa-card-sub">How many tracks fall in each BPM range.</p>'
        f'<ul class="pa-kpis"><li>min <strong>{tempo["min"]:g}</strong></li><li>max <strong>{tempo["max"]:g}</strong></li>'
        f'<li>mean <strong>{tempo["mean"]:g}</strong></li><li>median <strong>{tempo["median"]:g}</strong></li></ul>'
        + svg_tempo_histogram(tempo) + "</section>")

    add('<section class="pa-card" aria-labelledby="pa-energy"><h2 id="pa-energy">Energy curve</h2>'
        f'<p class="pa-card-sub">Shape: <strong>{escape(energy["shape"])}</strong>. {escape(energy["description"])}</p>'
        + svg_energy_curve(energy["points"]))
    notes = []
    if energy["peak"]:
        notes.append(f'Peak: #{energy["peak"]["position"]} {escape(energy["peak"]["title"])} ({energy["peak"]["energy"]:g})')
        notes.append(f'Lowest: #{energy["lowest"]["position"]} {escape(energy["lowest"]["title"])} ({energy["lowest"]["energy"]:g})')
    for d in energy["biggest_rises"][:1]:
        notes.append(f'Biggest rise: {d["from_position"]}&rarr;{d["to_position"]} ({_signed(d["change"])})')
    for d in energy["biggest_drops"][:1]:
        notes.append(f'Biggest drop: {d["from_position"]}&rarr;{d["to_position"]} ({_signed(d["change"])})')
    add('<ul class="pa-notes">' + "".join(f"<li>{n}</li>" for n in notes) + "</ul></section>")

    # Transitions
    add('<section class="pa-card" aria-labelledby="pa-trans"><h2 id="pa-trans">Transitions</h2>'
        f'<p class="pa-card-sub">{cats["compatible"]} compatible &middot; {cats["energy_boost"]} energy boost &middot; '
        f'{cats["energy_drop"]} energy drop &middot; {cats["clash"]} clash &middot; '
        f'{summary["tempo_flags"]["tricky"]} tricky and {summary["tempo_flags"]["hard"]} hard tempo jumps</p>'
        '<div class="pa-table-wrap"><table class="pa-table"><thead>' + _TRANSITION_HEAD + "</thead><tbody>"
        + _transition_rows(result["transitions"],
                           lambda t: (by_pos[t["position"]], by_pos[t["position"] + 1]))
        + "</tbody></table></div></section>")

    # Suggested order
    if "suggested_order" in result:
        so = result["suggested_order"]
        add('<section class="pa-card" aria-labelledby="pa-order"><h2 id="pa-order">Suggested order</h2>')
        if so["kept_original"]:
            add(f'<p class="pa-card-sub">The current order already scores best ({so["flow_before"]}/100). '
                "No reordering suggested.</p></section>")
        else:
            add(f'<p class="pa-card-sub">Flow score <strong>{so["flow_before"]}</strong> &rarr; '
                f'<strong>{so["flow_after"]}</strong> ({_signed(so["improvement"])}). Energy shape becomes '
                f'<strong>{escape(so["energy_shape_after"])}</strong>. Same tracks, each used exactly once.</p>')
            points = [{"position": t["new_position"], "title": t["title"], "artist": t["artist"],
                       "energy": t["energy"]} for t in so["tracks"]]
            add(svg_energy_curve(points, "Energy curve in the suggested order"))
            add('<div class="pa-table-wrap"><table class="pa-table"><thead><tr><th class="pa-num">New</th>'
                '<th class="pa-num">Was</th><th>Track</th><th class="pa-num">Key</th><th class="pa-num">BPM</th>'
                '<th class="pa-num">Energy</th><th>Into next</th></tr></thead><tbody>')
            for i, t in enumerate(so["tracks"]):
                nxt = so["transitions"][i] if i < len(so["transitions"]) else None
                into = (_badge(nxt["category"], CATEGORY_LABELS) + " " + _badge(nxt["tempo_flag"], TEMPO_LABELS)
                        if nxt else '<span class="pa-muted">end</span>')
                add(f'<tr><td class="pa-num">{t["new_position"]}</td><td class="pa-num pa-muted">{t["original_position"]}</td>'
                    f'<td>{_track_cell(t["title"], t["artist"])}</td><td class="pa-num">{t["key"]}</td>'
                    f'<td class="pa-num">{t["bpm"]:g}</td><td class="pa-num">{t["energy"]:g}</td><td>{into}</td></tr>')
            add("</tbody></table></div></section>")

    add('<footer class="pa-footer">Generated by playlist-analyzer. Key, tempo and energy values come from the '
        "imported data; nothing here was detected from audio.</footer>")
    return "".join(out)


def render_html(result):
    """A complete, self-contained HTML document (inline CSS and SVG, no external assets)."""
    title = escape(f"{result['playlist']['name']} - playlist analysis")
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{title}</title>\n<style>\n{stylesheet()}\nhtml, body {{ margin: 0; }}\n</style>\n</head>\n"
        f"<body class=\"pa-root\">\n<main class=\"pa-page\">\n{render_html_body(result)}\n</main>\n</body>\n</html>\n"
    )


RENDERERS = {"text": render_text, "json": render_json, "html": render_html}
