# Reference plans — calibration data

Fifteen to twenty measured Moroccan plans, used to replace placeholder constants
with distributions. **Calibration data, not training data.** The engine is not
being taught to imitate these; its invented numbers are being checked against
them.

Owned by the `planfgen-regs` agent. See `PROMPTS-NEXT.md` S18 for the original
scope, with two corrections recorded below.

## The arrangement

```
references/
  raw/         GITIGNORED. The drawings as received — DXF, DWG, PDF, JPG.
  measured/    COMMITTED. One JSON per plan, derived from the drawing.
```

**The drawings never enter git.** They are client work from the agency. Only the
derived measurements are committed, and even those must be anonymised: no client
name, no address, no project number, no architect. A plan is identified by a code
(`casa-f3-001`), a city, and a year — nothing that names a building or a person.

If a measurement cannot be anonymised without becoming useless, it does not go in.

## The format is `to_gh_json`, not `tests/fixtures/`

`PROMPTS-NEXT.md` S18 says to reuse the existing fixture format. That is wrong.
`tests/fixtures/*.json` is `{envelope, programme, adjacencies}` — a *brief*, with
no geometry in it — and all four S18 measurements need geometry.

Use the schema `document/gh.py:62` already emits. Per space it carries
`x, y, w, h`, `outline`, `net_outline`, `net_w`, `net_h`, `surface_utile` **and**
`axis_area`; plus walls with kind and thickness, and doors with a wall index and
a span. One `tools/measure_reference.py` then reads real plans and engine output
through the same code path, which is the whole point.

`measured/TEMPLATE.json` is a valid document with the extra `provenance` block
this corpus adds on top of that schema.

## Axis versus net — the trap

A 3.00 m cote against a 15 cm cloison means **either** 3.00 net **or** 2.85 net,
depending on whether the drawing dimensions to the wall axis or to the finished
face. That is a 5% error — larger than the effects being measured — and it goes
to the heart of the rule the whole project turns on: net area is not axis area.

So every entry must record `provenance.dimensioning` as `"axis"` or `"face"`, and
the wall thicknesses it was read against. **A fixture without those two fields is
not usable and should not be committed.**

## What each plan is measured for

1. Room aspect ratios by `RoomType`, as a distribution — against the project's
   own `max_ratio = 3.0`, which is measured but is the project's figure rather
   than a regulation.
2. Circulation coefficient, and metres of run per room served.
3. How many rooms open **directly** onto circulation rather than through another
   room.
4. How real plans resolve non-rectangular parcels — the one gap with no data at
   all. Collect a few of these on purpose.

## Multi-apartment floor plates

Prefer them. Crop each unit for the per-unit measurements above, **and keep the
intact plate**: the shared circulation, the party walls between units, whether
shafts align between neighbours, and the unit mix are S19 calibration data, and
nothing in a cropped single unit carries them.

## Expect refusals

The plan is a test that every fixture passes `all_gates`. The engine currently
finds no plan at all from six rooms up, so real six-room plans will mostly be
**refused**. That is the intended outcome and the most valuable failing test
available — read it as a list of which gates disagree with reality.

Route each refusal explicitly:

- a gate refusing a legally built plan because a **constant is wrong** →
  `planfgen-regs`
- a gate refusing it because the **gate is wrong** → `planfgen-engine`

Say which. A refusal filed to the wrong agent is worse than an unfiled one.
