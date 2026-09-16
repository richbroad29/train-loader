# train-loader

Tells you **which carriage of your train to get on** to maximise your chance of a seat.
Scoped deliberately to the Brighton Main Line — Southern, Thameslink and Gatwick Express
between Brighton and London.

Currently: research and a feasibility probe. No app yet, on purpose.

## Where things stand

The industry plumbing for this exists. Darwin, the national real-time information engine,
carries a `formationLoading` message giving an estimated **0–100 load figure per coach, per
calling point, per service** — it is a first-class field, not an inference. GTR has already
built a system feeding exactly this kind of data into Darwin, under RSSB funding with CACI
and the University of Southampton, including a tool that helped station staff direct
passengers to the best part of the platform.

What is *not* established is whether that data flows publicly for Southern and Thameslink
services on this route today. Community evidence contradicts itself and documentation cannot
settle it. So the first deliverable is a measurement, not a feature.

Read [`docs/01-feasibility.md`](docs/01-feasibility.md) for the full assessment.

## The finding that shaped the product

**At Brighton the train starts empty, so live loading tells you nothing.** Choosing a
carriage at an origin terminus is a forecasting problem; live sensing only becomes decisive
when boarding mid-route at Haywards Heath, Gatwick or East Croydon into an already-loaded
train with forty seconds of dwell time.

That splits the product in two — a calm forecast at the origin, an urgent live read at an
interception — and it means **recording the feed matters more than reading it**.

The app is designed in three tiers so it says something useful with no loading data at all:

| Tier | Source | Says |
|---|---|---|
| A | live per-coach loading | "Coach 11 is 35% full" |
| B | typical loading × learned carriage profile | "The front third usually isn't busy" |
| C | station geometry alone | "Front of the train — furthest from the Brighton barriers" |

Tier C is free, nearly always right on this route, and ships first.

## Layout

```
docs/01-feasibility.md      Can this be built? What is known, unknown, and how to settle it
docs/02-data-sources.md     Every candidate feed, with confirmed/verify markers
docs/03-product-concept.md  What the app says, the tiers, the seat-vs-exit trade-off
docs/04-roadmap.md          Phased plan, ordered by uncertainty reduction
docs/brighton-line-notes.md Route domain knowledge and the platform calibration protocol
data/brighton-line.json     Platform geometry -- the core asset, mostly still to be measured
probes/                     Runnable coverage probes for LDBWS and the Darwin Push Port
```

## Next step

```sh
python3 probes/ldbws_probe.py --selftest   # works now, offline
```

Then get a Rail Data Marketplace key and run it for real — see
[`probes/README.md`](probes/README.md).
