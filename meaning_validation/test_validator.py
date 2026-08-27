"""
test_validator.py — run with: python test_validator.py

Two properties this suite exists to prove, in this order:
  1. A faithful reconstruction is never marked failed. A validator that cries
     wolf is worse than no validator, because the team stops trusting it.
  2. Every category of real meaning loss is caught.

No message from semantic_messages.csv is hardcoded as an expected result.
"""

from validator import validate, extract_facts

PASS, FAIL = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m"
_score = [0, 0]


def check(label, cond):
    _score[cond is False] += 0
    _score[0 if cond else 1] += 1
    print(f"  {PASS if cond else FAIL}  {label}")


print("\n1. IDENTITY — a message against itself is always safe")
for m in ["Do not upload the customer file.",
          "Meet Riya outside Gate 2 at 4:30 PM today.",
          "The kitchen smells like gas; leave the room."]:
    check(m[:46], validate(m, m)["status"] == "safe")

print("\n2. FAITHFUL REWORDING — different words, same meaning, must not fail")
faithful = [
    ("Meet Riya outside Gate 2 at 4:30 PM today.",
     "Today at 16:30, meet Riya at Gate 2."),
    ("Do not upload the customer file; send only the anonymized summary.",
     "Do not upload the customer file. Send the anonymized summary instead."),
    ("Take the blue folder, not the green one, to the finance office before 11 AM.",
     "Before 11:00, take the blue folder to the finance office. Not the green one."),
    ("The kitchen smells like gas; leave the room and alert the building security desk.",
     "Gas detected in the kitchen. Leave the room and alert building security."),
    ("Transfer 750 to the approved vendor account after Priya confirms the invoice.",
     "After Priya confirms the invoice, transfer 750 to the approved vendor account."),
]
for orig, recon in faithful:
    check(recon[:46], validate(orig, recon)["status"] != "failed")

print("\n3. MEANING LOSS — every category must be caught")
broken = [
    ("negation dropped", "Do not upload the customer file.",
     "Upload the customer file.", "negation_lost"),
    ("negation invented", "Upload the customer file.",
     "Do not upload the customer file.", "negation_invented"),
    ("contrast flattened", "Take the blue folder, not the green one.",
     "Take the folder.", "negation_lost"),
    ("quantity changed", "Order 24 masks in size M.",
     "Order 42 masks in size M.", "quantity_invented"),
    ("time changed", "Meet at Gate 2 at 4:30 PM.",
     "Meet at Gate 2 at 4:30 AM.", "time_invented"),
    ("person invented", "Bring the folder to the office.",
     "Bring the folder to Priya at the office.", "person_invented"),
    ("person lost", "Meet Riya at Gate 2.",
     "Meet at Gate 2.", "person_lost"),
    ("safety context lost", "The kitchen smells like gas; leave the room.",
     "Leave the room.", "safety_context_lost"),
    ("day invented", "Bring the file to the office.",
     "Bring the file to the office tomorrow.", "day_invented"),
]
for label, orig, recon, expect in broken:
    codes = [i["code"] for i in validate(orig, recon)["issues"]]
    check(f"{label:20s} -> {expect}", expect in codes)

print("\n4. FALSE-POSITIVE GUARDS — measured on the real dataset")
guards = [
    ("bus stop is not a prohibition",
     "Walk 200 metres east from the bus stop, turn left at the pharmacy."),
    ("'no more than' is a quantity, not a negation",
     "At 7:05 AM, send Bus 12 to Platform 3 with no more than 20 passengers."),
    ("'has not arrived' inside a condition is not a prohibition",
     "At 2:20 PM, collect Leena from Entrance C, then call if she has not arrived."),
    ("'cancel' is an intent, not a negation",
     "Cancel today's client call, but keep tomorrow's internal review unchanged."),
]
for label, msg in guards:
    check(label, extract_facts(msg)["negation"]["type"] == "none")

print("\n5. NEGATION TYPING — the four kinds are distinguished")
types = [
    ("Do not upload the customer file.", "prohibition"),
    ("Take the blue folder, not the green one.", "contrast"),
    ("Share the link with engineering except external contractors.", "exception"),
    ("Please bring the project notebook to the lab.", "none"),
]
for msg, expect in types:
    check(f"{expect:12s} <- {msg[:34]}", extract_facts(msg)["negation"]["type"] == expect)

print("\n6. TIME NORMALISATION — same instant, different notation")
check("4:30 PM == 16:30", extract_facts("at 4:30 PM")["times"] == extract_facts("at 16:30")["times"])
check("noon == 12:00", extract_facts("by noon")["times"] == extract_facts("by 12:00")["times"])

print("\n7. DECODER OUTPUT STYLES — validation must survive B's formatting")
ORIG = "Bring the blue insulin pouch to City Hospital before 6 PM; do not bring the red pouch."
styles = [
    ("natural sentence",
     "Do not bring the red pouch. Bring the blue insulin pouch to City Hospital before 18:00."),
    ("label prefix",
     "PROHIBITED: bring the red pouch. Bring the blue insulin pouch to City Hospital before 6 PM."),
    ("restriction label",
     "Bring the blue insulin pouch to City Hospital before 6 PM. RESTRICTION: red pouch."),
    ("structured dump",
     "Action: bring | Object: blue insulin pouch | Location: City Hospital | "
     "Time: 18:00 | Negation: red pouch"),
]
for label, recon in styles:
    check(f"{label:20s} not falsely failed", validate(ORIG, recon)["status"] != "failed")

print("\n8. PIPELINE INTEGRATION — end to end through the live app")
try:
    from main import process_end_to_end, EncodeRequest, health
    src = health()
    print(f"     (encoder={src['encoder']}, decoder={src['decoder']})")

    r = process_end_to_end(EncodeRequest(
        message_id="T1", mode="normal",
        message="Do not upload the customer file; send only the anonymized summary."))
    check("end-to-end returns a verdict", r["validation"]["status"] in
          ("safe", "review required", "failed"))
    check("negation survives the round trip",
          r["validation"]["checks"]["negation"]["reconstructed"] != "none")
    check("benchmark metrics present",
          {"encode_latency_ms", "decode_latency_ms", "compression_percentage"}
          <= set(r["benchmark"]))

    lo = process_end_to_end(EncodeRequest(
        message_id="T2", mode="low_resource",
        message="Meet Riya outside Gate 2 at 4:30 PM today."))
    check("low-resource mode never reports failed", lo["validation"]["status"] != "failed")
    check("low-resource keeps the time (critical slot)",
          lo["validation"]["checks"]["times"]["reconstructed"] == [990])
except ImportError as e:
    print(f"     skipped, main.py not importable: {e}")

print(f"\n{'=' * 52}\n  {_score[0]} passed, {_score[1]} failed\n{'=' * 52}")
raise SystemExit(1 if _score[1] else 0)