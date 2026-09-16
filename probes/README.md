# Probes

Two scripts whose only purpose is to answer the question in `docs/01-feasibility.md` §5:
**does Darwin publish per-coach loading for Brighton Main Line services on a tier we can
access?** Nothing else in this project is worth building until they have run.

## 1. Get a key (10 minutes)

1. Create an account at <https://raildata.org.uk>.
2. Open the Data Product Catalogue, search **LDBWS**, subscribe to
   *Live Departure Board Web Service (LDBWS) - Public*. The free tier approves instantly.
3. Copy the **Consumer key**. That is the credential; it goes in the `x-apikey` header.
4. On the same product page, **check the endpoint path** and set `LDBWS_DEP_URL` /
   `LDBWS_SVC_URL` if it differs from the defaults in `ldbws_probe.py`. Do not skip this —
   a wrong path returns 404 and a 404 is indistinguishable from "there is no data here".

```sh
cp probes/.env.example probes/.env   # then fill it in; .env is gitignored
set -a && . probes/.env && set +a
```

## 2. LDBWS coverage probe

```sh
python3 probes/ldbws_probe.py --selftest              # offline, proves the parsing works
python3 probes/ldbws_probe.py                         # the real run
python3 probes/ldbws_probe.py --stations BTN,HHE,GTW --limit 20 --keep-raw
```

Stdlib only. Writes a markdown coverage report plus raw JSON to `probes/out/`. It discovers
fields rather than assuming a schema, so `--keep-raw` payloads are worth reading by hand the
first time — the real response shape is the thing the documentation is least reliable about.

Run it at **08:00 on a weekday**. Off-peak coverage tells you nothing about the trains you
actually care about.

## 3. Push Port probe

```sh
pip install -r probes/requirements.txt
python3 probes/pushport_probe.py --selftest
python3 probes/pushport_probe.py --hours 24
```

Connection details come from the Darwin push feed product page on RDM. This one is worth
leaving running permanently on a small VM even if coverage turns out to be poor: it is
building the per-coach history that the forecasting model needs, and that archive only
accumulates if something is recording it.

## Reading the result

| Outcome | Meaning | Next |
|---|---|---|
| Per-coach loading on >60% of peak services | Tier A viable | Build live advice |
| Formations yes, loading no | Request/response API may be flattening it | Run the Push Port probe a week |
| Neither, but HTTP 200s | GTR is not publishing it publicly | Tier B/C; start logging journeys by hand |
| 401/403/404 | Config problem, **not** a data finding | Fix the key or the path and rerun |

Record whatever you find in `docs/01-feasibility.md` §5 with the date. This is the kind of
thing that changes quietly, and a dated note is worth more than a remembered impression.
