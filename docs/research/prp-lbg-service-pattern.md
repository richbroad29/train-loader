# Preston Park ↔ London Bridge: which services, and in what formations?

Research note for [issue #6](https://github.com/richbroad29/train-loader/issues/6).
Date: 2026-09-16.

Confidence is labelled on every claim, following the house convention in
`docs/02-data-sources.md`:

- **[confirmed]** — stated by a source that owns the fact, and corroborated.
- **[likely]** — one good source, or a strong inference from two; safe to design against,
  worth one check before shipping.
- **[verify]** — plausible, uncorroborated, or possibly stale. Do not build on it.
- **[inferred]** — my reasoning, not anyone's published statement. Flagged as such.

> **Method caveat, read this first.** Outbound network egress from this environment is
> blocked by organisation policy at the proxy. Real Time Trains, National Rail, Wikipedia
> and the operators' own sites (`thameslinkrailway.com`, `southernrailway.com`) all refused
> the CONNECT. Every finding below therefore comes from **search-engine-surfaced content of
> those primary sources**, not from fetching the pages directly. Source URLs are given so
> each claim can be re-checked, but **nothing here has been read off a timetable PDF, a
> journey planner, or a live feed.** The 30 minutes needed to confirm §2 and §3 against a
> live departure board is the highest-value follow-up in this note.

---

## 1. The question

What actually runs between Preston Park (CRS **PRP**) and London Bridge (**LBG**), in both
directions, at commuting times — which operators, how many trains per hour, how long, what
formations, do they split, and where does the southbound evening train come from?

It matters because every downstream answer is keyed to it. "Stand at the back" is a
different physical spot on an 8-car than on a 12-car, and if both run on the same journey
the app has to re-derive carriage position per service rather than remember it.

---

## 2. What I established

### 2.1 Preston Park ↔ London Bridge is a **Thameslink-only** journey

Three operators call at Preston Park, but only one of them goes to London Bridge.

| Operator | Service at PRP | London terminal | Serves LBG? |
|---|---|---|---|
| Southern (`SN`) | London Victoria ↔ Littlehampton, via the Cliftonville Curve, Hove and Worthing | **Victoria** | **No** |
| Gatwick Express (`GX`) | Peak-only calls, Brighton ↔ Victoria | **Victoria** | **No** |
| Thameslink (`TL`) | Bedford ↔ Brighton, and (peaks only) Cambridge ↔ Brighton | through the core | **Yes — all of them** |

- **[confirmed]** Preston Park is served by Southern and Thameslink, with Gatwick Express
  providing "a limited number of services at peak times only". Southern's service there is
  London Victoria ↔ Littlehampton; Thameslink's is Bedford ↔ Brighton.
  ([Preston Park railway station, Wikipedia](https://en.wikipedia.org/wiki/Preston_Park_railway_station))
- **[confirmed]** The Cliftonville Curve links the West Coastway line to the Brighton Main
  Line between Hove and Preston Park, which is why Victoria–Littlehampton trains pass through
  Preston Park without going near Brighton.
  ([Cliftonville Curve, Wikipedia](https://en.wikipedia.org/wiki/Cliftonville_Curve))
- **[likely]** Southern runs **no regular direct PRP → LBG service**. Journey-planner output
  for that pair routes via a change at Haywards Heath.
  ([Southern — Preston Park to London Bridge](https://www.southernrailway.com/journey/preston-park-to-london-bridge))
  *Caveat:* GTR peak timetables carry one-off workings, and I could not read a full peak
  timetable. Treat "zero Southern PRP→LBG trains" as **[verify]**, not gospel.
- **[verify]** Gatwick Express peak calls at Preston Park (with Burgess Hill and Hassocks,
  half-hourly in the peak) are documented, but the Brighton extensions have been cut back
  more than once since 2020. Either way they run to **Victoria** and are out of scope here.
  ([Gatwick Express, Wikipedia](https://en.wikipedia.org/wiki/Gatwick_Express))

**Design consequence:** the app's PRP↔LBG journey is single-operator and — see §3 —
single-fleet. That is the best possible case for stable advice.

### 2.2 Two Thameslink service groups, both via London Bridge

- **[confirmed]** The Cambridge ↔ Brighton Thameslink route runs through the core via
  **London Bridge**: Cambridge – … – St Pancras International – Farringdon – City Thameslink
  – Blackfriars – **London Bridge** – East Croydon – Gatwick Airport – Three Bridges –
  Haywards Heath – Burgess Hill – Brighton.
  ([Thameslink, Wikipedia](https://en.wikipedia.org/wiki/Thameslink);
  [Brighton Main Line, Wikipedia](https://en.wikipedia.org/wiki/Brighton_Main_Line))
- **[likely]** The all-day Bedford ↔ Brighton group **also runs via London Bridge**, and runs
  **non-stop between East Croydon and London Bridge**.
  ([Thameslink — Brighton to Bedford](https://www.thameslinkrailway.com/journey/brighton-to-bedford))
  This is the one routing fact worth double-checking, because the same corridor was diverted
  **via Elephant & Castle** for roughly two years from 2015 while London Bridge was rebuilt
  ([Thameslink, Wikipedia](https://en.wikipedia.org/wiki/Thameslink)), and stale write-ups of
  that arrangement are still in circulation. Two things say the London Bridge routing is the
  current one: the 2018 Thameslink Programme restored London Bridge to the core, and the
  Preston Park service-change reporting in §2.3 only makes arithmetic sense if the
  pre-existing 2 tph already called there.
- **[inferred]** Geography backs this up. From Blackfriars the only sensible path to East
  Croydon and the Brighton Main Line is via London Bridge and Norwood Junction; the
  Elephant & Castle path reaches the BML only by the long way round through Herne Hill,
  Tulse Hill and Selhurst, which is what made it a rebuild-era diversion rather than a
  timetabled route.

### 2.3 Trains per hour: 2 tph off-peak, **4 tph in both peaks**

The peak doubling is recent and deliberate. From the timetable change of **Sunday 10
December 2023**:

- **[confirmed]** Six morning-peak Brighton → Cambridge departures were retimed five minutes
  earlier and given **additional calls at Hassocks and Preston Park**, departing Brighton at
  **0609, 0639, 0709, 0739, 0809, 0839** (previously 0614, 0644, 0714, 0744, 0814, 0844).
- **[confirmed]** Six evening-peak Cambridge → Brighton departures (from Cambridge at 1453,
  1523, 1553, 1623, 1653, 1724) likewise gained calls at Hassocks and Preston Park. These
  trains **depart London Bridge at 1615, 1645, 1715, 1745, 1815, 1845**.
- **[confirmed]** The stated effect: Preston Park and Hassocks each go from **two to four
  Thameslink trains per hour to London Bridge in the AM peak and from London Bridge in the PM
  peak**.

  ([More peak Preston Park trains timetabled from next month — Brighton and Hove News, 22 Nov 2023](https://www.brightonandhovenews.org/2023/11/22/more-peak-preston-park-trains-timetabled-from-next-month/);
  [GTR announces more trains for passengers — RailUK](https://railuk.com/travel/gtr-announces-more-trains-for-passengers/))

So the shape is:

| | Off-peak | AM peak (PRP → LBG) | PM peak (LBG → PRP) |
|---|---|---|---|
| Bedford ↔ Brighton | 2 tph | 2 tph | 2 tph |
| Cambridge ↔ Brighton | calls at PRP: **no** | **2 tph** | **2 tph** |
| **Total at Preston Park** | **2 tph** | **4 tph** | **4 tph** |

- **[verify]** Whether the December 2023 Preston Park calls survive into the current
  (December 2025) timetable. The December 2024 GTR change was focused on Great Northern and
  the East Coast Main Line, with "no significant changes to Thameslink or Gatwick Express"
  ([GTR press release](https://www.mynewsdesk.com/uk/govia-thameslink-railway/pressreleases/improved-timetable-for-great-northern-and-thameslink-passengers-on-east-coast-main-line-3420455)),
  and the December 2025 change confirms Cambridge–Brighton still exists as a service group —
  it gains a call at the new Cambridge South station in early 2026
  ([GTR press release](https://www.mynewsdesk.com/uk/govia-thameslink-railway/pressreleases/great-northern-and-thameslink-improves-services-in-december-timetable-3402924)).
  Nothing suggests the Preston Park calls were withdrawn, but nothing confirms they persist.

### 2.4 Journey time: about an hour

- **[likely]** Fastest PRP → LBG **1 h 02**, average **1 h 11**; roughly 48–50 services a day
  on the pair. Off-peak the Thameslink is half-hourly.
  ([Trainline](https://www.thetrainline.com/train-times/preston-park-to-london-bridge);
  [Thameslink — London Bridge to Preston Park](https://www.thameslinkrailway.com/journey/london-bridge-to-preston-park))
  These are aggregate journey-planner figures, not peak-specific, and the average is inflated
  by indirect itineraries via a change.
- **[verify]** Exact Preston Park departure times. I have Brighton departures (0609 etc.) and
  London Bridge departures (1615 etc.) but not the Preston Park times themselves. Preston
  Park is ~2 miles from Brighton, so **[inferred]** the AM calls land around **0614, 0644,
  0714, 0744, 0814, 0844** — which is neatly the *old* Brighton departure times, and is
  exactly the sort of coincidence that should be checked rather than trusted.

---

## 3. Formations — the part that decides the product

### 3.1 One fleet: Class 700, and nothing else

Because the journey is Thameslink-only (§2.1), the rolling stock question collapses to a
single class.

- **[confirmed]** Class 700 comes in exactly two variants: **700/0 with 8 cars** (60 units,
  700001–700060) and **700/1 with 12 cars** (55 units, 700101–700155).
  ([British Rail Class 700, Wikipedia](https://en.wikipedia.org/wiki/British_Rail_Class_700))
- **[confirmed]** Capacities: 700/0 — 427 seats + 719 standing. 700/1 — 242.6 m long,
  666 seats (52 First, 614 Standard) + 1,088 standing. (same source)
- **[likely]** Allocation follows route type: the **55 twelve-car 700/1s work the main-line
  routes — Bedford–Brighton and Brighton–Cambridge/Peterborough** — while the eight-car
  700/0s work the suburban routes (Sutton loop, Sevenoaks and similar). (same source)

  **This is the single most important claim in this note**, and it is the one I am least able
  to verify from here. It is a fleet-deployment statement in a Wikipedia article, not an
  operator diagram. Real operations short-form: a 700/0 substituted for a 700/1 on a peak
  Brighton working is an ordinary Tuesday, not an exception.

- **Class 377 (Southern) and Class 387 (Gatwick Express) are not in scope for this journey.**
  They run the Victoria services that call at Preston Park, so they will show up in any
  departure-board scrape of PRP and must be filtered out by destination, not by station.
  ([British Rail Class 377, Wikipedia](https://en.wikipedia.org/wiki/British_Rail_Class_377);
  [British Rail Class 387, Wikipedia](https://en.wikipedia.org/wiki/British_Rail_Class_387))

### 3.2 No splitting, no joining — the 700 is a fixed formation

- **[confirmed]** Class 700 units are **fixed formations that cannot couple or split in
  passenger service**. This is a known design constraint of the fleet, repeatedly discussed
  as the trade-off for consistent long trains: no flexibility to run shorter or to attach a
  strengthening portion.
  ([British Rail Class 700, Wikipedia](https://en.wikipedia.org/wiki/British_Rail_Class_700);
  [Thameslink/Class 700 Progress — RailUK Forums](https://www.railforums.co.uk/threads/thameslink-class-700-progress.92632/))

  **This is very good news for the product.** It means:
  1. **No portion working anywhere on PRP↔LBG.** The coach you board at Preston Park is
     still in the train, in the same position, at London Bridge — and vice versa.
  2. The *only* formation variable on this journey is **8 vs 12**, and it is a
     unit-substitution question, not a splitting question. One integer per service.

- **[confirmed]** Southern's Brighton Main Line services *do* split and join — typically at
  **Haywards Heath**, where Victoria portions divide for Littlehampton / Eastbourne /
  Hastings. Those are Class 377 Victoria services and therefore **outside** the PRP↔LBG
  journey, but they are on the same tracks and in the same departure boards, so a naive
  scrape will pick them up.
  ([British Rail Class 377, Wikipedia](https://en.wikipedia.org/wiki/British_Rail_Class_377);
  [377 Joining and Splitting — RailUK Forums](https://www.railforums.co.uk/threads/377-joining-and-splitting.119944/))

### 3.3 Coach numbering, and the direction trap

- **[likely]** Class 700 coaches are numbered **1–12** (or 1–8), and First Class sits at
  **coach 1 or coach 12 depending on the direction of travel** — i.e. the numbering is fixed
  to the *unit*, and which physical end of the train is "the front" flips between the
  northbound and southbound leg.
  ([Thameslink First Class guide](https://uk.trip.com/trains/guide/thameslink-first-class/);
  [Thameslink Class 700 audio description guide (PDF)](https://www.thameslinkrailway.com/-/media/goahead/gtr-all-shared-pdfs-and-documents/accessibility/tl-700-trains-guide/train-description-guide--class-700.pdf))
- **[verify]** Whether the coach numbering is fixed to unit orientation or is re-based per
  direction. This matters enormously and is exactly the kind of thing the Darwin `formation`
  message settles for free — `docs/01-feasibility.md` §2 already records that Darwin lists
  coaches **front-to-rear in the direction of travel**, which resolves the ambiguity *if you
  read it live and never cache it.*

---

## 4. Southbound: origin, and the upstream loading sensor

### 4.1 Where the evening trains come from

- **[confirmed]** The PM-peak Preston Park trains are the **Cambridge → Brighton** workings,
  starting at Cambridge at 1453, 1523, 1553, 1623, 1653 and 1724 and passing London Bridge at
  1615, 1645, 1715, 1745, 1815, 1845. ([Brighton and Hove News, as above](https://www.brightonandhovenews.org/2023/11/22/more-peak-preston-park-trains-timetabled-from-next-month/))
- **[likely]** The other 2 tph are the all-day **Bedford → Brighton** workings.

Both have therefore run the full length of the Thameslink core before reaching London Bridge.
By the time the user boards at London Bridge the train has already loaded at St Pancras
International, Farringdon, City Thameslink and Blackfriars.

### 4.2 The sensor is **London Blackfriars**

- **[confirmed]** The southbound core calling order is
  **St Pancras International → Farringdon → City Thameslink → London Blackfriars → London
  Bridge**. City Thameslink sits between Blackfriars to the south and Farringdon to the north.
  ([City Thameslink railway station, Wikipedia](https://en.wikipedia.org/wiki/City_Thameslink_railway_station);
  [Blackfriars station, Wikipedia](https://en.wikipedia.org/wiki/Blackfriars_station))

So the calling point immediately upstream of London Bridge southbound is **London Blackfriars
(CRS `BFR`)**, roughly three to four minutes ahead. That is the loading sensor for the
evening leg.

- **[inferred]** This is a genuinely useful sensor, unlike the Brighton case in
  `01-feasibility.md` §6. At Brighton the train starts empty so live loading says nothing.
  A southbound train reaching Blackfriars has already absorbed four core stations' worth of
  City and Farringdon commuters, so its per-coach distribution at Blackfriars is real signal.
- **[inferred]** But it is *incoming* signal only. London Bridge is itself one of the
  heaviest boarding points on the route, so the Blackfriars reading tells you which coaches
  still have seats **as the train arrives** — not what happens once the London Bridge crowd
  gets on. Read it as "where the gaps are", and let the platform-geometry tier handle the
  fact that everyone else is boarding alongside you.

### 4.3 Northbound, Preston Park has a sensor too — and this is a finding

- **[inferred]** Going north, Preston Park's immediate upstream calling point is **Brighton**
  itself, one stop and roughly four minutes back. Every Preston Park → London Bridge service
  in §2.3 originates at Brighton.

  That makes **Preston Park a structurally better case than Brighton** for this whole product.
  At Brighton the train is empty and the problem is forecasting. At Preston Park the train
  arrives already loaded with the Brighton departure crowd, and a `formationLoading` reading
  taken at Brighton is a four-minute-old, per-coach, live picture of the exact train pulling
  in. The repo's framing so far — "Brighton is the easy structural case, live sensing only
  matters at Haywards Heath and Gatwick" (`docs/brighton-line-notes.md`) — undersells
  Preston Park. It is an *interception* station, not an origin, and it is the user's home
  station.

---

## 5. What remains unverified

In rough order of how much it would change the design:

1. **The 12-car assumption (§3.1).** The claim that BML Thameslink diagrams are 700/1s rests
   on one Wikipedia fleet-allocation sentence. Needs confirming against real formations, and
   needs a measured **rate of 8-car substitution** — "usually 12, occasionally 8" is a very
   different product from "always 12".
2. **Whether the Bedford–Brighton group calls at London Bridge (§2.2).** Treated as
   **[likely]**. If it in fact runs via Elephant & Castle, the off-peak PRP↔LBG service is
   *zero* and the journey is peak-only. One departure-board look settles it.
3. **Whether the December 2023 peak Preston Park calls are still in the 2026 timetable
   (§2.3).** Everything about the peak frequency depends on this.
4. **Exact Preston Park departure and arrival times (§2.4).** Currently inferred.
5. **Whether any Southern working runs PRP → LBG direct (§2.1).** Believed none; not proven.
6. **Gatwick Express peak calls at Preston Park (§2.1).** Irrelevant to LBG but relevant to
   any departure-board filtering.
7. **Coach-numbering orientation (§3.3).**
8. **A frequency inconsistency I could not resolve.** Wikipedia gives Preston Park "three per
   hour" total, while the component figures point to 2 tph Thameslink plus up to 2 tph
   Southern Littlehampton. One of the two is stale. It does not affect the LBG answer, but it
   is a reminder that the Wikipedia station article is not a timetable.
9. **Platform geometry at Preston Park.** **[confirmed]** the station has **two long island
   platforms with three platform faces in use, linked by a subway with steps**, and the ticket
   office is on the main London-bound platform.
   ([Preston Park railway station, Wikipedia](https://en.wikipedia.org/wiki/Preston_Park_railway_station))
   Where that subway lands relative to where coach 1 and coach 12 of a 700/1 stop is
   unmeasured, and is exactly the calibration job in `docs/brighton-line-notes.md`.

**The cheapest way to close 1–5 is one run of `probes/ldbws_probe.py` against PRP and LBG
across a single peak.** It already pulls formations per service and reports per-operator
coverage. This note has taken the desk research as far as blocked egress allows; the
remaining questions are measurement questions, which is the same conclusion
`01-feasibility.md` reached about loading data.

---

## 6. Implications for carriage advice

1. **One operator, one fleet, no portion working.** This is the cleanest possible journey for
   the app. No Southern/Thameslink formation mismatch, no splitting, no "the front four
   coaches detach at Haywards Heath". The coach you pick is the coach you keep, end to end.
2. **Advice can be a coach number — but only if length is re-derived per service.** If §3.1
   holds and it is 12-car almost always, then advice *is* stable between days, which is what
   the ticket was really asking. If 8-car substitutions are common, the app must say
   "3rd coach from the front" rather than "coach 10", because a cached coach number is worse
   than no advice. `docs/brighton-line-notes.md` already states this rule; this research
   suggests the risk is lower here than on the Southern services, but does not eliminate it.
3. **Express position as a fraction, not a coach index.** Since the only variable is 8 vs 12,
   a position expressed as "fraction of train length from the London end" survives the
   substitution and converts to a coach number at render time.
4. **Peak means a real choice of train.** 4 tph gives the app something extra to say —
   "the 0744 is usually emptier than the 0739" — which the 2 tph off-peak service does not.
   That is a Tier B question for recorded history, not a Tier C geometry question.
5. **Two usable live sensors, one per direction.** Southbound: **Blackfriars**, 3–4 minutes
   before London Bridge. Northbound: **Brighton**, 3–4 minutes before Preston Park. Both give
   a live per-coach read of the actual train, which is the case `01-feasibility.md` identified
   as where loading data is decisive. Preston Park is not the "empty train at the origin"
   problem; it is the interception problem, in both directions.
6. **Filter departure boards by destination, not by station.** A PRP board carries Southern
   Victoria services and Gatwick Express as well as the Thameslink London Bridge trains, and
   the Southern ones split at Haywards Heath. Mixing them would poison both the advice and
   any recorded loading history.

---

## 7. Sources

Primary or near-primary, all accessed indirectly via search (see the method caveat at the
top):

- [Preston Park railway station — Wikipedia](https://en.wikipedia.org/wiki/Preston_Park_railway_station)
- [Cliftonville Curve — Wikipedia](https://en.wikipedia.org/wiki/Cliftonville_Curve)
- [Brighton Main Line — Wikipedia](https://en.wikipedia.org/wiki/Brighton_Main_Line)
- [Thameslink — Wikipedia](https://en.wikipedia.org/wiki/Thameslink)
- [Thameslink Programme — Wikipedia](https://en.wikipedia.org/wiki/Thameslink_Programme)
- [British Rail Class 700 — Wikipedia](https://en.wikipedia.org/wiki/British_Rail_Class_700)
- [British Rail Class 377 — Wikipedia](https://en.wikipedia.org/wiki/British_Rail_Class_377)
- [British Rail Class 387 — Wikipedia](https://en.wikipedia.org/wiki/British_Rail_Class_387)
- [Gatwick Express — Wikipedia](https://en.wikipedia.org/wiki/Gatwick_Express)
- [City Thameslink railway station — Wikipedia](https://en.wikipedia.org/wiki/City_Thameslink_railway_station)
- [Blackfriars station — Wikipedia](https://en.wikipedia.org/wiki/Blackfriars_station)
- [Thameslink — Preston Park to London Bridge](https://www.thameslinkrailway.com/journey/preston-park-to-london-bridge)
- [Thameslink — London Bridge to Preston Park](https://www.thameslinkrailway.com/journey/london-bridge-to-preston-park)
- [Thameslink — Brighton to Bedford](https://www.thameslinkrailway.com/journey/brighton-to-bedford)
- [Thameslink — Preston Park station information](https://www.thameslinkrailway.com/travel-information/plan-your-journey/station-information/PRP/preston-park)
- [Thameslink — Class 700 audio description guide (PDF)](https://www.thameslinkrailway.com/-/media/goahead/gtr-all-shared-pdfs-and-documents/accessibility/tl-700-trains-guide/train-description-guide--class-700.pdf)
- [Southern — Preston Park station information](https://www.southernrailway.com/travel-information/station-information/PRP/preston-park)
- [Southern — Preston Park to London Bridge](https://www.southernrailway.com/journey/preston-park-to-london-bridge)
- [GTR — Great Northern and Thameslink improves services in December timetable](https://www.mynewsdesk.com/uk/govia-thameslink-railway/pressreleases/great-northern-and-thameslink-improves-services-in-december-timetable-3402924)
- [GTR — Improved timetable on the East Coast Main Line](https://www.mynewsdesk.com/uk/govia-thameslink-railway/pressreleases/improved-timetable-for-great-northern-and-thameslink-passengers-on-east-coast-main-line-3420455)
- [More peak Preston Park trains timetabled from next month — Brighton and Hove News, 22 Nov 2023](https://www.brightonandhovenews.org/2023/11/22/more-peak-preston-park-trains-timetabled-from-next-month/)
- [GTR announces more trains for passengers — RailUK](https://railuk.com/travel/gtr-announces-more-trains-for-passengers/)
- [Thameslink/Class 700 Progress — RailUK Forums](https://www.railforums.co.uk/threads/thameslink-class-700-progress.92632/)
- [377 Joining and Splitting — RailUK Forums](https://www.railforums.co.uk/threads/377-joining-and-splitting.119944/)
- [Trainline — Preston Park to London Bridge train times](https://www.thetrainline.com/train-times/preston-park-to-london-bridge)

**Sources I wanted and could not reach:** Real Time Trains
(`realtimetrains.co.uk`, blocked) for actual formations and per-service calling patterns;
National Rail (`nationalrail.co.uk`, blocked) for the published timetable; the GTR timetable
PDFs. These are the right sources for closing §5 items 1–5 and should be used when egress
allows.
