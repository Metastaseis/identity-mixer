"""manual.py — melodies written by hand, as plain notes on the grid.

For a song whose recording does not carry the tune clearly (spoken, very free, several voices), the
melody people know is written here instead of being taken from the singer. arr.py uses an entry here
in place of the pitch track and of the detected chords; rendering and stems are the same.

Each song:
  units    grid steps across the 8-bar loop
  melody   [(first step, steps, note)] in the library key (F major / D minor); steps may be fractions
  chords   chord names in the library key, evenly spread over the loop: 8 = one per bar, 16 = one per half bar,
           24 = one per beat of a 3/4 bar, 32 = one per beat, 48 = two per beat of a 3/4 bar. Names: F, Dm, C7, Gm7, Fmaj7, Edim, Em7b5, Csus4, C7sus4,
           F6, Gm6, D5, and a bass note after a slash (C/E).
Optional:
  beats    accompaniment beats per bar: 4 (default) or 3 (a song in 3/4: the bar is split in three)
  style    how the harmony instrument plays (see arr.STYLE), overriding arr.STYLE[slug]
  bass     [(first step, steps, note)]: the bass line written out, instead of roots and fifths;
           or "eighths": the root on every eighth note
  lead     General MIDI program of the melody instrument (default 73, flute)
  drums    dict(kit=GM drum kit (bank 128 program), bars=[eight bars, each [(sixteenth 0-15, GM drum key, velocity)]]):
           the drum part, written by arr.py as a track named "drums" on the drum channel
"""

SONGS = {
    # Verse, lines 1-3, in 6/8: one step = one eighth note, six to a bar. Original key C, here in F.
    #   syllables per phrase: 1 | 4 | 4 | 5 | 5 |
    #   5 | 3 | 1 | (rest) 1
    "culture-hallelujah": dict(
        units=48,
        melody=[
            # the lilt of the tune: long-short, long-short; quick pairs of syllables are half steps
            (0, 2, "C5"), (2, 1, "C5"), (3, 2, "C5"), (5, 1, "C5"),                              # bar 1: 4 syllables
            (6, 2, "D5"), (8, 1, "D5"), (9, 2, "D5"), (11, 1, "A4"),                             # bar 2: 4 syllables
            (12, 2, "C5"), (14, 1, "C5"), (15, 2, "C5"), (17, 0.5, "C5"), (17.5, 0.5, "C5"),     # bar 3: 5 syllables
            (18, 2, "D5"), (20, 1, "D5"), (21, 2, "D5"), (23, 0.5, "D5"), (23.5, 0.5, "D5"),     # bar 4: 5 syllables
            (24, 2, "D5"), (26, 0.5, "D5"), (26.5, 0.5, "D5"), (27, 2, "D5"), (29, 1, "D5"),     # bar 5: 5 syllables
            (30, 2, "C5"), (32, 1, "C5"), (33, 3, "Bb4"),                                        # bar 6: 3 syllables
            (36, 6, "C5"),                                                                       # bar 7: 1 syllable
            (47, 1, "A4"),                                                                       # bar 8: 1 syllable (leads back into bar 1)
        ],
        chords=["F", "Dm", "F", "Dm", "Bb", "C", "F", "C"],
    ),
    # Verse 1, four lines of two bars, in 4/4: one step = one sixteenth, sixteen to a bar. Original key E, here in F.
    # Read off Arik Einstein's vocal track syllable by syllable; his three low pick-up syllables are sung between
    # two notes and are written as the fifth below the tonic. Chords read from the backing (bar 7 simplified).
    "lifestyle-shabbat-baboker": dict(
        units=128,
        melody=[
            (2, 4, "A4"), (6, 1, "A4"), (7, 1, "G4"), (8, 2, "G4"), (10, 4, "F4"),              # bar 1: 5 syllables
            (16, 3, "A4"), (20, 2, "A4"), (22, 5, "G4"),                                         # bar 2: 3 syllables
            (36, 2, "A4"), (38, 2, "A4"), (40, 2, "G4"), (42, 4, "G4"),                          # bar 3: 4 syllables
            (46, 2, "C4"), (48, 3, "A4"), (52, 2, "A4"), (54, 5, "G4"),                          # bar 3: 4 syllables
            (64, 2, "C4"), (66, 2, "D4"), (68, 3, "F4"), (71, 4, "A4"),                          # bar 5: 4 syllables
            (82, 2, "C4"), (84, 2, "A4"), (86, 4, "G4"), (90, 4, "F4"),                          # bar 6: 4 syllables
            (98, 2, "C4"), (100, 3, "A4"), (103, 1, "G4"), (104, 3, "G4"),                       # bar 7: 4 syllables
            (111, 4, "A4"), (115, 1, "A4"), (116, 3, "C5"), (119, 3, "D5"), (122, 5, "C5"),      # bar 7: 5 syllables
        ],
        chords=["F", "F", "G", "G", "Gm", "C", "F", "C", "F", "F", "G", "Dm", "F", "C", "F", "Dm"],
    ),
    # The first eight bars as sung by Rinat, in 4/4: one step = one sixteenth. Original key G, here in F.
    # Bars 1-5 are the verse lines (a b a b a), bars 6-8 the two-note chant that follows. The beat tracker sits
    # half a beat late on this recording (it locked onto the off-beat chords); the steps below are on the real beat.
    # Chords: the record alternates two chords a tone apart under a melody that leans on the tonic; written here
    # as IV - I so that nothing rubs against the tune. Written an octave above her voice: the sampled flute is weak down there.
    "lifestyle-leitzan-katan": dict(
        units=128,
        melody=[
            (0, 2, "C5"), (2, 2, "C5"), (4, 2, "D5"), (6, 2, "G5"), (8, 2, "F5"), (10, 4, "F5"),            # line a
            (16, 2, "F5"), (18, 2, "G5"), (20, 2, "F5"), (22, 2, "G5"), (24, 2, "F5"), (26, 4, "C5"),       # line b
            (31, 1, "C5"),
            (32, 2, "C5"), (34, 2, "Bb4"), (36, 2, "D5"), (38, 2, "G5"), (40, 2, "F5"), (42, 5, "F5"),      # line a
            (48, 2, "F5"), (50, 2, "G5"), (52, 2, "F5"), (54, 2, "G5"), (56, 2, "F5"), (58, 4, "C5"),       # line b
            (64, 2, "C5"), (66, 2, "Bb4"), (68, 2, "D5"), (70, 2, "G5"), (72, 2, "F5"), (74, 4, "F5"),      # line a
            (80, 3, "F5"), (83, 2, "G5"), (88, 3, "F5"), (91, 2, "G5"),                                     # chant
            (96, 3, "F5"), (99, 1, "G5"), (100, 2, "F5"), (102, 2, "G5"), (104, 2, "G5"), (106, 5, "F5"),   # chant, second half
            (112, 3, "F5"), (115, 2, "G5"), (120, 3, "F5"), (123, 3, "G5"),                                 # chant
        ],
        chords=["Bb", "F", "Bb", "F", "Bb", "F", "Bb", "F", "Bb", "F", "F", "F", "F", "F", "F", "F"],
    ),
    # The verse, one voice, in 4/4: one step = one sixteenth. Original key C (the record is tuned low), here in F.
    #   syllables per phrase: 8 | (answer in the band) 4 | 4 | 7
    # The record is sung by a group, so the pitch track hops between voices; these notes are the top line that
    # the three passes through the verse (0:55, 2:39, 2:56) agree on. Bar 3 is empty in the singing.
    "memory-rivers-of-babylon": dict(
        units=128,
        melody=[
            (4, 1, "C4"), (5, 1, "C4"), (6, 2, "C4"), (8, 2, "F4"), (10, 2, "F4"), (12, 4, "G4"),     # bar 1: 6 syllables
            (16, 4, "A4"), (20, 7, "A4"),                                                             # bar 2: 2 syllables
            (48, 2, "A4"), (50, 2, "A4"), (52, 2, "A4"), (54, 5, "A4"),                               # bar 4: 4 syllables
            (72, 4, "Bb4"), (76, 2, "A4"), (78, 2, "G4"), (80, 6, "G4"),                              # bar 5: 4 syllables
            (98, 2, "G4"), (100, 2, "G4"), (102, 2, "G4"), (104, 2, "G4"), (106, 3, "G4"),            # bar 7: 5 syllables
            (114, 4, "F4"), (118, 7, "F4"),                                                           # bar 8: 2 syllables
        ],
        chords=["F", "F", "F", "F", "F", "F", "F", "F", "F", "Gm", "C", "C", "C", "C", "F", "F"],
    ),
    # Verse 1, lines 1-2 as Yehoram Gaon sings them (1965), in 3/4: one step = one sixteenth, twelve to a bar; one bar of
    # the loop is one bar of the song. Original key D minor a quarter-tone sharp, here D minor.
    #   syllables per phrase: 7 | 2 | 1, (2 | 1) | 9 | 6 | 1
    # The record has one plucked line under the voice and no chords; that line is the bass here (i - iv - VII - III, then
    # the falling i - VII - VI - V), and the guitar fills in the same chords quietly.
    "hebrew-durme-durme": dict(
        units=96, beats=3, style="arp",
        melody=[
            (0, 5.5, "D4"), (6, 2, "E4"), (8, 1, "F4"), (9, 1, "G4"), (10, 1, "G4"), (11, 1, "A4"),               # bar 1: 6 syllables
            (12, 8, "A4"), (20, 3.75, "D5"),                                                                       # bar 2: 2 syllables
            (24, 4.5, "C5"), (30, 2, "A4"), (32, 3.75, "Bb4"),                                                     # bar 3: 2 syllables
            (36, 6, "A4"),
            (48, 2, "G4"), (50, 3, "G4"), (53, 1, "G4"), (54, 0.75, "A4"), (54.75, 1.25, "Bb4"),                   # bar 5: 5 syllables
            (56, 0.75, "G4"), (56.75, 2, "A4"), (58.75, 1.25, "F4"),                                               # bar 5: 4 syllables
            (60, 3.5, "F4"), (66, 1, "E4"), (67, 2.25, "G4"), (69.25, 1.25, "G4"), (70.5, 3.5, "F4"),              # bar 6: 6 syllables
            (74, 1.75, "E4"), (75.75, 2.25, "D4"), (78, 9.5, "A4"),                                                # bar 7: 1 syllable
        ],
        chords=["Dm"] * 6 + ["Dm"] * 4 + ["Gm"] * 2 + ["Gm", "Gm", "C", "C", "F", "F"] + ["F"] * 4 + ["C/G"] * 2
               + ["Dm"] * 4 + ["F"] * 2 + ["Dm", "Dm", "Dm/F", "C7/E", "C7/E", "C7/E"] + ["Bb", "Bb", "Eb", "A7/E", "A", "A"] + ["A"] * 3 + ["A7/G"] * 3,
        bass=[
            (0, 2, "A1"), (2, 4, "D2"), (6, 4, "A1"), (10, 2, "D2"),
            (12, 4, "D2"), (16, 4, "D2"), (20, 4, "G2"),
            (24, 4, "G2"), (28, 4, "C3"), (32, 4, "F2"),
            (36, 2, "F2"), (38, 2, "C3"), (40, 4, "F2"), (44, 4, "G2"),
            (48, 4, "D2"), (52, 4, "D2"), (56, 2, "F2"), (58, 2, "G2"),
            (60, 4, "D2"), (64, 2, "F2"), (66, 2, "E2"), (68, 4, "E2"),
            (72, 2, "Bb2"), (74, 2, "D3"), (76, 2, "Eb3"), (78, 2, "E3"), (80, 4, "A2"),
            (84, 4, "A2"), (88, 2, "A2"), (90, 6, "G2"),
        ],
    ),
    # Verse 1, lines 1-4 as Matti Caspi sings them, in 4/4: one step = one sixteenth. Original key C minor, here D minor.
    #   syllables per phrase: (3) | 6 | 6 | 5 | 6 |
    #   8 | 5 | 6 | (3)
    # The loop starts on the bar line of the band (where the chords change), two beats after the tracked bar line the first
    # version used; the three pick-up notes sit at the end of bar 8. Chords read from the guitar and the bass:
    # Dm - Bbmaj7 - Gm - C - Cm7 F7 - Bbmaj7 - Gm - A7sus4 over E, A7; the guitar comps a bossa pattern, the bass plays root, fifth, root, root.
    "hebrew-eliezer-ben-yehuda": dict(
        units=128, style="bossa",
        melody=[
            (0, 3, "A4"), (4, 2, "G4"), (6, 2.5, "A4"), (10, 2, "D4"), (12, 2, "E4"), (14, 2, "F4"),               # bar 1: 6 syllables
            (16, 2, "A4"), (18, 3, "G4"), (22, 3, "A4"), (28, 1, "Bb4"), (29, 1, "A4"), (30, 1, "A4"), (31, 4, "G4"),   # bar 2: 6 syllables
            (38, 2, "F4"), (40, 2, "E4"), (42, 2, "D4"), (44, 2, "E4"), (46, 2, "F4"),                              # bar 3: 5 syllables
            (48, 2, "G4"), (50, 2, "F4"), (52, 3.5, "A4"), (56, 2.5, "G4"), (60, 2, "G4"), (62, 2, "A4"),           # bar 4: 6 syllables
            (64, 2, "C5"), (66, 3.5, "C5"), (70, 2, "D5"), (72, 1, "C5"), (73, 1, "Bb4"), (74, 1.5, "A4"),          # bar 5: 6 syllables
            (76, 1, "A4"), (77, 4, "G4"),                                                                           # bar 5: 2 syllables
            (81, 3, "A4"), (90, 1, "G4"), (91, 2, "F4"), (93, 2, "E4"), (95, 2, "F4"),                              # bar 6: 5 syllables
            (97, 2, "E4"), (99, 3, "D4"), (102, 4, "F4"), (106, 2, "E4"), (108, 1, "A4"), (109, 2, "G#4"), (111, 4, "G4"),   # bar 7: 6 syllables (falls A G# G)
            (123, 1, "D4"), (124, 2, "E4"), (126, 2, "F4"),                                                         # bar 8: 3 syllables
        ],
        chords=["Dm", "Dm", "Bbmaj7", "Bbmaj7", "Gm", "Gm", "C", "C", "Cm7", "F7", "Bbmaj7", "Bbmaj7", "Gm", "Gm", "A7sus4/E", "A7"],
        bass=[
            (0, 4, "D2"), (4, 4, "A2"), (8, 4, "D2"), (12, 4, "D2"), (16, 4, "Bb2"), (20, 4, "F2"), (24, 4, "Bb2"), (28, 4, "Bb2"),
            (32, 4, "G2"), (36, 4, "D3"), (40, 4, "G2"), (44, 4, "G2"), (48, 4, "C3"), (52, 4, "G2"), (56, 4, "C3"), (60, 4, "G2"),
            (64, 4, "C3"), (68, 4, "C3"), (72, 4, "F2"), (76, 4, "F2"), (80, 4, "Bb2"), (84, 4, "F2"), (88, 4, "Bb2"), (92, 4, "Bb2"),
            (96, 4, "G2"), (100, 4, "D3"), (104, 4, "G2"), (108, 4, "G2"), (112, 4, "E2"), (116, 4, "E2"), (120, 4, "A2"), (124, 4, "A2"),
        ],
    ),
    # Verse 1, four lines of two bars, as Uzi Hitman sings them, in 4/4: one step = one sixteenth. The record is in
    # B minor (the tune starts on the third, which is why it was first read as D major); here D minor.
    #   syllables per phrase: (rest) 4 | 4 | 4 | 4 | 3 | 5 | 5 | 4
    # Each line starts half a bar before the chord changes, as on the record. Chords from the keyboard and the bass:
    # Dm | Gm6 over D | (same) | C7 | C7 | Fmaj7 | Am, A/C# | Dm. The band plays steady eighths.
    "hebrew-adon-olam": dict(
        units=128, style="eighths", bass="eighths",
        melody=[
            (8, 2, "F4"), (10, 2, "F4"), (12, 2, "G4"), (14, 2, "G4"),                                              # bar 1: 4 syllables
            (16, 3, "A4"), (19, 2, "G4"), (21, 5, "A4"), (26, 2, "Bb4"), (28, 7.5, "G4"),                           # bar 2: 4 syllables
            (41, 1, "F4"), (42, 1.5, "F4"), (43.5, 2, "G4"), (45.5, 4, "F4"),                                       # bar 3: 4 syllables
            (50, 3, "G4"), (53, 2, "G4"), (55, 4, "G4"), (59, 4, "G4"),                                             # bar 4: 4 syllables
            (73, 3, "E4"), (76, 4, "F4"), (80, 3, "G4"),                                                            # bar 5: 3 syllables
            (83, 3, "A4"), (86, 3, "A4"), (89, 2, "A4"), (91, 3, "A4"), (94, 2, "G4"),                              # bar 6: 5 syllables
            (96, 2, "F4"), (98, 4, "E4"), (105, 1, "A4"), (106, 3, "A4"), (109, 2, "A4"), (111, 2, "G4"),           # bar 7: 5 syllables
            (113, 1, "A4"), (114, 4, "A4"), (118, 3, "A4"), (121, 4, "A4"),                                         # bar 8: 4 syllables
        ],
        chords=["Dm", "Dm", "Gm6/D", "Gm6/D", "Gm6/D", "Gm/D", "C7", "C7", "C7", "C7", "Fmaj7", "Fmaj7", "Am", "A/C#", "Dm", "Dm"],
    ),
    # The chorus (the title line), as Yehoram Gaon sings it, in 4/4: one step = one sixteenth. Original key E flat, here F.
    # The tune is the chorus of "City of New Orleans" (Steve Goodman). The first version looped the first verse instead.
    #   syllables per phrase: (rest) 8 | 1 | 8 | 2 |
    #   6 | 7 | 9 | 1
    # Written an octave above his voice. Chords and the walking bass read from the band: Bb C | F | Dm Bb C | F C7 | F Am | Dm G | Bb C | F.
    "israel-shalom-lach-eretz": dict(
        units=128, style="folk",
        melody=[
            (4, 1, "F5"), (5, 1, "F5"), (6, 2, "F5"), (8, 2, "E5"), (10, 2, "E5"), (12, 1, "E5"), (13, 2, "D5"), (15, 3, "C5"),      # bar 1: 8 syllables
            (18, 6, "F4"),                                                                                                           # bar 2: 1 syllable
            (33, 1.5, "A4"), (34.5, 3, "A4"), (38, 2, "F4"), (40, 2, "Bb4"), (42, 2, "D5"), (44, 1.5, "C5"), (45.5, 1.5, "C5"),      # bar 3: 7 syllables
            (47, 9, "C5"), (58, 3.5, "C5"), (61.5, 2, "Bb4"), (63.5, 5, "A4"),                                                       # bar 3: 3 syllables
            (73, 1, "C5"), (74, 1, "C5"), (75, 2, "C5"), (77, 2, "D5"), (79, 1, "A4"), (80, 2, "A4"),                                # bar 5: 6 syllables
            (82, 1, "F4"), (83, 1, "F4"), (84, 2, "F4"), (86, 1, "F4"), (87, 1.5, "F4"),                                             # bar 6: 6 syllables
            (95, 1, "Bb4"), (96, 1.5, "Bb4"), (97.5, 1.5, "Bb4"), (99, 1.5, "Bb4"), (100.5, 1.5, "Bb4"),                             # bar 6: 5 syllables
            (104.5, 1.5, "F4"), (106, 1.5, "G4"), (107.5, 2, "F4"), (109.5, 1.5, "E4"), (111, 1, "F4"), (112, 4.5, "F4"),            # bar 7: 6 syllables
        ],
        chords=["Bb", "Bb", "C", "C", "F", "F", "F", "Am/E", "Dm", "Dm", "Bb", "C", "F", "F", "C7", "C7",
                "F", "F", "Am", "Am", "Dm", "Dm", "G", "G", "Bb", "Bb", "C", "C", "F", "F", "F", "F"],
        bass=[
            (0, 4, "Bb2"), (4, 4, "D3"), (8, 4, "C3"), (12, 4, "E3"), (16, 4, "F2"), (20, 4, "A2"), (24, 4, "F2"), (28, 4, "E2"),
            (32, 4, "D2"), (36, 4, "A2"), (40, 4, "Bb2"), (44, 4, "C3"), (48, 4, "F2"), (52, 4, "C3"), (56, 4, "C3"), (60, 4, "G2"),
            (64, 4, "F2"), (68, 4, "C3"), (72, 4, "A2"), (76, 4, "E2"), (80, 4, "D2"), (84, 4, "D2"), (88, 4, "G2"), (92, 4, "A2"),
            (96, 4, "Bb2"), (100, 4, "D3"), (104, 4, "C3"), (108, 4, "E3"), (112, 4, "F2"), (116, 4, "C3"), (120, 4, "F2"), (124, 4, "A2"),
        ],
        # Drums: the separated drum track of this section shows an even eighth-note pulse but no beat that recurs in half
        # the bars (pipeline/arrange/drums.py), so this is written in the song's folk feel instead: kick on 1 and 3,
        # a soft snare on 2 and 4, eighth-note hats. Jazz kit.
        drums=dict(kit=32, bars=[[(0, 36, 95), (8, 36, 85), (4, 38, 70), (12, 38, 75)]
                                 + [(e, 42, 70 if e % 4 == 0 else 50) for e in range(0, 16, 2)]] * 8),
    ),
    # The opening phrase as sung on the record (Porat Nov with Sinai Tor), one step = one sixteenth of the loop's 4/4.
    # The song's own beat is half the tracked one (68 to the minute, the drum plays dum - dum - dum dum dum -), so the
    # loop holds four bars of the song and plays it at about three quarters of its speed. Original key D minor.
    # Each word leaps from a low note up to its held last syllable: D-A, D-A | C-A, C-A | Bb-G, Bb-G | then the winding
    # close around E. His low C and B flat are real (checked against the voice's spectrum). Written two octaves above him.
    # The quarter-tone under the last E (between D and E flat) is written as E flat.
    "israel-kirya-yefefiya": dict(
        units=128,
        melody=[
            (0, 6.5, "D5"), (9, 6.5, "A5"), (16, 3.5, "D5"), (20.5, 9, "A5"),
            (31, 8, "C5"), (40.5, 5.25, "A5"), (47, 4.5, "C5"), (52.5, 7, "A5"),
            (63, 8.5, "Bb4"), (72, 6.5, "G5"), (80, 7, "Bb4"), (88, 5.5, "G5"), (94, 3, "F5"),
            (97, 2.5, "E5"), (99.5, 1.75, "F5"), (101.25, 2.5, "E5"), (103.75, 1.25, "F5"), (105, 1.75, "E5"),
            (107.25, 2.25, "F5"), (109.5, 1.5, "G5"), (111, 2, "E5"), (113, 2.75, "Eb5"), (115.75, 6, "E5"),
        ],
        chords=["Dm", "Dm", "Dm", "Dm", "Am", "Am", "Am", "Am", "Gm", "Gm", "Gm", "Gm", "Bb", "Bb", "C", "C"],
        bass=[
            (0, 7, "D2"), (8, 5, "D2"), (14, 2, "D2"), (16, 4, "D2"), (20, 4, "D2"), (24, 4, "A2"), (28, 4, "D2"),
            (32, 7, "A2"), (40, 5, "A2"), (46, 2, "A2"), (48, 4, "A2"), (52, 4, "A2"), (56, 4, "E2"), (60, 4, "A2"),
            (64, 7, "G2"), (72, 5, "G2"), (78, 2, "G2"), (80, 4, "G2"), (84, 4, "G2"), (88, 4, "D3"), (92, 4, "G2"),
            (96, 7, "Bb2"), (104, 5, "Bb2"), (110, 2, "Bb2"), (112, 4, "C3"), (116, 4, "C3"), (120, 4, "G2"), (124, 4, "A2"),
        ],
        # Drums, read off the separated drum track (pipeline/arrange/drums.py): every bar hits low, mid and high together
        # on beats 1 and 3, with a light high hit on beat 2; the dum - dum - dum dum dum - of one song bar spans two
        # loop bars. The dum is a kick with a low floor tom, the high hits are closed hats. Standard kit.
        drums=dict(kit=0, bars=[[(0, 36, 110), (0, 41, 80), (0, 42, 100), (4, 42, 80), (8, 36, 100), (8, 41, 75), (8, 42, 95), (12, 42, 65)],
                                [(0, 36, 110), (0, 41, 80), (0, 42, 100), (4, 36, 95), (4, 41, 70), (4, 42, 85), (8, 36, 100), (8, 41, 75), (8, 42, 95), (12, 42, 65)]] * 4),
    ),
    # The opening line, as Ehud Banai sings it the third time (308.6 s; the same line opens both verse blocks, at 70.1 s
    # and 155.5 s, and this return fits the shared progression best). 4/4, one step = one sixteenth; the beat is tracked
    # in eighths (pick.NBEATS 64), so the loop holds eight bars of the song, 81 -> 100 BPM. Original key D minor.
    # Read off trace.py / notes.py / syll.py: a recitation on F with a turn down to D, the leading tone C# under A in bars
    # 4-5, and a climb to A in bars 6-8. His scoops into notes (B-G# before bar 2's G) are left out. Written an octave
    # above his voice. Chords from notes.py's reading of the band, one per half bar.
    "hebrew-banai-bed": dict(
        units=128, style="offbeat",
        melody=[
            (0, 2, "E4"), (2, 1.5, "F4"), (3.5, 1.5, "D4"), (5, 7.5, "F4"),                                                # bar 1
            (18.5, 1, "G4"), (19.5, 2.5, "F4"), (22, 1, "G4"), (23, 1, "F4"), (24, 2.5, "F4"), (26.5, 2, "D4"),           # bar 2
            (29.5, 1, "E4"), (30.5, 7, "F4"),
            (42.5, 1.5, "G4"), (44, 2, "F4"), (46, 0.5, "D4"), (46.5, 1.5, "G4"), (48, 4, "F4"),                           # bar 3
            (53, 3.5, "D4"), (58.5, 1, "C4"), (59.5, 1, "C#4"), (60.5, 2.5, "E4"),                                         # bar 4
            (65.5, 1, "D4"), (66.5, 1.5, "E4"), (68.5, 2.5, "C#4"), (71, 8.5, "D4"),                                       # bar 5
            (84, 2, "D4"), (86.5, 1, "A4"), (87.5, 1.5, "G4"), (89, 4.5, "F4"), (93.5, 3.5, "G4"),                         # bar 6
            (97, 6.5, "A4"), (107.5, 1, "C4"), (108.5, 1.5, "D4"), (110, 1.5, "A4"), (111.5, 1.5, "G4"),                   # bar 7
            (113, 4.5, "F4"), (117.5, 1, "G4"), (118.5, 8.5, "A4"),                                                        # bar 8
        ],
        chords=["Dm", "A", "Gm", "Dm", "A", "Gm", "Dm", "A", "A", "Dm", "Dm", "F", "Dm", "Dm", "F", "Dm"],
    ),
    # Verse 1, lines 1-2 (four half-lines of two bars), in 4/4: one step = one sixteenth. Original key C sharp minor, here D minor.
    #   syllables per phrase: (rest) 6 | 2 | 4 | 1 | 6 | 2 | 4 | 1
    # Shiri Maimon sings it freely over held chords with no beat, so the notes are hers and the rhythm is her phrasing set on
    # the grid. The half-step dips are in the tune (line 2: A G# A, then G F# G; line 4 climbs G G# A). The band holds a D in the bass throughout (D - Gm - C - Dm7 over it); here a pad and a held bass do the same.
    "values-shir-lashalom": dict(
        units=128, style="pad",
        melody=[
            (4, 4, "D4"), (8, 5, "D4"), (13.5, 1.5, "A4"), (15, 5, "A4"), (21, 1.5, "G#4"), (22.5, 1.5, "A4"), (24, 9.5, "A4"),    # bar 1: 7 syllables
            (34, 4, "A4"), (38, 2, "G#4"), (40, 6, "A4"), (46, 3, "G4"), (49, 2, "F#4"), (51, 9.5, "G4"),                           # bar 3: 6 syllables
            (64, 1.5, "G4"), (65.5, 1, "G4"), (66.5, 1.5, "G4"), (68, 1.5, "Bb4"), (69.5, 6.5, "C5"), (76, 8, "Bb4"), (84, 3.5, "A4"),   # bar 5: 7 syllables
            (87.5, 8, "G4"), (95.5, 1.5, "G#4"), (97, 3, "A4"), (100, 7, "A4"), (107, 5, "A4"), (112, 7.5, "A4"),                   # bar 6: 6 syllables
        ],
        chords=["Dm", "Dm", "Dm", "Dm", "Dm", "Gm/D", "Gm/D", "Gm/D", "Gm/D", "C/D", "C/D", "C/D", "Dm7", "Dm7", "Dm7", "Dm7"],
        bass=[(k * 16, 16, "D2") for k in range(8)],
    ),
    # The first eight bars of the strophe as Avraham Perrera sings it, in 4/4: one step = one sixteenth. Original key D minor
    # with the A held in the bass (the Hijaz colour: C sharp against B flat). Not the folk-dance tune of the same words.
    # Bars 1-4: a quick run D-E-F-D at the end of each bar and what it lands on (F E | A held | E | A); bars 5-8: the loud
    # line A - Bb A | A G F E, G A | F F F D, E D C# | B Bb C#, and the A that is held over the bar line into bar 1.
    # The vocal track of this record also carries other voices and instruments (the measured "clean" share is 42%), so
    # the quiet parts are the least certain; his in-between third (F a quarter-tone sharp) is written as F.
    # Played by the clarinet an octave above him: the flute cannot reach the low B flat.
    "values-tzadik-katamar": dict(
        units=128, style="oud", lead=71,
        melody=[
            (12, 1, "D4"), (13, 1, "E4"), (14, 1.5, "F4"), (15.5, 1, "D4"),                                          # run 1
            (21, 1, "F4"), (22, 2, "E4"), (28, 1, "D4"), (29, 1, "E4"), (30, 2, "F4"),                               # F E, run 2
            (32, 1, "D4"), (33, 7, "A4"), (44, 1, "D4"), (45, 1, "E4"), (46, 1.5, "F4"), (47.5, 2, "D4"),            # A held, run 3
            (53, 3, "E4"), (58, 2.5, "D4"), (60.5, 1.5, "E4"), (62, 1, "F4"), (63, 1.5, "D4"),                       # E, run 4
            (65, 7, "A4"), (72, 3, "A4"), (75, 3, "Bb4"), (78, 1.5, "Bb4"), (79.5, 1.5, "A4"),                       # A - Bb A
            (81, 2, "G4"), (83, 2.5, "F4"), (85.5, 2, "E4"), (89, 2, "G4"), (91, 3, "A4"), (94, 1.5, "A4"), (95.5, 1.5, "G4"),   # G F E, G A A G
            (97, 1, "F4"), (98, 2, "F4"), (100, 1.5, "F4"), (101.5, 2.5, "D4"), (106, 1, "E4"), (107, 3.5, "D4"), (110.5, 1.5, "C#4"),   # F F F D, E D C#
            (112, 2, "B3"), (114, 2.5, "Bb3"), (116.5, 4, "C#4"), (122.75, 11, "A4"),                                # B Bb C#, A (held into bar 1)
        ],
        chords=["A"] * 16 + ["A", "D", "D7", "Gm", "C7", "C7", "C7", "F", "Dm", "Dm", "E", "E", "E", "A7", "A7", "A"],
        bass=[(16 * b + 4 * k, 4, n) for b in range(4) for k, n in enumerate(("A2", "A2", "A2", "C#3"))]
             + [(64 + 4 * k, 4, n) for k, n in enumerate(("A2", "A2", "D3", "G2", "C3", "C3", "C3", "F2", "D2", "D2", "E2", "E2", "E2", "A2", "A2", "A2"))],
    ),
    # The first two lines of the verse as Danny Bassan sings them, one step = one sixteenth of the loop's 4/4. The song's
    # own beat is half the tracked one (73 to the minute, with the snare on its second beat), so the loop holds four bars of
    # the song at about two thirds of its speed, like the first version. Original key A flat major, here F major.
    #   1 | 7 syllables (G held) ... | then the line that climbs with the chords: B flat and C back and forth,
    #   D, E flat, F | and D E F D F over the last two chords.
    # Chords from the band, one to a bar: F over A, Gm7, Dm7, Eb | F, Gm7, F over A, Bb. In bar 5 he rocks between C and the
    # note under it, sung between B flat and B and nearer B; it is written as B. Written two octaves above him.
    "values-kichlot-hakol": dict(
        units=128, style="beats",
        melody=[
            (124, 6, "F5"), (5, 3, "F5"), (8, 1.5, "D5"), (9.5, 1.5, "D5"), (11, 1.5, "F5"), (12.5, 2.5, "D5"), (15, 1.5, "E5"),     # bar 8: 7 syllables
            (16.5, 3.5, "G5"), (29.5, 2.5, "C5"), (32, 3, "D5"), (39.5, 7, "F5"),                                                    # bar 2: 1 syllable then held
            (59.5, 3, "Bb4"), (62.5, 4.5, "C5"), (67, 3, "B4"), (70, 3, "C5"), (73, 1, "B4"), (74, 1.5, "B4"), (75.5, 2, "C5"),      # the climbing line
            (77.5, 2, "B4"), (79.5, 2, "C5"), (81.5, 5.5, "D5"), (87.5, 3, "Eb5"), (90.5, 3, "F5"), (93.5, 2, "D5"), (95.5, 7.5, "F5"),
            (103.5, 2, "D5"), (105.5, 2.5, "E5"), (108, 1.5, "F5"), (109.5, 2.5, "D5"), (112, 3, "F5"),
        ],
        chords=["Fmaj7/A", "Gm7", "Dm7", "Eb", "F", "Gm7", "Fmaj7/A", "Bb"],
        bass=[(16 * b + k, 8, n) for b, n in enumerate(("A2", "G2", "D2", "Eb2", "F2", "G2", "A2", "Bb2")) for k in (0, 8)],     # held, two to the bar
    ),
    # The opening eight bars as Netanela sings them, one step = one sixteenth of the loop's 4/4. The song's own beat is half
    # the tracked one (66 to the minute), so the loop holds four bars of the song at about three quarters of its speed.
    # Original key E major, here F major; the band holds the F in the bass (B flat and F chords over it) until the D7 of bar 8.
    #   syllables per phrase: 5 | 4 | 4 | 4 | (F held) then the answering line up to C and D
    # She slides into almost every note; the notes written are where the slides arrive (C C G G A | A C D E F | A A A A | A C D F).
    # Line 2 of the loop (bars 5-8) stops where the record goes on to G minor.
    "values-haya-li-chaver": dict(
        units=128, style="beats",
        melody=[
            (8, 2, "C4"), (10, 2, "C4"), (12, 2, "G4"), (14, 3, "G4"), (17, 4.5, "A4"),                                 # bar 1: 5 syllables
            (22, 2, "A3"), (24, 2.5, "C4"), (26.5, 3.5, "D4"), (30.5, 1.5, "E4"), (32, 3, "F4"),                        # bar 2: 4 syllables
            (43, 1, "A4"), (44, 4, "A4"), (48, 3, "A4"), (51, 2.75, "A4"),                                              # bar 3: 4 syllables
            (54.5, 1.5, "A3"), (56, 3.5, "C4"), (59.5, 4, "D4"), (64, 11, "F4"),                                        # bar 4: 4 syllables
            (76, 2, "G4"), (78, 5, "A4"), (84, 6, "C5"), (90, 3, "B4"), (93, 1, "Bb4"), (94, 2.5, "A4"),                # the answering line
            (96.5, 3, "A4"), (100, 2, "B4"), (102, 3, "C5"), (105, 2, "C5"), (107, 1, "B4"), (108, 1.5, "C5"),
            (109.5, 2, "A4"), (111.5, 1.5, "C5"), (113, 2, "D5"), (115, 2, "C5"), (117, 2.5, "Bb4"), (119.5, 3.5, "A4"), (123, 4.5, "A4"),
        ],
        chords=["Bb/F", "F", "Bb/F", "F", "Bb/F", "F", "Fmaj7", "D7"],
        bass=[(16 * b + k, 8, "D2" if b == 7 else "F2") for b in range(8) for k in (0, 8)],
    ),
    # Verse 1, four lines of two bars, as sung on the record (a different singer takes each line), in 4/4: one step = one
    # sixteenth. Original key A minor, here D minor. Lines 1 and 2 are the same tune.
    #   syllables per phrase: 7 | 1 | 7 | 1 | 8 | 1 | 6 | 2
    # Chords from the band: Dm for four bars, F, Gm, Bb, and a suspended C that falls back to Dm. Written an octave above the singers.
    "culture-shevet-achim": dict(
        units=128, style="strum",
        melody=[
            (0, 4, "F5"), (4, 1, "F5"), (5, 2, "F5"), (7, 4.5, "E5"), (11.5, 1.5, "D5"), (13, 3, "C5"), (16, 2.5, "C5"),            # bar 1: 7 syllables
            (19.5, 1.5, "C5"), (21, 6, "D5"),                                                                                       # bar 2: 1 syllable
            (34, 2, "F5"), (36, 1.5, "F5"), (37.5, 1.5, "F5"), (39, 1, "E5"), (40, 3.5, "E5"), (43.5, 1.5, "D5"), (45, 7, "C5"),    # bar 3: 7 syllables
            (52.5, 7, "D5"),                                                                                                        # bar 4: 1 syllable
            (65.5, 2.5, "C5"), (68, 3, "C5"), (72, 1.5, "F5"), (73.5, 2.5, "F5"), (76, 1.5, "F5"), (77.5, 1.5, "G5"), (79, 1, "G5"),    # bar 5: 7 syllables
            (80, 2.5, "G5"), (82.5, 1.5, "F5"), (84, 2.5, "D5"),                                                                    # bar 6: 2 syllables
            (97, 3, "G5"), (100, 1.5, "F5"), (101.5, 3.5, "G5"), (105, 2, "F5"), (107, 3.5, "G5"), (110.5, 1.5, "A5"),              # bar 7: 6 syllables
            (112, 3, "D5"), (118.5, 1.5, "F5"), (120, 3, "E5"), (123, 3.5, "D5"),                                                   # bar 8: 2 syllables
        ],
        chords=["Dm"] * 8 + ["F", "F", "Gm", "Gm", "Bb", "Bb", "C7sus4", "Dm"],
    ),
    # Verse 1 as Ofra Haza sings it, in 4/4: one step = one sixteenth. Original key A minor, here D minor.
    #   syllables per phrase: (rest) 3 | 4 | 5 | 5 | 4 | 4 | 5 |
    #   5 | 1 (held over the bar line into bar 1)
    # The pick-ups are set on the eighth-note grid (she pushes them a sixteenth early). The bass plays the record's riff,
    # one note to the beat: G C D F under the long notes, G D C C at the line ends; the chords follow it and the guitar
    # answers on the off-beats. Written an octave above her.
    "memory-chai": dict(
        units=128, style="offbeat",
        melody=[
            (10, 2, "D5"), (12, 2, "F5"), (14, 2, "G5"), (16, 4, "G5"),                                                    # bar 1: 4 syllables
            (26, 2, "D5"), (28, 2, "F5"), (30, 2, "G5"), (32, 5, "G5"),                                                    # bar 2: 4 syllables
            (40.5, 1, "D5"), (41.5, 2, "D5"), (44, 2, "F5"), (46, 6, "G5"),                                                # bar 3: 4 syllables
            (54, 1.25, "F5"), (55.25, 1.5, "E5"), (56.75, 2, "F5"), (59, 2, "E5"), (61, 3, "C5"), (64, 8, "D5"),           # bar 4: 6 syllables
            (74, 2, "D5"), (76, 2, "F5"), (78, 2, "G5"), (80, 4, "G5"),                                                    # bar 5: 4 syllables
            (90, 2, "D5"), (92, 2, "F5"), (94, 2, "G5"), (96, 6, "G5"),                                                    # bar 6: 4 syllables
            (106, 1, "D5"), (107, 1, "D5"), (108, 1, "F5"), (109, 2, "A5"), (111, 6, "G5"),                                # bar 7: 4 syllables
            (118, 2, "F5"), (120, 1.5, "E5"), (121.5, 1.5, "F5"), (123, 2.5, "E5"), (125.5, 1.5, "C5"), (127, 8.5, "D5"),  # bar 8: 6 syllables
        ],
        chords=["Dm", "Dm", "Dm", "Dm/F", "Gm", "C", "Dm", "Dm/F", "Gm", "C", "Dm", "Dm/F", "Gm", "Gm/D", "C", "C"] * 2,
        bass=[(16 * b + 4 * k, 4, n) for b, row in enumerate(("D2 A2 D3 F3", "G2 C3 D3 F3", "G2 C3 D3 F3", "G2 D3 C3 C3") * 2) for k, n in enumerate(row.split())],
    ),
}

PC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}


QUAL = {"": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "m7": (0, 3, 7, 10), "maj7": (0, 4, 7, 11), "dim": (0, 3, 6), "m7b5": (0, 3, 6, 10),
        "sus4": (0, 5, 7), "sus2": (0, 2, 7), "7sus4": (0, 5, 7, 10), "6": (0, 4, 7, 9), "m6": (0, 3, 7, 9), "5": (0, 7, 12)}


def parse(name):
    """'Gm7/Bb' -> (root pitch class, intervals above the root, bass pitch class)."""
    body, _, low = name.partition("/")
    r = body[:2] if len(body) > 1 and body[1] in "#b" else body[:1]
    if r not in PC or body[len(r):] not in QUAL: raise ValueError(f"chord name not understood: {name}")
    return PC[r], QUAL[body[len(r):]], PC[low] if low else PC[r]


def chord_list(names):
    """The chords of a song as (root, intervals, bass) tuples: 8, 16, 24 or 32 of them, evenly spread over the loop."""
    if len(names) not in (8, 16, 24, 32, 48): raise ValueError("chords: give 8 (one per bar), 16 (per half bar), 24 (per beat in 3/4), 32 (per beat) or 48 (per half beat in 3/4)")
    return [parse(n) for n in names]
