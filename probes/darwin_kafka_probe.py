#!/usr/bin/env python3
"""Does GTR publish per-coach loading on the Darwin push feed?

The last open question on https://github.com/richbroad29/train-loader/issues/1.
LDBSVWS says no across 27 Thameslink, Southern and Gatwick Express services at
peak and off-peak. The push feed is the fuller stream, so this is the check
that settles it.

**The RDM push feed is Kafka, not STOMP.** The old ActiveMQ/STOMP Push Port is
closed to new subscribers; the Rail Data Marketplace product "Darwin Real Time
Train Information (Push)" is Kafka only, SASL_SSL, and carries JSON rather than
gzipped XML. Connection values come from the subscription page:

    RDM field              env var
    ---------------------- ---------------------------
    Kafka bootstrap server DARWIN_BOOTSTRAP
    Consumer username      DARWIN_CONSUMER_KEY
    Consumer password      DARWIN_CONSUMER_SECRET
    Consumer group         DARWIN_GROUP_ID
    Topic                  DARWIN_TOPIC
    (certificate bundle)   DARWIN_SSL_CA   — optional, falls back to certifi

    pip3 install confluent_kafka
    python3 probes/darwin_kafka_probe.py --minutes 30
    python3 probes/darwin_kafka_probe.py --selftest    # offline, no deps

Like the LDBSVWS probe this DISCOVERS fields rather than assuming them: the
JSON shape of the push feed is not something to take on trust, and the last
probe that assumed a shape reported a parser bug as a finding about the railway.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

WATCHED = ("TL", "SN", "GX")          # Govia Thameslink Railway's operator codes


def walk(node: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    yield path, node
    if isinstance(node, dict):
        for key, value in node.items():
            yield from walk(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")


def leaf(path: str) -> str:
    """Final path element, lowercased, with XML-to-JSON attribute sigils stripped."""
    return path.rsplit(".", 1)[-1].split("[")[0].lower().lstrip("@_")


def attr(node: dict, *names: str) -> Any:
    """Read an attribute whatever the converter did to its name (@rid, _rid, rid)."""
    wanted = {n.lower() for n in names}
    for key, value in node.items():
        if key.lower().lstrip("@_") in wanted and not isinstance(value, (dict, list)):
            return value
    return None


def numeric(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip().rstrip("%")
        return int(stripped) if stripped.isdigit() else None
    if isinstance(value, dict):                 # {"#text": "48"} and similar
        for key, inner in value.items():
            if key.lower().lstrip("@_#") in ("text", "value", "loading", "percentage"):
                found = numeric(inner)
                if found is not None:
                    return found
    return None


def xml_to_dict(element) -> Any:
    """ElementTree -> the same nested shape an XML-to-JSON converter produces.

    Attributes become "@name", text becomes "#text", repeated children become
    lists. That way one set of walk/attr/numeric helpers reads both payload
    formats and nothing downstream needs to know which arrived.
    """
    node: dict[str, Any] = {f"@{k}": v for k, v in element.attrib.items()}
    text = (element.text or "").strip()
    if text:
        node["#text"] = text
    for child in element:
        tag = child.tag.rsplit("}", 1)[-1]
        value = xml_to_dict(child)
        if tag in node:
            if not isinstance(node[tag], list):
                node[tag] = [node[tag]]
            node[tag].append(value)
        else:
            node[tag] = value
    return node or text


def unwrap(raw: bytes | str) -> Any:
    """Kafka value -> Darwin payload, whatever the topic is serving.

    The message is double-encoded: the outer JSON carries the real payload as a
    string under `bytes`. Both official clients then json.loads that string --
    but the RDM topics come in JSON and XML flavours (the XML one is named
    ...-XML), and the payload may also arrive gzipped. Sniff rather than assume:
    a probe that mistakes a format it cannot read for an absence of data is
    exactly the failure this whole exercise has already been burnt by once.
    """
    data = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    try:
        outer = json.loads(data.decode("utf-8", "replace"))
        if isinstance(outer, dict) and "bytes" in outer:
            inner = outer["bytes"]
            data = inner.encode("utf-8") if isinstance(inner, str) else inner
        else:
            return outer                       # already the payload
    except ValueError:
        pass                                   # not a JSON envelope; treat as raw

    if data[:2] == b"\x1f\x8b":
        import gzip
        data = gzip.decompress(data)

    stripped = data.lstrip()
    if stripped[:1] == b"<":
        import xml.etree.ElementTree as ET
        root = ET.fromstring(stripped.decode("utf-8", "replace"))
        return {root.tag.rsplit("}", 1)[-1]: xml_to_dict(root)}

    text = data.decode("utf-8", "replace")
    if stripped[:1] in (b"{", b"["):
        return json.loads(text)

    # base64 is the remaining plausible wrapper; try it once before giving up.
    try:
        import base64
        decoded = base64.b64decode(text, validate=True)
        if decoded[:1] in (b"<", b"{") or decoded[:2] == b"\x1f\x8b":
            return unwrap(decoded)
    except Exception:
        pass
    raise ValueError(f"unrecognised payload, starts: {text[:60]!r}")


class Findings:
    def __init__(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        self.out_dir = out_dir
        self.jsonl = out_dir / f"loading-{datetime.now(timezone.utc):%Y%m%d}.jsonl"
        self.started = datetime.now(timezone.utc)
        self.messages = 0
        self.rid_toc: dict[str, str] = {}
        self.loading_by_toc: Counter = Counter()
        self.values_by_toc: dict[str, list[int]] = defaultdict(list)
        self.element_types: Counter = Counter()
        self.loading_paths: set[str] = set()
        self.decode_errors = 0
        self.first_payload: str | None = None

    def handle(self, raw: bytes | str) -> None:
        self.messages += 1
        try:
            payload = unwrap(raw)
        except (ValueError, TypeError) as exc:
            self.decode_errors += 1
            if self.first_payload is None:
                self.first_payload = str(exc)[:200]
            return

        # Pass 1: schedules carry the operator. Darwin keys a service by RID,
        # which does not encode the TOC, so without this every loading message
        # is unattributable and the run cannot answer the question asked.
        for path, node in walk(payload):
            if leaf(path) == "schedule" and isinstance(node, dict):
                rid, toc = attr(node, "rid"), attr(node, "toc")
                if rid and toc:
                    self.rid_toc[str(rid)] = str(toc).upper()
            if isinstance(node, (dict, list)) and path:
                self.element_types[leaf(path)] += 1

        # Pass 2: loading.
        for path, node in walk(payload):
            if leaf(path) != "formationloading" or not isinstance(node, dict):
                continue
            self.loading_paths.add(path)
            rid = str(attr(node, "rid") or "")
            toc = self.rid_toc.get(rid, "??")
            coaches = []
            for cpath, cnode in walk(node):
                if leaf(cpath) != "loading" or cpath == path:
                    continue
                value = numeric(cnode if not isinstance(cnode, dict)
                                else {k: v for k, v in cnode.items()})
                if value is None and isinstance(cnode, dict):
                    value = numeric(attr(cnode, "loadingpercentage", "percentage", "value"))
                if value is not None:
                    number = (attr(cnode, "coachnumber", "coachletter", "number")
                              if isinstance(cnode, dict) else None)
                    coaches.append({"coach": str(number) if number else str(len(coaches) + 1),
                                    "loading": value})
            if not coaches:
                continue
            self.loading_by_toc[toc] += 1
            self.values_by_toc[toc] += [c["loading"] for c in coaches]
            with self.jsonl.open("a") as handle:
                handle.write(json.dumps({
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "rid": rid, "toc": toc,
                    "tpl": attr(node, "tpl"), "coaches": coaches,
                }) + "\n")

    def progress(self) -> str:
        mins = (datetime.now(timezone.utc) - self.started).total_seconds() / 60
        by_toc = ", ".join(f"{t}={self.loading_by_toc[t]}"
                           for t in sorted(self.loading_by_toc)) or "none yet"
        return (f"{mins:.0f}m — {self.messages} messages, {len(self.rid_toc)} services known\n"
                f"  per-coach loading BY OPERATOR: {by_toc}")

    def report(self) -> str:
        gtr = sum(self.loading_by_toc[t] for t in WATCHED)
        total = sum(self.loading_by_toc.values())
        lines = [
            "# Darwin push feed (Kafka) — per-coach loading coverage",
            "",
            f"- Listening since: {self.started.isoformat(timespec='seconds')}",
            f"- Messages: {self.messages} ({self.decode_errors} undecodable)",
            f"- Services whose operator is known: {len(self.rid_toc)}",
            "",
            "## formationLoading by operator",
            "",
            "| TOC | messages | coach values | min | max | mean |",
            "|---|---|---|---|---|---|",
        ]
        for toc in sorted(self.loading_by_toc):
            values = self.values_by_toc[toc]
            stats = (f"| {min(values)} | {max(values)} | {sum(values)/len(values):.1f} |"
                     if values else "| - | - | - |")
            lines.append(f"| {toc} | {self.loading_by_toc[toc]} | {len(values)} {stats}")
        if not self.loading_by_toc:
            lines.append("| _none_ | 0 | 0 | - | - | - |")

        lines += ["", "## Verdict", ""]
        if gtr:
            lines.append(f"**GTR PUBLISHES per-coach loading on the push feed** — {gtr} "
                         f"messages across {', '.join(WATCHED)}, despite LDBSVWS showing "
                         "none. The carriage-level product is back on, via this feed.")
        elif total:
            others = ", ".join(f"{t}={self.loading_by_toc[t]}"
                               for t in sorted(self.loading_by_toc) if t not in WATCHED)
            lines.append(f"Per-coach loading flows on this feed ({others}) but **none from "
                         f"{', '.join(WATCHED)}**. The fuller feed agrees with LDBSVWS: GTR "
                         "does not produce this data. The carriage-level product is not "
                         "possible on this route, and no further checking will change that.")
        else:
            lines.append("**Inconclusive.** No formationLoading from any operator. Either the "
                         "run was too short, or the subscription/topic is wrong. Do not read "
                         "this as an answer about GTR.")
            if self.decode_errors:
                lines += ["", f"{self.decode_errors} messages could not be decoded. "
                              f"First failure: `{self.first_payload}`"]
            if self.element_types:
                seen = ", ".join(f"{k}={v}" for k, v in self.element_types.most_common(12))
                lines += ["", f"Message types seen: {seen}"]
        if self.loading_paths:
            lines += ["", "## Where loading was found", ""]
            lines += [f"- `{p}`" for p in sorted(self.loading_paths)[:10]]
        return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> int:
    config_env = {
        "bootstrap.servers": "DARWIN_BOOTSTRAP",
        "sasl.username": "DARWIN_CONSUMER_KEY",
        "sasl.password": "DARWIN_CONSUMER_SECRET",
        "group.id": "DARWIN_GROUP_ID",
    }
    config = {key: os.environ.get(var, "").strip() for key, var in config_env.items()}
    topic = os.environ.get("DARWIN_TOPIC", "").strip()
    missing = [var for key, var in config_env.items() if not config[key]]
    if not topic:
        missing.append("DARWIN_TOPIC")
    if missing:
        print("Missing: " + ", ".join(missing), file=sys.stderr)
        print("These are on the RDM subscription page for 'Darwin Real Time Train "
              "Information (Push)' — as Kafka bootstrap server, Consumer username, "
              "Consumer password, Consumer group and Topic.", file=sys.stderr)
        return 2
    try:
        from confluent_kafka import Consumer
    except ImportError:
        print("pip3 install confluent_kafka", file=sys.stderr)
        return 2

    config.update({"security.protocol": "SASL_SSL", "sasl.mechanism": "PLAIN",
                   "auto.offset.reset": "earliest"})

    # RDM tells you to point the client at a certificate bundle. librdkafka does
    # not read the macOS keychain, so on a Mac this is not optional: without it
    # the connection fails with a broker certificate verification error that
    # looks like a credentials problem and is not.
    ca = os.environ.get("DARWIN_SSL_CA", "").strip()
    if not ca:
        try:
            import certifi
            ca = certifi.where()
        except ImportError:
            pass
    if ca:
        config["ssl.ca.location"] = ca
        print(f"CA bundle: {ca}")
    else:
        print("No CA bundle found. If the broker refuses the TLS handshake, run\n"
              "  pip3 install certifi\n"
              "or set DARWIN_SSL_CA to a PEM bundle.", file=sys.stderr)
    findings = Findings(Path(args.out))
    report_path = findings.out_dir / "darwin-kafka-coverage.md"

    consumer = Consumer(config)
    consumer.subscribe([topic])
    print(f"subscribed to {topic}; listening for {args.minutes} minutes")

    deadline = time.time() + args.minutes * 60
    next_report = time.time() + args.report_every
    try:
        while time.time() < deadline:
            message = consumer.poll(timeout=5.0)
            if message is None:
                continue
            if message.error():
                print(f"  ! {message.error()}", file=sys.stderr)
                continue
            findings.handle(message.value())
            if time.time() >= next_report:
                print(f"[{datetime.now(timezone.utc):%H:%M:%S}] {findings.progress()}")
                report_path.write_text(findings.report())   # survive an interrupted run
                next_report = time.time() + args.report_every
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        consumer.close()

    report_path.write_text(findings.report())
    print("\n" + findings.report())
    print(f"report -> {report_path}")
    return 0 if findings.messages else 1


SYNTHETIC = json.dumps({"bytes": json.dumps({
    "Pport": {"ts": "2026-09-17T08:12:03Z", "uR": {
        "schedule": [{"@rid": "202609178012345", "@toc": "TL", "@trainId": "9F12"},
                     {"@rid": "202609178099999", "@toc": "SE", "@trainId": "2K45"}],
        "formationLoading": [
            {"@rid": "202609178012345", "@tpl": "PRESTPK",
             "loading": [{"@coachNumber": "A", "#text": "48"},
                         {"@coachNumber": "B", "#text": "77"}]},
            {"@rid": "202609178099999", "@tpl": "LBG",
             "loading": [{"@coachNumber": "A", "#text": "90"}]},
        ],
    }}})})


def selftest() -> int:
    import tempfile
    findings = Findings(Path(tempfile.mkdtemp()))
    findings.handle(SYNTHETIC.encode())

    assert findings.rid_toc == {"202609178012345": "TL", "202609178099999": "SE"}, findings.rid_toc
    assert findings.loading_by_toc["TL"] == 1, findings.loading_by_toc
    assert findings.loading_by_toc["SE"] == 1, findings.loading_by_toc
    assert findings.values_by_toc["TL"] == [48, 77], findings.values_by_toc
    assert "GTR PUBLISHES per-coach loading" in findings.report()

    # GTR silent while others publish must read as a decision, not as "no data".
    other = Findings(Path(tempfile.mkdtemp()))
    other.handle(json.dumps({"bytes": json.dumps({"Pport": {"uR": {
        "schedule": {"@rid": "r1", "@toc": "SE"},
        "formationLoading": {"@rid": "r1", "loading": [{"@coachNumber": "A", "#text": "90"}]},
    }}})}).encode())
    report = other.report()
    assert "none from TL, SN, GX" in report, report
    assert "Inconclusive" not in report

    # Nothing at all must NOT be reported as an answer about GTR.
    empty = Findings(Path(tempfile.mkdtemp()))
    empty.handle(json.dumps({"bytes": json.dumps({"Pport": {"uR": {"TS": {"@rid": "x"}}}})}).encode())
    assert "Inconclusive" in empty.report()

    empty.handle(b"\x00\x01 not a payload")
    assert empty.decode_errors == 1
    assert "unrecognised payload" in (empty.first_payload or "")

    # The topic this project subscribes to is named ...-XML, so the XML payload
    # path is the one that matters most; gzip is plausible on top of it.
    xml = ('<?xml version="1.0"?><Pport xmlns="http://www.thalesgroup.com/rtti/PushPort/v16">'
           '<uR><schedule rid="r-tl" toc="TL"/>'
           '<formationLoading rid="r-tl" tpl="PRESTPK">'
           '<loading coachNumber="A">48</loading><loading coachNumber="B">77</loading>'
           '</formationLoading></uR></Pport>')
    as_xml = Findings(Path(tempfile.mkdtemp()))
    as_xml.handle(json.dumps({"bytes": xml}).encode())
    assert as_xml.rid_toc == {"r-tl": "TL"}, as_xml.rid_toc
    assert as_xml.values_by_toc["TL"] == [48, 77], as_xml.values_by_toc

    import gzip
    zipped = Findings(Path(tempfile.mkdtemp()))
    zipped.handle(gzip.compress(xml.encode()))
    assert zipped.values_by_toc["TL"] == [48, 77], zipped.values_by_toc

    print("selftest ok: JSON, XML and gzipped-XML payloads, double-encoded unwrap,")
    print("             @attribute sigils, schedule->operator map, positional + named")
    print("             coaches, undecodable diagnostics, and all three verdicts")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--minutes", type=float, default=30.0)
    parser.add_argument("--report-every", type=float, default=120.0)
    parser.add_argument("--out", default="probes/out/darwin-kafka")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    return selftest() if args.selftest else run(args)


if __name__ == "__main__":
    sys.exit(main())
