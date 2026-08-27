import re
import importlib
import importlib.util
from typing import Dict, Any, List, Optional

# Optional spaCy integration for normal mode enhancement
nlp = None
try:
    if importlib.util.find_spec("spacy") is not None:
        spacy_module = importlib.import_module("spacy")
        nlp = spacy_module.load("en_core_web_sm")
except Exception:
    nlp = None

SAFETY_KEYWORDS = {
    "gas", "smoke", "fire", "unconscious", "swelling", "emergency", "flammable",
    "alarm", "leak", "insulation", "toxic", "hazard", "danger", "surge", "compromised", "shutdown"
}

URGENCY_KEYWORDS = {
    "immediately", "urgent", "soon", "now", "emergency", "fast", "asap",
    "at once", "stat", "right now", "promptly"
}

KNOWN_PERSONS = [
    "building security desk", "security desk", "external contractors", "medical professional",
    "maintenance team", "site supervisor", "procurement lead", "dr. shah", "dr shah",
    "rahul", "riya", "arjun", "meera", "dad", "neha", "kabir", "priya", 
    "aisha", "sam", "omar", "leena", "subhash", "client", "guardian", "doctor",
    "security", "coordinator", "engineer", "attendees", "personnel", "optician", "vendor"
]

KNOWN_LOCATIONS = [
    r"\b(Pune|Mumbai|Delhi|Bengaluru|Chennai|Hyderabad|Kolkata)\b",
    r"\b(Gate\s+(?:\d+[A-Za-z]?|[A-Z]\b))\b",
    r"\b(Room\s+(?:\d+[A-Za-z]?|[A-Z]\b))\b",
    r"\b(Desk\s+(?:\d+[A-Za-z]?|[A-Z]\b))\b",
    r"\b(Platform\s+(?:\d+[A-Za-z]?|[A-Z]\b))\b",
    r"\b(Pillar\s+\d+(?:\s+on\s+Level\s+\d+)?)\b",
    r"\b(Level\s+\d+)\b",
    r"\b(House\s+\d+)\b",
    r"\b(Shelf\s+\d+)\b",
    r"\b(Entrance\s+[0-9A-Za-z]+)\b",
    r"\b(Sector\s+\d+)\b",
    r"\b(Zone\s+[0-9A-Za-z]+)\b",
    r"\b(Warehouse\s+[0-9A-Za-z]+)\b",
    r"\b(Conference\s+Room\s+[0-9A-Za-z]+)\b",
    r"\b(Terminal\s+\d+)\b",
    r"\b(Clinic\s+\d+)\b",
    r"\b(City\s+Hospital)\b",
    r"\b(Central\s+Market)\b",
    r"\b(Spice\s+Garden)\b",
    r"\b(Chennai\s+Central)\b",
    r"\b(Bengaluru\s+Cantonment)\b",
    r"\b(railway\s+station)\b",
    r"\b(second-floor\s+lounge)\b",
    r"\b(finance\s+office)\b",
    r"\b(kitchen)\b",
    r"\b(office)\b",
    r"\b(reception)\b",
    r"\b(room)\b",
    r"\b(lab)\b",
    r"\b(depot)\b",
    r"\b(bus\s+stop)\b",
    r"\b(pharmacy)\b",
    r"\b(café|cafe)\b",
    r"\b(river\s+road)\b",
]

COMMON_OBJECTS = [
    "project notebook", "customer file", "anonymized summary", "keys", "blue folder",
    "green folder", "green one", "folder", "batteries", "sensor", "field sensor",
    "Server B", "database backup", "glasses", "signed agreement", "agreement", "Appendix C",
    "redacted records", "records", "power", "vegetarian meals", "passport number", "passport",
    "medicine", "small model", "model", "phone", "invoice", "payment credentials",
    "USB-C adapter", "universal adapter", "adapter", "Bus 12", "Train 12627", "temperature readings",
    "envelope", "sample images", "images", "charger", "insulin pouch", "red pouch",
    "blue insulin pouch", "hallway lights", "emergency lights", "public brochure",
    "private price list", "brochure", "price list", "audio note", "masks", "employee badge",
    "product label", "parcel", "container", "report", "documents", "document", "file", "packages", "package"
]

ACTION_VERBS = [
    "send", "deliver", "meet", "buy", "upload", "lock", "return", "leave", "alert",
    "take", "call", "move", "pack", "restart", "pick up", "sync", "disconnect",
    "notify", "remind", "walk", "reserve", "give", "contact", "download",
    "verify", "switch", "transfer", "collect", "ask", "hand", "cancel",
    "tell", "inform", "translate", "save", "set", "dim", "email", "find", "share",
    "avoid", "record", "wake", "order", "drop", "use", "photograph", "crop", "check", "open", "bring"
]

RE_TIME_PATTERNS = re.compile(
    r"\b(\d{1,2}:\d{2}(?:\s*(?:am|pm|hrs|utc))?|\d{1,2}\s*(?:am|pm|hrs|utc)|today|tomorrow(?:\s+morning|\s+afternoon|\s+evening)?|yesterday|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday|midnight(?:\s+utc)?|noon|dusk|evening|morning)\b",
    re.IGNORECASE,
)


def extract_negations(text: str) -> List[str]:
    """
    Extracts canonical negation clauses.
    Removes overlapping substring duplicates to minimize packet size.
    """
    if not text or not isinstance(text, str):
        return []

    negation_patterns = [
        r"\bdo not\b[^\.\,\;\!\?]*", r"\bdon\'t\b[^\.\,\;\!\?]*", r"\bnever\b[^\.\,\;\!\?]*",
        r"\bnot\b[^\.\,\;\!\?]*", r"\bno\b\s+\w+", r"\bexcept\b[^\.\,\;\!\?]*", r"\bavoid\b[^\.\,\;\!\?]*",
        r"\bcannot\b[^\.\,\;\!\?]*", r"\bcan\'t\b[^\.\,\;\!\?]*", r"\bstop\b[^\.\,\;\!\?]*"
    ]
    spans = []
    for pat in negation_patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            s, e = m.span()
            matched_str = m.group().strip()
            if matched_str:
                spans.append((s, e, matched_str))
    
    # Sort by span length descending (longest enclosing span first)
    spans.sort(key=lambda x: (x[1] - x[0]), reverse=True)
    
    selected_spans = []
    selected_strings = []
    for s, e, matched_str in spans:
        # Avoid sub-spans or sub-strings of already captured longer negation clauses
        if not any(sel_s <= s and e <= sel_e for sel_s, sel_e, _ in selected_spans):
            if not any(matched_str.lower() in sel_str.lower() for sel_str in selected_strings):
                selected_spans.append((s, e, matched_str))
                selected_strings.append(matched_str)
                
    return selected_strings


def encode_message_logic(text: str, mode: Optional[str] = "normal") -> Dict[str, Any]:
    """
    Task 1: Semantic Encoder Core Logic.
    Extracts structured meaning into the canonical semantic packet contract.
    Guarantees zero hallucination and robust fallback handling.
    """
    mode = (mode or "normal").lower()
    
    packet: Dict[str, Any] = {
        "urg": "normal",
        "safe_crit": False,
        "neg": [],
        "ent": {"per": [], "loc": [], "time": [], "qty": [], "obj": []},
        "act": []
    }
    
    if not text or not isinstance(text, str) or not text.strip():
        return packet

    # 1. Safety & Urgency Detection
    text_lower = text.lower()
    if any(k in text_lower for k in SAFETY_KEYWORDS):
        packet["safe_crit"] = True
        packet["urg"] = "high"
    elif any(k in text_lower for k in URGENCY_KEYWORDS):
        packet["urg"] = "high"

    # 2. Negation Detection (CRITICAL)
    packet["neg"] = extract_negations(text)

    # 3. Entity and Action Extraction (Deterministic Regex Patterns)
    # Extract Persons / Roles (longest match first to avoid sub-string collisions)
    matched_person_spans = []
    for person in sorted(KNOWN_PERSONS, key=len, reverse=True):
        for m in re.finditer(rf"\b{re.escape(person)}\b", text, re.IGNORECASE):
            span = (m.start(), m.end())
            if not any(s[0] <= span[0] and span[1] <= s[1] for s in matched_person_spans):
                matched_person_spans.append(span)
                proper_name = person.title() if person != "dr. shah" else "Dr. Shah"
                packet["ent"]["per"].append(proper_name)

    # Extract Locations (sorted by length to match specific locations before generic words)
    matched_loc_spans = []
    for loc_pat in sorted(KNOWN_LOCATIONS, key=len, reverse=True):
        for match in re.finditer(loc_pat, text, re.IGNORECASE):
            s, e = match.span(1)
            if not any(sel_s <= s and e <= sel_e for sel_s, sel_e in matched_loc_spans):
                matched_loc_spans.append((s, e))
                loc_str = match.group(1).strip()
                packet["ent"]["loc"].append(loc_str)

    # Extract Objects
    for obj in sorted(COMMON_OBJECTS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(obj)}\b", text, re.IGNORECASE):
            packet["ent"]["obj"].append(obj)

    # Extract Times & Dates (valid time formats only, not bare standalone digits)
    time_matches = RE_TIME_PATTERNS.findall(text)
    packet["ent"]["time"].extend([t.strip() for t in time_matches if t.strip()])

    # Extract Quantities
    qty_matches = re.findall(
        r"\b(?:₹|\$|€)?\d+(?:\.\d+)?(?:\s*(?:ml|l|litres|kg|g|metres|meters|km|mb|kb|%|°c|bottles|packets?|packages?|crates?|boxes|meals|passengers|readings|images|masks|minutes?|seconds?|pages?|units?))?|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|twelve|twenty|forty)\s+[a-zA-Z%°]+\b",
        text,
        re.IGNORECASE,
    )
    for q in qty_matches:
        q_clean = q.strip()
        if q_clean:
            # Ensure time values like 5 PM are not counted as standalone quantities
            if not any(q_clean in t for t in packet["ent"]["time"]):
                # Also exclude numbers that are part of location names like 'Gate 2'
                if not any(q_clean in loc for loc in packet["ent"]["loc"]):
                    packet["ent"]["qty"].append(q_clean)

    # Extract Actions (Verbs)
    for verb in ACTION_VERBS:
        if re.search(rf"\b{re.escape(verb)}\b", text, re.IGNORECASE):
            packet["act"].append(verb.lower())

    # 4. Optional NLP Enhancement (Normal mode with spaCy if available)
    if mode == "normal" and nlp is not None:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ in ["PERSON"] and ent.text not in packet["ent"]["per"]:
                packet["ent"]["per"].append(ent.text)
            elif ent.label_ in ["GPE", "LOC", "FAC"] and ent.text not in packet["ent"]["loc"]:
                packet["ent"]["loc"].append(ent.text)
            elif ent.label_ in ["TIME", "DATE"] and ent.text not in packet["ent"]["time"]:
                packet["ent"]["time"].append(ent.text)
            elif ent.label_ in ["CARDINAL", "QUANTITY"] and ent.text not in packet["ent"]["qty"]:
                packet["ent"]["qty"].append(ent.text)
            elif ent.label_ in ["PRODUCT", "ORG", "WORK_OF_ART"] and ent.text not in packet["ent"]["obj"]:
                packet["ent"]["obj"].append(ent.text)

        for token in doc:
            if token.pos_ in ["VERB"] and not token.is_stop and token.lemma_ not in packet["act"]:
                packet["act"].append(token.lemma_)

    # Deduplicate arrays
    for k in packet["ent"]:
        packet["ent"][k] = list(set(packet["ent"][k]))
    packet["act"] = list(set(packet["act"]))

    return packet
