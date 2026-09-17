#!/usr/bin/env python3
"""Darwin Push Port probe: measure and record per-coach loading coverage.

The Push Port is the full Darwin message stream; the request/response API is a
lossy view of it. If probes/ldbws_probe.py finds no per-coach loading, run this
for a week before concluding the data does not exist.

It does two jobs at once, and the second matters more:
  1. counts `formationLoading` messages so you can see who publishes what;
  2. appends every per-coach value to JSONL, building the historical archive
     that the forecasting model in docs/03-product-concept.md needs. Nobody
     holds a per-coach loading history for the Brighton line. After three
     months of this running, you would.

Usage:
    pip install -r probes/requirements.txt
    export DARWIN_STOMP_HOST=... DARWIN_STOMP_PORT=61613 \
           DARWIN_STOMP_USER=... DARWIN_STOMP_PASS=... DARWIN_STOMP_TOPIC=...
    python3 probes/pushport_probe.py --hours 24

    python3 probes/pushport_probe.py --selftest     # no network, no deps
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
import pathlib
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Connection details are NOT hardcoded: take them from the Darwin push feed
# product page on raildata.org.uk. Host and topic have changed before.
HOST = os.environ.get("DARWIN_STOMP_HOST", "")
PORT = int(os.environ.get("DARWIN_STOMP_PORT", "61613"))
USER = os.environ.get("DARWIN_STOMP_USER", "")
PASSWORD = os.environ.get("DARWIN_STOMP_PASS", "")
TOPIC = os.environ.get("DARWIN_STOMP_TOPIC", "")


def localname(tag: str) -> str:
    """'{ns}formationLoading' -> 'formationloading'. Survives schema versions."""
    return tag.rsplit("}", 1)[-1].lower()


def decode(body: bytes | str) -> str:
    if isinstance(body, str):
        body = body.encode("utf-8", "replace")
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return body.decode("utf-8", "replace")


def parse_message(xml_text: str) -> dict:
    """Pull message-type counts and any per-coach loading out of one Pport message."""
    result: dict = {"types": Counter(), "loadings": [], "formations": [], "schedules": []}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        result["types"]["_parse_error"] += 1
        return result

    timestamp = root.attrib.get("ts")
    for element in root.iter():
        name = localname(element.tag)
        if name in ("pport", "ur", "sr"):
            continue
        result["types"][name] += 1

        if name == "formationloading":
            coaches = []
            for child in element:
                if localname(child.tag) == "loading":
                    number = (child.attrib.get("coachNumber")
                              or child.attrib.get("coachnumber"))
                    raw = (child.text or child.attrib.get("loadingPercentage") or "").strip()
                    try:
                        coaches.append({"coach": number, "loading": int(raw)})
                    except ValueError:
                        coaches.append({"coach": number, "loading": None, "raw": raw})
            result["loadings"].append({
                "ts": timestamp,
                "rid": element.attrib.get("rid"),
                "fid": element.attrib.get("fid"),
                "tpl": element.attrib.get("tpl"),
                "wta": element.attrib.get("wta"),
                "wtd": element.attrib.get("wtd"),
                "coaches": coaches,
            })

        # Darwin identifies a service by RID, which does not encode the operator.
        # The operator only arrives on the schedule message, so build the map as
        # schedules stream past. Without this the run produces a loading count
        # nobody can attribute -- useless for a question about one operator.
        if name == "schedule":
            rid = element.attrib.get("rid")
            toc = element.attrib.get("toc")
            if rid and toc:
                result["schedules"].append((rid, toc.upper()))

        if name == "formation":
            coaches = [
                {
                    "coach": c.attrib.get("coachNumber") or c.attrib.get("coachnumber"),
                    "class": c.attrib.get("coachClass") or c.attrib.get("coachclass"),
                }
                for c in element if localname(c.tag) == "coach"
            ]
            if coaches:
                result["formations"].append({
                    "ts": timestamp,
                    "rid": element.attrib.get("rid"),
                    "fid": element.attrib.get("fid"),
                    "coaches": coaches,
                })
    return result


class Recorder:
    def __init__(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        self.loading_file = out_dir / f"loading-{stamp}.jsonl"
        self.formation_file = out_dir / f"formation-{stamp}.jsonl"
        self.types: Counter = Counter()
        self.messages = 0
        self.loading_messages = 0
        self.coach_values = 0
        self.rid_toc: dict[str, str] = {}            # built from schedule messages
        self.loading_by_toc: Counter = Counter()     # formationLoading, per operator
        self.formation_by_toc: Counter = Counter()   # consist, per operator
        self.values_by_toc: dict[str, list[int]] = defaultdict(list)
        self.started = datetime.now(timezone.utc)

    def handle(self, body: bytes | str) -> None:
        self.messages += 1
        parsed = parse_message(decode(body))
        self.types.update(parsed["types"])

        for rid, toc in parsed["schedules"]:
            self.rid_toc[rid] = toc

        for record in parsed["loadings"]:
            toc = self.rid_toc.get(record.get("rid") or "", "??")
            record["toc"] = toc
            self.loading_by_toc[toc] += 1
            self.values_by_toc[toc] += [
                c["loading"] for c in record["coaches"] if isinstance(c.get("loading"), int)
            ]
        for record in parsed["formations"]:
            record["toc"] = self.rid_toc.get(record.get("rid") or "", "??")
            self.formation_by_toc[record["toc"]] += 1

        if parsed["loadings"]:
            self.loading_messages += len(parsed["loadings"])
            with self.loading_file.open("a") as handle:
                for record in parsed["loadings"]:
                    self.coach_values += len(record["coaches"])
                    handle.write(json.dumps(record) + "\n")
        if parsed["formations"]:
            with self.formation_file.open("a") as handle:
                for record in parsed["formations"]:
                    handle.write(json.dumps(record) + "\n")

    def summary(self) -> str:
        mins = (datetime.now(timezone.utc) - self.started).total_seconds() / 60
        by_toc = ", ".join(
            f"{toc}={self.loading_by_toc[toc]}" for toc in sorted(self.loading_by_toc)
        ) or "none yet"
        return (
            f"{mins:.0f}m in: {self.messages} messages, {len(self.rid_toc)} services known, "
            f"{self.loading_messages} formationLoading\n"
            f"  per-coach loading BY OPERATOR: {by_toc}\n"
            f"  (?? = loading seen before that service's schedule arrived)"
        )

    def report(self) -> str:
        """The answer, in the form the question was asked."""
        watched = ("TL", "SN", "GX")
        lines = [
            "# Darwin Push Port coverage",
            "",
            f"- Listening since: {self.started.isoformat(timespec='seconds')}",
            f"- Messages: {self.messages}; services seen: {len(self.rid_toc)}",
            f"- formationLoading messages: {self.loading_messages}",
            "",
            "## Per-coach loading by operator",
            "",
            "| TOC | formationLoading msgs | formation msgs | coach values |",
            "|---|---|---|---|",
        ]
        for toc in sorted(set(self.loading_by_toc) | set(self.formation_by_toc)):
            lines.append(f"| {toc} | {self.loading_by_toc[toc]} | "
                         f"{self.formation_by_toc[toc]} | {len(self.values_by_toc[toc])} |")
        lines += ["", "## Verdict", ""]
        gtr = sum(self.loading_by_toc[t] for t in watched)
        if gtr:
            lines.append(f"**GTR DOES publish formationLoading on the Push Port** "
                         f"({gtr} messages across {', '.join(watched)}) even though LDBSVWS "
                         "showed none. The carriage-level product is back on.")
        elif self.loading_messages:
            others = ", ".join(f"{t}={self.loading_by_toc[t]}"
                               for t in sorted(self.loading_by_toc) if t not in watched)
            lines.append(f"Other operators publish it ({others}) but **{', '.join(watched)} "
                         "published none**. Same answer as LDBSVWS, now from the fuller feed. "
                         "The carriage-level product is not possible on this route.")
        else:
            lines.append("No formationLoading seen from anyone. Inconclusive — check the "
                         "subscription covers the right topic before reading anything into it.")
        return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> int:
    missing = [n for n, v in
               (("DARWIN_STOMP_HOST", HOST), ("DARWIN_STOMP_USER", USER),
                ("DARWIN_STOMP_PASS", PASSWORD), ("DARWIN_STOMP_TOPIC", TOPIC)) if not v]
    if missing:
        print("Missing env vars: " + ", ".join(missing), file=sys.stderr)
        print("Get them from the Darwin push feed product page on raildata.org.uk.",
              file=sys.stderr)
        return 2
    try:
        import stomp  # type: ignore
    except ImportError:
        print("pip install -r probes/requirements.txt", file=sys.stderr)
        return 2

    recorder = Recorder(Path(args.out))

    class Listener(stomp.ConnectionListener):
        def on_message(self, frame):  # noqa: D102
            try:
                recorder.handle(frame.body)
            except Exception as exc:  # a bad frame must not kill a week-long run
                print(f"  ! frame error: {exc}", file=sys.stderr)

        def on_error(self, frame):  # noqa: D102
            print(f"  ! broker error: {frame.body}", file=sys.stderr)

    connection = stomp.Connection12(
        [(HOST, PORT)], heartbeats=(15000, 15000), auto_decode=False,
    )
    connection.set_listener("recorder", Listener())
    connection.connect(USER, PASSWORD, wait=True)
    connection.subscribe(destination=TOPIC, id=1, ack="auto")
    print(f"subscribed to {TOPIC} on {HOST}:{PORT}; running for {args.hours}h")
    report_path = Path(args.out) / "pushport-coverage.md"

    deadline = time.time() + args.hours * 3600
    try:
        while time.time() < deadline:
            time.sleep(args.report_every)
            print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {recorder.summary()}")
            report_path.write_text(recorder.report())   # survive an interrupted run
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        connection.disconnect()

    report_path.write_text(recorder.report())
    print("\n" + recorder.report())
    print(f"loading records -> {recorder.loading_file}")
    print(f"report          -> {report_path}")
    return 0


SYNTHETIC = b"""<?xml version="1.0" encoding="utf-8"?>
<Pport xmlns="http://www.thalesgroup.com/rtti/PushPort/v16" ts="2026-09-16T08:12:03.1Z">
  <uR updateOrigin="CIS">
    <schedule rid="202609168012345" uid="W12345" trainId="9F12" toc="TL"
              ssd="2026-09-16"/>
    <formationLoading fid="202609160812-001" rid="202609168012345" tpl="HYWRDSH"
                      wta="08:40" wtd="08:41">
      <loading coachNumber="A">48</loading>
      <loading coachNumber="B">77</loading>
      <loading coachNumber="C">100</loading>
    </formationLoading>
    <formation fid="202609160812-001" rid="202609168012345">
      <coach coachNumber="A" coachClass="Standard"/>
      <coach coachNumber="B" coachClass="Standard"/>
      <coach coachNumber="C" coachClass="First"/>
    </formation>
  </uR>
</Pport>"""


def selftest() -> int:
    parsed = parse_message(decode(gzip.compress(SYNTHETIC)))
    assert parsed["schedules"] == [("202609168012345", "TL")], parsed["schedules"]
    assert parsed["types"]["formationloading"] == 1, parsed["types"]
    assert len(parsed["loadings"]) == 1
    record = parsed["loadings"][0]
    assert record["tpl"] == "HYWRDSH", record
    assert [c["loading"] for c in record["coaches"]] == [48, 77, 100], record
    assert [c["coach"] for c in record["coaches"]] == ["A", "B", "C"], record
    assert len(parsed["formations"]) == 1
    assert parsed["formations"][0]["coaches"][2]["class"] == "First"
    assert parse_message("not xml")["types"]["_parse_error"] == 1

    # The question is "does GTR publish this", so attribution to an operator is
    # the whole point. A run that cannot answer that is a wasted day of listening.
    import tempfile
    rec = Recorder(pathlib.Path(tempfile.mkdtemp()))
    rec.handle(gzip.compress(SYNTHETIC))
    assert rec.rid_toc == {"202609168012345": "TL"}, rec.rid_toc
    assert rec.loading_by_toc["TL"] == 1, rec.loading_by_toc
    assert rec.values_by_toc["TL"] == [48, 77, 100], rec.values_by_toc
    assert rec.formation_by_toc["TL"] == 1, rec.formation_by_toc
    report = rec.report()
    assert "GTR DOES publish formationLoading" in report, report

    # Loading arriving before its schedule must not be silently attributed.
    orphan = SYNTHETIC.replace(b'<schedule rid="202609168012345" uid="W12345" '
                               b'trainId="9F12" toc="TL"\n              ssd="2026-09-16"/>', b"")
    rec2 = Recorder(pathlib.Path(tempfile.mkdtemp()))
    rec2.handle(gzip.compress(orphan))
    assert rec2.loading_by_toc["??"] == 1, rec2.loading_by_toc
    assert "Inconclusive" not in rec2.report()

    print("selftest ok: gzip decode, namespace-agnostic parse, loading + formation")
    print("             extraction, schedule->operator mapping, unattributed loading,")
    print("             verdict wording")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--report-every", type=float, default=300.0)
    parser.add_argument("--out", default="probes/out/pushport")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    return selftest() if args.selftest else run(args)


if __name__ == "__main__":
    sys.exit(main())
