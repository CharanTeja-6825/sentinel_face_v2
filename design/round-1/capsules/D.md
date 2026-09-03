# D

**Premise.** Enrolment asks for one orientation at a time — front, then left, then
right, then up, then down — and refuses every frame that is not the orientation being
asked for. Reading the page requires the same five movements: each passage is placed
where its angle points, so the eye traverses top, left, centre, right, bottom in the
order the capture demands.

**Fonts.** Panchang (Indian Type Foundry; Barbara Bigosinska, Hitesh Malaviya) weights
300–800 for the prompts. Supreme (Indian Type Foundry; Jérémie Hornus, Ilya Naumoff)
weights 300–700 for spoken messages. Both ITF Free Font License — free for personal
and commercial use, no purchase, no account. Served from api.fontshare.com.
Fallbacks: sans-serif, system-ui.

**Type roles.** Centre prompt = Panchang 800 at `clamp(3.4rem, 11vw, 9rem)`,
line-height 0.86, tracking −0.045em. Side prompts = Panchang 600 at
`clamp(1.6rem, 4.4vw, 3.4rem)`, line-height 1.02. Top and bottom prompts = Panchang
400 at `clamp(1.125rem, 2.2vw, 1.625rem)`. Messages = Supreme 400/500 at 1.0625rem,
line-height 1.65. Angle words = Panchang 300 with 0.5em tracking, lowercase.

**Case.** Lowercase for the five angle words — they are the system's own tokens.
Sentence case for messages. Uppercase at 0.36em for the roles only.

**Colour.** Canvas #EDEFEA (flat, not counted). Three active letterform colours.
Primary #1B2019 sets every prompt — name, proposition, both claims, the verdict row:
roughly 50%. Secondary #5C6B57 sets the five angle markers, the messages that report a
held state, and the roles: roughly 30%. Accent #A03E2E sets only what the system is
actively asking for or refusing — the turn-your-head instruction, the never-present
rule — and the figures: roughly 20%.

**Space.** Max 88rem, padding 4.5rem / 3.5rem / 7rem. No column grid; placement is by
text-align and max-width. `up` and `down` are centred with 24ch and full measure;
`left` is flush left at 30ch with auto right margin; `right` is flush right at 30ch
with auto left margin; `front` is centred at 24ch. Three vertical intervals: 3.25rem,
6.5rem, 10rem.

**Signature relationship.** Alignment as instruction. The page cannot be read without
performing the five orientations, so the reading path is the enrolment sequence.

**Invariants.** Five placements bound to the five angles, in order. Three colours with
the ask/hold/state split. Panchang prompting, Supreme reporting.

**Allowed variation.** Prompt sizes, measure widths, interval choice within the three.

**Prohibited normalization.** Left-aligning the whole page. Reordering the five
placements. Merging the accent into the primary.

**Assumptions and risks.** Extreme alignment changes cost horizontal scanning effort;
at narrow widths the left/right displacement mostly collapses and the sequence reads as
a plain column.

**Round 2 translation.** The guided capture screen inherits the placement rule directly
— the prompt for the current angle sits where that angle points. Elsewhere, keep the
three-colour ask/hold/state split and use the placement rule only where an orientation
is genuinely being requested.
