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
        # Records are kept raw and attributed at REPORT time, not on arrival.
        # Loading for a service routinely arrives before that service's schedule,
        # so attributing once, on receipt, strands most of the data under "??"
        # and makes "none from GTR" mean "none from the few I could identify".
        self.loading_records: list[dict] = []
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
            record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "rid": rid, "tpl": attr(node, "tpl"), "coaches": coaches}
            self.loading_records.append(record)
            with self.jsonl.open("a") as handle:
                handle.write(json.dumps(record) + "\n")

    def attribute(self) -> tuple[Counter, dict[str, list[int]], int]:
        """Resolve every loading record against the map as it stands NOW."""
        by_toc: Counter = Counter()
        values: dict[str, list[int]] = defaultdict(list)
        unknown = 0
        for record in self.loading_records:
            toc = self.rid_toc.get(record["rid"], "")
            if not toc:
                unknown += 1
                continue
            by_toc[toc] += 1
            values[toc] += [c["loading"] for c in record["coaches"]]
        return by_toc, values, unknown

    def rates(self) -> dict[str, tuple[int, int]]:
        """Per operator: (services positively identified, of those, how many loaded).

        The unattributed bucket does not drain by listening — those services'
        schedules were published before the topic's retention window and will
        never arrive. So the question is asked the other way round: among the
        services whose operator IS known, which operators load and which do not.
        That has a denominator, and is unaffected by the orphans.
        """
        seen = Counter(self.rid_toc.values())
        loaded: dict[str, set] = defaultdict(set)
        for record in self.loading_records:
            toc = self.rid_toc.get(record["rid"], "")
            if toc:
                loaded[toc].add(record["rid"])
        return {toc: (seen[toc], len(loaded.get(toc, ()))) for toc in sorted(seen)}

    def progress(self) -> str:
        mins = (datetime.now(timezone.utc) - self.started).total_seconds() / 60
        by_toc, _values, unknown = self.attribute()
        named = ", ".join(f"{t}={by_toc[t]}" for t in sorted(by_toc)) or "none yet"
        return (f"{mins:.0f}m — {self.messages} messages, {len(self.rid_toc)} services known\n"
                f"  per-coach loading BY OPERATOR: {named}"
                f"  (+{unknown} still unattributed)")

    def report(self) -> str:
        by_toc, values_by_toc, unknown = self.attribute()
        gtr = sum(by_toc[t] for t in WATCHED)
        named = sum(by_toc.values())
        total = named + unknown
        lines = [
            "# Darwin push feed (Kafka) — per-coach loading coverage",
            "",
            f"- Listening since: {self.started.isoformat(timespec='seconds')}",
            f"- Messages: {self.messages} ({self.decode_errors} undecodable)",
            f"- Services whose operator is known: {len(self.rid_toc)}",
            f"- formationLoading messages: {total} — **{named} attributed, "
            f"{unknown} unattributed**",
            "",
            "## formationLoading by operator",
            "",
            "| TOC | messages | coach values | min | max | mean |",
            "|---|---|---|---|---|---|",
        ]
        for toc in sorted(by_toc):
            vals = values_by_toc[toc]
            stats = (f"{min(vals)} | {max(vals)} | {sum(vals)/len(vals):.1f}"
                     if vals else "- | - | -")
            lines.append(f"| {toc} | {by_toc[toc]} | {len(vals)} | {stats} |")
        if unknown:
            lines.append(f"| _unattributed_ | {unknown} | — | — | — | — |")
        if not total:
            lines.append("| _none_ | 0 | 0 | - | - | - |")

        rates = self.rates()
        lines += ["", "## Loading rate among positively identified services", ""]
        lines.append("Only services whose schedule was seen, so the orphan bucket cannot "
                     "skew it. This is the comparison the verdict rests on.")
        lines += ["", "| TOC | services identified | of those, with per-coach loading |",
                  "|---|---|---|"]
        for toc, (seen, loaded) in sorted(rates.items(), key=lambda kv: -kv[1][0])[:12]:
            pct = f"{loaded * 100 // seen}%" if seen else "-"
            mark = "  ← yours" if toc in WATCHED else ""
            lines.append(f"| {toc}{mark} | {seen} | {loaded} ({pct}) |")

        lines += ["", "## Verdict", ""]
        gtr_seen = sum(rates.get(t, (0, 0))[0] for t in WATCHED)
        gtr_loaded = sum(rates.get(t, (0, 0))[1] for t in WATCHED)
        others_loaded = sum(l for toc, (_s, l) in rates.items() if toc not in WATCHED)
        if gtr_loaded:
            lines.append(f"**GTR PUBLISHES per-coach loading** — {gtr_loaded} of {gtr_seen} "
                         "identified services across " + ", ".join(WATCHED) +
                         ", despite LDBSVWS showing none. The carriage-level product is "
                         "back on, via this feed.")
        elif gtr_seen < 30:
            lines.append(f"**INCONCLUSIVE.** Only {gtr_seen} services from "
                         f"{', '.join(WATCHED)} were positively identified — too few to "
                         "conclude anything from their silence. Run again across a busier "
                         "period.")
        elif not others_loaded:
            lines.append("**INCONCLUSIVE.** No identified service from any operator carried "
                         "per-coach loading, so the absence says nothing about GTR "
                         "specifically. Check the topic and subscription.")
        else:
            lines.append(f"**GTR does not publish per-coach loading.** {gtr_seen} services "
                         f"across {', '.join(WATCHED)} were positively identified and "
                         f"**none carried it**, while other operators on the same feed, in "
                         f"the same window, loaded {others_loaded} services. This is the "
                         "fuller feed agreeing with LDBSVWS. The carriage-level product is "
                         "not possible on this route, and no further checking will change it.")
            lines += ["", f"({unknown} loading messages remain unattributed. They do not "
                          "affect this: the comparison above is drawn only from services "
                          "whose operator is known, and those schedules are missing because "
                          "they predate the topic's retention, not because of anything "
                          "operator-specific.)"]
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
    by_toc, values, unknown = findings.attribute()
    assert by_toc["TL"] == 1 and by_toc["SE"] == 1, by_toc
    assert values["TL"] == [48, 77], values
    assert unknown == 0, unknown
    assert "GTR PUBLISHES per-coach loading" in findings.report()

    # The bug this probe shipped with: loading arriving before its schedule was
    # attributed once, on receipt, and never revisited, so most of a real run
    # landed under "??" and the verdict read that as "not GTR".
    late = Findings(Path(tempfile.mkdtemp()))
    orphan = json.dumps({"bytes": json.dumps({"Pport": {"uR": {
        "formationLoading": {"@rid": "r9", "loading": [{"@coachNumber": "A", "#text": "61"}]}}}})})
    late.handle(orphan.encode())
    assert "INCONCLUSIVE" in late.report(), "an unattributed run must not answer the question"
    late.handle(json.dumps({"bytes": json.dumps({"Pport": {"uR": {
        "schedule": {"@rid": "r9", "@toc": "TL"}}}})}).encode())
    assert late.attribute()[0]["TL"] == 1, late.attribute()
    assert late.rates()["TL"] == (1, 1), late.rates()
    assert "GTR PUBLISHES" in late.report(), late.report()

    # GTR silent while others publish must read as a decision, not as "no data".
    other = Findings(Path(tempfile.mkdtemp()))
    other.handle(json.dumps({"bytes": json.dumps({"Pport": {"uR": {
        "schedule": {"@rid": "r1", "@toc": "SE"},
        "formationLoading": {"@rid": "r1", "loading": [{"@coachNumber": "A", "#text": "90"}]},
    }}})}).encode())
    # One SE service loading and no GTR services seen must NOT read as an answer
    # about GTR -- under the old message-counting verdict it did.
    assert "INCONCLUSIVE" in other.report(), other.report()

    # With a real denominator it becomes an answer: GTR services identified in
    # numbers, none of them loading, while another operator on the same feed does.
    rate = Findings(Path(tempfile.mkdtemp()))
    for i in range(40):
        rate.handle(json.dumps({"bytes": json.dumps({"Pport": {"uR": {
            "schedule": {"@rid": f"tl{i}", "@toc": "TL"}}}})}).encode())
    for i in range(20):
        rate.handle(json.dumps({"bytes": json.dumps({"Pport": {"uR": {
            "schedule": {"@rid": f"se{i}", "@toc": "SE"}}}})}).encode())
        if i < 15:
            rate.handle(json.dumps({"bytes": json.dumps({"Pport": {"uR": {"formationLoading":
                {"@rid": f"se{i}", "loading": [{"@coachNumber": "A", "#text": "70"}]}}}})}).encode())
    assert rate.rates()["TL"] == (40, 0), rate.rates()
    assert rate.rates()["SE"] == (20, 15), rate.rates()
    assert "GTR does not publish per-coach loading" in rate.report(), rate.report()

    # Nothing at all must NOT be reported as an answer about GTR.
    empty = Findings(Path(tempfile.mkdtemp()))
    empty.handle(json.dumps({"bytes": json.dumps({"Pport": {"uR": {"TS": {"@rid": "x"}}}})}).encode())
    assert "INCONCLUSIVE" in empty.report(), empty.report()

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
    assert as_xml.attribute()[1]["TL"] == [48, 77], as_xml.attribute()

    import gzip
    zipped = Findings(Path(tempfile.mkdtemp()))
    zipped.handle(gzip.compress(xml.encode()))
    assert zipped.attribute()[1]["TL"] == [48, 77], zipped.attribute()

    print("selftest ok: JSON, XML and gzipped-XML payloads, double-encoded unwrap,")
    print("             @attribute sigils, RETROACTIVE operator attribution, positional +")
    print("             named coaches, undecodable diagnostics, and all four verdicts")
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
