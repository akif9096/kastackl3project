import pytest
from fastapi.testclient import TestClient
from main import app
from app.encoder import encode_message_logic

client = TestClient(app)


# ==========================================================
# TASK 1: MANDATORY HACKATHON EVALUATION SCENARIOS
# ==========================================================

def test_1_simple_action():
    """1. Simple action message: Send the report to Rahul."""
    msg = "Send the report to Rahul."
    packet = encode_message_logic(msg, "normal")

    assert "send" in packet["act"]
    assert "Rahul" in packet["ent"]["per"]
    assert "report" in packet["ent"]["obj"]
    assert len(packet["neg"]) == 0
    assert packet["safe_crit"] is False


def test_2_time_location_quantity():
    """2. Time + Location + Quantity message: Deliver 3 packages to Gate 2 at 5 PM."""
    msg = "Deliver 3 packages to Gate 2 at 5 PM."
    packet = encode_message_logic(msg, "normal")

    assert "deliver" in packet["act"]
    assert "Gate 2" in packet["ent"]["loc"]
    assert any("5 PM" in t or "5 pm" in t.lower() for t in packet["ent"]["time"])
    assert any("3" in q for q in packet["ent"]["qty"])
    assert "packages" in packet["ent"]["obj"]
    assert len(packet["neg"]) == 0


def test_3_negation():
    """3. Critical Negation message: Do not send the file to Rahul."""
    msg = "Do not send the file to Rahul."
    packet = encode_message_logic(msg, "normal")

    # CRITICAL: Negation MUST be preserved
    assert len(packet["neg"]) == 1
    assert packet["neg"] == ["Do not send the file to Rahul"]
    assert "send" in packet["act"]
    assert "Rahul" in packet["ent"]["per"]
    assert "file" in packet["ent"]["obj"]


def test_no_duplicate_overlapping_negations():
    """Verify that overlapping negation patterns produce a single canonical clause."""
    msg = "Do not send the file to Rahul."
    packet = encode_message_logic(msg, "normal")
    assert packet["neg"] == ["Do not send the file to Rahul"]


def test_4_incomplete_message():
    """4. Incomplete message: Send the documents. (Must NOT invent missing info)."""
    msg = "Send the documents."
    packet = encode_message_logic(msg, "normal")

    assert "send" in packet["act"]
    assert "documents" in packet["ent"]["obj"]
    # Zero hallucination guarantee:
    assert len(packet["ent"]["per"]) == 0
    assert len(packet["ent"]["loc"]) == 0
    assert len(packet["ent"]["time"]) == 0
    assert len(packet["ent"]["qty"]) == 0


def test_5_safety_sensitive():
    """5. Safety-sensitive / Critical warning: Do not open the container until 6 PM."""
    msg = "Do not open the container until 6 PM."
    packet = encode_message_logic(msg, "normal")

    assert len(packet["neg"]) == 1
    assert packet["neg"] == ["Do not open the container until 6 PM"]
    assert "open" in packet["act"]
    assert "container" in packet["ent"]["obj"]
    assert any("6 PM" in t or "6 pm" in t.lower() for t in packet["ent"]["time"])


# ==========================================================
# TASK 1: REPRESENTATIVE DATASET TESTS (semantic_messages.csv)
# ==========================================================

def test_sem_001_lab_notebook():
    msg = "Please bring the project notebook to the lab."
    packet = encode_message_logic(msg, "normal")
    assert "bring" in packet["act"]
    assert "project notebook" in packet["ent"]["obj"]
    assert "lab" in packet["ent"]["loc"]


def test_sem_002_meet_gate():
    msg = "Meet Riya outside Gate 2 at 4:30 PM today."
    packet = encode_message_logic(msg, "normal")
    assert "meet" in packet["act"]
    assert "Riya" in packet["ent"]["per"]
    assert "Gate 2" in packet["ent"]["loc"]
    assert any("4:30 PM" in t or "4:30 pm" in t.lower() for t in packet["ent"]["time"])


def test_sem_004_negation_file_upload():
    msg = "Do not upload the customer file; send only the anonymized summary."
    packet = encode_message_logic(msg, "normal")
    assert len(packet["neg"]) == 1
    assert packet["neg"] == ["Do not upload the customer file"]
    assert "customer file" in packet["ent"]["obj"]
    assert "anonymized summary" in packet["ent"]["obj"]


def test_sem_007_hazard_gas_warning():
    msg = "The kitchen smells like gas; leave the room and alert the building security desk."
    packet = encode_message_logic(msg, "normal")
    assert packet["safe_crit"] is True
    assert packet["urg"] == "high"


def test_sem_011_quantity_extraction():
    msg = "Pack 6 small batteries for the field sensor and keep 2 as backup."
    packet = encode_message_logic(msg, "normal")
    assert "pack" in packet["act"]
    assert any("6" in q for q in packet["ent"]["qty"])


# ==========================================================
# TASK 1: FASTAPI /encode INTEGRATION TESTS
# ==========================================================

def test_api_encode_endpoint_normal_mode():
    res = client.post("/encode", json={
        "message_id": "SEM_002",
        "message": "Meet Riya outside Gate 2 at 4:30 PM today.",
        "mode": "normal"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["message_id"] == "SEM_002"
    assert "semantic_packet" in data
    assert "metrics" in data
    assert data["metrics"]["original_size_bytes"] == len("Meet Riya outside Gate 2 at 4:30 PM today.".encode("utf-8"))
    assert data["metrics"]["raw_packet_bytes"] > 0
    assert data["metrics"]["compressed_packet_bytes"] > 0
    assert "compression_percentage" in data["metrics"]
    assert "latency_ms" in data["metrics"]


def test_api_encode_endpoint_low_resource_mode():
    res = client.post("/encode", json={
        "message_id": "SEM_003",
        "message": "Deliver 3 packages to Gate 2 at 5 PM.",
        "mode": "low_resource"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "low_resource"
    assert "semantic_packet" in data
    assert data["metrics"]["latency_ms"] >= 0.0
