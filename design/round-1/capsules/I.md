# I

**Premise.** A class is not a moment but a window: consecutive periods of one subject
merge into a single block, and every decision the system makes is scoped to that
window. The page is read as a schedule — successive horizontal registers, each named
by one of the system's own tokens and each given a measure and a leading proportional
to how long its passage lasts.

**Fonts.** Khand (Indian Type Foundry; Satya Rajpurohit), SIL Open Font License 1.1,
weights 400–700, condensed, for markers and the title. Recia (Indian Type Foundry;
Carlos de Toro), ITF Free Font License, weights 400–600 with italics, for the
passages. Both free for personal and commercial use, no purchase, no account. Served
from api.fontshare.com. Fallbacks: system-ui, Georgia.

**Type roles.** Title = Khand 700 at `clamp(3rem, 9vw, 7rem)`, line-height 0.92,
uppercase. Markers = Khand 600 at 1.0625rem, tracking 0.2em, uppercase, in a fixed 9rem
first column. Passages = Recia at three durations: long (`clamp(1.5rem, 3.4vw, 2.5rem)`,
line-height 1.72, max 30ch), medium (`clamp(1.125rem, 2.1vw, 1.5rem)`, line-height 1.42,
max 40ch), short (1rem, line-height 1.22, max 58ch). Leading and measure move together —
a long block is both wider-leaded and narrower-set.

**Case.** Markers and title uppercase, because they are labels in a register. Passages
in sentence case. Roles uppercase at 0.3em in the condensed face.

**Colour.** Canvas #F4F1EC (flat, not counted). Three active letterform colours.
Primary #211E1B sets the title and every passage the system asserts: roughly 55%.
Secondary #6E5B45 sets the markers drawn from the five angles and the passages that
report a retained or held state: roughly 30%. Accent #2C5F8A sets the three markers
that name a verdict, plus all figures and the roles: roughly 15%.

**Space.** A two-column register: fixed 9rem marker column, 2.5rem gutter, fluid
passage column, max 76rem, padding 3.5rem / 3rem / 8rem, collapsing to one column below
760px. Baseline-aligned across the gutter. Vertical separation is set by duration:
5.5rem after a long register, 3.25rem after a medium one, 1.75rem after a short one.

**Signature relationship.** Duration expressed as leading and measure simultaneously —
the longer the block, the more open its leading and the narrower its column, so the
page's rhythm is read as elapsed time rather than as importance.

**Invariants.** Fixed marker column at 9rem in the condensed face. Three durations with
leading and measure moving together. Markers drawn only from the system's own
vocabulary. Three colours with the assert / hold / verdict split.

**Allowed variation.** Which token names a register, number of registers, title size.

**Prohibited normalization.** Making the marker column fluid. Setting all passages at
one leading. Inventing marker words outside the system's vocabulary.

**Assumptions and risks.** Below 760px the two columns stack and the schedule reading
weakens into a list; the duration rule then carries the premise alone.

**Round 2 translation.** Timetable blocks, session lifecycle and results all have real
durations to express. Keep the marker column fixed and the three durations; do not add
a fourth to fit a long passage — shorten the passage.
