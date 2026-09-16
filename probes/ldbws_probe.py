#!/usr/bin/env python3
"""Coverage probe for Darwin per-coach loading via the LDBWS REST API.

Answers the one question that decides whether this project is viable (see
docs/01-feasibility.md sec.5): do Brighton Main Line services on Southern,
Thameslink and Gatwick Express carry populated `formation` and per-coach
`loading` on a tier we can access?

It deliberately *discovers* fields rather than assuming a schema. The public
LDBWS is documented loosely and is known to omit fields the docs promise, so
the probe walks every response for anything loading- or formation-shaped and
reports what it actually found.

Usage:
    export RDM_API_KEY=...            # 'Consumer key' from raildata.org.uk
    python3 probes/ldbws_probe.py --stations BTN,HHE,GTW,ECR
    python3 probes/ldbws_probe.py --selftest      # no network, no key

Stdlib only, so it runs anywhere.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# --- Configuration ----------------------------------------------------------
#
# VERIFY THESE against the product page on raildata.org.uk before trusting a
# negative result: the product prefix ("1010-live-departure-board-dep") and the
# version segment differ per product and change over time. A wrong path gives a
# 404, which looks exactly like "no data" if you are not paying attention.

DEFAULT_DEP_URL = os.environ.get(
    "LDBWS_DEP_URL",
    "https://api1.raildata.org.uk/1010-live-departure-board-dep"
    "/LDBWS/api/20220120/GetDepBoardWithDetails/{crs}",
)
DEFAULT_SVC_URL = os.environ.get(
    "LDBWS_SVC_URL",
    "https://api1.raildata.org.uk/1010-live-departure-board-dep"
    "/LDBWS/api/20220120/GetServiceDetails/{sid}",
)

# Brighton Main Line, ordered coast -> London.
DEFAULT_STATIONS = "BTN,PRP,HHE,TBD,GTW,ECR,CLJ,VIC,LBG,ZFD"
# Southern, Thameslink, Gatwick Express.
DEFAULT_OPERATORS = "SN,TL,GX"

# Keys worth noticing, lowercased substring match.
LOADING_KEYS = ("loading", "occupancy", "crowd", "capacity", "seat")
FORMATION_KEYS = ("formation", "coach", "carriage", "length", "toilet")


# --- JSON walking -----------------------------------------------------------

def walk(node: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Yield (dotted_path, value) for every node in a JSON document."""
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")


def interesting_paths(doc: Any) -> dict[str, list[str]]:
    """Group paths whose final key smells like formation or loading data."""
    found: dict[str, list[str]] = {"loading": [], "formation": []}
    for path, _value in walk(doc):
        leaf = path.rsplit(".", 1)[-1].split("[")[0].lower()
        if any(k in leaf for k in LOADING_KEYS):
            found["loading"].append(path)
        elif any(k in leaf for k in FORMATION_KEYS):
            found["formation"].append(path)
    return found


def coach_loadings(doc: Any) -> list[tuple[str, int]]:
    """Extract (coach identifier, percentage) pairs however they are nested.

    Handles the shapes seen in the Darwin schema family without committing to
    one: a coach object carrying its own loading, or a parallel loading list
    keyed by coach number.
    """
    pairs: list[tuple[str, int]] = []
    for _path, node in walk(doc):
        if not isinstance(node, dict):
            continue
        coach = None
        load = None
        for key, value in node.items():
            low = key.lower()
            if coach is None and low in (
                "coachnumber", "coachid", "coach", "number", "identifier", "coachletter",
            ) and isinstance(value, (str, int)):
                coach = str(value)
            if load is None and any(k in low for k in ("loading", "occupancy")):
                if isinstance(value, (int, float)):
                    load = int(value)
                elif isinstance(value, str) and value.strip().rstrip("%").isdigit():
                    load = int(value.strip().rstrip("%"))
        if coach is not None and load is not None:
            pairs.append((coach, load))
    return pairs


# --- HTTP -------------------------------------------------------------------

class ApiError(RuntimeError):
    pass


def fetch(url: str, api_key: str, timeout: float = 20.0) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "x-apikey": api_key,
            "Accept": "application/json",
            "User-Agent": "train-loader-feasibility-probe/0.1",
        },
    )
    context = ssl.create_default_context()
    ca_bundle = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    if ca_bundle and Path(ca_bundle).exists():
        context.load_verify_locations(ca_bundle)
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        if exc.code in (401, 403):
            raise ApiError(
                f"HTTP {exc.code}: key rejected. Check RDM_API_KEY is the Consumer key "
                f"for a product you are subscribed to. {detail}"
            ) from exc
        if exc.code == 404:
            raise ApiError(
                f"HTTP 404 for {url}\nThe product prefix or version segment is probably "
                f"wrong -- confirm the path on the RDM product page and set LDBWS_DEP_URL "
                f"/ LDBWS_SVC_URL. A 404 is NOT evidence that the data is missing."
            ) from exc
        raise ApiError(f"HTTP {exc.code} for {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"network error for {url}: {exc.reason}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise ApiError(f"non-JSON response from {url}: {body[:300]}") from None


# --- Probe ------------------------------------------------------------------

def services_from_board(board: Any) -> list[dict]:
    """Pull the service list out of a departure board, whatever it is nested in."""
    for path, node in walk(board):
        if path.rsplit(".", 1)[-1].lower() in ("trainservices", "service", "services"):
            if isinstance(node, list):
                return [s for s in node if isinstance(s, dict)]
            if isinstance(node, dict) and isinstance(node.get("service"), list):
                return [s for s in node["service"] if isinstance(s, dict)]
    return []


def field(service: dict, *names: str) -> Any:
    lowered = {k.lower(): v for k, v in service.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def run(args: argparse.Namespace) -> int:
    api_key = os.environ.get("RDM_API_KEY", "").strip()
    if not api_key:
        print("RDM_API_KEY is not set. See probes/README.md.", file=sys.stderr)
        return 2

    stations = [s.strip().upper() for s in args.stations.split(",") if s.strip()]
    operators = {o.strip().upper() for o in args.operators.split(",") if o.strip()}
    out_dir = Path(args.out)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)

    stats: dict[str, Counter] = defaultdict(Counter)
    loading_values: dict[str, list[int]] = defaultdict(list)
    discovered: dict[str, set[str]] = {"loading": set(), "formation": set()}
    errors: list[str] = []

    for crs in stations:
        try:
            board = fetch(DEFAULT_DEP_URL.format(crs=crs), api_key)
        except ApiError as exc:
            errors.append(f"{crs}: {exc}")
            print(f"  ! {crs}: {exc}", file=sys.stderr)
            continue

        (out_dir / "raw" / f"board-{crs}.json").write_text(json.dumps(board, indent=2))
        found = interesting_paths(board)
        discovered["loading"].update(found["loading"])
        discovered["formation"].update(found["formation"])

        services = services_from_board(board)
        relevant = [
            s for s in services
            if str(field(s, "operatorCode", "operator_code", "toc") or "").upper() in operators
        ]
        print(f"{crs}: {len(services)} services, {len(relevant)} on target operators")

        for service in relevant[: args.limit]:
            toc = str(field(service, "operatorCode", "operator_code", "toc") or "??").upper()
            stats[toc]["services"] += 1

            payloads = [("board", service)]
            sid = field(service, "serviceID", "serviceIdUrlSafe", "serviceId", "service_id")
            if sid and not args.no_service_details:
                try:
                    detail = fetch(DEFAULT_SVC_URL.format(sid=sid), api_key)
                    payloads.append(("detail", detail))
                    stats[toc]["details_fetched"] += 1
                except ApiError as exc:
                    errors.append(f"{crs}/{sid}: {exc}")
                time.sleep(args.sleep)

            merged_found = {"loading": [], "formation": []}
            pairs: list[tuple[str, int]] = []
            for label, payload in payloads:
                paths = interesting_paths(payload)
                discovered["loading"].update(paths["loading"])
                discovered["formation"].update(paths["formation"])
                merged_found["loading"] += paths["loading"]
                merged_found["formation"] += paths["formation"]
                pairs += coach_loadings(payload)
                if label == "detail" and args.keep_raw:
                    name = f"detail-{crs}-{toc}-{stats[toc]['services']}.json"
                    (out_dir / "raw" / name).write_text(json.dumps(payload, indent=2))

            if merged_found["formation"]:
                stats[toc]["has_formation_fields"] += 1
            if merged_found["loading"]:
                stats[toc]["has_loading_fields"] += 1
            if pairs:
                stats[toc]["has_per_coach_loading"] += 1
                loading_values[toc] += [p for _c, p in pairs]

    report = build_report(stats, loading_values, discovered, errors, stations, operators)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"coverage-{stamp}.md"
    path.write_text(report)
    print("\n" + report)
    print(f"\nWritten to {path}")
    return 0


def build_report(
    stats: dict[str, Counter],
    loading_values: dict[str, list[int]],
    discovered: dict[str, set[str]],
    errors: list[str],
    stations: list[str],
    operators: set[str],
) -> str:
    lines = [
        "# LDBWS per-coach loading coverage",
        "",
        f"- Run: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- Stations: {', '.join(stations)}",
        f"- Operators: {', '.join(sorted(operators))}",
        "",
        "## Coverage by operator",
        "",
        "| TOC | services | formation fields | loading fields | **per-coach loading** |",
        "|---|---|---|---|---|",
    ]
    total_coach = 0
    for toc in sorted(stats):
        counter = stats[toc]
        n = counter["services"] or 1
        total_coach += counter["has_per_coach_loading"]
        lines.append(
            f"| {toc} | {counter['services']} "
            f"| {counter['has_formation_fields']} ({counter['has_formation_fields'] * 100 // n}%) "
            f"| {counter['has_loading_fields']} ({counter['has_loading_fields'] * 100 // n}%) "
            f"| {counter['has_per_coach_loading']} "
            f"({counter['has_per_coach_loading'] * 100 // n}%) |"
        )

    lines += ["", "## Loading values seen", ""]
    if any(loading_values.values()):
        for toc, values in sorted(loading_values.items()):
            if values:
                lines.append(
                    f"- **{toc}**: n={len(values)}, min={min(values)}, max={max(values)}, "
                    f"mean={sum(values) / len(values):.1f}"
                )
    else:
        lines.append("- None. No per-coach loading values were extracted.")

    lines += ["", "## Field paths discovered", ""]
    for kind in ("formation", "loading"):
        paths = sorted(discovered[kind])[:40]
        lines.append(f"**{kind}** ({len(discovered[kind])} distinct paths)")
        lines += [f"  - `{p}`" for p in paths] or ["  - none"]
        lines.append("")

    lines += ["## Verdict", ""]
    if total_coach:
        lines.append(
            "Per-coach loading IS present on the public LDBWS tier. Tier A of the product "
            "is buildable. Next: measure stability over a week and per fleet."
        )
    elif discovered["formation"]:
        lines.append(
            "Formations present, per-coach loading absent from LDBWS. Do NOT conclude the "
            "data does not exist -- run probes/pushport_probe.py for a week, since the "
            "Push Port carries messages the request/response API flattens away."
        )
    else:
        lines.append(
            "Neither formations nor loading found. Before concluding anything, verify the "
            "endpoint paths (a 404 looks identical to empty data) and check the errors below."
        )

    if errors:
        lines += ["", "## Errors", ""] + [f"- {e}" for e in errors[:25]]
    return "\n".join(lines) + "\n"


# --- Self test --------------------------------------------------------------

SYNTHETIC = {
    "trainServices": [
        {
            "serviceID": "abc123",
            "operatorCode": "TL",
            "std": "08:12",
            "destination": [{"locationName": "Bedford"}],
            "length": 12,
            "formation": {
                "coaches": [
                    {"coachNumber": "A", "coachClass": "Standard",
                     "toilet": {"status": "InService"}, "loading": 91},
                    {"coachNumber": "B", "coachClass": "Standard", "loading": 74},
                    {"coachNumber": "C", "coachClass": "Standard", "loading": "38%"},
                ]
            },
        },
        {"serviceID": "def456", "operatorCode": "SN", "std": "08:19", "length": 8},
    ]
}


def selftest() -> int:
    services = services_from_board(SYNTHETIC)
    assert len(services) == 2, services
    pairs = coach_loadings(SYNTHETIC)
    assert pairs == [("A", 91), ("B", 74), ("C", 38)], pairs
    paths = interesting_paths(SYNTHETIC)
    assert any("loading" in p for p in paths["loading"]), paths
    assert any("formation" in p for p in paths["formation"]), paths
    assert field(services[0], "operatorCode") == "TL"
    report = build_report(
        {"TL": Counter({"services": 1, "has_formation_fields": 1,
                        "has_loading_fields": 1, "has_per_coach_loading": 1})},
        {"TL": [91, 74, 38]},
        {"loading": set(paths["loading"]), "formation": set(paths["formation"])},
        [], ["BTN"], {"TL"},
    )
    assert "Per-coach loading IS present" in report, report
    print("selftest ok: board parsing, coach/loading extraction, report generation")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stations", default=DEFAULT_STATIONS)
    parser.add_argument("--operators", default=DEFAULT_OPERATORS)
    parser.add_argument("--limit", type=int, default=10,
                        help="max services per station to fetch details for")
    parser.add_argument("--sleep", type=float, default=0.3,
                        help="seconds between service-detail calls")
    parser.add_argument("--out", default="probes/out")
    parser.add_argument("--no-service-details", action="store_true",
                        help="board only; cheap, but loading usually lives in the detail")
    parser.add_argument("--keep-raw", action="store_true",
                        help="save every service-detail payload for schema inspection")
    parser.add_argument("--selftest", action="store_true",
                        help="run offline checks of the parsing logic and exit")
    args = parser.parse_args()
    return selftest() if args.selftest else run(args)


if __name__ == "__main__":
    sys.exit(main())
