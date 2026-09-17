#!/usr/bin/env python3
"""Coverage probe for Darwin per-coach loading, via the LDBSVWS staff feed.

Answers https://github.com/richbroad29/train-loader/issues/10 — the single
measurement the whole map is waiting on.

RUN THIS ON THE VPS. The rail data API is unreachable from Claude Code's
container (the egress proxy refuses the tunnel), and the RDM key lives in
`backend/.env` on the Oracle box anyway. Nothing needs to move.

    cd ~/rail-crossing && set -a && . backend/.env && set +a
    python3 ldbsv_probe.py --samples 12 --interval 600

That samples every 10 minutes for two hours. Run it across a weekday MORNING
peak (07:00-09:00) — off-peak coverage answers none of the open questions.
Then send back the report it prints.

Endpoint, header and time format are taken from rail-crossing's own
`backend/src/ldb-poller.js`, so if that works, this works.

Stdlib only. Python 3.9+.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

BASE = os.environ.get("RDM_BASE", "https://api1.raildata.org.uk")
PATH = os.environ.get(
    "RDM_LDBSV_PATH",
    "/1010-live-arrival-and-departure-boards---staff-version1_0"
    "/LDBSVWS/api/20220120/GetArrDepBoardWithDetails",
)

DEFAULT_STATIONS = "PRP,LBG"
# Thameslink is the operator of record for PRP<->LBG; SN and GX call at PRP but
# run to Victoria. Left broad on purpose so the probe can confirm or refute that.
OPERATORS_OF_INTEREST = {"TL", "SN", "GX", "GN"}

LOADING_HINTS = ("loading", "occupancy", "crowd")
FORMATION_HINTS = ("formation", "coach", "fmloc", "length", "reverse")


# --- JSON walking (discover the shape, don't assume it) ---------------------

def walk(node: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")


def leaf(path: str) -> str:
    return path.rsplit(".", 1)[-1].split("[")[0].lower()


def paths_matching(doc: Any, hints: tuple[str, ...]) -> list[str]:
    return [p for p, _ in walk(doc) if any(h in leaf(p) for h in hints)]


def numeric(value: Any) -> int | None:
    """A 0-100 out of a scalar, a percent string, or a wrapper object."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip().rstrip("%")
        return int(stripped) if stripped.isdigit() else None
    if isinstance(value, dict):
        for key, inner in value.items():
            if any(h in key.lower() for h in ("percent", "value", "loading", "amount")):
                found = numeric(inner)
                if found is not None:
                    return found
    return None


COACH_INDEX = re.compile(r"(?:coaches|coach)\[(\d+)\]$")


def coach_loadings(doc: Any) -> list[tuple[str, int]]:
    """Every (coach identifier, 0-100) pair, however the response nests them.

    LDBSVWS coach objects carry `coachClass` and `loading` but NO coach number:
    a coach is identified by its position in the `coaches` array. An earlier
    version of this function required an explicit number field, found none, and
    reported zero loading for services that were publishing it in full — a
    parser bug dressed up as a finding about the railway. Hence the fallback to
    the array index, and the guard in the report when paths exist but values
    do not.
    """
    pairs: list[tuple[str, int]] = []
    for path, node in walk(doc):
        if not isinstance(node, dict):
            continue

        load = None
        for key, value in node.items():
            if any(h in key.lower() for h in LOADING_HINTS):
                load = numeric(value)
                if load is not None:
                    break
        if load is None:
            continue

        coach = None
        for key, value in node.items():
            if key.lower() in ("coachnumber", "coachletter", "coachid", "number",
                               "identifier") and isinstance(value, (str, int)):
                coach = str(value)
                break
        if coach is None:                      # positional: coaches[0] is coach 1
            match = COACH_INDEX.search(path)
            if match:
                coach = str(int(match.group(1)) + 1)
        if coach is None:                      # whole-train serviceLoading, not a coach
            continue
        pairs.append((coach, load))
    return pairs


def find_first(doc: Any, *names: str) -> Any:
    wanted = {n.lower() for n in names}
    for path, node in walk(doc):
        if leaf(path) in wanted and not isinstance(node, (dict, list)):
            return node
    return None


def services_of(board: Any) -> list[dict]:
    for path, node in walk(board):
        if leaf(path) in ("trainservices", "service", "services"):
            if isinstance(node, list):
                return [s for s in node if isinstance(s, dict)]
            if isinstance(node, dict) and isinstance(node.get("service"), list):
                return [s for s in node["service"] if isinstance(s, dict)]
    return []


# --- HTTP -------------------------------------------------------------------

def london_stamp(when: datetime | None = None) -> str:
    """YYYYMMDDTHHMMSS in Europe/London wall clock, as ldb-poller.js builds it."""
    try:
        from zoneinfo import ZoneInfo
        now = (when or datetime.now(timezone.utc)).astimezone(ZoneInfo("Europe/London"))
    except Exception:
        now = when or datetime.now()
    return now.strftime("%Y%m%dT%H%M%S")


def fetch(station: str, api_key: str, stamp: str, timeout: float = 25.0) -> Any:
    url = f"{BASE}{PATH}/{station}/{stamp}"
    request = urllib.request.Request(
        url,
        headers={"x-apikey": api_key, "Accept": "application/json",
                 "User-Agent": "train-loader-probe/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout,
                                    context=ssl.create_default_context()) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        hint = ""
        if exc.code in (401, 403):
            hint = "  -> is RDM_API_KEY set, and does the subscription cover LDBSVWS?"
        if exc.code == 404:
            hint = "  -> check RDM_LDBSV_PATH against the product page; a 404 is NOT 'no data'"
        raise RuntimeError(f"HTTP {exc.code} for {station}: {detail}{hint}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"network error for {station}: {exc.reason}") from exc


# --- Probe ------------------------------------------------------------------

class Findings:
    def __init__(self) -> None:
        self.services = Counter()            # toc -> count
        self.with_formation = Counter()
        self.with_coach_loading = Counter()
        self.with_service_loading = Counter()     # whole-train figure, the weaker tier
        self.service_loading_values = defaultdict(list)
        self.coach_counts = defaultdict(Counter)   # toc -> {8: n, 12: n}
        self.loading_values = defaultdict(list)
        self.destinations = defaultdict(Counter)   # toc -> destination -> n
        self.formation_locations = Counter()  # services carrying per-calling-point formation
        self.reverse_flags = Counter()
        self.field_paths = {"loading": set(), "formation": set()}
        self.seen_keys: set[str] = set()
        self.errors: list[str] = []
        self.samples = 0

    def absorb(self, station: str, board: Any) -> None:
        self.field_paths["loading"].update(paths_matching(board, LOADING_HINTS))
        self.field_paths["formation"].update(paths_matching(board, FORMATION_HINTS))

        for service in services_of(board):
            toc = str(find_first(service, "operatorCode", "toc", "operator_code") or "??").upper()
            key = (str(find_first(service, "rid", "serviceID", "uid") or id(service)), station)
            if key in self.seen_keys:      # same service seen on a later sample
                continue
            self.seen_keys.add(key)

            self.services[toc] += 1
            dest = find_first(service, "locationName", "destination") or "?"
            self.destinations[toc][str(dest)] += 1

            fpaths = paths_matching(service, FORMATION_HINTS)
            if fpaths:
                self.with_formation[toc] += 1
            if any("fmloc" in leaf(p) or "formationlocation" in leaf(p) for p in fpaths):
                self.formation_locations[toc] += 1

            reverse = find_first(service, "isReverseFormation")
            if reverse is not None:
                self.reverse_flags[f"{toc}:{reverse}"] += 1

            # Only indexed entries: walk() also yields the containing list node,
            # so the array and each element share a leaf name, and counting both
            # overstates the formation by one. The real LDBSVWS shape is
            # `formation.coaches[i]` (leaf "coaches"); accept "coach" too.
            coaches = [p for p in fpaths
                       if leaf(p) in ("coach", "coaches") and p.endswith("]")]
            if coaches:
                self.coach_counts[toc][len(coaches)] += 1
            else:
                length = find_first(service, "length")
                if isinstance(length, int) and length:
                    self.coach_counts[toc][length] += 1

            # Whole-train loading is a different, much weaker thing than per-coach,
            # and the two must never be conflated in the coverage table: an operator
            # can publish "this train is busy" while publishing nothing per carriage.
            for spath, snode in walk(service):
                if leaf(spath) == "serviceloading" and isinstance(snode, dict):
                    value = numeric(snode)
                    if value is not None:
                        self.with_service_loading[toc] += 1
                        self.service_loading_values[toc].append(value)
                    break

            pairs = coach_loadings(service)
            if pairs:
                self.with_coach_loading[toc] += 1
                self.loading_values[toc] += [v for _c, v in pairs]

    def report(self) -> str:
        out = [
            "# LDBSVWS coverage probe",
            "",
            f"- Run: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            f"- Samples taken: {self.samples}",
            f"- Distinct services seen: {sum(self.services.values())}",
            "",
            "## The decisive question: per-coach loading",
            "",
            "| TOC | services | formation | **per-coach loading** | whole-train loading |",
            "|---|---|---|---|---|",
        ]
        total_loading = 0
        for toc in sorted(self.services):
            n = self.services[toc] or 1
            total_loading += self.with_coach_loading[toc]
            out.append(
                f"| {toc} | {self.services[toc]} "
                f"| {self.with_formation[toc]} ({self.with_formation[toc]*100//n}%) "
                f"| **{self.with_coach_loading[toc]} ({self.with_coach_loading[toc]*100//n}%)** "
                f"| {self.with_service_loading[toc]} ({self.with_service_loading[toc]*100//n}%) |"
            )

        out += ["", "## Loading values", ""]
        if any(self.loading_values.values()):
            for toc, values in sorted(self.loading_values.items()):
                if values:
                    out.append(f"- **{toc}**: n={len(values)}, min={min(values)}, "
                               f"max={max(values)}, mean={sum(values)/len(values):.1f}")
        else:
            out.append("- None extracted.")

        out += ["", "## Whole-train loading values (the weaker tier)", ""]
        if any(self.service_loading_values.values()):
            for toc, values in sorted(self.service_loading_values.items()):
                if values:
                    out.append(f"- **{toc}**: n={len(values)}, min={min(values)}, "
                               f"max={max(values)}, mean={sum(values)/len(values):.1f}")
        else:
            out.append("- None extracted.")

        out += ["", "## Formation lengths (the 8-vs-12 question)", ""]
        if self.coach_counts:
            for toc, counts in sorted(self.coach_counts.items()):
                breakdown = ", ".join(f"{k}-car x{v}" for k, v in sorted(counts.items()))
                out.append(f"- **{toc}**: {breakdown}")
        else:
            out.append("- No formation lengths seen.")

        out += ["", "## Destinations (is this journey Thameslink-only?)", ""]
        for toc, dests in sorted(self.destinations.items()):
            top = ", ".join(f"{d} x{n}" for d, n in dests.most_common(6))
            out.append(f"- **{toc}**: {top}")

        if self.reverse_flags:
            out += ["", "## isReverseFormation", ""]
            out += [f"- {k}: {v}" for k, v in sorted(self.reverse_flags.items())]

        out += ["", "## Field paths discovered", ""]
        for kind in ("formation", "loading"):
            found = sorted(self.field_paths[kind])
            out.append(f"**{kind}** ({len(found)} distinct)")
            out += [f"  - `{p}`" for p in found[:30]] or ["  - none"]
            out.append("")

        out += ["## Verdict", ""]
        if total_loading:
            out.append("Per-coach loading IS published for these services. The live half of "
                       "the product is buildable on this feed.")
        elif any(self.with_formation.values()):
            out.append("Formations published, per-coach loading ABSENT. GTR does not supply "
                       "it on this tier. The app cannot say which carriage from the feed "
                       "alone; the recorder cannot record what is not published.")
        else:
            out.append("Neither formations nor loading found. Check the errors below before "
                       "concluding anything — a bad path or key looks identical to no data.")

        if self.errors:
            out += ["", "## Errors", ""] + [f"- {e}" for e in self.errors[:20]]
        return "\n".join(out) + "\n"


def run(args: argparse.Namespace) -> int:
    api_key = os.environ.get("RDM_API_KEY", "").strip()
    if not api_key:
        print("RDM_API_KEY is not set.\n"
              "On the VPS:  cd ~/rail-crossing && set -a && . backend/.env && set +a",
              file=sys.stderr)
        return 2

    stations = [s.strip().upper() for s in args.stations.split(",") if s.strip()]
    findings = Findings()
    out_dir = Path(args.out)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)

    for sample in range(args.samples):
        stamp = london_stamp()
        for station in stations:
            try:
                board = fetch(station, api_key, stamp)
            except RuntimeError as exc:
                findings.errors.append(str(exc))
                print(f"  ! {exc}", file=sys.stderr)
                continue
            if args.keep_raw or sample == 0:
                path = out_dir / "raw" / f"{station}-{stamp}.json"
                path.write_text(json.dumps(board, indent=2))
            findings.absorb(station, board)
        findings.samples += 1

        # Per-operator, because the aggregate is misleading: Southeastern at London
        # Bridge can supply every per-coach figure in the sample while the operator
        # actually being investigated supplies none.
        breakdown = ", ".join(
            f"{toc} {findings.with_coach_loading[toc]}/{findings.services[toc]}"
            for toc in sorted(findings.services)
        ) or "nothing yet"
        print(f"[{stamp}] sample {sample+1}/{args.samples} — per-coach loading: {breakdown}")

        # Write the report after every sample, not only at the end. A two-hour run
        # killed by a closed laptop lid at sample 9 otherwise produces nothing at all.
        interim = out_dir / f"ldbsv-coverage-{london_stamp()}.md"
        interim.write_text(findings.report())
        for stale in sorted(out_dir.glob("ldbsv-coverage-*.md"))[:-1]:
            stale.unlink(missing_ok=True)

        if sample + 1 < args.samples:
            time.sleep(args.interval)

    report = findings.report()
    path = out_dir / f"ldbsv-coverage-{london_stamp()}.md"
    path.write_text(report)
    print("\n" + report)
    print(f"Written to {path}")
    print("Raw payloads in", out_dir / "raw", "- worth one read by eye.")

    # Exit non-zero when nothing at all came back. Unattended, a run where every
    # request failed looks identical to a run that found no loading data, and a
    # cron job reporting success while learning nothing is worse than no cron job.
    if not sum(findings.services.values()):
        print("\nNO SERVICES RETURNED - treating as failure, not as a finding.\n"
              "Every request failed, or the endpoint path is wrong. Check the errors above.",
              file=sys.stderr)
        return 1
    return 0


# --- Offline self-test ------------------------------------------------------

SYNTHETIC = {
    "GetArrDepBoardWithDetailsResult": {
        "trainServices": {"service": [
            {
                "rid": "202609160712345", "operatorCode": "TL", "std": "07:42",
                "destination": {"location": [{"locationName": "Bedford"}]},
                "isReverseFormation": False,
                # Shape confirmed against a real LDBSVWS response on 2026-09-16:
                # positional coaches, coachClass + loading, NO coachNumber.
                "formation": {
                    "coaches": [
                        {"coachClass": "Standard", "loading": 91},
                        {"coachClass": "Standard", "loading": 74},
                        {"coachClass": "Standard", "loading": "38%"},
                    ],
                    "serviceLoading": {"loadingPercentage": 68},
                },
            },
            {"rid": "202609160798765", "operatorCode": "SN", "std": "07:49",
             "destination": {"location": [{"locationName": "London Victoria"}]},
             "length": 8},
        ]}
    }
}


def selftest() -> int:
    f = Findings()
    f.absorb("PRP", SYNTHETIC)
    f.samples = 1
    assert f.services["TL"] == 1 and f.services["SN"] == 1, f.services
    assert f.with_coach_loading["TL"] == 1, f.with_coach_loading
    assert f.with_coach_loading["SN"] == 0
    assert f.loading_values["TL"] == [91, 74, 38], f.loading_values
    assert 68 not in f.loading_values["TL"], "whole-train serviceLoading leaked in as a coach"
    assert f.coach_counts["TL"][3] == 1, f.coach_counts     # 3 coaches in the fixture
    assert f.coach_counts["SN"][8] == 1, f.coach_counts     # falls back to `length`
    assert f.reverse_flags["TL:False"] == 1, f.reverse_flags
    f.absorb("PRP", SYNTHETIC)                              # same services, second sample
    assert f.services["TL"] == 1, "deduplication by rid failed"
    report = f.report()
    assert "Per-coach loading IS published" in report
    assert "Bedford" in report and "London Victoria" in report
    stamp = london_stamp()
    assert len(stamp) == 15 and stamp[8] == "T", stamp
    print("selftest ok: parsing, dedup, coach counts, length fallback, reverse flag,")
    print("             destination breakdown, verdict, London timestamp format")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stations", default=DEFAULT_STATIONS)
    parser.add_argument("--samples", type=int, default=1,
                        help="how many times to poll (12 x 600s covers a 2h peak)")
    parser.add_argument("--interval", type=float, default=600.0, help="seconds between samples")
    parser.add_argument("--out", default="probes/out/ldbsv")
    parser.add_argument("--keep-raw", action="store_true",
                        help="save every payload, not just the first")
    parser.add_argument("--selftest", action="store_true", help="offline checks, then exit")
    args = parser.parse_args()
    return selftest() if args.selftest else run(args)


if __name__ == "__main__":
    sys.exit(main())
