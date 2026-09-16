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
import xml.etree.ElementTree as ET
from collections import Counter
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
    result: dict = {"types": Counter(), "loadings": [], "formations": []}
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

    def handle(self, body: bytes | str) -> None:
        self.messages += 1
        parsed = parse_message(decode(body))
        self.types.update(parsed["types"])
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
        top = ", ".join(f"{name}={count}" for name, count in self.types.most_common(12))
        return (
            f"messages={self.messages} formationLoading={self.loading_messages} "
            f"coach_values={self.coach_values}\n  types: {top}"
        )


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

    deadline = time.time() + args.hours * 3600
    try:
        while time.time() < deadline:
            time.sleep(args.report_every)
            print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {recorder.summary()}")
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        connection.disconnect()

    print("\n" + recorder.summary())
    print(f"loading records -> {recorder.loading_file}")
    return 0


SYNTHETIC = b"""<?xml version="1.0" encoding="utf-8"?>
<Pport xmlns="http://www.thalesgroup.com/rtti/PushPort/v16" ts="2026-09-16T08:12:03.1Z">
  <uR updateOrigin="CIS">
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
    assert parsed["types"]["formationloading"] == 1, parsed["types"]
    assert len(parsed["loadings"]) == 1
    record = parsed["loadings"][0]
    assert record["tpl"] == "HYWRDSH", record
    assert [c["loading"] for c in record["coaches"]] == [48, 77, 100], record
    assert [c["coach"] for c in record["coaches"]] == ["A", "B", "C"], record
    assert len(parsed["formations"]) == 1
    assert parsed["formations"][0]["coaches"][2]["class"] == "First"
    assert parse_message("not xml")["types"]["_parse_error"] == 1
    print("selftest ok: gzip decode, namespace-agnostic parse, loading + formation extraction")
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
