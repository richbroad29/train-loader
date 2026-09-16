# Data sources

Reference sheet for everything the app might consume. Marked **[confirmed]** where the
research in `01-feasibility.md` is solid, **[verify]** where it must be checked against the
live service before you rely on it.

## A. Darwin — the only source of per-coach loading

Darwin is National Rail's real-time information engine. Two ways in.

### A1. LDBWS (request/response) — start here

- **[confirmed]** Access via Rail Data Marketplace: create an account at `raildata.org.uk`,
  subscribe to *Live Departure Board Web Service (LDBWS) - Public*, instant approval, free
  tier. The credential is a **Consumer key**, sent as the `x-apikey` header.
- **[verify]** REST base path reported as:
  `https://api1.raildata.org.uk/1010-live-departure-board-dep/LDBWS/api/20220120/GetDepBoardWithDetails/{CRS}`
  Confirm the exact product prefix and version segment on the RDM product page — they differ
  per product and change. `probes/ldbws_probe.py` takes them from env vars for this reason.
- **[confirmed]** Legacy SOAP OpenLDBWS (`lite.realtime.nationalrail.co.uk`, schema
  `2021-11-01`) still documented; the REST product is the current route.
- **[verify]** ~100,000 calls/month on the free tier.
- Operations that matter: `GetDepBoardWithDetails` (board + calling points in one call),
  `GetServiceDetails` (full detail for one `serviceID` — where formation should appear).
- **[verify]** Whether per-coach loading appears here at all. A developer report has the
  public service omitting documented fields (typical loading, previous calling points) that
  the staff service does return.

### A2. Darwin Push Port (streaming) — needed for history, maybe for loading

- STOMP feed of gzipped XML messages; **[confirmed]** reported free at any volume.
- Carries the full message set including `formationLoading`, which the request/response API
  may flatten or omit.
- **[verify]** Current broker host/port/topic and credentials — obtain from the RDM product
  page for the Darwin push feed. Historically `darwin-dist-*.nationalrail.co.uk:61613`.
- This is the feed to run 24/7 and persist, because **the historical archive is the asset**
  (see `01-feasibility.md` §6). Nobody else has a per-coach loading history for the Brighton
  line; after three months, you would.

### A3. LDBSVWS (staff version)

- **[confirmed]** "Simply a more granular version of LDBWS" with extra fields on responses.
- **[verify]** Whether it is obtainable on the public/open tier via RDM or is restricted.
  If loading is missing from the public LDBWS but present here, this is the unlock.

### Schema elements to look for

```
formation
  coach[]            identifier ("A", "1"), class ("First"/"Standard"), toilet{status,type}
                     ORDERED FRONT TO REAR in direction of travel
formationLoading     rid, fid, tpl (location)
  loading[]          coachNumber, loadingPercentage (int 0-100), source, sourceSystem
serviceLoading       rid, tpl
  loadingCategory    code (1-4 chars) + type: "Typical" | "Expected"
  loadingPercentage  int 0-100 + type
LoadingCategoryReference   code, name, TOC, typicalDescription, expectedDescription,
                           definition, colour (hex), image
```

Notes: 0 = lowest load, 100 = highest. Coach identifiers "are not necessarily alphabetically
or numerically sequential" — never sort them, use feed order. Loading is published per
calling location, not once per service.

## B. Station and geometry data

| Need | Source | Status |
|---|---|---|
| CRS codes, names, lat/long | RDM stations product; NaPTAN (open, DfT); openraildata station CSVs | **[verify]** which is cleanest |
| Platform for today's train | LDBWS board (`platform`) | **[confirmed]** but often late at Brighton |
| Where the stairs/exits/barriers are on each platform | **Does not exist in any feed** | Hand-built — `brighton-line-notes.md` |
| Coach → position on platform | Derived: feed order + direction of travel + platform layout | Hand-built |

The last two are the moat. There is no API for "the exit at Haywards Heath is at the London
end"; a daily commuter can calibrate it in a fortnight.

## C. Fallbacks if per-coach loading is absent

1. **`serviceLoading` (Typical/Expected)** — whole-train busy-ness. Widely populated;
   Southern's public "find a quieter train" tool is built on the same counting data
   (previous-two-weeks average, refreshed daily).
2. **Your own recorded history** — log what you observe. For a single commuter on a single
   route, ~30 logged journeys gives a usable per-carriage prior. This is not a consolation
   prize: it is the highest-quality data available for *your* specific trains.
3. **Crowdsourced reports** — one-tap "got a seat in coach 8". Chicken-and-egg at scale, but
   viable for one line with a few dozen regulars.
4. **Geometry prior alone** — distance-decay from the platform entrance. Weak per train,
   strong on average, and available with zero data.

## D. Deliberately not used

- **Scraping operator apps/websites** for their internal loading JSON. Technically possible,
  fragile, and outside the licence you would be operating under. Not recommended as a primary
  source; acceptable only as a one-off sanity check of what GTR itself knows.
- **Network Rail TRUST/TD feeds** — excellent for train running and berth-level tracking,
  no passenger loading. Add later if you want accurate "where is it now".
- **Real Time Trains API** — good schedules and running data, not a loading source.

## E. Security

- The Consumer key is a secret. Server-side only; never in a client bundle, never committed.
  `probes/` reads it from the environment and `.env` is gitignored.
- If the app becomes public, the key is a shared resource with a monthly quota — one abusive
  client exhausts everyone's budget. Rate-limit per session at the proxy.
