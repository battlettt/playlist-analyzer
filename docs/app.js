/*
 * playlist-analyzer browser demo.
 *
 * A dependency-free JavaScript port of the Python package: same key parsing,
 * Camelot rules, flow score, reorder algorithm and report layout. It never
 * makes a network request, so it works from file:// as well as GitHub Pages.
 * Under Node (`require("./app.js")`) it exports the analysis functions so the
 * Python test-suite can check both implementations agree.
 */
(function (root) {
  "use strict";

  // ------------------------------------------------------------------ keys

  var NOTE_BASE = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
  var MAJOR_NAMES = [null, "B major", "F# major", "Db major", "Ab major", "Eb major", "Bb major",
    "F major", "C major", "G major", "D major", "A major", "E major"];
  var MINOR_NAMES = [null, "Ab minor", "Eb minor", "Bb minor", "F minor", "C minor", "G minor",
    "D minor", "A minor", "E minor", "B minor", "F# minor", "C# minor"];
  var CAMELOT_RE = /^0?(1[0-2]|[1-9])\s*([AaBb])$/;
  var MINOR_WORDS = ["m", "-", "min", "minor", "moll"];
  var MAJOR_WORDS = ["", "M", "maj", "major", "dur"];
  var SHARPS = ["#", "♯", "-sharp", "sharp"];
  var FLATS = ["♭", "-flat", "flat", "b"];

  function KeyParseError(message) { this.name = "KeyParseError"; this.message = message; }
  KeyParseError.prototype = Object.create(Error.prototype);

  function camelot(number, letter) {
    var minor = letter === "A";
    return {
      number: number, letter: letter, code: number + letter, minor: minor,
      mode: minor ? "minor" : "major",
      name: (minor ? MINOR_NAMES : MAJOR_NAMES)[number]
    };
  }
  function shifted(key, steps) {
    return camelot((((key.number - 1 + steps) % 12) + 12) % 12 + 1, key.letter);
  }
  function swapped(key) { return camelot(key.number, key.letter === "A" ? "B" : "A"); }
  function sameKey(a, b) { return a.number === b.number && a.letter === b.letter; }

  function fromPitchClass(pc, minor) {
    var majorPc = minor ? (pc + 3) % 12 : pc % 12;
    var fifths = (majorPc * 7) % 12;
    return camelot(((fifths + 7) % 12) + 1, minor ? "A" : "B");
  }

  function parseKey(text) {
    if (text === null || text === undefined) throw new KeyParseError("key is missing");
    var raw = String(text).trim();
    if (!raw) throw new KeyParseError("key is empty");
    var m = CAMELOT_RE.exec(raw);
    if (m) return camelot(parseInt(m[1], 10), m[2].toUpperCase());
    var bad = new KeyParseError("unrecognised key '" + raw + "' (expected e.g. '8A', 'A minor', 'Am', 'C')");
    var rootLetter = raw[0].toUpperCase();
    if (!(rootLetter in NOTE_BASE)) throw bad;
    var pc = NOTE_BASE[rootLetter];
    var rest = raw.slice(1).trim();
    var lowered = rest.toLowerCase();
    var groups = [[SHARPS, 1], [FLATS, -1]];
    for (var g = 0; g < groups.length; g++) {
      var words = groups[g][0], found = null;
      for (var w = 0; w < words.length; w++) {
        if (lowered.indexOf(words[w]) === 0) { found = words[w]; break; }
      }
      if (found) { pc += groups[g][1]; rest = rest.slice(found.length).trim(); break; }
    }
    var minor;
    if (rest === "m" || rest === "M") minor = rest === "m";
    else if (MINOR_WORDS.indexOf(rest.toLowerCase()) >= 0) minor = true;
    else if (MAJOR_WORDS.indexOf(rest.toLowerCase()) >= 0) minor = false;
    else throw bad;
    return fromPitchClass(((pc % 12) + 12) % 12, minor);
  }

  function allKeys() {
    var out = [];
    for (var n = 1; n <= 12; n++) { out.push(camelot(n, "A")); out.push(camelot(n, "B")); }
    return out;
  }
  function wheelOrder(key) { return (key.number - 1) * 2 + (key.letter === "A" ? 0 : 1); }
  function wheelDistance(a, b) {
    var diff = Math.abs(a.number - b.number) % 12;
    return Math.min(diff, 12 - diff);
  }

  function classifyKeys(a, b) {
    if (sameKey(a, b)) return ["compatible", "same key"];
    if (a.letter === b.letter) {
      if (sameKey(b, shifted(a, 1))) return ["compatible", "+1 on the wheel (up a fifth)"];
      if (sameKey(b, shifted(a, -1))) return ["compatible", "-1 on the wheel (down a fifth)"];
      if (sameKey(b, shifted(a, 2))) return ["energy_boost", "+2 on the wheel (up a whole tone)"];
      if (sameKey(b, shifted(a, -2))) return ["energy_drop", "-2 on the wheel (down a whole tone)"];
    } else if (a.number === b.number) {
      return ["compatible", "relative major/minor (letter swap)"];
    }
    return ["clash", wheelDistance(a, b) + " steps apart" + (a.letter === b.letter ? "" : " and a mode change")];
  }

  // --------------------------------------------------------------- parsing

  var FIELD_ALIASES = {
    title: ["title", "name", "track", "trackname", "tracktitle", "song", "songname"],
    artist: ["artist", "artists", "artistname", "artistnames", "performer", "by"],
    key: ["key", "musicalkey", "initialkey", "camelot", "camelotkey", "keycamelot", "tonality"],
    bpm: ["bpm", "tempo", "beatsperminute"],
    energy: ["energy", "energylevel", "energyscore", "intensity"],
    duration: ["duration", "length", "time", "durationms", "durationseconds"],
    genre: ["genre", "genres", "style"]
  };
  var REQUIRED = ["title", "artist", "key", "bpm", "energy"];
  var MIN_BPM = 20, MAX_BPM = 300, MAX_ENERGY = 100;
  var NUMBER_RE = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;

  function PlaylistParseError(message, errors) {
    this.name = "PlaylistParseError";
    this.errors = errors || [];
    this.message = message + this.errors.map(function (e) { return "\n  - " + e.toString(); }).join("");
  }
  PlaylistParseError.prototype = Object.create(Error.prototype);

  function RowError(row, message) { this.row = row; this.message = message; }
  RowError.prototype.toString = function () { return "row " + this.row + ": " + this.message; };

  function normHeader(name) {
    return String(name).trim().toLowerCase().replace(/^﻿/, "").replace(/[\s_\-()]+/g, "");
  }
  function mapHeaders(headers) {
    var lookup = {};
    Object.keys(FIELD_ALIASES).forEach(function (field) {
      FIELD_ALIASES[field].forEach(function (alias) { if (!(alias in lookup)) lookup[alias] = field; });
    });
    var mapping = {};
    headers.forEach(function (h, i) {
      var field = lookup[normHeader(h)];
      if (field && !(field in mapping)) mapping[field] = [i, normHeader(h)];
    });
    return mapping;
  }

  function roundHalfUp(value, digits) {
    var scale = Math.pow(10, digits || 0);
    return Math.floor(value * scale + 0.5) / scale;
  }
  function fmt(n) { return String(n); }
  function repr(v) { return "'" + String(v) + "'"; }

  function parseNumber(value, what) {
    var text = value === null || value === undefined ? "" : String(value).trim().replace(/,/g, ".");
    if (!text) throw new Error(what + " is missing");
    if (!NUMBER_RE.test(text)) throw new Error(what + " " + repr(value) + " is not a number");
    return parseFloat(text);
  }
  function parseDuration(value, header) {
    var text = value === null || value === undefined ? "" : String(value).trim();
    if (!text) return null;
    if (text.indexOf(":") >= 0) {
      var seconds = 0, parts = text.split(":");
      for (var i = 0; i < parts.length; i++) {
        if (!NUMBER_RE.test(parts[i].trim())) throw new Error("duration " + repr(value) + " is not like 3:45");
        seconds = seconds * 60 + parseFloat(parts[i]);
      }
      return seconds;
    }
    var n = parseNumber(text, "duration");
    if (n < 0) throw new Error("duration " + repr(value) + " is negative");
    return header === "durationms" || n > 10000 ? n / 1000 : n;
  }

  function buildTrack(raw) {
    var problems = [];
    var title = String(raw.title === undefined || raw.title === null ? "" : raw.title).trim();
    var artist = String(raw.artist === undefined || raw.artist === null ? "" : raw.artist).trim();
    if (!title) problems.push("title is missing");
    var key = null, bpm = null, energy = null, duration = null;
    try { key = parseKey(raw.key); } catch (e) { problems.push(e.message); }
    try {
      bpm = parseNumber(raw.bpm, "bpm");
      if (bpm < MIN_BPM || bpm > MAX_BPM) problems.push("bpm " + fmt(bpm) + " is outside " + MIN_BPM + "-" + MAX_BPM);
    } catch (e) { problems.push(e.message); }
    try {
      energy = parseNumber(raw.energy, "energy");
      if (energy < 0 || energy > MAX_ENERGY) problems.push("energy " + fmt(energy) + " is outside 0-" + MAX_ENERGY);
    } catch (e) { problems.push(e.message); }
    try { duration = parseDuration(raw.duration, raw._durationHeader || ""); } catch (e) { problems.push(e.message); }
    if (problems.length) throw new Error(problems.join("; "));
    var genre = String(raw.genre === undefined || raw.genre === null ? "" : raw.genre).trim() || null;
    return {
      title: title, artist: artist, key: key, bpm: bpm, energy: energy,
      keyRaw: String(raw.key).trim(), duration: duration, genre: genre,
      label: artist ? artist + " - " + title : title
    };
  }

  function normaliseEnergy(tracks) {
    if (!tracks.length) return "0-10";
    var top = Math.max.apply(null, tracks.map(function (t) { return t.energy; }));
    var factor, scale;
    if (top <= 1) { factor = 10; scale = "0-1"; }
    else if (top > 10) { factor = 0.1; scale = "0-100"; }
    else return "0-10";
    tracks.forEach(function (t) { t.energy = roundHalfUp(t.energy * factor, 2); });
    return scale;
  }

  function finish(rows, name, format, lenient, emptyMessage) {
    var tracks = [], errors = [];
    rows.forEach(function (r) {
      if (r[1] instanceof RowError) { errors.push(r[1]); return; }
      try { tracks.push(buildTrack(r[1])); } catch (e) { errors.push(new RowError(r[0], e.message)); }
    });
    if (errors.length && !lenient) throw new PlaylistParseError(errors.length + " invalid row(s) in " + format + " input", errors);
    if (!tracks.length) throw new PlaylistParseError(emptyMessage, errors);
    var scale = normaliseEnergy(tracks);
    var warnings = errors.map(function (e) { return "skipped " + e.toString(); });
    if (scale !== "0-10") warnings.push("energy values looked like a " + scale + " scale and were rescaled to 0-10");
    return { tracks: tracks, name: name, sourceFormat: format, energyScale: scale, warnings: warnings };
  }

  function detectDelimiter(text) {
    var lines = text.split(/\r\n|\r|\n/), first = "";
    for (var i = 0; i < lines.length; i++) if (lines[i].trim()) { first = lines[i]; break; }
    var best = [0, ","];
    [",", ";", "\t"].forEach(function (d) {
      var c = first.split(d).length - 1;
      if (c > best[0]) best = [c, d];
    });
    return best[1];
  }

  /* RFC 4180-style reader. Each record carries the line number it ends on,
     matching Python's csv.reader.line_num. */
  function readCsv(text, delim) {
    var records = [], field = "", record = [], inQuotes = false, line = 1, i = 0, quotedField = false;
    function endRecord() { record.push(field); records.push([line, record]); record = []; field = ""; quotedField = false; }
    while (i < text.length) {
      var ch = text[i];
      if (inQuotes) {
        if (ch === '"') {
          if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
          inQuotes = false; i++; continue;
        }
        if (ch === "\n" || (ch === "\r" && text[i + 1] !== "\n")) line++;
        field += ch; i++; continue;
      }
      if (ch === '"' && field === "" && !quotedField) { inQuotes = true; quotedField = true; i++; continue; }
      if (ch === delim) { record.push(field); field = ""; quotedField = false; i++; continue; }
      if (ch === "\r" || ch === "\n") {
        if (ch === "\r" && text[i + 1] === "\n") i++;
        endRecord(); line++; i++; continue;
      }
      field += ch; i++;
    }
    if (field !== "" || record.length) endRecord();
    return records;
  }

  function parseCsv(text, name, lenient) {
    text = text.replace(/^﻿/, "");
    if (!text.trim()) throw new PlaylistParseError("CSV input is empty");
    var records = readCsv(text, detectDelimiter(text));
    var idx = 0;
    while (idx < records.length && !records[idx][1].some(function (c) { return c.trim(); })) idx++;
    var header = idx < records.length ? records[idx][1] : [];
    var mapping = mapHeaders(header);
    var missing = REQUIRED.filter(function (f) { return !(f in mapping); });
    if (missing.length) {
      var found = header.map(function (h) { return h.trim(); }).join(", ") || "nothing";
      throw new PlaylistParseError("CSV header is missing required column(s): " + missing.join(", ") + " (found: " + found + ")");
    }
    var rows = [];
    records.slice(idx + 1).forEach(function (rec) {
      var cells = rec[1];
      if (!cells.some(function (c) { return c.trim(); })) return;
      var raw = {};
      Object.keys(mapping).forEach(function (field) {
        var col = mapping[field][0];
        raw[field] = col < cells.length ? cells[col] : "";
        if (field === "duration") raw._durationHeader = mapping[field][1];
      });
      rows.push([rec[0], raw]);
    });
    return finish(rows, name, "csv", lenient, "CSV contains no valid tracks");
  }

  function parseJson(text, name, lenient) {
    var data;
    try { data = JSON.parse(text); } catch (e) { throw new PlaylistParseError("invalid JSON: " + e.message); }
    if (data && typeof data === "object" && !Array.isArray(data)) {
      name = String(data.name || data.title || name);
      data = "tracks" in data ? data.tracks : data.items;
    }
    if (!Array.isArray(data)) throw new PlaylistParseError("JSON must be a list of tracks or an object with a 'tracks' list");
    var rows = data.map(function (item, i) {
      var n = i + 1;
      if (!item || typeof item !== "object" || Array.isArray(item)) {
        var kind = item === null ? "NoneType" : Array.isArray(item) ? "list" : typeof item === "string" ? "str"
          : typeof item === "number" ? (Number.isInteger(item) ? "int" : "float") : typeof item === "boolean" ? "bool" : typeof item;
        return [n, new RowError(n, "expected a track object, got " + kind)];
      }
      var keys = Object.keys(item), mapping = mapHeaders(keys), raw = {};
      Object.keys(mapping).forEach(function (field) {
        var value = item[keys[mapping[field][0]]];
        if (Array.isArray(value)) value = value.map(String).join(", ");
        raw[field] = value === null || value === undefined ? "" : value;
        if (field === "duration") raw._durationHeader = mapping[field][1];
      });
      return [n, raw];
    });
    return finish(rows, name, "json", lenient, "JSON contains no valid tracks");
  }

  function parseText(text, name, lenient) {
    if (!text.trim()) throw new PlaylistParseError("text input is empty");
    var rows = [];
    text.split(/\r\n|\r|\n/).forEach(function (line, i) {
      var n = i + 1, stripped = line.trim();
      if (!stripped || stripped[0] === "#") return;
      var parts = stripped.split("|").map(function (p) { return p.trim(); });
      if (parts.length !== 4) {
        rows.push([n, new RowError(n, "expected 4 fields separated by '|' (Artist - Title | key | bpm | energy), got " + parts.length)]);
        return;
      }
      var who = parts[0], cut = who.indexOf(" - ");
      if (cut < 0) { rows.push([n, new RowError(n, "expected 'Artist - Title' but got '" + who + "'")]); return; }
      rows.push([n, { artist: who.slice(0, cut).trim(), title: who.slice(cut + 3).trim(), key: parts[1], bpm: parts[2], energy: parts[3] }]);
    });
    return finish(rows, name, "text", lenient, "text input contains no valid tracks");
  }

  function detectFormat(text) {
    var s = text.replace(/^﻿/, "").trim();
    if (s[0] === "[" || s[0] === "{") return "json";
    var lines = s.split(/\r\n|\r|\n/).filter(function (l) { return l.trim() && l.trim()[0] !== "#"; }).slice(0, 5);
    if (lines.length && lines.every(function (l) { return l.split("|").length - 1 === 3; })) return "text";
    return "csv";
  }

  function parse(text, format, name, lenient) {
    format = !format || format === "auto" ? detectFormat(text) : format;
    name = name || "Playlist";
    if (format === "csv") return parseCsv(text, name, lenient);
    if (format === "json") return parseJson(text, name, lenient);
    if (format === "text") return parseText(text, name, lenient);
    throw new PlaylistParseError("unknown format '" + format + "' (use csv, json, text or auto)");
  }

  // -------------------------------------------------------------- analysis

  var TEMPO_BUCKETS = [["<90", null, 90], ["90-100", 90, 100], ["100-110", 100, 110],
    ["110-120", 110, 120], ["120-130", 120, 130], ["130+", 130, null]];
  var KEY_POINTS = { compatible: 1, energy_boost: 0.75, energy_drop: 0.75, clash: 0 };

  function pct(part, total) { return total ? roundHalfUp(100 * part / total, 1) : 0; }
  function mean(xs) { var s = 0; xs.forEach(function (x) { s += x; }); return s / xs.length; }
  function median(xs) {
    var s = xs.slice().sort(function (a, b) { return a - b; }), n = s.length;
    return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
  }

  function keyDistribution(tracks) {
    var total = tracks.length, counts = {}, byCode = {};
    tracks.forEach(function (t) { counts[t.key.code] = (counts[t.key.code] || 0) + 1; byCode[t.key.code] = t.key; });
    var keys = Object.keys(byCode).map(function (c) { return byCode[c]; })
      .sort(function (a, b) { return wheelOrder(a) - wheelOrder(b); });
    var minor = 0;
    keys.forEach(function (k) { if (k.minor) minor += counts[k.code]; });
    var top = keys.length ? Math.max.apply(null, keys.map(function (k) { return counts[k.code]; })) : 0;
    var most = keys.filter(function (k) { return counts[k.code] === top; });
    return {
      total: total, distinct: keys.length,
      keys: keys.map(function (k) {
        return { key: k.code, name: k.name, mode: k.mode, count: counts[k.code], percent: pct(counts[k.code], total) };
      }),
      major: { count: total - minor, percent: pct(total - minor, total) },
      minor: { count: minor, percent: pct(minor, total) },
      most_common: {
        key: most.length ? most[0].code : null, name: most.length ? most[0].name : null, count: top,
        tied_with: most.slice(1).map(function (k) { return k.code; })
      }
    };
  }

  function tempoBucket(bpm) {
    for (var i = 0; i < TEMPO_BUCKETS.length; i++) {
      var b = TEMPO_BUCKETS[i];
      if ((b[1] === null || bpm >= b[1]) && (b[2] === null || bpm < b[2])) return b[0];
    }
  }

  function tempoHistogram(tracks) {
    var bpms = tracks.map(function (t) { return t.bpm; }), counts = {};
    TEMPO_BUCKETS.forEach(function (b) { counts[b[0]] = 0; });
    bpms.forEach(function (b) { counts[tempoBucket(b)] += 1; });
    return {
      buckets: TEMPO_BUCKETS.map(function (b) { return { label: b[0], count: counts[b[0]], percent: pct(counts[b[0]], bpms.length) }; }),
      min: bpms.length ? Math.min.apply(null, bpms) : null,
      max: bpms.length ? Math.max.apply(null, bpms) : null,
      mean: bpms.length ? roundHalfUp(mean(bpms), 2) : null,
      median: bpms.length ? roundHalfUp(median(bpms), 2) : null
    };
  }

  function correlation(xs, ys) {
    var n = xs.length, mx = mean(xs), my = mean(ys), sxy = 0, sxx = 0, syy = 0;
    for (var i = 0; i < n; i++) {
      sxy += (xs[i] - mx) * (ys[i] - my); sxx += Math.pow(xs[i] - mx, 2); syy += Math.pow(ys[i] - my, 2);
    }
    return sxx === 0 || syy === 0 ? 0 : sxy / Math.pow(sxx * syy, 0.5);
  }

  function classifyShape(energies) {
    if (energies.length < 2 || Math.max.apply(null, energies) - Math.min.apply(null, energies) < 2) return "flat";
    var r = correlation(energies.map(function (_, i) { return i; }), energies);
    if (r >= 0.6) return "rising";
    if (r <= -0.6) return "falling";
    return "peak-and-valley";
  }

  function describeShape(shape, e, peak) {
    if (!e.length) return "No tracks, so no energy curve.";
    var n = e.length;
    if (shape === "flat") return "Energy stays level (between " + fmt(Math.min.apply(null, e)) + " and " + fmt(Math.max.apply(null, e)) + ") the whole way through.";
    if (shape === "rising") return "Energy builds from " + fmt(e[0]) + " to " + fmt(e[n - 1]) + " across the playlist.";
    if (shape === "falling") return "Energy winds down from " + fmt(e[0]) + " to " + fmt(e[n - 1]) + " across the playlist.";
    if (0.25 * n <= peak && peak < 0.85 * n && e[0] < e[peak] && e[n - 1] < e[peak]) {
      return "An arc: energy climbs to a peak of " + fmt(e[peak]) + " at track " + (peak + 1) + " of " + n + ", then eases off.";
    }
    return "Energy swings up and down rather than following one direction.";
  }

  function extreme(tracks, i) {
    if (i === null) return null;
    var t = tracks[i];
    return { position: i + 1, title: t.title, artist: t.artist, energy: t.energy };
  }

  function energyCurve(tracks) {
    var e = tracks.map(function (t) { return t.energy; });
    var deltas = [];
    for (var i = 1; i < tracks.length; i++) {
      deltas.push({ from_position: i, to_position: i + 1, from: tracks[i - 1].label, to: tracks[i].label,
        change: roundHalfUp(e[i] - e[i - 1], 2) });
    }
    var ups = deltas.filter(function (d) { return d.change > 0; })
      .sort(function (a, b) { return b.change - a.change || a.from_position - b.from_position; });
    var downs = deltas.filter(function (d) { return d.change < 0; })
      .sort(function (a, b) { return a.change - b.change || a.from_position - b.from_position; });
    var peak = null, low = null;
    e.forEach(function (v, i) {
      if (peak === null || v > e[peak]) peak = i;
      if (low === null || v < e[low]) low = i;
    });
    var shape = tracks.length ? classifyShape(e) : "flat";
    return {
      points: tracks.map(function (t, i) { return { position: i + 1, title: t.title, artist: t.artist, energy: t.energy }; }),
      shape: shape, description: describeShape(shape, e, peak),
      mean: e.length ? roundHalfUp(mean(e), 2) : null,
      peak: extreme(tracks, peak), lowest: extreme(tracks, low),
      biggest_rises: ups.slice(0, 3), biggest_drops: downs.slice(0, 3)
    };
  }

  function tempoFlag(delta) {
    var gap = Math.abs(delta);
    return gap > 10 ? "hard" : gap > 6 ? "tricky" : "ok";
  }

  function transitionScore(category, bpmDelta, energyDelta) {
    var tempo = { ok: 1, tricky: 0.5, hard: 0 }[tempoFlag(bpmDelta)];
    var gap = Math.abs(energyDelta);
    var energy = gap <= 2 ? 1 : gap <= 4 ? 0.5 : 0;
    return 0.5 * KEY_POINTS[category] + 0.3 * tempo + 0.2 * energy;
  }

  function analyzeTransition(a, b, position) {
    var c = classifyKeys(a.key, b.key);
    var bpmDelta = roundHalfUp(b.bpm - a.bpm, 2), energyDelta = roundHalfUp(b.energy - a.energy, 2);
    return {
      position: position, from: a.label, to: b.label, from_key: a.key.code, to_key: b.key.code,
      category: c[0], rule: c[1], bpm_from: a.bpm, bpm_to: b.bpm, bpm_delta: bpmDelta,
      tempo_flag: tempoFlag(bpmDelta), energy_delta: energyDelta,
      score: roundHalfUp(transitionScore(c[0], bpmDelta, energyDelta), 3)
    };
  }

  function transitions(tracks) {
    var out = [];
    for (var i = 0; i < tracks.length - 1; i++) out.push(analyzeTransition(tracks[i], tracks[i + 1], i + 1));
    return out;
  }

  function pairScore(a, b) { return transitionScore(classifyKeys(a.key, b.key)[0], b.bpm - a.bpm, b.energy - a.energy); }

  function flowScore(tracks) {
    if (tracks.length < 2) return 100;
    var sum = 0;
    for (var i = 0; i < tracks.length - 1; i++) sum += pairScore(tracks[i], tracks[i + 1]);
    return roundHalfUp(100 * sum / (tracks.length - 1));
  }

  function transitionSummary(items) {
    var cats = { compatible: 0, energy_boost: 0, energy_drop: 0, clash: 0 }, tempo = { ok: 0, tricky: 0, hard: 0 };
    items.forEach(function (t) { cats[t.category] += 1; tempo[t.tempo_flag] += 1; });
    return { categories: cats, tempo_flags: tempo, total: items.length };
  }

  // --------------------------------------------------------------- reorder

  var ARC_WEIGHT = 0.3, PEAK_AT = 0.7, LANDING = 0.6, MAX_STARTS = 24;

  function energyRange(tracks) {
    var e = tracks.map(function (t) { return t.energy; });
    return [Math.min.apply(null, e), Math.max.apply(null, e)];
  }

  function targetArc(tracks) {
    var n = tracks.length;
    if (!n) return [];
    var r = energyRange(tracks), out = [];
    for (var i = 0; i < n; i++) {
      var p = n > 1 ? i / (n - 1) : 0;
      var shape = p <= PEAK_AT ? p / PEAK_AT : 1 - (1 - LANDING) * (p - PEAK_AT) / (1 - PEAK_AT);
      out.push(r[0] + shape * (r[1] - r[0]));
    }
    return out;
  }

  function arcDeviation(tracks, targets) {
    if (tracks.length < 2) return 0;
    var r = energyRange(tracks), spread = r[1] - r[0];
    if (spread === 0) return 0;
    var s = 0;
    tracks.forEach(function (t, i) { s += Math.abs(t.energy - targets[i]); });
    return s / (tracks.length * spread);
  }

  function greedyWalk(tracks, start, targets) {
    var r = energyRange(tracks), spread = (r[1] - r[0]) || 1;
    var remaining = [], order = [start];
    for (var i = 0; i < tracks.length; i++) if (i !== start) remaining.push(i);
    while (remaining.length) {
      var current = tracks[order[order.length - 1]], slot = order.length, best = -1, bestCost = Infinity;
      for (var j = 0; j < remaining.length; j++) {
        var t = tracks[remaining[j]];
        var cost = (1 - pairScore(current, t)) + ARC_WEIGHT * Math.abs(t.energy - targets[slot]) / spread;
        if (cost < bestCost) { bestCost = cost; best = j; } // remaining is ascending, so ties keep the lower index
      }
      order.push(remaining[best]);
      remaining.splice(best, 1);
    }
    return order;
  }

  function objective(ordered, targets) { return flowScore(ordered) - 100 * ARC_WEIGHT * arcDeviation(ordered, targets); }

  function bestOrder(tracks) {
    var n = tracks.length, original = [];
    for (var i = 0; i < n; i++) original.push(i);
    if (n < 3) return original;
    var targets = targetArc(tracks);
    var starts = original.slice().sort(function (a, b) { return tracks[a].energy - tracks[b].energy || a - b; }).slice(0, MAX_STARTS);
    var baseline = flowScore(tracks), best = original, bestValue = objective(tracks, targets);
    starts.forEach(function (start) {
      var order = greedyWalk(tracks, start, targets);
      var ordered = order.map(function (k) { return tracks[k]; });
      if (flowScore(ordered) < baseline) return;
      var value = objective(ordered, targets);
      if (value > bestValue + 1e-9) { best = order; bestValue = value; }
    });
    return best;
  }

  function suggestOrder(tracks) {
    var order = bestOrder(tracks);
    var ordered = order.map(function (k) { return tracks[k]; });
    var before = flowScore(tracks), after = flowScore(ordered);
    return {
      order: order.map(function (k) { return k + 1; }),
      tracks: order.map(function (k, n) {
        var t = tracks[k];
        return { new_position: n + 1, original_position: k + 1, title: t.title, artist: t.artist, key: t.key.code, bpm: t.bpm, energy: t.energy };
      }),
      flow_before: before, flow_after: after, improvement: after - before,
      kept_original: order.every(function (k, i) { return k === i; }),
      energy_shape_after: energyCurve(ordered).shape,
      transitions: transitions(ordered),
      method: "greedy Camelot walk with energy-arc target (see reorder.py)"
    };
  }

  function analyze(playlist) {
    var tracks = playlist.tracks, items = transitions(tracks);
    var total = null;
    if (tracks.length && tracks.every(function (t) { return t.duration !== null; })) {
      var s = 0;
      tracks.forEach(function (t) { s += t.duration; });
      total = roundHalfUp(s, 1);
    }
    return {
      playlist: { name: playlist.name, source_format: playlist.sourceFormat, track_count: tracks.length,
        total_duration: total, energy_scale: playlist.energyScale, warnings: playlist.warnings.slice() },
      tracks: tracks.map(function (t, i) {
        return { title: t.title, artist: t.artist, key: t.key.code, key_name: t.key.name, key_raw: t.keyRaw,
          bpm: t.bpm, energy: t.energy, duration: t.duration, genre: t.genre, position: i + 1 };
      }),
      keys: keyDistribution(tracks), tempo: tempoHistogram(tracks), energy: energyCurve(tracks),
      transitions: items, transition_summary: transitionSummary(items), flow_score: flowScore(tracks),
      suggested_order: suggestOrder(tracks)
    };
  }

  // ------------------------------------------------------------- rendering

  var CATEGORY_LABELS = {
    compatible: ["Compatible", "good", "✓"], energy_boost: ["Energy boost", "info", "▲"],
    energy_drop: ["Energy drop", "info", "▼"], clash: ["Clash", "critical", "✕"]
  };
  var TEMPO_LABELS = { ok: ["Smooth", "good", "✓"], tricky: ["Tricky", "warning", "!"], hard: ["Hard jump", "critical", "✕"] };

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#x27;");
  }
  function signed(n) { return (n > 0 ? "+" : "") + fmt(n); }
  function f1(n) { return roundHalfUp(n, 1).toFixed(1); }
  function f2(n) { return roundHalfUp(n, 2).toFixed(2); }
  function badge(kind, labels) {
    var l = labels[kind];
    return '<span class="pa-badge ' + l[1] + '"><span aria-hidden="true">' + l[2] + "</span>" + esc(l[0]) + "</span>";
  }
  function durationText(seconds) {
    seconds = Math.round(seconds);
    var h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
    var pad = function (x) { return (x < 10 ? "0" : "") + x; };
    return h ? h + ":" + pad(m) + ":" + pad(s) : m + ":" + pad(s);
  }

  function arcPath(cx, cy, r0, r1, a0, a1) {
    function pt(r, a) { var rad = a * Math.PI / 180; return [cx + r * Math.sin(rad), cy - r * Math.cos(rad)]; }
    var p0 = pt(r1, a0), p1 = pt(r1, a1), p2 = pt(r0, a1), p3 = pt(r0, a0);
    return "M" + f2(p0[0]) + "," + f2(p0[1]) + " A" + r1 + "," + r1 + " 0 0 1 " + f2(p1[0]) + "," + f2(p1[1]) +
      " L" + f2(p2[0]) + "," + f2(p2[1]) + " A" + r0 + "," + r0 + " 0 0 0 " + f2(p3[0]) + "," + f2(p3[1]) + " Z";
  }

  function svgKeyWheel(keys) {
    var counts = {};
    keys.keys.forEach(function (k) { counts[k.key] = k; });
    var top = Math.max.apply(null, [0].concat(keys.keys.map(function (k) { return k.count; })));
    var cx = 160, cy = 160, rings = [["B", 102, 150], ["A", 56, 100]];
    var parts = ['<svg class="pa-chart" viewBox="0 0 320 320" role="img" aria-label="Camelot wheel showing how many tracks are in each key">'];
    for (var n = 1; n <= 12; n++) {
      var center = (n % 12) * 30;
      rings.forEach(function (ring) {
        var key = camelot(n, ring[0]), row = counts[key.code], count = row ? row.count : 0;
        var step = count ? Math.max(1, Math.min(7, Math.ceil(7 * count / top))) : 0;
        var lr = (ring[1] + ring[2]) / 2, rad = center * Math.PI / 180;
        var tip = key.code + " · " + key.name + " · " + count + " track" + (count !== 1 ? "s" : "") + (row ? " (" + row.percent + "%)" : "");
        parts.push('<g class="pa-wheel-g"><title>' + esc(tip) + '</title><path class="pa-wheel-seg c' + step + '" d="' +
          arcPath(cx, cy, ring[1], ring[2], center - 15, center + 15) + '"/><text class="pa-wheel-text t' + step + '" x="' +
          f1(cx + lr * Math.sin(rad)) + '" y="' + f1(cy - lr * Math.cos(rad)) + '">' + key.code + "</text></g>");
      });
    }
    parts.push('<text class="pa-wheel-center" x="' + cx + '" y="' + (cy - 4) + '">inner: minor</text>');
    parts.push('<text class="pa-wheel-center" x="' + cx + '" y="' + (cy + 12) + '">outer: major</text></svg>');
    return parts.join("");
  }

  function niceTicks(top) {
    var step = top <= 5 ? 1 : top <= 10 ? 2 : top <= 25 ? 5 : 10, end = Math.ceil(top / step) * step, out = [];
    for (var t = 0; t <= end; t += step) out.push(t);
    return out;
  }

  function columnPath(x, baseY, w, h) {
    var r = Math.min(4, w / 2, h), top = baseY - h;
    return "M" + f1(x) + "," + f1(baseY) + " L" + f1(x) + "," + f1(top + r) + " Q" + f1(x) + "," + f1(top) + " " + f1(x + r) + "," + f1(top) +
      " L" + f1(x + w - r) + "," + f1(top) + " Q" + f1(x + w) + "," + f1(top) + " " + f1(x + w) + "," + f1(top + r) +
      " L" + f1(x + w) + "," + f1(baseY) + " Z";
  }

  function svgTempo(tempo) {
    var b = tempo.buckets, width = 420, height = 220, left = 28, right = 8, topPad = 20, bottom = 30;
    var plotH = height - topPad - bottom, band = (width - left - right) / b.length;
    var top = Math.max.apply(null, b.map(function (x) { return x.count; })) || 1;
    var ticks = niceTicks(top), yMax = ticks[ticks.length - 1], baseY = topPad + plotH;
    var summary = b.map(function (x) { return x.label + " BPM: " + x.count; }).join("; ");
    var parts = ['<svg class="pa-chart" viewBox="0 0 ' + width + " " + height + '" role="img" aria-label="Tempo histogram. ' + esc(summary) + '">'];
    ticks.forEach(function (t) {
      var y = baseY - plotH * t / yMax;
      parts.push('<line class="' + (t === 0 ? "pa-baseline" : "pa-grid-line") + '" x1="' + left + '" x2="' + (width - right) + '" y1="' + f1(y) + '" y2="' + f1(y) + '"/>');
      parts.push('<text class="pa-axis-label" x="' + (left - 6) + '" y="' + f1(y + 4) + '" text-anchor="end">' + t + "</text>");
    });
    var barW = Math.min(24, band * 0.6);
    b.forEach(function (bucket, i) {
      var x = left + band * i + band / 2, h = plotH * bucket.count / yMax;
      parts.push('<g class="pa-bar-group"><title>' + esc(bucket.label) + " BPM: " + bucket.count + " track" + (bucket.count !== 1 ? "s" : "") +
        " (" + bucket.percent + "%)</title>" + '<rect class="pa-bar-hit" x="' + f1(x - band / 2) + '" y="' + topPad + '" width="' + f1(band) + '" height="' + plotH + '"/>');
      if (bucket.count) {
        parts.push('<path class="pa-bar" d="' + columnPath(x - barW / 2, baseY, barW, h) + '"/><text class="pa-value-label" x="' + f1(x) +
          '" y="' + f1(baseY - h - 6) + '" text-anchor="middle">' + bucket.count + "</text>");
      }
      parts.push("</g>");
      parts.push('<text class="pa-axis-label" x="' + f1(x) + '" y="' + (baseY + 18) + '" text-anchor="middle">' + esc(bucket.label) + "</text>");
    });
    parts.push("</svg>");
    return parts.join("");
  }

  function svgEnergy(points, label) {
    label = label || "Energy per track in playlist order";
    var width = 680, height = 240, left = 28, right = 16, topPad = 16, bottom = 30;
    var plotW = width - left - right, plotH = height - topPad - bottom, n = points.length, baseY = topPad + plotH;
    function xy(i, e) { return [left + (n > 1 ? plotW * i / (n - 1) : plotW / 2), baseY - plotH * e / 10]; }
    var values = points.map(function (p) { return p.position + ": " + fmt(p.energy); }).join(", ");
    var parts = ['<svg class="pa-chart" viewBox="0 0 ' + width + " " + height + '" role="img" aria-label="' + esc(label) +
      ' (track: energy out of 10). ' + values + '">'];
    [0, 2.5, 5, 7.5, 10].forEach(function (t) {
      var y = baseY - plotH * t / 10;
      parts.push('<line class="' + (t === 0 ? "pa-baseline" : "pa-grid-line") + '" x1="' + left + '" x2="' + (width - right) + '" y1="' + f1(y) + '" y2="' + f1(y) + '"/>');
      parts.push('<text class="pa-axis-label" x="' + (left - 6) + '" y="' + f1(y + 4) + '" text-anchor="end">' + t + "</text>");
    });
    var coords = points.map(function (p, i) { return xy(i, p.energy); });
    if (coords.length) {
      var line = coords.map(function (c) { return f1(c[0]) + "," + f1(c[1]); }).join(" ");
      parts.push('<polygon class="pa-area" points="' + f1(coords[0][0]) + "," + baseY + " " + line + " " + f1(coords[coords.length - 1][0]) + "," + baseY + '"/>');
      parts.push('<polyline class="pa-line" points="' + line + '"/>');
    }
    var e = points.map(function (p) { return p.energy; });
    var peak = e.indexOf(Math.max.apply(null, e)), low = e.indexOf(Math.min.apply(null, e));
    var step = Math.max(1, Math.ceil(n / 16));
    points.forEach(function (p, i) {
      var x = coords[i][0], y = coords[i][1], who = p.artist ? p.artist + " - " + p.title : p.title;
      parts.push('<g class="pa-dot-group"><title>#' + p.position + " " + esc(who) + ": energy " + fmt(p.energy) + '</title><circle class="pa-dot-hit" cx="' +
        f1(x) + '" cy="' + f1(y) + '" r="12"/><circle class="pa-dot" cx="' + f1(x) + '" cy="' + f1(y) + '" r="4.5"/></g>');
      if ((i === peak || i === low) && n > 1) {
        var ly = i === peak ? y - 12 : Math.min(y + 20, baseY - 4);
        var anchor = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
        parts.push('<text class="pa-value-label" x="' + f1(x) + '" y="' + f1(ly) + '" text-anchor="' + anchor + '">' + (i === peak ? "peak" : "low") + " " + fmt(p.energy) + "</text>");
      }
      if (i % step === 0 || i === n - 1) parts.push('<text class="pa-axis-label" x="' + f1(x) + '" y="' + (baseY + 18) + '" text-anchor="middle">' + p.position + "</text>");
    });
    parts.push("</svg>");
    return parts.join("");
  }

  function trackCell(title, artist) {
    return '<div class="pa-track">' + esc(title) + '</div><div class="pa-artist">' + esc(artist) + "</div>";
  }
  function tile(label, value, note) {
    return '<div class="pa-tile"><p class="pa-tile-label">' + esc(label) + '</p><p class="pa-tile-value">' + value + "</p>" +
      (note ? '<p class="pa-tile-note">' + esc(note) + "</p>" : "") + "</div>";
  }
  var UNIT = '<span class="pa-muted" style="font-size:16px">';

  function renderBody(r) {
    var p = r.playlist, keys = r.keys, tempo = r.tempo, energy = r.energy, s = r.transition_summary, cats = s.categories;
    var byPos = {};
    r.tracks.forEach(function (t) { byPos[t.position] = [t.title, t.artist]; });
    var out = [];
    var meta = [p.track_count + " tracks", "imported from " + esc(p.source_format)];
    if (p.total_duration) meta.push("running time " + durationText(p.total_duration));
    out.push('<header class="pa-header"><p class="pa-eyebrow">Playlist analysis</p><h1 class="pa-title">' + esc(p.name) +
      '</h1><p class="pa-sub">' + meta.join(" &middot; ") + "</p></header>");
    if (p.warnings.length) {
      out.push('<div class="pa-warn" role="note"><strong>Import notes</strong><ul>' +
        p.warnings.map(function (w) { return "<li>" + esc(w) + "</li>"; }).join("") + "</ul></div>");
    }
    out.push('<section class="pa-tiles" aria-label="Summary">');
    out.push('<div class="pa-tile"><p class="pa-tile-label">Flow score</p><p class="pa-tile-value">' + r.flow_score + UNIT + "/100</span></p>" +
      '<div class="pa-score-bar" aria-hidden="true"><div class="pa-score-fill" style="width:' + r.flow_score + '%"></div></div>' +
      '<p class="pa-tile-note">' + cats.compatible + " of " + s.total + " transitions compatible</p></div>");
    out.push(tile("Most common key", esc(keys.most_common.key || "-"), keys.most_common.name || ""));
    out.push(tile("Median tempo", fmt(tempo.median) + UNIT + " BPM</span>", "range " + fmt(tempo.min) + "-" + fmt(tempo.max)));
    out.push(tile("Energy shape", esc(energy.shape), "mean energy " + fmt(energy.mean) + " / 10"));
    var so = r.suggested_order;
    out.push(tile("Suggested order", so.flow_after + UNIT + "/100</span>", so.kept_original ? "current order already best" : signed(so.improvement) + " vs current"));
    out.push("</section>");

    var swatches = "";
    for (var i = 1; i <= 7; i++) swatches += '<span class="pa-swatch" style="background:var(--seq-' + i + ')"></span>';
    out.push('<section class="pa-card" aria-labelledby="pa-keys"><h2 id="pa-keys">Keys</h2><p class="pa-card-sub">' + keys.distinct +
      " distinct keys &middot; major " + keys.major.count + " (" + fmt(keys.major.percent) + "%) &middot; minor " + keys.minor.count +
      " (" + fmt(keys.minor.percent) + "%). Darker segments hold more tracks; neighbours on the wheel mix smoothly.</p>" +
      '<div class="pa-grid-2"><div>' + svgKeyWheel(keys) + '<div class="pa-legend"><span>fewer</span>' + swatches + "<span>more tracks</span></div></div>" +
      '<div class="pa-table-wrap"><table class="pa-table"><thead><tr><th>Camelot</th><th>Key</th><th class="pa-num">Tracks</th><th class="pa-num">Share</th></tr></thead><tbody>' +
      keys.keys.map(function (k) {
        return "<tr><td>" + k.key + "</td><td>" + esc(k.name) + '</td><td class="pa-num">' + k.count + '</td><td class="pa-num">' + fmt(k.percent) + "%</td></tr>";
      }).join("") + "</tbody></table></div></div></section>");

    out.push('<section class="pa-card" aria-labelledby="pa-tempo"><h2 id="pa-tempo">Tempo</h2><p class="pa-card-sub">How many tracks fall in each BPM range.</p>' +
      '<ul class="pa-kpis"><li>min <strong>' + fmt(tempo.min) + "</strong></li><li>max <strong>" + fmt(tempo.max) + "</strong></li><li>mean <strong>" +
      fmt(tempo.mean) + "</strong></li><li>median <strong>" + fmt(tempo.median) + "</strong></li></ul>" + svgTempo(tempo) + "</section>");

    var notes = [];
    if (energy.peak) {
      notes.push("Peak: #" + energy.peak.position + " " + esc(energy.peak.title) + " (" + fmt(energy.peak.energy) + ")");
      notes.push("Lowest: #" + energy.lowest.position + " " + esc(energy.lowest.title) + " (" + fmt(energy.lowest.energy) + ")");
    }
    energy.biggest_rises.slice(0, 1).forEach(function (d) { notes.push("Biggest rise: " + d.from_position + "&rarr;" + d.to_position + " (" + signed(d.change) + ")"); });
    energy.biggest_drops.slice(0, 1).forEach(function (d) { notes.push("Biggest drop: " + d.from_position + "&rarr;" + d.to_position + " (" + signed(d.change) + ")"); });
    out.push('<section class="pa-card" aria-labelledby="pa-energy"><h2 id="pa-energy">Energy curve</h2><p class="pa-card-sub">Shape: <strong>' +
      esc(energy.shape) + "</strong>. " + esc(energy.description) + "</p>" + svgEnergy(energy.points) +
      '<ul class="pa-notes">' + notes.map(function (n) { return "<li>" + n + "</li>"; }).join("") + "</ul></section>");

    out.push('<section class="pa-card" aria-labelledby="pa-trans"><h2 id="pa-trans">Transitions</h2><p class="pa-card-sub">' + cats.compatible +
      " compatible &middot; " + cats.energy_boost + " energy boost &middot; " + cats.energy_drop + " energy drop &middot; " + cats.clash + " clash &middot; " +
      s.tempo_flags.tricky + " tricky and " + s.tempo_flags.hard + " hard tempo jumps</p>" +
      '<div class="pa-table-wrap"><table class="pa-table"><thead><tr><th class="pa-num">#</th><th>From</th><th>To</th><th class="pa-num">Keys</th>' +
      '<th>Harmony</th><th class="pa-num">BPM &Delta;</th><th>Tempo</th><th class="pa-num">Energy &Delta;</th><th class="pa-num">Score</th></tr></thead><tbody>' +
      r.transitions.map(function (t) {
        var a = byPos[t.position], b = byPos[t.position + 1];
        return '<tr><td class="pa-num pa-muted">' + t.position + "&rarr;" + (t.position + 1) + "</td><td>" + trackCell(a[0], a[1]) + "</td><td>" +
          trackCell(b[0], b[1]) + '</td><td class="pa-num">' + esc(t.from_key) + " &rarr; " + esc(t.to_key) + "</td><td>" + badge(t.category, CATEGORY_LABELS) +
          '<div class="pa-artist">' + esc(t.rule) + '</div></td><td class="pa-num">' + signed(t.bpm_delta) + "</td><td>" + badge(t.tempo_flag, TEMPO_LABELS) +
          '</td><td class="pa-num">' + signed(t.energy_delta) + '</td><td class="pa-num">' + roundHalfUp(t.score * 100) + "</td></tr>";
      }).join("") + "</tbody></table></div></section>");

    out.push('<section class="pa-card" aria-labelledby="pa-order"><h2 id="pa-order">Suggested order</h2>');
    if (so.kept_original) {
      out.push('<p class="pa-card-sub">The current order already scores best (' + so.flow_before + "/100). No reordering suggested.</p></section>");
    } else {
      out.push('<p class="pa-card-sub">Flow score <strong>' + so.flow_before + "</strong> &rarr; <strong>" + so.flow_after + "</strong> (" + signed(so.improvement) +
        "). Energy shape becomes <strong>" + esc(so.energy_shape_after) + "</strong>. Same tracks, each used exactly once.</p>");
      out.push(svgEnergy(so.tracks.map(function (t) { return { position: t.new_position, title: t.title, artist: t.artist, energy: t.energy }; }),
        "Energy curve in the suggested order"));
      out.push('<div class="pa-table-wrap"><table class="pa-table"><thead><tr><th class="pa-num">New</th><th class="pa-num">Was</th><th>Track</th>' +
        '<th class="pa-num">Key</th><th class="pa-num">BPM</th><th class="pa-num">Energy</th><th>Into next</th></tr></thead><tbody>');
      so.tracks.forEach(function (t, i) {
        var nxt = so.transitions[i];
        var into = nxt ? badge(nxt.category, CATEGORY_LABELS) + " " + badge(nxt.tempo_flag, TEMPO_LABELS) : '<span class="pa-muted">end</span>';
        out.push('<tr><td class="pa-num">' + t.new_position + '</td><td class="pa-num pa-muted">' + t.original_position + "</td><td>" + trackCell(t.title, t.artist) +
          '</td><td class="pa-num">' + t.key + '</td><td class="pa-num">' + fmt(t.bpm) + '</td><td class="pa-num">' + fmt(t.energy) + "</td><td>" + into + "</td></tr>");
      });
      out.push("</tbody></table></div></section>");
    }
    return out.join("");
  }

  // -------------------------------------------------------- embedded data
  // Copies of examples/ so the demo works from file:// (no fetch needed).
  // tests/test_demo.py checks these stay byte-identical to the files.

  var EXAMPLES = {
    // BEGIN EXAMPLE sunset-drive.csv
    "sunset-drive.csv": String.raw`#,Title,Artist,Key,BPM,Energy,Duration,Genre,Added By
1,Golden Hour Overture,The Low Tides,C major,98,3,3:52,Downtempo,sam
2,Coastline Static,Mara Vey,Am,100,4,4:10,Chillwave,sam
3,Paper Lanterns,Juniper Atlas,9A,102,4,3:41,Indie Electronic,jo
4,Mile Marker 9,Halcyon Freight,E minor,104,5,4:25,Nu-Disco,sam
5,Saltwater Radio,The Low Tides,10A,106,6,3:58,Nu-Disco,jo
6,Neon Gulls,"Pocket Satellites, Ivo Brandt",D major,108,6,4:02,Synthpop,sam
7,Overpass Bloom,Mara Vey,11B,110,7,3:47,,jo
8,Long Shadows,Kite Orchard,F#m,112,8,4:33,Deep House,sam
9,Heat Shimmer,Juniper Atlas,11A,114,9,5:01,Deep House,sam
10,Tailwind Chorus,Pocket Satellites,C# minor,116,8,4:12,"House, Vocal",jo
11,Dusk Lane,Halcyon Freight,12B,114,7,3:55,Nu-Disco,sam
12,Afterglow Exit,Kite Orchard,12A,110,6,4:18,Chillwave,jo
13,Streetlight Hymn,The Low Tides,F# minor,106,5,3:36,Downtempo,sam
14,Last Light Home,Mara Vey,A,102,4,4:44,Downtempo,sam
`,
    // END EXAMPLE sunset-drive.csv
    // BEGIN EXAMPLE mixed-bag.json
    "mixed-bag.json": String.raw`{
  "name": "Mixed Bag",
  "tracks": [
    {
      "title": "Static Bloom",
      "artist": "Velvet Arcade",
      "key": "Am",
      "bpm": 124,
      "energy": 6,
      "duration_ms": 214000,
      "genre": "Electro Pop",
      "album": "Fictional Sampler Vol. 1"
    },
    {
      "title": "Thunder in Aisle Five",
      "artist": "The Cardboard Kings",
      "key": "B minor",
      "bpm": 130,
      "energy": 8,
      "duration_ms": 187000,
      "genre": "Garage Rock",
      "album": "Fictional Sampler Vol. 1"
    },
    {
      "title": "Lullaby for Robots",
      "artist": "Nina Okafor-Lind",
      "key": "F# minor",
      "bpm": 88,
      "energy": 2,
      "duration_ms": 262000,
      "genre": "Ambient",
      "album": "Fictional Sampler Vol. 1"
    },
    {
      "title": "Disco Ferry",
      "artist": "Glass Pelican",
      "key": "8B",
      "bpm": 126,
      "energy": 9,
      "duration_ms": 231000,
      "genre": "Disco",
      "album": "Fictional Sampler Vol. 1"
    },
    {
      "title": "Rain on Tin",
      "artist": "Moss & Marrow",
      "key": "Bbm",
      "bpm": 76,
      "energy": 3,
      "duration_ms": null,
      "genre": null,
      "album": "Fictional Sampler Vol. 1"
    },
    {
      "title": "Sprint Club",
      "artist": "Hyperlane",
      "key": "10A",
      "bpm": 140,
      "energy": 9,
      "duration_ms": 198000,
      "genre": "Drum & Bass",
      "album": "Fictional Sampler Vol. 1"
    },
    {
      "title": "Window Seat",
      "artist": "Moss & Marrow",
      "key": "G",
      "bpm": 100,
      "energy": 4,
      "duration_ms": 243000,
      "genre": "Folk",
      "album": "Fictional Sampler Vol. 1"
    },
    {
      "title": "Bassline Bakery",
      "artist": "Velvet Arcade",
      "key": "9A",
      "bpm": 128,
      "energy": 7,
      "duration_ms": 276000,
      "genre": "House",
      "album": "Fictional Sampler Vol. 1"
    },
    {
      "title": "Copper Moon",
      "artist": "Ana Lisboa Trio",
      "key": "C#m",
      "bpm": 118,
      "energy": 5,
      "duration_ms": 301000,
      "genre": "Jazz",
      "album": "Fictional Sampler Vol. 1"
    },
    {
      "title": "Hyperdrive Picnic",
      "artist": "Hyperlane",
      "key": "6B",
      "bpm": 132,
      "energy": 8,
      "duration_ms": 209000,
      "genre": "Electro",
      "album": "Fictional Sampler Vol. 1"
    },
    {
      "title": "Slow Orbit",
      "artist": "Nina Okafor-Lind",
      "key": "D minor",
      "bpm": 84,
      "energy": 3,
      "duration_ms": 288000,
      "genre": "Ambient",
      "album": "Fictional Sampler Vol. 1"
    },
    {
      "title": "Fever Ladder",
      "artist": "Glass Pelican",
      "key": "10B",
      "bpm": 122,
      "energy": 8,
      "duration_ms": 226000,
      "genre": "Disco",
      "album": "Fictional Sampler Vol. 1"
    },
    {
      "title": "Quiet Engine",
      "artist": "The Cardboard Kings",
      "key": "6A",
      "bpm": 114,
      "energy": 5,
      "duration_ms": 239000,
      "genre": "Indie Rock",
      "album": "Fictional Sampler Vol. 1"
    },
    {
      "title": "Night Bus Anthem",
      "artist": "Velvet Arcade",
      "key": "8A",
      "bpm": 126,
      "energy": 7,
      "duration_ms": 254000,
      "genre": "House",
      "album": "Fictional Sampler Vol. 1"
    }
  ]
}
`
    // END EXAMPLE mixed-bag.json
  };

  var API = {
    parseKey: parseKey, classifyKeys: classifyKeys, parse: parse, detectFormat: detectFormat,
    analyze: analyze, flowScore: flowScore, suggestOrder: suggestOrder, renderBody: renderBody,
    EXAMPLES: EXAMPLES, PlaylistParseError: PlaylistParseError, KeyParseError: KeyParseError
  };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  root.PlaylistAnalyzer = API;

  // -------------------------------------------------------------------- UI

  if (typeof document === "undefined") return;

  function $(id) { return document.getElementById(id); }

  function run() {
    var text = $("pa-input").value;
    var status = $("pa-status"), output = $("pa-output");
    if (!text.trim()) {
      status.className = "pa-status";
      status.textContent = "Paste a playlist (CSV, JSON or Artist - Title | key | bpm | energy lines), or load an example.";
      output.innerHTML = "";
      return;
    }
    try {
      var playlist = parse(text, $("pa-format").value, $("pa-name").value.trim() || "Pasted playlist", $("pa-lenient").checked);
      if ($("pa-name").value.trim()) playlist.name = $("pa-name").value.trim();
      var result = analyze(playlist);
      output.innerHTML = renderBody(result);
      status.className = "pa-status ok";
      status.textContent = "Analysed " + result.playlist.track_count + " tracks from " + result.playlist.source_format.toUpperCase() +
        ". Flow score " + result.flow_score + "/100.";
      lastResult = result;
      $("pa-download").disabled = false;
    } catch (e) {
      status.className = "pa-status error";
      status.textContent = e.message;
      output.innerHTML = "";
      lastResult = null;
      $("pa-download").disabled = true;
    }
  }

  var lastResult = null;

  function loadExample(name, title) {
    $("pa-input").value = EXAMPLES[name];
    $("pa-format").value = "auto";
    $("pa-name").value = title;
    run();
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    $("pa-output").scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    $("pa-output").focus({ preventScroll: true });
  }

  function init() {
    $("pa-analyze").addEventListener("click", run);
    $("pa-example-sunset").addEventListener("click", function () { loadExample("sunset-drive.csv", "Sunset Drive"); });
    $("pa-example-mixed").addEventListener("click", function () { loadExample("mixed-bag.json", "Mixed Bag"); });
    $("pa-clear").addEventListener("click", function () {
      $("pa-input").value = ""; $("pa-name").value = ""; $("pa-output").innerHTML = "";
      $("pa-status").className = "pa-status"; $("pa-status").textContent = "Cleared.";
      $("pa-download").disabled = true; lastResult = null;
    });
    $("pa-file").addEventListener("change", function (ev) {
      var file = ev.target.files[0];
      if (!file) return;
      var reader = new FileReader();
      reader.onload = function () {
        $("pa-input").value = reader.result;
        $("pa-name").value = file.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
        run();
      };
      reader.readAsText(file);
    });
    $("pa-download").addEventListener("click", function () {
      if (!lastResult) return;
      var blob = new Blob([JSON.stringify(lastResult, null, 2) + "\n"], { type: "application/json" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = (lastResult.playlist.name || "playlist").toLowerCase().replace(/[^a-z0-9]+/g, "-") + "-analysis.json";
      document.body.appendChild(a); a.click(); a.remove();
    });
    $("pa-input").addEventListener("keydown", function (ev) {
      if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") run();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})(typeof globalThis !== "undefined" ? globalThis : this);
