# The music theory behind playlist-analyzer

This is a beginner's guide to the ideas the analyzer uses. You don't need to read music. If you can count to twelve, you can follow it.

Contents:

1. [Notes, keys and why they matter](#1-notes-keys-and-why-they-matter)
2. [The circle of fifths](#2-the-circle-of-fifths)
3. [The Camelot wheel](#3-the-camelot-wheel)
4. [Harmonic mixing rules](#4-harmonic-mixing-rules)
5. [Tempo and beatmatching](#5-tempo-and-beatmatching)
6. [Reading an energy curve](#6-reading-an-energy-curve)
7. [How the flow score and the reorder work](#7-how-the-flow-score-and-the-reorder-work)
8. [What this tool cannot do](#8-what-this-tool-cannot-do)

---

## 1. Notes, keys and why they matter

Western music uses 12 notes that repeat in every octave:

```
C  C#/Db  D  D#/Eb  E  F  F#/Gb  G  G#/Ab  A  A#/Bb  B   (then C again)
```

A **key** is a home note plus a family of seven of those twelve notes that the song mostly uses. C major uses only the white keys of a piano: `C D E F G A B`.

Keys come in two flavours:

- **Major** keys tend to sound bright or settled.
- **Minor** keys tend to sound darker or more wistful.

Every major key has a **relative minor** built from exactly the same seven notes, starting somewhere else. A minor uses `A B C D E F G`, the same white keys as C major. Same notes, different home, different mood.

**Why DJs and playlist makers care:** when one song fades into the next, for a few seconds you hear both at once. If they share most of their notes, the overlap sounds like one piece of music. If they share very few, you hear two songs fighting: a sour, "wrong" sound. That is a **clash**.

## 2. The circle of fifths

A **fifth** is the jump from one note up seven semitones (seven piano keys, black and white counted). C up a fifth is G. G up a fifth is D. Keep going and you visit all twelve notes before landing on C again:

```
C → G → D → A → E → B → F# → C# (Db) → G# (Ab) → D# (Eb) → A# (Bb) → F → C
```

Arrange those twelve keys in a circle and you have the **circle of fifths**.

**The useful part:** keys that sit next to each other on the circle differ by exactly one note.

> **Worked example.**
> C major: `C D E F G A B`
> G major (one step clockwise): `C D E F# G A B`
> Six of the seven notes are shared. Only F becomes F#.
>
> Now jump across the circle. F# major: `F# G# A# B C# D# E#`. Against C major it shares only B and E# (which sounds the same as F). Two out of seven notes.

So distance on the circle is a measure of how different two keys sound. Neighbours blend; opposites clash. Every step round the circle swaps one note, so two steps swaps two notes, and so on.

## 3. The Camelot wheel

The circle of fifths is useful, but note names with sharps and flats are hard to scan quickly, especially in a dark DJ booth. The **Camelot wheel** (popularised by DJ software such as Mixed In Key) relabels the same circle with simple codes:

- A **number from 1 to 12**: the position on the circle. One step = one fifth.
- A **letter**: **B** for major keys (outer ring), **A** for minor keys (inner ring).

A major key and its relative minor share a number, because they share all their notes.

| Number | A (minor, inner) | B (major, outer) |
|-------:|------------------|------------------|
| 1  | Ab minor (G# minor) | B major |
| 2  | Eb minor (D# minor) | F# major (Gb) |
| 3  | Bb minor | Db major (C#) |
| 4  | F minor | Ab major |
| 5  | C minor | Eb major |
| 6  | G minor | Bb major |
| 7  | D minor | F major |
| 8  | A minor | C major |
| 9  | E minor | G major |
| 10 | B minor | D major |
| 11 | F# minor | A major |
| 12 | C# minor (Db minor) | E major |

**How to read it.** Find your track's code, for example **8A** (A minor). Moving one number up or down (7A, 9A) is one step round the circle of fifths. Swapping the letter (8B) moves to the relative major, which has the same notes. The numbers wrap around like a clock, so 12A sits next to 1A.

The analyzer accepts any of these spellings and converts them to a Camelot code: `8A`, `A minor`, `Am`, `a min`, `A-`, `C major`, `C`, `Cmaj`, `F#m`, `F♯ minor`, `E flat minor`, `Bbm` and so on. A bare note name such as `C` means C major. Try it from the command line:

```
$ python3 -m playlist_analyzer key "E flat minor"
E flat minor = 2A (Eb minor)
Compatible: 2A Eb minor, 1A Ab minor, 3A Bb minor, 2B F# major
Energy boost (+2): 4A F minor
Energy drop (-2):  12A C# minor
Clashes (18): 1B, 3B, 4B, 5A, 5B, 6A, 6B, 7A, 7B, 8A, 8B, 9A, 9B, 10A, 10B, 11A, 11B, 12B
```

## 4. Harmonic mixing rules

**Harmonic mixing** means choosing the next track so its key sits comfortably next to the current one. The analyzer implements exactly these rules and nothing else:

| Move | Example | Classified as | Why |
|------|---------|---------------|-----|
| Same code | 8A → 8A | **compatible** | Identical notes. |
| ±1, same letter | 8A → 9A, 8A → 7A | **compatible** | One fifth apart: six of seven notes shared. |
| Same number, letter swap | 8A → 8B | **compatible** | Relative major/minor: all seven notes shared, only the mood shifts. |
| +2, same letter | 8A → 10A | **energy boost** | Up a whole tone. Five notes shared, so it still holds together, but the lift is audible. DJs use it on purpose to raise the room. |
| −2, same letter | 8A → 6A | **energy drop** | Down a whole tone. The same idea in reverse: a deliberate cool-down. |
| Anything else | 8A → 3B, 8A → 9B | **clash** | Too few shared notes, or a combined step-and-mode-change. |

> **Worked example.** A minor (8A) `A B C D E F G` into B minor (10A) `B C# D E F# G A`. Shared: A, B, D, E, G, five of seven. The two changed notes (C→C#, F→F#) are what you hear as a "lift".

A few notes on the choices:

- **Diagonal moves** such as 8A → 9B are treated as clashes. Some DJs like them as a mood change, but they combine a step and a mode switch, and enough listeners hear them as off that the analyzer flags them. If one sounds good to you, trust your ears.
- Some guides also list "+7" (one semitone up) as an energy boost. The analyzer does **not** use that rule, because it shares very few notes and only works with a quick cut, not a long blend.
- Every key has exactly 4 compatible neighbours (including itself), 1 energy-boost key, 1 energy-drop key, and 18 clashes. That is why random shuffles clash so often.

## 5. Tempo and beatmatching

**Tempo** is measured in **BPM**, beats per minute. Most pop and house music sits between about 100 and 130 BPM; hip-hop is often 85-100; drum & bass is around 170.

**Beatmatching** is lining up the beats of two tracks so the kick drums land together during a transition. To do it, a DJ speeds up or slows down one track, usually with a pitch fader that covers about ±6 to ±8 percent.

**Why small gaps are fine and big ones are not:**

- A 4 BPM gap at 120 BPM is about a 3% change. Nobody notices; the mix is smooth.
- A 6 BPM gap is about 5%. Still workable, but you are near the edge of a comfortable pitch adjustment.
- Beyond that the stretched track starts to sound wrong: vocals go chipmunk or sludgy, and without "key lock" the track's key shifts too. Around 6% of speed change moves a song by roughly a semitone, which on the Camelot wheel is a jump of seven steps: a guaranteed clash.

So the analyzer flags each transition:

| BPM gap between consecutive tracks | Flag | Meaning |
|---|---|---|
| 6 or less | smooth | Easy to beatmatch. |
| over 6, up to 10 | tricky | Possible, but noticeable. |
| over 10 | hard jump | Hard to blend; it will feel like a gear change. |

> **Worked example.** 124 BPM → 128 BPM: gap 4, smooth. 128 → 118: gap 10, tricky. 118 → 132: gap 14, hard jump.

**What DJs do about big jumps:** build tempo gradually over several tracks; use a quick cut, an echo-out or a drop-to-silence instead of a long blend; or play the next track at **half or double time** (a 70 BPM track feels similar to a 140 BPM one). The analyzer compares raw BPM numbers only; it does not try the half/double-time trick, so a 70 → 140 move is flagged as a hard jump even though a DJ could make it work.

## 6. Reading an energy curve

**Energy** is a 0-10 score for how intense a track feels: loudness, density, drive. It comes from your export (Mixed In Key and similar tools write 1-10; Spotify-style exports use 0-1; some tools use 0-100). The analyzer detects the scale from the whole playlist and rescales to 0-10: if every value is 1 or less it assumes 0-1, if any value is above 10 it assumes 0-100.

Plot energy against track order and you get the **energy curve**. The analyzer gives it one of four shapes:

| Shape | Rule | Looks like |
|-------|------|------------|
| flat | highest minus lowest is under 2 points | `▄▄▄▄▄▄` |
| rising | energy correlates with position (Pearson r ≥ 0.6) | `▁▂▄▅▇█` |
| falling | r ≤ −0.6 | `█▇▅▄▂▁` |
| peak-and-valley | anything else | `▂▅█▅▂` or `▇▂█▁▇` |

It also says in plain words whether a peak-and-valley curve is a proper **arc** (a single climb to a peak in the middle and a wind-down after) or just swinging up and down. It reports the peak track, the lowest track, and the biggest single-step rises and drops.

**Why order matters**, even with the same songs:

- **A DJ set** usually warms up, builds to a peak about two-thirds of the way through, then gives the crowd a landing. Big sudden drops empty a dance floor; a long flat stretch bores it.
- **A workout** wants a short warm-up, a long high plateau with a couple of pushes, then a cool-down. A slow ballad in the middle of the intervals kills momentum.
- **A road trip** wants gentle waves: lift for the motorway, ease off for the scenic stretch, never a jarring jump that makes someone reach for the volume knob.

> **Worked example.** Energies `3 4 4 5 6 6 7 8 9 8 7 6 5 4` (the `sunset-drive.csv` sample) climb steadily to 9 at track 9 of 14, then ease off one step at a time. The biggest single change is ±1. That is a textbook arc. The `mixed-bag.json` sample goes `6 8 2 9 3 9 4 7 …`: rises and drops of 5-7 points between neighbours. Same kind of songs; much rougher ride.

## 7. How the flow score and the reorder work

### Flow score (0-100)

Each consecutive pair of tracks gets a score between 0 and 1:

```
pair = 0.5 × key + 0.3 × tempo + 0.2 × energy

key    = 1.0 compatible · 0.75 energy boost or drop · 0.0 clash
tempo  = 1.0 if BPM gap ≤ 6 · 0.5 if ≤ 10 · 0.0 above 10
energy = 1.0 if energy change ≤ 2 · 0.5 if ≤ 4 · 0.0 above 4
```

The flow score is the average pair score × 100, rounded (halves round up). A playlist with one track has no transitions and scores 100. Key matters most because a clash is the most audible problem. Tempo comes next. Energy jumps matter least because a big jump is sometimes on purpose.

> **Worked example.** 8A @120 BPM, energy 5 → 9A @122, energy 6: compatible, gap 2, change 1 → 0.5 + 0.3 + 0.2 = **1.0**.
> 9A @122, energy 6 → 3B @140, energy 9: clash, gap 18, change 3 → 0 + 0 + 0.1 = **0.1**.
> Two transitions, average 0.55 → flow score **55**.

### Suggested order

The reorder is a **greedy walk round the Camelot wheel**:

1. It sets a target energy arc for the playlist: a climb to the playlist's own highest energy about 70% of the way through, then a landing at 60% of the energy range.
2. Starting from a track, it repeatedly picks the unused track with the lowest cost, where cost = (1 − pair score) + 0.3 × (distance from the target energy for that slot, as a fraction of the energy range). Ties go to the track that came first in your playlist, so results are repeatable.
3. It repeats the walk from every possible starting track (the 24 lowest-energy starts for very long playlists) and keeps the best result.
4. Your original order is always one of the candidates, and any walk with a lower flow score than yours is thrown away. **The suggestion can never score worse than what you started with.** Every walk places each track exactly once: nothing is dropped or duplicated. The test suite checks both promises on the samples and on hundreds of random playlists.

Greedy means it is fast and easy to explain, but not guaranteed to find the best possible order. It is a strong first draft, not an oracle. If your tracks are spread across distant keys and tempos, no order can make them all compatible; the suggestion just makes the best of it.

## 8. What this tool cannot do

Being honest about the limits:

- **It cannot fetch your library.** There is no Spotify, Apple Music, YouTube or SoundCloud connection; those need API keys and accounts, and this project uses neither. You export a playlist yourself (from DJ software, a spreadsheet, or an export tool) and give the analyzer the file.
- **It cannot detect key, tempo or energy from audio.** It never sees audio. Every key, BPM and energy value comes from the data you supply. If the export is wrong, the analysis is wrong.
- **It cannot play music**, preview transitions, or beatmatch anything for you.
- **It does not judge taste.** A "clash" can be a brilliant creative choice, and a "compatible" mix can still be dull. The rules describe what tends to sound smooth, not what is good.
- **Tempo is compared as raw BPM**, without half/double-time matching, and key is compared without considering pitch-shifting or key lock.
