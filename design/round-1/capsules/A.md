# A

**Premise.** Roll call is spoken exchange before it is a record: a name is called, a
pause is held, a voice answers. SentinelFace replaces the voice but not the
structure — the system still asks and still waits. The composition is that
exchange: every statement is either a call or an answer, and the interval between
them is measured rather than left over.

**Fonts.** Zodiak (Indian Type Foundry; Jérémie Hornus, Gaetan Baehr, Jean-Baptiste
Morizot, Alisa Nowak, Theo Guillard) for the calling voice, weights 300/400 plus
italic. Synonym (Indian Type Foundry) weights 400–600 for the answering voice.
Both under the ITF Free Font License — free for personal and commercial use, no
purchase, no account. Served from api.fontshare.com. Fallbacks: Georgia, system-ui.

**Type roles.** Call = Zodiak 400, `clamp(2.6rem, 6.4vw, 5.2rem)`, line-height 0.98,
tracking −0.022em, max 20ch. Its subordinate clause is Zodiak 300 italic. Answer =
Synonym 500, 1rem, line-height 1.55, max 34ch. Verdict stack = Zodiak 700 at
`clamp(1.5rem, 3vw, 2.4rem)`, with the two lower bands dropped to weight 300 and the
secondary colour. Angles and figures = Synonym, 0.9375rem / 0.8125rem, tracking
0.42em and 0.16em, tabular numerals.

**Case.** Sentence case throughout, except the roles line and the roll number, which
are uppercase at 0.16em to read as identifiers rather than speech.

**Colour.** Canvas #F2EFE7 (flat, not counted). Two active letterform colours:
primary #16130E carries every call — roughly 65% of the visible text; secondary
#9A7B4F carries every answer, the angle row, the two lower verdicts and all figures —
roughly 35%. The rule is absolute: if the system said it, it is ochre; if the system
asked it, it is ink. Colour therefore encodes who is speaking, not emphasis.

**Space.** Single column, max 74rem, padding 9rem top / 3rem sides / 12rem bottom.
Three interval lengths only — beat 2.25rem, breath 5.5rem, silence 11rem — and no
other vertical value exists in the file. Calls sit on the left margin. Answers are
displaced into the page: `near` starts at 38%, `deep` is pushed to the right edge.
Horizontal displacement is distance in the room.

**Signature relationship.** The three fixed intervals. Every vertical gap is a beat, a
breath or a silence, so the page has a measurable cadence rather than a layout.

**Invariants.** Two colours with the speaker rule. The three-interval system. Call
left, answer displaced right. Zodiak for asking, Synonym for answering.

**Allowed variation.** Displacement percentage, call size, number of exchanges.

**Prohibited normalization.** Adding a third interval length. Letting a call take the
answer colour. Centring the calls.

**Assumptions and risks.** Assumes the reader will follow an alternating rhythm without
a visible connector. At narrow widths the `near`/`deep` displacement compresses and
the two voices may sit closer than intended.

**Round 2 translation.** Interface prompts are calls; system responses are answers, in
the secondary colour, indented. The three intervals become the entire vertical spacing
scale. Do not introduce a fourth spacing step to solve a dense screen — reduce content.
