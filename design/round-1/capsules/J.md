# J

**Premise.** A face in the front row and the same face in the back row are the same
face at different effective resolutions, and the pipeline bands crops by exactly that
measurement before deciding what it can conclude. The page is built on that single
variable: one voice, one colour, read from the front of the room to the back, where
hierarchy is distance rather than importance.

**Fonts.** Melodrama (Indian Type Foundry) alone, weights 300–700. ITF Free Font
License — free for personal and commercial use, no purchase, no account. Served from
api.fontshare.com. Fallback: Georgia.

**Type roles.** Eight distance steps in one typeface, from `clamp(4rem, 14vw, 11rem)`
at weight 700 down to 0.6875rem at weight 300. Weight falls as size falls, and tracking
does the opposite — from −0.045em at the front to +0.4em at the back — because a face
at distance needs more separation to stay resolvable, and so does type. Line-height
rises 0.84 → 2.0 across the same span. Measure widens from 11ch to 60ch as size falls.

**Case.** Sentence case for every step except the final one, which is uppercase at
0.4em — the furthest text is identified rather than read.

**Colour.** Canvas #12100E (flat, not counted). One active letterform colour, #EDE6DA,
carrying 100% of the text. A second colour would introduce a variable other than
distance, which is the only variable this direction has.

**Space.** Single column, max 70rem, padding 5rem / 3rem / 10rem, no gutters, no
indentation. Vertical clearance grows monotonically with distance — 2.5rem after the
first step, rising to 5rem before the last — so the page opens up as it recedes.
Nothing is centred; every step starts at the same left margin, and the varying measure
alone shapes the right edge.

**Signature relationship.** Five typographic axes — size, weight, tracking, leading and
measure — all driven by one variable, so a step's position in the sequence is legible
from any one of them.

**Invariants.** One typeface, one colour. The monotonic distance ladder with all five
axes bound to it. Flush-left origin. Clearance growing with distance.

**Allowed variation.** Number of steps, top size, canvas and text values as a pair.

**Prohibited normalization.** Adding a second colour to create emphasis. Breaking the
monotonic order to promote an important line. Setting two steps at the same size.

**Assumptions and risks.** Hierarchy is strictly sequential, so anything that must be
found quickly has to be moved forward in the order rather than highlighted — a real
constraint on dense screens. The final steps are small and heavily tracked and will
need a size floor before carrying essential text.

**Round 2 translation.** The ladder is the type scale, and position in the ladder is
the only hierarchy mechanism. When a screen needs something to stand out, move it
toward the front of the room; do not colour it.
