# Brighton Main Line — domain notes and calibration guide

Companion to `data/brighton-line.json`. This is the part of the product no API provides and
no competitor can copy quickly: knowing that the front of a Brighton departure is a
90-second walk from the barriers, and that this is precisely why it has seats.

## Route facts that drive the model

- **Operators:** Southern (`SN`), Thameslink (`TL`), Gatwick Express (`GX`). Great Northern
  (`GN`) is the same owning group but not this corridor.
- **Two London destinations, two different products.** Victoria services (via Clapham
  Junction) terminate; Thameslink services (via London Bridge) run through to Blackfriars,
  City Thameslink, Farringdon, St Pancras and beyond. Through-running changes the exit
  calculus completely — on a Thameslink service most of the train does not empty at the
  first London stop.
- **Formation varies.** 8 and 12-car are both routine; Southern services attach/detach
  portions. **Never cache a coach number between services** — always re-derive from today's
  live formation length. Advice to "get coach 11" on an 8-car train is worse than no advice.
- **Fleets:** Class 377/387 (Southern/Gatwick Express) and Class 700 (Thameslink). The 700s
  measure load per car natively for their on-board displays; the 377/387s rely on Southern's
  passenger counting equipment. Data availability may well differ by fleet, so the probe
  reports coverage **per operator**, and you should read it per fleet too.

## The geometry model

All positions in `data/brighton-line.json` are a fraction from the **London end** (0.0) of
the platform to the **country end** (1.0). This holds regardless of travel direction and
never needs re-basing.

Two functions come out of it:

1. **Boarding density prior** — people cluster near where they arrived on the platform.
   Density decays with distance from each access point. So at Brighton, with its single
   access point at `pos 1.0`, the emptiest coaches are reliably near `pos 0.0`: the front.
2. **Exit penalty** — at the destination, walking the length of a 12-car train costs roughly
   a minute plus the crowd. A carriage next to the escalators at London Bridge is worth real
   money to a commuter and the app should price it.

The two pull in opposite directions on this route, which is the whole reason the
Seat / Exit / Balanced preference exists (see `03-product-concept.md`).

## Why Brighton is the easy case and Victoria is the trap

- **Brighton:** terminus, concourse at the buffers (south), all London trains depart north.
  Front = far end = long walk = quiet. Structurally certain, no measurement needed.
- **Victoria:** terminus, buffers at the north end, so an arriving train's **front** is at
  the concourse. Front coaches are the fast exit — and everyone who works that out fills
  them. The carriage that was quiet leaving Brighton may be the one everyone crowds into by
  Clapham Junction. This is a real, checkable hypothesis and one of the first things the
  recorded loading history should be asked.

## Calibration protocol

Everything marked `unverified` in the JSON needs one trip to fix. Doing it properly:

1. On the platform, note where you came onto it — barrier, footbridge, subway, escalator —
   as a fraction of platform length from the London end. Pacing is fine; ±0.1 is plenty.
2. Note **which coach number stops opposite that access point** on a 12-car and on an 8-car
   train. Stopping positions differ by formation length and that difference is exactly what
   breaks naive advice.
3. Time the full-platform walk. This gates the "can they actually get there" check.
4. Photograph the platform-length view from each access point. Cheap, and settles arguments
   with your own memory later.

Priority order, by value: **BTN** (done, structural) → **HHE** → **GTW** → **ECR** →
**LBG** → **VIC** → the rest. Those five cover the overwhelming majority of real journeys on
this corridor.

## Hypotheses worth testing against recorded data

Write them down now so the data can prove you wrong later:

1. Front coaches at Brighton stay quieter all the way to East Croydon. *(Expected true.)*
2. On Victoria services the front fills progressively from Clapham Junction as people
   position for the exit. *(Expected true, and it would mean the best seat for Brighton→
   Victoria is not the best seat for Brighton→East Croydon.)*
3. Gatwick boarding is near-uniform across the train — luggage and unfamiliarity beat
   optimisation — so the post-Gatwick distribution mostly preserves the pre-Gatwick one.
   *(Genuinely uncertain, and important: if true, advice given at Brighton survives Gatwick.)*
4. 12-car services have a quieter "dead zone" around the join than 8-car services do.
5. First-class declassification and the toilet positions distort local density enough to
   matter. `formation` carries coach class and toilet status, so this is testable for free.
