# Feasibility: carriage-level seat advice on the Brighton Main Line

Status: research complete, **one decisive unknown remains** (see §5).
Date: 2026-09-16. Everything here should be re-checked against live data before it is trusted.

## 1. Verdict in one paragraph

The idea is **technically feasible and the industry plumbing for it already exists** — Darwin,
the national real-time information engine, carries a purpose-built message
(`formationLoading`) that reports an estimated 0–100 load figure *per coach, per calling
point, per service*. It is not a hack or an inference; it is a first-class field. The risk is
not "can the data exist" but **"does GTR actually publish it for Southern and Thameslink
services on the Brighton line, today, on the public tier"** — coverage is decided
operator-by-operator, the community evidence is contradictory, and it cannot be settled
from documentation. It needs a measurement, which is why the first thing to build is a
probe, not an app (§5, `probes/`).

There is also a product finding that matters more than the API question: **live loading is
the wrong tool for the job at Brighton.** Brighton is the origin — every coach is empty when
you board. The question "which carriage should I get on?" at an origin station is a
*forecasting* question, not a *sensing* one. Live per-coach data is decisive at Haywards
Heath, Gatwick and East Croydon; at Brighton its value is as training data for a model.
See §6 and `03-product-concept.md`.

## 2. What the data actually is

Darwin's Push Port schema distinguishes two things that are easy to conflate:

| Message | Granularity | Content | Use to us |
|---|---|---|---|
| `formationLoading` | **per coach**, per location, per service | `coachNumber` + `loadingPercentage` (integer 0–100), plus `source` / `sourceSystem` | **This is the product.** Exactly the field the app needs. |
| `serviceLoading` | whole train, per location | either a `loadingPercentage` (0–100) or a `loadingCategory` code, each tagged `Typical` or `Expected` | Fallback tier. Drives "this train is usually busy" in consumer apps. |
| `formation` | per coach | ordered coach list with `coachNumber`, `coachClass`, toilet status/type | Needed to turn "coach C" into "5th of 12". |

Two properties matter for design:

- **Coaches are listed front-to-rear** — the first element is the front of the train in the
  direction of travel. This is the hook that lets us say "walk to the far end", but it only
  works with station geometry bolted on (§6, `brighton-line-notes.md`).
- **Loading is stated per calling location.** A service gets a loading figure at each point
  where it calls to pick up or set down. So a Brighton departure can in principle carry a
  figure for what it will look like at Haywards Heath — but whether GTR populates forward
  locations, or only the here-and-now, is part of what the probe must establish.
- **`loadingCategory` has a reference table** (`LoadingCategoryReference`: code, name,
  per-TOC descriptions, colour, icon). If we fall back to categories we get the operator's
  own wording and colour for free, which is good for a UI that shouldn't over-claim.

Accuracy is entirely the operator's: the wiki is blunt that loading "is maintained by train
operators and is as accurate as the input they provide". Sources vary — seat reservations,
weight/mass detection, door counters, camera counting.

## 3. Why the Brighton line is a *good* case, not a bad one

- **GTR has already built this exact system.** Under RSSB funding, GTR and CACI combined 15
  data sources — carriage telemetry, shoe-counting cameras, mobile device addresses —
  calibrated with algorithms from the University of Southampton, and **fed the result
  directly into new fields in Darwin**. Train loading and consist appeared in customer apps,
  and a companion system was used by station staff to direct passengers to the best part of
  the platform. That is, almost precisely, this idea — built, proven, and pointed at this
  operator.
- **The Class 700s (Thameslink) measure load per car natively.** Their on-board passenger
  information system already displays per-coach loading to people on the train.
- **Southern already publishes crowding to the public**, via its "find a quieter train" tool:
  colour-coded seat-availability symbols on live departure boards for journeys in the next
  two hours, derived from on-train passenger counting equipment averaged over the previous
  two weeks. That is proof the counting hardware exists and its output is publishable.

## 4. Why it is not a slam dunk

- **Southern's public tool is whole-train and historical**, not per-coach and not live. It is
  the `serviceLoading`/`Typical` tier. Its existence is weak evidence *against* live
  per-coach data being on the public feed, or GTR would likely surface it themselves.
- **Community reports contradict each other and are undated.** One account has Thameslink
  publishing crowding for *some* routes but *not* formations, with Chiltern and Southeastern
  publishing both; another has loading "starting to appear on GTR services (e.g. Gatwick
  Express)". Without formations, per-coach loading is unusable — you cannot place a coach
  identifier on a platform without the ordered consist.
- **The CACI work was a pilot.** Pilots are switched off. Whether that pipeline is in
  business-as-usual operation in 2026 is unknown from the outside.
- **Loading may be richer on the staff feed (LDBSVWS) than the public one.** The staff web
  service is "simply a more granular version" of the public one, and the public service is
  already known to omit documented fields in practice — one developer found typical
  passenger loading and previous calling points absent from public `GetDepBoardWithDetails`
  responses despite the docs.

## 5. The decisive unknown, and how to settle it

> **Does a Brighton-line Southern / Thameslink / Gatwick Express service carry populated
> `formation` *and* `formationLoading` on a tier we can access?**

No amount of further reading answers this. It needs an empirical coverage measurement over
a real week, because coverage may vary by fleet (377 vs 387 vs 700), by route, and by time
of day. `probes/` contains two scripts for exactly this:

1. `probes/ldbws_probe.py` — polls the LDBWS REST API for departure boards at BTN, PRP, HHE,
   TBD, GTW, ECR, CLJ, VIC, LBG, ZFD; pulls service details for every GTR service; and
   reports what fraction carry formation and per-coach loading, broken down by operator.
   It **discovers** fields rather than assuming them, because the public schema's real
   behaviour is not reliably documented.
2. `probes/pushport_probe.py` — a Darwin Push Port STOMP consumer that counts
   `formationLoading` messages and logs every per-coach value to JSONL.

Run the LDBWS probe first (minutes to set up). If it shows per-coach loading, the app is a
straightforward build. If it shows nothing, run the Push Port probe for a week before
concluding anything — the Push Port is the richer feed and the request/response API is a
lossy view of it.

**Decision rule.** After one week of probing:
- per-coach loading present on >60% of peak Brighton-line services → build Tier A, live advice.
- formations present but loading absent/sparse → build Tier B/C and start recording your own
  observations; revisit in six months.
- neither → the app is still worth building on geometry alone (§6), but bill it honestly as
  "where to stand", not "where the seats are".

## 6. The finding that changes the product

At **Brighton the train starts empty**, so live loading tells you nothing about the journey
you are about to take. The useful signal at an origin terminus is a *forecast*: where will
this train be full after Haywards Heath and Gatwick, given the formation it is running today
and the day/time. That is a modelling problem fed by historical per-coach loading — which
means **recording the feed from day one is more valuable than reading it**.

Conversely, the live signal is at its most valuable exactly where the passenger is most
anxious — boarding at Haywards Heath or Gatwick into an already-loaded train, with 40
seconds of dwell time to choose a door. That is the killer use case, and it is also the
easier one technically.

Two further constraints the design has to absorb:

- **Coach identity is not platform position.** Darwin gives front-to-rear order; turning that
  into "stand at the far end, past the third shelter" needs per-station geometry that no feed
  provides. For one route that is a hand-built table of a dozen stations —
  see `brighton-line-notes.md`. It is the app's real defensible asset.
- **"Best carriage" is a trade-off, not a fact.** A seat you keep for 55 minutes versus a
  carriage that lands by the Blackfriars exit are different answers. The app must ask, or
  score both.

## 7. Access and licensing, briefly

- Tokens now come from the **Rail Data Marketplace** (`raildata.org.uk`); the old National
  Rail Data Portal was retired in early 2026. Subscribe to "Live Departure Board Web Service
  (LDBWS) - Public" and the free tier is approved instantly; the token is called a
  *Consumer key*.
- LDBWS is now a **REST/JSON API** on `api1.raildata.org.uk`, authenticated with an
  `x-apikey` header — the legacy SOAP OpenLDBWS is the old path.
- Free tier reported at **100,000 calls/month** (~3,300/day). Ample for personal use; tight
  for a public app. Cache hard, proxy server-side, and never ship the key to a browser.
- Darwin XML Push Feeds are reported free regardless of volume — which is what makes
  long-run history recording viable.
- Check the licence terms before publishing anything public; personal use is uncontroversial,
  redistribution and commercial use are not. Verify current rate limits and terms on the RDM
  product page rather than trusting these figures.

## 8. Sources

- [Darwin:Train Loading — Open Rail Data Wiki](https://wiki.openraildata.com/index.php?title=Darwin:Train_Loading)
- [Darwin:Formations — Open Rail Data Wiki](https://wiki.openraildata.com/index.php/Darwin:Formations)
- [Darwin:Push Port — Open Rail Data Wiki](https://wiki.openraildata.com/index.php/Darwin:Push_Port)
- [railreader Darwin unmarshaller types (Go) — formation/loading structs](https://pkg.go.dev/github.com/headblockhead/railreader/ingesters/darwin/unmarshaller)
- [Live Passenger Data for Govia Thameslink — CACI case study](https://www.caci.co.uk/insights/case-studies/live-passenger-data-for-govia-thameslink/)
- [Southern — Find a quieter train](https://www.southernrailway.com/travel-information/onboard-travel/find-a-quieter-train)
- [Southeastern — Usual seat availability](https://www.southeasternrailway.co.uk/travel-information/plan-your-journey/usual-seat-availability)
- [TOCs' passenger loading data on Rail Data Marketplace — RailUK Forums](https://www.railforums.co.uk/threads/tocs-passenger-loading-data-on-rail-data-marketplace.275259/)
- [Expected service detail fields in OpenLDBWS — openraildata-talk](https://groups.google.com/g/openraildata-talk/c/BdOgqIm3WHQ)
- [Rail Data Marketplace](https://raildata.org.uk/) and [data product catalogue](https://raildata.org.uk/dataProducts)
- [Darwin Data Feeds — National Rail](https://www.nationalrail.co.uk/developers/darwin-data-feeds/)
- [NRE Darwin Web Service (Public) — Open Rail Data Wiki](https://wiki.openraildata.com/index.php/NRE_Darwin_Web_Service_(Public))
- [British Rail Class 700 — per-coach passenger load on PIS](https://en.wikipedia.org/wiki/British_Rail_Class_700)
