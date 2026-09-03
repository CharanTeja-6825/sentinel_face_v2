# H

**Premise.** What the system retains of a person is not a face. It is 512 numbers, and
the images that produced them are discarded. Nothing a human can look at survives
enrolment; the numbers are the only readable record. The page therefore sets the
figures as the primary text and demotes the words to annotations in the margin of
their own numerals.

**Fonts.** Tabular (Indian Type Foundry) weights 400–700, which is drawn for figure
setting, as the primary voice. Technor (Indian Type Foundry) weights 300–700 as the
annotating voice. Both ITF Free Font License — free for personal and commercial use,
no purchase, no account. Served from api.fontshare.com. Fallbacks: ui-monospace,
system-ui. `font-variant-numeric: tabular-nums` is set on `body`, so every figure in
the document aligns on the same advance.

**Type roles.** Figures at three levels: 700 at `clamp(4rem, 15vw, 12rem)` / 0.82;
600 at `clamp(2rem, 6vw, 4.5rem)` / 0.95; 500 at `clamp(1.25rem, 3vw, 2.25rem)` / 1.15.
Annotations = Technor 400 at 0.8125rem / 1.7 and Technor 700 at 1.0625rem / 1.4 —
the largest word on the page is smaller than the smallest figure.

**Case.** Sentence case for annotations. Uppercase at 0.24em–0.3em for the product name
and the roles, which are identifiers rather than prose.

**Colour.** Canvas #0B0D10 (flat, not counted). Four active letterform colours with
four jobs. Primary #E8EEF2 sets the bare measured figures: roughly 30%. Secondary
#7E8A96 sets every annotation — the proposition, the capture messages, the band words,
the retention statement, the roles: roughly 35%. Tertiary #4CC2A0 sets comparison and
rule — the threshold comparison and the two sentences that state a decision rule:
roughly 20%. Accent #F2B441 sets identity only — the product name and the roll number:
roughly 15%.

**Space.** Single column, max 80rem, padding 4rem / 3rem / 8rem. Figure and annotation
sit in the same block with 0.5–0.6rem between them, so the annotation reads as
subordinate rather than adjacent. Blocks are separated by 4.25rem. No indentation and
no gutters — the alignment of the numerals is the only vertical structure.

**Signature relationship.** Figures set as display type with words as their captions,
held in register by document-wide tabular numerals.

**Invariants.** Four colours bound to figure / annotation / rule / identity. Tabular
numerals globally. The largest word smaller than the smallest figure.

**Allowed variation.** Figure sizes, number of blocks.

**Prohibited normalization.** Promoting a sentence above a figure. Using the identity
accent for emphasis. Turning off tabular numerals for prose.

**Assumptions and risks.** A page led by numbers is unreadable to someone who does not
yet know what the numbers mean, so the annotation layer has to carry more explanatory
load in Round 2 than it does here.

**Round 2 translation.** Scores, margins, thresholds, counts and roll numbers are the
display type of every results and diagnostic surface. Labels stay small, grey and
subordinate. Identity accent is reserved for roll numbers and never spent on a button.
