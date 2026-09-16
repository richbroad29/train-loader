# Roadmap

Ordered by what reduces uncertainty fastest, not by what is most fun to build. The first
phase is deliberately not an app.

## Phase 0 — Settle the unknown (this week)

- [ ] Register on Rail Data Marketplace, subscribe to LDBWS - Public, get the Consumer key.
- [ ] Confirm the REST endpoint paths on the product page; update `probes/.env`.
- [ ] Run `ldbws_probe.py` at 08:00 on a weekday from Brighton-line stations.
- [ ] Read one `--keep-raw` service-detail payload by hand. The schema's real shape is worth
      ten minutes of your own eyes.
- [ ] If loading is absent: subscribe to the Darwin push feed, run `pushport_probe.py` 24h.
- [ ] Write the answer, dated, into `docs/01-feasibility.md` §5.

**Exit criterion:** you can state, with a date and a number, what fraction of peak
Brighton-line services carry per-coach loading.

## Phase 1 — Tier C, shipped (a weekend)

Build the smallest thing that is genuinely useful, using no loading data at all.

- [ ] Server-side LDBWS proxy with caching. Key never leaves the server.
- [ ] Departure board for a hardcoded favourite: Brighton → London Bridge / Victoria.
- [ ] Live formation length per service (8 vs 12 car) — this alone prevents the worst advice.
- [ ] Geometry advice from `data/brighton-line.json`: which end, and the walk time.
- [ ] Mobile-first PWA. One screen, one instruction, big text.
- [ ] Walk-time feasibility check: never recommend a carriage the user cannot reach in time.

**Why first:** it is useful on day one, it is unblocked by the data question, and it forces
the geometry table to exist — which is the asset, not the API integration.

## Phase 2 — Calibration and recording (ongoing from day one)

- [ ] Fill in `data/brighton-line.json` for BTN, HHE, GTW, ECR, LBG, VIC. One trip each.
- [ ] One-tap journey log: which coach, how full, seat or not. Yours only, no accounts.
- [ ] If the Push Port carries loading, run the recorder continuously on a small VM.

Thirty logged journeys is enough for a usable personal prior. This phase is cheap, boring,
and the difference between a toy and something you would actually use.

## Phase 3 — Tier B, the model

- [ ] Per-carriage distribution learned from recorded loading, keyed by service pattern ×
      day-of-week × time band.
- [ ] Combine with `serviceLoading` (typical/expected) for today's whole-train busy-ness.
- [ ] Forecast for origin boarding: "where will this be full after Gatwick".
- [ ] Test hypotheses 1–5 in `brighton-line-notes.md` against the recorded data. Publish the
      answers in the repo — they are interesting whether or not they confirm the design.

## Phase 4 — Tier A, live

Only if Phase 0 says the data is there.

- [ ] Per-coach live loading in interception mode (HHE / GTW / ECR).
- [ ] Freshness handling: an 11-minute-old reading is not a live reading; say so.
- [ ] Disagreement handling: when the live read contradicts the model, show both and trust
      live — but log the disagreement, because a systematic one means the model is wrong in
      a way worth knowing.

## Phase 5 — The version people keep

- [ ] Home-screen widget / lock-screen: next three departures and the recommended coach.
- [ ] "Trains leaving soon near you" as the discovery surface.
- [ ] Seat / Exit / Balanced preference per saved route.

## Explicitly not now

- Other routes or operators. One corridor, done properly.
- Accounts, sync, social features, crowdsourcing at scale.
- Anything that needs the advice to be right for strangers before it is right for you.
