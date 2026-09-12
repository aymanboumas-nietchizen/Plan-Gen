# How the agents work

Seven agents in `.claude/agents/`. This file is the contract between them — who
decides what, how findings travel, and the two rules that keep the arrangement
honest. `CLAUDE.md` still governs everything; this only says who does it.

## The one rule that makes it work

**No agent both finds a problem and fixes it.**

That is the whole design. An agent that measures its own repair reports success;
an agent that cannot touch what it measures reports what it found. Every
boundary below exists to keep those two jobs in different hands.

| | measures — produces facts, changes nothing | decides — owns what "right" means | builds — changes code |
|---|---|---|---|
| **engine** | `planfgen-qa` | `planfgen-optima` | `planfgen-engine` |
| **numbers** | `planfgen-critique` | `planfgen-regs` | — |
| **outside** | `planfgen-analyst` | — | `planfgen-product` |

## Decision rights

Each agent owns exactly one thing and may be overruled on everything else.

| agent | owns | prevents |
|---|---|---|
| `planfgen-qa` | where the engine actually breaks | believing a green suite |
| `planfgen-engine` | L0–L7 code | — (it is the builder) |
| `planfgen-regs` | every dimensional constant, and legality | numbers invented in code |
| `planfgen-product` | the surface: studio, exports, onboarding | an engine nobody can drive |
| `planfgen-optima` | the objective structure and the search | optimising the wrong thing well |
| `planfgen-analyst` | outside knowledge | reinventing, and being blindsided |
| `planfgen-critique` | whether the output is good architecture | passing every gate and drawing rubbish |

## Routing — where a finding goes

A finding is not filed until it names an owner.

- a gate refuses a **legally built** plan → is it a wrong constant (`regs`) or a
  wrong gate (`engine`)? Say which.
- a plan is bad and a constant permits it → `regs`
- a plan is bad and no score measures it → `optima`
- the engine will not give the studio what it needs → `product` reports it,
  `engine` fixes it; `product` never reaches into a layer package
- a competitor or a paper has solved something → `analyst` routes it onward with
  a cost, never as "we should build X"

## The scoreboard is the manager

There is no coordinating agent, and there should not be one. The agents are held
together by a **single versioned measurement** that none of them can fake.

Today that is `tools/probe_ceiling.py`. Every build agent runs it **before and
after**, and both tables go in the report. **No claim of progress is admissible
without it.** It currently measures one axis — rooms placeable from an
uncalibrated brief — and should grow to carry capacity, score distribution, cost
per candidate, gate-refusal mix, determinism, and once a corpus exists, the
fixture pass rate.

A change that does not move the scoreboard is not necessarily bad — `d94cf26`
bought no capacity and was worth committing — but it must be **reported as
buying nothing**. That honesty is the point of having one number everyone shares.

## Concurrency — the operational constraint

**Agents share one working tree.** Two builders at once will collide: staged
files get swept into the wrong commit, and edits interleave.

- **At most one build agent at a time** (`engine`, `product`) in the shared tree.
- Measurement agents (`qa`, `analyst`, `critique`) and decision agents (`optima`,
  `regs` when not editing constants) may run concurrently with one builder.
- A second builder must be given `isolation: "worktree"`.
- When committing alongside a running agent, commit with an explicit pathspec —
  `git add <paths> && git commit -- <paths>` — so its in-progress work is not
  swept in.

## The shape of a session

The working agreement in `CLAUDE.md`, generalised:

1. **Measure** — `qa` first, always, because it is cheap and the alternative is
   building against a belief.
2. **Decide** — `regs` or `optima` says what should change, and why.
3. **Build** — one agent, one step, tests in the same session.
4. **Re-measure** — the same scoreboard, before and after.
5. **Record** — a `PROGRESS.md` entry under ten lines, and a commit.

`PROMPTS-NEXT.md` is the backlog. Tag each item with its owning agent.

## What this does not solve

Be honest about the limits, or the arrangement will be trusted further than it
deserves.

- **Every agent starts cold.** They re-derive context from `CLAUDE.md`,
  `PROGRESS.md` and their own brief. Keeping those three accurate is what makes
  the system work; letting them drift is what breaks it.
- **The human is still the bottleneck**, and no agent removes it. Only the
  architect can supply reference plans, get a zone's CES, decide what a
  corridorless flat should do, and judge whether a drawing is worth signing.
- **Seven agents on a solo project is a lot of coordination.** They are not all
  meant to run. Most sessions need one or two.
