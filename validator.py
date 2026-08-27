"""
validator.py — Part 3, Meaning Validation. Owner: Jahanvi.

DESIGN DECISION: this module extracts facts INDEPENDENTLY. It does not import
the encoder.

The obvious design is to re-run the encoder on the reconstructed message and
diff the two packets. It is wrong here, for two reasons:

  1. A systematic encoder bug becomes invisible. If the encoder fails to see
     the negation in "do not upload the customer file", both packets agree
     there is no negation, the diff is clean, and validation reports "safe"
     on a reconstruction that inverted the instruction.
  2. It blocks this module on the encoder being finished.

Independent extraction means the validator is a genuine second opinion. It
catches encoder misses, decoder drops, and invented information alike.

Public API:
    extract_facts(text) -> dict
    validate(original, reconstructed, packet=None) -> dict
"""

import re
from typing import Dict, Any, List, Optional

# --------------------------------------------------------------- vocabularies

SAFETY_TERMS = {
    "gas", "smoke", "fire", "unconscious", "swelling", "swollen", "emergency",
    "flammable", "alarm", "leak", "medicine", "insulin", "hospital", "clinic",
    "medical", "ambulance", "injured", "burning", "evacuate",
}

# Bare "no" is deliberately NOT a cue. In this dataset it only ever appears as
# a quantity constraint ("no more than 20 passengers") or a stock exclusion
# ("no size S masks are required"), never as a prohibition. Including it
# produced 2 false positives out of 60 and caught nothing real.
PROHIBITION_CUES = [
    r"\bdo not\b", r"\bdon'?t\b", r"\bnever\b", r"\bcannot\b", r"\bcan'?t\b",
    r"\bwon'?t\b", r"\bmust not\b", r"\bavoid\b", r"\brefrain from\b",
    r"\bhold off\b", r"\bstop using\b",
]
CONTRAST_CUES = [r",\s*not\b", r"\bnot the\b", r"\brather than\b", r"\binstead of\b"]
EXCEPTION_CUES = [r"\bexcept\b", r"\bunless\b"]

# Spans removed before any negation scan. Each is a measured false positive.
FALSE_POSITIVE_SPANS = [
    r"\bbus stop\b",                    # SEM_020 - "stop" is a noun here
    r"\bno (?:more|less|fewer) than\b",  # SEM_027 - quantity constraint
    r"\bif\b[^.;]*?\bnot\b",             # SEM_060 - negation inside a condition
]

# Capitalised tokens that are places or things, never people.
NON_PERSON_CAPS = {
    "Gate", "Room", "Platform", "House", "Entrance", "Office", "Lab", "Depot",
    "Station", "Bridge", "Road", "Tunnel", "Cafe", "Café", "Clinic", "Server",
    "Hospital", "City", "Bus", "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday", "January", "February", "March", "April",
    "May", "June", "July", "August", "September", "October", "November",
    "December", "AM", "PM", "Please", "Take", "Bring", "Send", "Meet", "Order",
    "Cancel", "Find", "Share", "Walk", "Set", "Call", "Remind", "Transfer",
    "Collect", "Drop", "After", "Confirm", "Check", "The", "Do", "Don", "At",
    "Buy", "Book", "Keep", "Move", "Leave", "Alert", "Return", "Wait", "Add",
    # Structural labels emitted by decoders. Not content - never people.
    "Action", "Actions", "Details", "Alert", "Urgent", "Safety", "Critical",
    "Acknowledged", "Restrictions", "Negations", "Status", "Update", "Note",
    "Warning", "Info", "Person", "Location", "Time", "Quantity", "Object",
}

UNIT_WORDS = (
    r"ml|l|kg|g|mg|metres?|meters?|km|minutes?|mins?|hours?|hrs?|days?|weeks?|"
    r"pages?|passengers?|masks?|bottles?|packets?|copies|units?|boxes|items?|"
    r"people|persons?|°C|°F|%|₹|\$"
)

TIME_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(AM|PM|am|pm)\b|\b(\d{1,2}):(\d{2})\b|\b(noon|midnight)\b"
)
NUM_UNIT_RE = re.compile(rf"(\d+(?:\.\d+)?)\s*({UNIT_WORDS})\b", re.IGNORECASE)
BARE_NUM_RE = re.compile(r"\b(\d+(?:\.\d+)?)\b")
DAY_RE = re.compile(
    r"\b(today|tomorrow|tonight|yesterday|this (?:morning|afternoon|evening)|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.IGNORECASE
)


# ------------------------------------------------------------------ extraction

def _strip_false_positives(text: str) -> str:
    out = text
    for pat in FALSE_POSITIVE_SPANS:
        out = re.sub(pat, " ", out, flags=re.IGNORECASE)
    return out


def _negation(text: str) -> Dict[str, Any]:
    """Returns {'type': ..., 'cues': [...]}. Type ordering matters:
    prohibition outranks contrast outranks exception."""
    clean = _strip_false_positives(text)
    found = {"prohibition": [], "contrast": [], "exception": []}
    for kind, pats in (("prohibition", PROHIBITION_CUES),
                       ("contrast", CONTRAST_CUES),
                       ("exception", EXCEPTION_CUES)):
        for p in pats:
            for m in re.finditer(p, clean, re.IGNORECASE):
                found[kind].append(m.group(0).strip().lower())

    for kind in ("prohibition", "contrast", "exception"):
        if found[kind]:
            return {"type": kind, "cues": sorted(set(found[kind]))}
    return {"type": "none", "cues": []}


def _times(text: str) -> List[int]:
    """Clock times normalised to minutes since midnight, so 4:30 PM and
    16:30 compare equal."""
    out = []
    for m in TIME_RE.finditer(text):
        if m.group(6):
            out.append(720 if m.group(6).lower() == "noon" else 0)
        elif m.group(4):
            out.append(int(m.group(4)) * 60 + int(m.group(5)))
        else:
            h, mi = int(m.group(1)), int(m.group(2) or 0)
            mer = m.group(3).lower()
            if mer == "pm" and h != 12:
                h += 12
            if mer == "am" and h == 12:
                h = 0
            out.append(h * 60 + mi)
    return sorted(set(out))


def _quantities(text: str) -> List[str]:
    """Numbers, normalised as 'value unit' where a unit is present. Time spans
    are removed first so 11 in '11 AM' is not double-counted as a quantity."""
    masked = TIME_RE.sub(" ", text)
    out, consumed = [], []
    for m in NUM_UNIT_RE.finditer(masked):
        out.append(f"{float(m.group(1)):g} {m.group(2).lower()}")
        consumed.append(m.span())
    for m in BARE_NUM_RE.finditer(masked):
        if not any(s <= m.start() < e for s, e in consumed):
            out.append(f"{float(m.group(1)):g}")
    return sorted(set(out))


def _sentence_starts(text: str) -> set:
    """Offsets where a new sentence begins. A capital there is grammar, not a
    name - without this, 'Today at 16:30...' reports Today as an invented person."""
    starts = {0}
    for m in re.finditer(r"[.;!?]\s+|\n", text):
        starts.add(m.end())
    for m in re.finditer(r"[|>\-]\s+", text):  # decoder scaffolding separators
        starts.add(m.end())
    return starts


def _persons(text: str) -> List[str]:
    starts = _sentence_starts(text)
    out = []
    for m in re.finditer(r"\b([A-Z][a-z]{2,})\b", text):
        w = m.group(1)
        if w in NON_PERSON_CAPS or m.start() in starts:
            continue
        nxt = text[m.end():m.end() + 12].strip().split(" ")[:1]
        if nxt and nxt[0].rstrip(",.;") in NON_PERSON_CAPS:
            continue  # "City Hospital" - this is a place
        out.append(w)
    return sorted(set(out))


def _safety(text: str) -> List[str]:
    tl = text.lower()
    return sorted({t for t in SAFETY_TERMS if re.search(rf"\b{re.escape(t)}\b", tl)})


def extract_facts(text: str) -> Dict[str, Any]:
    """The single definition of 'what this message says' used by validation."""
    return {
        "negation": _negation(text),
        "times": _times(text),
        "quantities": _quantities(text),
        "days": sorted({d.lower() for d in DAY_RE.findall(text)}),
        "persons": _persons(text),
        "safety": _safety(text),
    }


# ------------------------------------------------------------------ validation

CRITICAL, HIGH, MEDIUM = "critical", "high", "medium"


def _issue(code, severity, detail):
    return {"code": code, "severity": severity, "detail": detail}


def _values(quantities: List[str]) -> set:
    """'24 masks' -> 24.0. The number carries the meaning; the unit is wording."""
    return {float(q.split(" ")[0]) for q in quantities}


def validate(original: str, reconstructed: str,
             packet: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    a = extract_facts(original)
    b = extract_facts(reconstructed)
    issues: List[Dict[str, str]] = []

    # --- negation: the highest-stakes check in the system --------------------
    if a["negation"]["type"] != b["negation"]["type"]:
        if a["negation"]["type"] != "none" and b["negation"]["type"] == "none":
            issues.append(_issue(
                "negation_lost", CRITICAL,
                f"original was a {a['negation']['type']}; reconstruction carries none"))
        elif a["negation"]["type"] == "none":
            issues.append(_issue(
                "negation_invented", CRITICAL,
                f"reconstruction adds a {b['negation']['type']} the original did not have"))
        else:
            issues.append(_issue(
                "negation_type_changed", CRITICAL,
                f"{a['negation']['type']} became {b['negation']['type']}"))

    # --- quantities ----------------------------------------------------------
    # The NUMBER is what changes meaning. A unit appearing or disappearing
    # ("12" vs "12 masks") is a wording difference, not a meaning change, so it
    # is reported separately at medium severity. Without this split, a
    # reconstruction that correctly restores an implied unit gets marked failed.
    va = _values(a["quantities"])
    vb = _values(b["quantities"])
    for q in sorted(va - vb):
        issues.append(_issue("quantity_lost", CRITICAL, f"missing value: {q}"))
    for q in sorted(vb - va):
        issues.append(_issue("quantity_invented", CRITICAL, f"value not in original: {q}"))
    if va == vb and set(a["quantities"]) != set(b["quantities"]):
        issues.append(_issue(
            "unit_differs", MEDIUM,
            f"same numbers, different units: {a['quantities']} vs {b['quantities']}"))

    # --- times ---------------------------------------------------------------
    for t in set(a["times"]) - set(b["times"]):
        issues.append(_issue("time_lost", CRITICAL, f"missing: {t // 60:02d}:{t % 60:02d}"))
    for t in set(b["times"]) - set(a["times"]):
        issues.append(_issue("time_invented", CRITICAL, f"not in original: {t // 60:02d}:{t % 60:02d}"))

    # --- safety --------------------------------------------------------------
    for s in set(a["safety"]) - set(b["safety"]):
        issues.append(_issue("safety_context_lost", CRITICAL, f"missing: {s}"))

    # --- days ----------------------------------------------------------------
    for d in set(a["days"]) - set(b["days"]):
        issues.append(_issue("day_lost", HIGH, f"missing: {d}"))
    for d in set(b["days"]) - set(a["days"]):
        issues.append(_issue("day_invented", CRITICAL, f"not in original: {d}"))

    # --- persons -------------------------------------------------------------
    for p in set(a["persons"]) - set(b["persons"]):
        issues.append(_issue("person_lost", HIGH, f"missing: {p}"))
    for p in set(b["persons"]) - set(a["persons"]):
        issues.append(_issue("person_invented", CRITICAL, f"not in original: {p}"))

    # --- optional second layer: packet vs reconstruction ---------------------
    if packet:
        issues.extend(_check_packet(a, packet))

    sev = {i["severity"] for i in issues}
    status = ("failed" if CRITICAL in sev
              else "review required" if issues
              else "safe")

    return {
        "status": status,
        "issues": issues,
        "checks": {
            "negation": {"original": a["negation"]["type"], "reconstructed": b["negation"]["type"]},
            "quantities": {"original": a["quantities"], "reconstructed": b["quantities"]},
            "times": {"original": a["times"], "reconstructed": b["times"]},
            "days": {"original": a["days"], "reconstructed": b["days"]},
            "persons": {"original": a["persons"], "reconstructed": b["persons"]},
            "safety": {"original": a["safety"], "reconstructed": b["safety"]},
        },
        "summary": _summary(status, issues),
    }


def _check_packet(facts: Dict[str, Any], packet: Dict[str, Any]) -> List[Dict[str, str]]:
    """Did the ENCODER drop something before transmission? Tolerant of the
    packet schema still being in flux - only checks fields it recognises."""
    out = []
    if facts["negation"]["type"] != "none":
        carried = packet.get("neg") or packet.get("neg_type") or packet.get("negation")
        if not carried or carried == "none":
            out.append(_issue(
                "encoder_dropped_negation", CRITICAL,
                f"original is a {facts['negation']['type']} but the packet carries no negation"))
    return out


def _summary(status: str, issues: List[Dict[str, str]]) -> str:
    if status == "safe":
        return "All critical facts survived the round trip."
    crit = [i["code"] for i in issues if i["severity"] == CRITICAL]
    if crit:
        return f"Meaning was not preserved: {', '.join(sorted(set(crit)))}."
    return f"Non-critical differences found: {', '.join(sorted({i['code'] for i in issues}))}."
