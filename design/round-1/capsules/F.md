# F

**Premise.** The accuracy of this system is produced by subtraction. A face is compared
against roughly sixty roster candidates and not against twenty thousand students, and
that refusal to consider is the single decision that makes the error rate usable. The
page is built the same way: one measure, one size, one weight, one colour, and a very
large amount of deliberately unused page. What the design does not do is the design.

**Fonts.** Author (Indian Type Foundry) alone, weights 400 and 500. ITF Free Font
License — free for personal and commercial use, no purchase, no account. Served from
api.fontshare.com. Fallback: Georgia.

**Type roles.** There is one type size: 1rem, line-height 1.62, tracking 0.004em. The
only distinction in the entire page is weight 500 on the first line against weight 400
everywhere else. Figures use tabular numerals and 0.02em tracking so the comparison
row aligns; nothing else changes.

**Case.** Sentence case throughout. No uppercase, no small caps, no tracking-out. The
roles line is set exactly as every other line.

**Colour.** Canvas #F7F7F5 (flat, not counted). One active letterform colour, #14161A,
carrying 100% of the text. There is no secondary role, because introducing one would
be the addition this premise exists to refuse.

**Space.** A single 34ch measure, centred both horizontally and vertically in the
viewport, with 9rem block padding and a minimum full-viewport height. Every internal
gap is exactly one line — 1.62rem — matching the leading, so the block has a single
uninterrupted rhythm. Hyphenation off. Every remaining pixel is margin.

**Signature relationship.** One measure, one interval. The 34ch column and the
1.62rem gap are the only two spatial values in the file, and the vast surrounding
emptiness is what those two values are set against.

**Invariants.** One typeface, one size, one colour. The 34ch measure. Gap equals
leading. Centred in the viewport.

**Allowed variation.** Weight 500 may mark one more line if content demands it.
Measure may move between 32ch and 36ch.

**Prohibited normalization.** Adding a second colour, a display size, a rule, or a
column. Filling the empty space with anything.

**Assumptions and risks.** This direction has almost no hierarchy, so a reader looking
for a specific value must read sequentially. It will be under strain in a dense
interface and its discipline is likely to be the first thing broken.

**Round 2 translation.** The measure and the single interval become the layout system;
hierarchy comes from position and sequence, not from size. A screen that cannot be
built inside those constraints should lose content rather than gain a type size.
