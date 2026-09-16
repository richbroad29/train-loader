# Product concept

> **Superseded in part.** This document was written before the destination was settled. The
> current, canonical statement of what is being built is the wayfinder map:
> <https://github.com/richbroad29/train-loader/issues/1>. Where they disagree, the map wins.
> In particular: the journey is Preston Park ↔ London Bridge (an interception in both
> directions, not boarding at Brighton), the operator is Thameslink only, and the output is a
> **carriage number**, not a platform position.


## The job to be done

> "I'm walking into Brighton station. The 08:12 is on platform 6. Which door do I stand at
> so I'm still sitting down when we leave Gatwick?"

Answered in under three seconds, on a phone, one-handed, while walking. Everything below
serves that sentence.

## What the app actually says

The output is not a dashboard. It is **one instruction**:

> **Coach 11 — far end of the platform (a 90-second walk).**
> Usually ~40% full leaving Haywards Heath. Rear coaches are full by Gatwick.
> *Live per-coach data · updated 30s ago*

with a second line of honesty about where the answer came from, and a one-tap "was that
right?" that feeds the model.

## Confidence tiers — design for the data you have, not the data you want

The single most important architectural decision: **the app must give a useful answer when
there is no loading data at all**, and get better, not different, as data appears. Three
tiers behind one interface.

| Tier | Input | What it can say | Confidence shown |
|---|---|---|---|
| **A — Live** | Darwin `formationLoading`, per coach | "Coach 11 is 35% full, coach 3 is 95%" | High. Cite the timestamp. |
| **B — Learned** | `serviceLoading` (typical/expected) × learned per-carriage distribution for this service pattern | "This train is usually busy; the front third usually isn't" | Medium. Say "usually". |
| **C — Geometry** | Station layout only: distance from entrance, stairs, barriers | "Front of the train — furthest from the Brighton concourse, so it fills last" | Low but rarely wrong. |

Tier C is not a stopgap. For a terminus like Brighton it is genuinely close to optimal, and
it costs nothing to build. Ship Tier C first; it makes the app useful on day one and gives
you a live product to hang the data work on.

## The insight that shapes the whole thing

**Boarding at an origin, live loading is worthless — the train is empty.** The real question
at Brighton is a forecast: *where will this train be full in 25 minutes?* Live sensing only
becomes decisive when boarding mid-route (Haywards Heath, Gatwick, East Croydon) into an
already-loaded train, with ~40 seconds of dwell to pick a door.

So there are two distinct modes, and they should feel different:

- **Origin mode (Brighton):** a forecast. Calm, delivered before you reach the barriers,
  talks about the whole journey. "Coach 11 — it'll still have seats after Gatwick."
- **Interception mode (HHE / GTW / ECR):** a live read. Urgent, big text, arrives as the
  train does, talks about *right now*. "Coach 11 — 30% full. Walk 40m north."

Interception mode is the harder technical problem and the more valuable product.

## The second trade-off: a seat, or the exit

"Best carriage" is ambiguous. Sitting for 55 minutes and landing next to the Blackfriars
stairs are different answers, and regular commuters have a fixed preference. The app should
carry a per-route setting — **Seat / Exit / Balanced** — and score carriages as:

```
score(coach) = w_seat · P(seat available on boarding)
             − w_exit · walk_penalty(coach, destination_platform_layout)
             − w_walk · walk_penalty(coach, origin_platform_entrance)
```

The third term is the one other people forget: advice that requires a 90-second walk is
wrong if the user has 40 seconds. **The app must know how long they have** — it does, from
the departure time — and should never recommend a carriage they cannot reach. This is a
genuine differentiator and it is pure logic, no data needed.

## Entry points

1. **Trains leaving soon near you.** Geolocate → nearest CRS → LDBWS departure board →
   list with a busy-ness indicator against each. One tap for advice.
   Watch the failure mode: at Brighton you are 200m from the platform but GPS says you are
   at the station, so "leaving soon" must mean "leaving in 4–20 minutes", not "2 minutes".
2. **Favourite routes.** The real daily path. "Brighton → London Bridge, weekday mornings"
   pinned to the top, pre-warmed, works offline-ish from cache. For a commuter this is the
   *only* entry point that matters after week one; treat #1 as the discovery surface and
   #2 as the habit surface.
3. **Deep link / widget / lock screen.** The genuinely correct endgame: you should not have
   to open an app. A home-screen widget showing the next three departures and their
   recommended coach is the version of this product people would actually keep.

## Scope discipline

Build for **Brighton ↔ London on Southern, Thameslink and Gatwick Express only**. Not as a
limitation — as the strategy. The geometry table, the carriage-fill model and the
calibration all have to be hand-made per station; one corridor done properly beats the
whole network done uselessly. Expanding to a second route should be a deliberate decision
made after the first one is provably right.

## What would make this fail

Worth writing down now, honestly:

- **Data never materialises** and Tier B/C prove no better than "walk to the far end, mate".
  Mitigation: Tier C is cheap; find out fast; the app is still mildly useful.
- **Formations change late.** Brighton services split/join and vary 8 vs 12 cars. Advice
  keyed to "coach 11" is dangerous if today's train is 8 cars. Always re-derive from live
  formation length; never cache a coach number across services.
- **Advice becomes self-defeating** at scale. If everyone is told coach 11, coach 11 fills.
  Irrelevant at personal scale; a real design problem if it ever gets popular — at which
  point randomised advice among the top-3 equivalent coaches is the fix.
- **The walk is the real constraint.** Users will ignore advice requiring a walk they don't
  have time for. Solved by modelling walk time, not by better loading data.

## Name

`train-loader` is the repo. Candidates for the thing itself: **Carriage**, **Platform Nine**,
**Which Coach**, **Seatward**. Not urgent — decide when there is something to name.
