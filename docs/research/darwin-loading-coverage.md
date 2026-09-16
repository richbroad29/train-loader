# Darwin loading data for Southern and Thameslink: what is published, and at what granularity

Resolves the desk-research half of [issue #2](https://github.com/richbroad29/train-loader/issues/2).
Date: 2026-09-16. Desk research only — **no live query was made** (the RDM key is on the VPS,
out of reach from here). Every claim below is labelled with a confidence level and the source
it rests on.

Builds on `docs/01-feasibility.md` and `docs/02-data-sources.md`; it does not restate them.
Where it contradicts them, §6 says so explicitly.

## 1. The question

For Southern (SN) and Thameslink (TL) services calling at Preston Park (PRP) and London
Bridge (LBG):

1. Is `formationLoading` — 0–100 per `coachNumber`, per calling location — populated? Public
   feed, staff feed (LDBSVWS), or neither?
2. Is there a **historic / typical figure per carriage**, or only per whole train? Rich
   believes a historic per-carriage figure exists in the API and so will not need deriving.
3. Are ordered coach formations published for these operators?

## 2. What I could and could not reach

This matters for reading everything below. The network egress allowlist in this environment
permitted **github.com / raw.githubusercontent.com and a web search index, and nothing else**.
Specifically blocked: `wiki.openraildata.com`, `raildata.org.uk`, `nationalrail.co.uk`,
`railforums.co.uk`, `groups.google.com`, `caci.co.uk`, `en.wikipedia.org`,
`rspaccreditation.org`.

The consequence is a clean split:

- **The schema questions are fully answered**, because the official Darwin XSDs — the ones
  shipped by RDG/Thales and vendored verbatim into public repos, including National Rail's
  own `openraildata` GitHub org — were reachable and I read them directly. That is a primary
  source, not a write-up of one.
- **The operator-coverage question is not answered at all**, because every source that could
  have spoken to it was blocked. I have nothing on GTR coverage beyond what
  `01-feasibility.md` already records, and I am not going to launder search-engine summaries
  of a forum thread into a finding.

## 3. What I established

### 3.1 The per-coach message has no historic variant. This is the answer to Q2.

**Confidence: high.** Read directly from the shipped schema, latest version.

The current Push Port schema is v18 (`27/06/2023`, "Copyright (c) 2023 RDG & Thales"). I found
no v19 or v20 anywhere on GitHub, so v18 is current.
[`rttiPPTSchema_v18.xsd`](https://raw.githubusercontent.com/Phils0/DarwinClient/master/schemas/rttiPPTSchema_v18.xsd)

Two distinct loading elements sit side by side in `DataResponse`, and v18 documents the
relationship between them in so many words:

> `serviceLoading` — "Service-level Train Loading data. This loading data applies to **the
> whole service** at the specified locations. Note that loading data may also be provided at
> the coach-level using the formationLoading element. Consumers should favour the coach-level
> data, as this is more granular, but both may be provided. Also note that the
> loadingPercentage value here is the same data as the avgLoading element on schedule
> elements. The avgLoading element will be removed in a future release, so consumers must
> migrate to use this data instead."

> `formationLoading` — "Formation-level Train Loading data. This loading data applies to **the
> individual coaches** in a formation at the specified locations."

Now the crux. The `Typical` / `Expected` marker lives on **one** of these and not the other.

`serviceLoading` is typed `fm3:LoadingData` from Formations/v3, added at Push Port v17
(`01/11/2021`, "Support for Train Loading Categories").
[`rttiPPTFormations_v3.xsd`](https://raw.githubusercontent.com/Phils0/DarwinClient/master/schemas/rttiPPTFormations_v3.xsd)

```xml
<xs:simpleType name="LoadingValueType">
  <xs:documentation>The "type" of loading data provided. "Typical" loading data is sourced
  from historic data related to previous services that have run. "Expected" data is specific
  to the service to which it is attached.</xs:documentation>
  <xs:restriction base="xs:string">
    <xs:enumeration value="Typical"/>
    <xs:enumeration value="Expected"/>
  </xs:restriction>
</xs:simpleType>
```

That `type` attribute (default `Typical`) is carried by the `LoadingAttrs` attribute group,
and `LoadingAttrs` is referenced in exactly two places — on `loadingCategory` and on
`loadingPercentage`, both children of `LoadingData`. `LoadingData` is keyed on `rid` + `tpl`.
**It has no coach dimension at all.**

`formationLoading` is typed `fm:Loading` from Formations/v1, unchanged since Push Port v15
(`02/02/2017`) and still the type used in v18.
[`rttiPPTFormations_v1.xsd`](https://raw.githubusercontent.com/openraildata/stomp-client-python/master/ppv16/rttiPPTFormations_v1.xsd)

```xml
<xs:complexType name="CoachLoadingData">
  <xs:documentation>Type describing the loading data for an identified coach.</xs:documentation>
  <xs:simpleContent>
    <xs:extension base="ct3:LoadingValue">
      <xs:attribute name="coachNumber" type="ct3:CoachNumberType" use="required"/>
      <xs:attribute name="src" type="xs:string" use="optional"/>
      <xs:attribute name="srcInst" type="ct:SourceTypeInst" use="optional"/>
    </xs:extension>
  </xs:simpleContent>
</xs:complexType>
```

`coachNumber`, `src`, `srcInst`, and a 0–100 integer. **No `type`. No `Typical`. No historic
variant.** Nine years of schema evolution — v15 through v18 — did not add one.

> **Q2 is refuted.** There is no historic or typical per-carriage figure in Darwin, on any
> feed, at any access tier. The only historic figure Darwin publishes is whole-train:
> `serviceLoading` with `type="Typical"`. A per-carriage typical profile does not exist to be
> read; it has to be built by recording `formationLoading` over weeks. This is a property of
> the schema, not of GTR's coverage, so no live query can overturn it.

Supporting confirmation from the request/response side: the public LDBWS 2017-10-01 schema
defines `avgLoading` as
["Average Loading of the train **as a whole** at this Calling Point. This is a fixed value
that is based on **long-term averages** and does not vary according to real-time actual
loading."](https://raw.githubusercontent.com/onewby/bus-boards/main/server/src/darwin/rtti_2017-10-01_ldb_types.xsd)
— the historic figure, explicitly whole-train. The per-coach field in the very same file is
defined as ["The **currently estimated** passenger loading value for this coach, where
known."](https://raw.githubusercontent.com/onewby/bus-boards/main/server/src/darwin/rtti_2017-10-01_ldb_types.xsd)
Two different fields, two different semantics, and only the whole-train one is historic.

### 3.2 Per-coach loading is in the public LDBWS schema, not just the staff one

**Confidence: high for the schema; says nothing about whether GTR populates it.**

Current public schema:
[`rtti_2021-11-01_ldb_types.xsd`](https://raw.githubusercontent.com/onewby/bus-boards/main/server/src/darwin/rtti_2021-11-01_ldb_types.xsd)

- `FormationData` (2021-11-01) = `loadingCategory` (service-level) + `coaches`
  (`ldbt20171001:ArrayOfCoaches`).
- `CoachData` (2017-10-01, still the type in force) = `coachClass`, `toilet`, `loading`
  ("currently estimated…"), with a **required** `number` attribute.
- `formation` hangs off `ServiceItem` (board rows on the `…WithDetails` calls), off
  `CallingPoint`, and off `ServiceDetails`.

So a per-coach 0–100 figure is a documented part of the *public* product. This narrows Q1: if
it is missing for SN/TL it is because GTR does not supply it, not because the public tier
strips it.

Two changes in the 2021-11-01 revision worth knowing before writing a parser:

- **`avgLoading` is gone from the public `FormationData`.** The 2021-11-01 schema replaced it
  with `loadingCategory`. The whole-train *percentage* is no longer on the public
  request/response API; only the *category* is.
- **The public `LoadingCategory` type has no `type` attribute** — just string content plus
  `code`, `colour` and `image`. A public consumer therefore **cannot tell whether a category
  is Typical or Expected**. On the Push Port you can, because `LoadingAttrs` is there. That is
  a real, concrete reason to prefer the Push Port for this project beyond volume.

### 3.3 The staff feed's advantage is the forward-look, and it is exactly what this product needs

**Confidence: high for the schema. Medium that 2017-10-01 is still the current staff version**
— I could only reach `rtti_2017-10-01_ldbsv_types.xsd`, and RDM/National Rail were blocked, so
a newer LDBSV revision may exist.
[`rtti_2017-10-01_ldbsv_types.xsd`](https://raw.githubusercontent.com/nathan3882/SOAPIdealTrains/master/xml-resources/web-service-references/wsdl/wsdl/lite.realtime.nationalrail.co.uk/OpenLDBSVWS/rtti_2017-10-01_ldbsv_types.xsd)

The staff schema's per-coach `loading` is worded identically to the public one ("The currently
estimated passenger loading value for this coach, where known") and adds `src` / `srcInst`
attributes the public feed omits — so the staff feed tells you *where the number came from*
(seat reservations vs weight vs cameras), which the public feed does not.

The bigger difference is structural. On the staff service a service's `formation` is an
`ArrayOfFormationLocations`, not a single `FormationData`:

> "A list of the train formation data at **each non-cancelled calling point** of the train
> running the schedule. If any formation data is available at any of the non-cancelled calling
> points in the schedule then a `fmloc` element will be supplied for all non-cancelled calling
> points in the schedule. If no actual formation data is available at a calling point, the
> `fmloc` element will be empty. If no formation data is available at any of the non-cancelled
> calling points in the schedule then the `formation` element will be absent."

One staff call on a PRP departure returns formation and per-coach loading for **every** calling
point through to LBG. That is precisely the forward-look `01-feasibility.md` §6 identified as
the product's real need, and it is a staff-only shape. It also makes an unusually clean
coverage test: `formation` absent means no data anywhere on that service, unambiguously.

The staff feed still has **no** historic per-coach figure. `FormationData` carries `avgLoading`
(whole-train, long-term average) and that is all.

### 3.4 Coach ordering is *not* guaranteed by any schema I read

**Confidence: high that the schema is silent. Low-to-medium on the front-to-rear rule itself.**

`ArrayOfCoaches` is documented, in all three schemas, as nothing more than "A list of coaches
in a train formation." There is no statement of ordering, direction, or orientation in the
public LDBWS, staff LDBSVWS, or Push Port formations XSDs.

The front-to-rear guarantee that `01-feasibility.md` §2 states as established comes from the
Open Rail Data Wiki's `Darwin:Formations` page, which I could not open (blocked); a search
index rendering of it says the coaches "are listed in order with the first being at the front
of the train, and the last being at the rear". That is a community wiki, not the schema, and I
could not verify it firsthand.

Separately, and this is a genuine find: **`isReverseFormation`** — "True if the service is
operating in the reverse of its normal formation" — exists on `BaseServiceDetails` in the
public LDBWS 2017-10-01 schema and is inherited by the 2021-11-01 `BaseServiceDetails`, so it
reaches `GetServiceDetails` responses; it is also on the staff service. It is **not** on
2021-11-01 `ServiceItem`, which extends the 2016-02-16 base — so departure-board rows do not
carry it and service-detail calls do.

The implication for this app is direct: coach order alone never determines platform position.
You need `isReverseFormation` too, which means you need a per-service detail call, not just a
board.

### 3.5 Partial coverage is designed in

**Confidence: high.** Every loading and formation element in every schema is
`minOccurs="0"`, and the staff schema spells out the "no formation data anywhere on this
service" case as normal and expected. `formationLoading`'s own documentation — "If no loading
data is provided for a coach in the formation then it should be assumed to have been cleared"
— contemplates a formation where only some coaches report.

Darwin is built to carry whatever each operator chooses to supply. Presence for SN/TL is an
operator decision, and there is no schema-level answer to it. Which brings us to what I could
not do.

## 4. What remains unverified

**Q1 (is `formationLoading` populated for SN/TL) and Q3 (are formations published for them)
are exactly as open as they were before this ticket.** I could not reach a single source that
speaks to GTR's coverage. The wiki, Rail Data Marketplace, National Rail's developer pages,
the RailUK forums thread, the openraildata-talk archive and the CACI case study were all
blocked. I will not upgrade a search-engine paraphrase of a forum post into evidence; the
contradictory community reports catalogued in `01-feasibility.md` §4 remain the state of
knowledge, undated and unverified.

Also unverified:

- Whether an LDBSV schema newer than 2017-10-01 exists (medium confidence it does not matter —
  per-coach loading semantics are identical across Push Port v15–v18 and public LDBWS
  2017/2021, so a revision changing them would be a break with nine years of consistency).
- Whether the RDM staff product is subscribable, and on what terms. A search rendering of the
  wiki's RDM page suggests the staff web service on RDM "doesn't currently work" and that the
  SOAP LDBSVWS is the only route — unverified, and moot if Rich's key already works.
- The front-to-rear ordering rule (§3.4).

### The live query that settles it

Run from the VPS, **08:00–09:00 on a weekday**. Off-peak proves nothing: the coaches that
matter are the ones that fill.

**1. Staff feed, PRP (the decisive one).** `GetArrivalDepartureBoardByCRS` for `PRP`, filter to
`toc` in {`SN`, `TL`}. For each service take the RID, call `GetServiceDetailsByRID`, and record
per service:

- is `formation` present at all, or absent? (absent = no data at *any* calling point — a clean
  negative)
- how many `fmloc` entries are non-empty, and at which `tpl`? Specifically: do the TIPLOCs for
  Haywards Heath, Gatwick, East Croydon and London Bridge each carry one, or only the current
  location? (Resolve the TIPLOCs from the Darwin reference data rather than guessing them —
  `tpl` is TIPLOC, not CRS, and the two do not correspond.)
- within each `fmloc`, does any `coaches/coach[@number]/loading` carry a value, and for how
  many of the coaches?
- what `src` / `srcInst` do the loading values declare?
- `avgLoading` present? `isReverseFormation` present?

**2. Same window, public feed, same services.** RDM REST `GetDepBoardWithDetails/PRP` then
`GetServiceDetails/{serviceID}`; check `formation.coaches[].loading` and
`formation.loadingCategory`. Comparing 1 against 2 on the *same services in the same minute* is
the only way to answer "staff feed, public feed, or neither" — anything else confounds coverage
with timing.

**3. Repeat both for LBG**, which is the other end of the corridor and a different set of
platforms and TOCs.

**4. Push Port, 24 hours.** Count `formationLoading` vs `serviceLoading` messages whose RID maps
to an SN/TL schedule calling at PRP or LBG. For every `serviceLoading`, **record the `type`
attribute actually seen on the wire** (`Typical` / `Expected` / absent-so-defaulted). That
confirms in live data what §3.1 establishes from the schema, and it is the one thing that would
show a surprise.

`probes/ldbws_probe.py` already does most of step 2. It needs `PRP` added to its station list;
step 1 needs a staff-feed sibling, which is a small job given the staff service returns the
whole forward-look in one call.

## 5. Recommendation

**Stop treating "historic per-carriage loading from the API" as an open possibility, and
replan around its absence.** §3.1 is not a coverage question that a key would resolve — the
field does not exist in the schema. Darwin's only historic figure is whole-train. If the
product wants to say "coach 11 is usually quiet at Preston Park", that number has to be
manufactured from recorded `formationLoading`, which is the materially larger job issue #2
anticipated. Plan it in now rather than discovering it after the key comes out.

Concretely:

1. **Start the Push Port recorder before anything else**, and leave it running whatever the
   coverage probe says. It is the only route to a per-carriage historic figure, it accrues only
   while something is running, and every week not recording is a week the forecast tier cannot
   be built. `01-feasibility.md` §6 already reached this conclusion for product reasons; §3.1
   makes it the *only* route rather than the preferred one.
2. **Run the staff-feed query at PRP first**, per §4. The staff `fmloc` list is the cheapest and
   most complete coverage test in existence for this corridor, and Rich already has the access.
3. **Prefer the Push Port over the request/response API for loading**, for a reason beyond
   volume: the public `LoadingCategory` has no `type` attribute, so the public feed cannot tell
   you whether a category is typical or expected (§3.2). The Push Port can.
4. **Treat `isReverseFormation` as a required input** to any coach-to-platform-position mapping,
   and note it is only on service-detail responses, not board rows (§3.4).
5. **Do not ship anything that relies on coach ordering until it is confirmed against live
   data**, since no schema guarantees it (§3.4).

### Corrections to existing docs

- `docs/01-feasibility.md` §2 tabulates `formationLoading` and `serviceLoading` in a way that
  reads as though "typical/expected" were a general property of Darwin loading. It is a
  property of `serviceLoading` only. Worth a sentence making that exclusive.
- `docs/01-feasibility.md` §2 states coaches are listed front-to-rear as an established
  property. It is a wiki claim, not a schema guarantee (§3.4). Downgrade it and add
  `isReverseFormation`.
- `docs/02-data-sources.md` §A's schema sketch shows `formation` with `coach[]` but does not
  mention that the public 2021-11-01 `FormationData` dropped `avgLoading`, nor that the staff
  service returns formation per calling point via `fmloc`. Both change what a parser should
  expect.

## 6. Sources

Primary, read directly (verbatim XSDs shipped by RDG/Thales, vendored into public repos —
`openraildata` is National Rail's own GitHub organisation):

- [`rttiPPTSchema_v18.xsd`](https://raw.githubusercontent.com/Phils0/DarwinClient/master/schemas/rttiPPTSchema_v18.xsd) — current Push Port root schema; `serviceLoading` / `formationLoading` documentation
- [`rttiPPTSchema_v16.xsd`](https://raw.githubusercontent.com/openraildata/stomp-client-python/master/ppv16/rttiPPTSchema_v16.xsd) — version history, v15 "Support for Train Formation and Loading data"
- [`rttiPPTFormations_v1.xsd`](https://raw.githubusercontent.com/openraildata/stomp-client-python/master/ppv16/rttiPPTFormations_v1.xsd) — `Loading`, `CoachLoadingData`, `ScheduleFormations`
- [`rttiPPTFormations_v3.xsd`](https://raw.githubusercontent.com/Phils0/DarwinClient/master/schemas/rttiPPTFormations_v3.xsd) — `LoadingData`, `LoadingValueType` (Typical/Expected), `LoadingAttrs`
- [`rttiPPTCommonTypes_v3.xsd`](https://raw.githubusercontent.com/openraildata/stomp-client-python/master/ppv16/rttiPPTCommonTypes_v3.xsd) — `LoadingValue` (0–100), `CoachNumberType`, `CoachClassType`
- [`rtti_2021-11-01_ldb_types.xsd`](https://raw.githubusercontent.com/onewby/bus-boards/main/server/src/darwin/rtti_2021-11-01_ldb_types.xsd) — current public LDBWS: `FormationData`, `LoadingCategory`
- [`rtti_2017-10-01_ldb_types.xsd`](https://raw.githubusercontent.com/onewby/bus-boards/main/server/src/darwin/rtti_2017-10-01_ldb_types.xsd) — public LDBWS: `CoachData.loading`, `avgLoading`, `isReverseFormation`
- [`rtti_2017-10-01_ldbsv_types.xsd`](https://raw.githubusercontent.com/nathan3882/SOAPIdealTrains/master/xml-resources/web-service-references/wsdl/wsdl/lite.realtime.nationalrail.co.uk/OpenLDBSVWS/rtti_2017-10-01_ldbsv_types.xsd) — staff LDBSVWS: `ArrayOfFormationLocations`, `LocFormationData`, `CoachData.loading` with `src`

Wanted and unreachable (egress-blocked from this environment; all still worth reading from the
VPS):

- `wiki.openraildata.com` — `Darwin:Train_Loading`, `Darwin:Formations`,
  `NRE_Darwin_Web_Service_(Staff)`, `Rail_Data_Marketplace/Feeds`
- `raildata.org.uk` — LDBWS / LDBSVWS / Push Port product pages, current endpoints and terms
- `nationalrail.co.uk/developers/darwin-data-feeds/`
- `railforums.co.uk` thread 140935 — the origin of the "Thameslink publishes crowding but not
  formations" claim
- `groups.google.com/g/openraildata-talk` — the public-vs-staff field-omission report
- `caci.co.uk` GTR case study; `rspaccreditation.org` Darwin output ports specification
