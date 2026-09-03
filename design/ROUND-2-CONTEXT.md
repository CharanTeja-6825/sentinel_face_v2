# C

**Premise.** The quality gate rejects far more frames than it accepts, and every
rejection names one specific, actionable fault. The system is therefore mostly a
record of refusal with one acceptance in it. The page separates those two kinds of
speech: machine refusals accumulate in a dense narrow log; the single thing that was
accepted takes the whole remaining width in a human voice.

**Fonts.** Azeret Mono (Displaay Type Foundry, Prague; Martin Vácha, Daniel Quisek),
SIL Open Font License 1.1, weights 300–700 — the refusal log. Clash Display (Indian
Type Foundry), ITF Free Font License, weights 400–700 — the accepted statement. Both
free for personal and commercial use, no purchase, no account. Served from
api.fontshare.com. Fallbacks: ui-monospace, sans-serif.

**Type roles.** Log = Azeret Mono 0.8125rem, line-height 2.15, tracking −0.012em, with
weight carrying meaning: 500 for a refusal, 400 for an instruction, 700 for a
measurement. Acceptance = Clash Display 600 at `clamp(3.25rem, 8vw, 6.5rem)`,
line-height 0.94, tracking −0.035em, max 13ch. Claims = Clash Display 500 at
`clamp(1.125rem, 1.9vw, 1.5rem)`, max 28ch.

**Case.** Sentence case for all message text — these are strings a user reads. Uppercase
at 0.26em–0.3em only for the angle stamp and the roles.

**Colour.** Canvas #FBFBF9 (flat, not counted). Four active letterform colours with
four different jobs. Primary #101014 is the accepted human statement — the name, the
proposition, three of the four claims: roughly 40%. Secondary #B3372B marks every
refusal, in both columns, including the one claim that is itself a refusal: roughly
25%. Tertiary #2F6F62 marks every instruction the system gives instead of refusing,
plus the angle stamp and the roles: roughly 20%. Accent #C2761A is reserved for
measured values — the captured quality line, the roll number, the score comparison,
the margin: roughly 15%. A colour never crosses into another job.

**Space.** Two columns, `26fr / 44fr`, 4.5rem gutter, max 82rem, padding 4rem / 3rem /
8rem, collapsing to one column below 900px. The log has no internal margins other than
1.6rem breaks that group attempts into passes. The right column is loose by comparison.
Density contrast between the columns is the composition.

**Signature relationship.** Weight-and-colour as message class inside one monospaced
log — the reader can see the shape of a failing session before reading a word of it.

**Invariants.** Four colours bound to four message classes. Mono log versus display
acceptance. The dense-left, open-right asymmetry.

**Allowed variation.** Log length, column ratio, acceptance size.

**Prohibited normalization.** Setting the log in the display face. Giving refusals and
instructions the same colour. Balancing the two columns.

**Assumptions and risks.** The log repeats supplied messages to show accumulation; a
reader may briefly read the repetition as an error rather than as a record of attempts.

**Round 2 translation.** The four message classes map onto the real reason codes,
prompts, and numeric readouts. The log becomes the live capture feed; the acceptance
becomes the confirmed state.

---

# Lock

**Locked by the human on direction C.** The other nine Round 1 directions are
terminated. The premise, palette, type roles and spatial rules above are the
authority for every artifact from here; the notes below record how they were
carried into the running application and nothing else.

## Message classes, resolved against the real system

C's four colours are four *message classes*, not four decorations. In the
application they bind to what the pipeline actually produces:

| Class | Token | Governs |
|---|---|---|
| accepted | `--foreground` / `--primary` `#101014` | headings, confirmed state, the `confident` band, anything the system has settled |
| refuse | `--destructive` `#B3372B` | quality-gate rejections, errors, failed jobs, the `no match` band, absent, and every irreversible action |
| instruct | `--accent` / `--success` `#2F6F62` | what the system asks a person to do — navigation, primary actions, directional prompts, resolved-by-instruction states |
| measure | `--warning` `#C2761A` | every measured value — scores, margins, thresholds, counts, progress, quality, and the `uncertain` band, which is a measurement awaiting a human |

The band mapping follows from the classes rather than from convention:
`confident` is settled and therefore takes primary ink at the heaviest weight;
`uncertain` is measured but unresolved and takes the measure colour;
`no match` is a refusal to name and takes refuse.

## Type roles

- **Azeret Mono is the interface's default face.** In C it is machine speech, and
  most of what this application says — reason codes, statuses, roll numbers,
  scores, table cells — is machine speech.
- **Clash Display carries human statements**: page titles, section headings, the
  claims on the overview, and primary action labels.
- Log density (`line-height: 2.15`, `0.8125rem`) is reserved for actual logs — the
  capture feed and the detection readout. Prose runs looser.

## Surfaces

C has one flat canvas and no shapes. Round 2 keeps that: **no card fills and no
shadows anywhere.** Separation is carried by hairlines, the mono/display voice
change, and the dense-left / open-right density asymmetry. `boxShadow.card` and
`boxShadow.lift` are defined as `none` so no existing call site can reintroduce
a raised surface. Radius is 2px — precise rather than soft.

## Invariants carried forward

Four colours bound to four message classes, and no fifth. Mono for machine
speech, display for human statements. Dense log against open statement. Flat
ground, hairlines, no fills.

## Prohibited normalization

Setting a log in the display face. Giving refusals and instructions the same
colour. Using the measure colour for general emphasis. Reintroducing card fills
or shadows to separate content. Balancing the two columns.
