# B

**Premise.** The system's three bands — confident, uncertain, no match — are not
severity levels, they are degrees of what it is willing to claim. Confident is stated
and closed. Uncertain is held open for a person. No match is nearly silence. The page
gives each tier a size, a weight, a colour and, critically, an amount of surrounding
air inversely proportional to certainty: what is known is set tight; what is doubted
is given room to be looked at.

**Fonts.** Bespoke Serif (Indian Type Foundry) weights 400/500/700/800 plus italic for
the claimed tier. Switzer (Indian Type Foundry) weights 300–700 for the doubted and
silent tiers. Both ITF Free Font License — free for personal and commercial use, no
purchase, no account. Served from api.fontshare.com. Fallbacks: Georgia, system-ui.

**Type roles.** Tier one = Bespoke Serif 800, `clamp(3rem, 8.2vw, 7.2rem)`,
line-height 0.90, tracking −0.035em, max 15ch; its qualifier is Bespoke Serif 400
italic; its running statements are Switzer 700 at 1.0625rem / 1.35. Tier two = Switzer
400 at `clamp(1.25rem, 2.4vw, 1.875rem)`, line-height 1.7, max 33ch; its list runs at
1.0625rem with line-height 2.9. Tier three = Switzer 300/400 at 0.8125rem–1rem,
line-height 1.9–2.4, uppercase, tracking 0.2em–0.34em.

**Case.** Sentence case for tiers one and two. Tier three is uppercase — at that size
the words are being identified, not read.

**Colour.** Canvas #0E1116 (flat, not counted). Three active letterform colours.
Primary #F4F6F8 governs the whole first tier — the name, the proposition, both
claims, the word `confident`: roughly 45% of visible text. Secondary #C6A15B governs
the entire second tier — the absent-never-present rule, the four capture messages,
the retention statement, the word `uncertain`: roughly 35%. Tertiary #5A6472 governs
the third tier — `no match`, the angle row, all figures, the roles: roughly 20%.
No colour appears outside its tier.

**Space.** Single column, max 78rem, padding 5rem / 3.5rem / 10rem. Indentation is the
certainty gradient: tier one starts at the left margin, tier two at 14%, tier three at
42%. Vertical air scales the same way — 0.35rem between tier-one lines, 4.5–5.5rem
around tier-two blocks, 9–11rem before tier-three blocks.

**Signature relationship.** Air as inverse confidence. The less the system will claim,
the further right it sits and the more emptiness surrounds it.

**Invariants.** Three colours bound to three tiers. Indent 0 / 14% / 42%. The
serif-for-claims, sans-for-doubt split. Air increasing as certainty falls.

**Allowed variation.** Tier-one display size, number of statements per tier.

**Prohibited normalization.** Equalising the vertical rhythm across tiers. Moving a
colour outside its tier. Setting tier three at tier-two size to make it easier to read.

**Assumptions and risks.** Tertiary #5A6472 on #0E1116 is deliberately low contrast and
will need to be lightened before it carries any text a user must act on — a Round 2
accessibility correction, not a premise change.

**Round 2 translation.** The three bands in the results view take these three
treatments directly. Resist giving `no match` a stronger colour to make it "findable":
its recessiveness is the argument.
