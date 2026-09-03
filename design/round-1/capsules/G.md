# G

**Premise.** The two errors this system can make are not equivalent. A wrong absent is
corrected in three seconds by a student sitting in the room; a wrong present is
invisible and is exactly the fraud the system exists to prevent. Every threshold in the
pipeline is set from that asymmetry. The page refuses to balance: one side carries
almost all the typographic mass, the other almost none, and the imbalance is the
argument rather than a layout preference.

**Fonts.** Tanker (Indian Type Foundry), single weight 400, for the loaded side.
General Sans (Indian Type Foundry) weights 300–600 for the light side. Both ITF Free
Font License — free for personal and commercial use, no purchase, no account. Served
from api.fontshare.com. Fallbacks: sans-serif, system-ui.

**Type roles.** Mass = Tanker at `clamp(4rem, 15.5vw, 13.5rem)`, line-height 0.80,
tracking −0.02em; secondary mass at `clamp(2rem, 6.6vw, 5.25rem)`, line-height 0.90,
max 14ch. Supporting text under the mass = General Sans 400 at 1.0625rem, max 42ch.
Light side = General Sans 300 at 0.8125rem with 0.12em tracking and line-height 2.2,
with one 600 block at 0.9375rem for the capture messages and 500 for figures.

**Case.** Sentence case for everything the system says. Uppercase at 0.34em for the
roles only, which sit on the light side as the smallest text on the page.

**Colour.** Canvas #101010 (flat, not counted). Two active letterform colours.
Primary #F0EDE6 carries the mass and most of the light column: roughly 75%.
Secondary #D9452E carries only what names the costly error — the never-present rule at
full display size, the retention statement, and the roles: roughly 25%. The two
colours also carry unequal weight classes, so the imbalance is in size and colour at
once.

**Space.** Two columns at `72fr / 28fr` with a 3rem gutter, max 86rem, padding 3.5rem /
3rem / 9rem, collapsing below 860px. The heavy column starts hard against the top-left
and runs long. The light column starts at the same baseline and stops early, leaving
the lower right of the page empty.

**Signature relationship.** A 72/28 split executed in both dimensions at once — column
width, type size, weight and quantity of text all lean the same way, so the page reads
as weighted rather than as two columns.

**Invariants.** The 72/28 asymmetry. Two colours where the second names only the costly
error. Tanker heavy, General Sans light. The empty lower right.

**Allowed variation.** Display size, quantity in the light column.

**Prohibited normalization.** Equalising the columns. Using the accent for general
emphasis. Filling the lower right.

**Assumptions and risks.** #D9452E on #101010 is at the lower end of comfortable
contrast at small sizes and will need checking wherever it carries body text.

**Round 2 translation.** Destructive and irreversible actions — finalize, override —
take the accent; nothing else does. Keep the 72/28 weighting in page layout, and do not
let a symmetrical grid re-enter through a component library.
