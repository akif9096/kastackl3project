import time
import json
import zlib
import re
import sqlite3
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Task 1: Import isolated Semantic Encoder
from app.encoder import (
    encode_message_logic,
    extract_negations,
    SAFETY_KEYWORDS,
)

# Task 2: Import isolated Semantic Decoder
try:
    from decode.decoder import advanced_decode_packet
except ImportError:
    def advanced_decode_packet(packet: Dict[str, Any]) -> str:
        parts = []
        if packet.get("safe_crit"):
            parts.append("🚨 [SAFETY-CRITICAL ALERT]")
        if packet.get("urg") == "high":
            parts.append("⚠️ [URGENT]")
        actions = packet.get("act", [])
        if actions:
            parts.append(f"Action(s): {', '.join(actions)}.")
        entities = packet.get("ent", {})
        ent_strs = []
        for etype, values in entities.items():
            if values:
                ent_strs.append(f"{etype.upper()}: {', '.join(values)}")
        if ent_strs:
            parts.append(f"Details -> {' | '.join(ent_strs)}.")
        negations = packet.get("neg", [])
        if negations:
            parts.append(f"RESTRICTIONS: {'; '.join(negations)}.")
        return " ".join(parts) if parts else "Acknowledge: System status normal."

app = FastAPI(title="Semantic Communication Engine", version="1.0.0")

# Database Setup
DB_FILE = "semantic_benchmarks.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS benchmark_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT,
            mode TEXT,
            original_message TEXT,
            original_size_bytes INTEGER,
            packet_size_bytes INTEGER,
            compression_ratio_pct REAL,
            encode_latency_ms REAL,
            decode_latency_ms REAL,
            reconstructed_message TEXT,
            validation_status TEXT,
            validation_details TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Request / Response Schemas ---

class EncodeRequest(BaseModel):
    message_id: Optional[str] = "CUSTOM"
    message: str
    mode: Optional[str] = "normal"  # "normal" or "low_resource"

class DecodeRequest(BaseModel):
    packet: Dict[str, Any]

class ValidateRequest(BaseModel):
    original: str
    reconstructed: str
    packet: Optional[Dict[str, Any]] = None

# --- Meaning Validation Logic (Task 3) ---

def validate_reconstruction(original: str, reconstructed: str, packet: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    issues = []
    orig_lower = original.lower()
    recon_lower = reconstructed.lower()

    # Negation Check
    orig_negs = extract_negations(original)
    if orig_negs:
        for neg in orig_negs:
            words = set(re.findall(r"\b\w+\b", neg.lower()))
            if not any(w in recon_lower for w in ["not", "never", "don't", "no", "except", "avoid", "restriction", "restrictions"]):
                issues.append(f"Missing critical negation context: '{neg}'")

    # Numeric/Quantity Check
    orig_nums = re.findall(r"\b\d+(?:\.\d+)?\b", original)
    for num in orig_nums:
        if num not in reconstructed:
            issues.append(f"Missing quantitative metric: {num}")

    # Safety Keyword Check
    for word in SAFETY_KEYWORDS:
        if word in orig_lower and word not in recon_lower and "[safety-critical" not in recon_lower and "[alert:" not in recon_lower:
            issues.append(f"Missing critical safety alert keyword: '{word}'")

    if not issues:
        return {"status": "safe", "issues": []}
    elif len(issues) <= 2 and not any("safety" in i.lower() for i in issues):
        return {"status": "review required", "issues": issues}
    else:
        return {"status": "failed", "issues": issues}

# --- API Endpoints ---

# TASK 1: SEMANTIC ENCODER ENDPOINT
@app.post("/encode")
def encode_message(payload: EncodeRequest):
    start_time = time.perf_counter()
    
    packet = encode_message_logic(payload.message, payload.mode or "normal")
    
    # Calculate sizes
    orig_bytes = len(payload.message.encode("utf-8"))
    json_bytes = len(json.dumps(packet).encode("utf-8"))
    compressed_bytes = len(zlib.compress(json.dumps(packet).encode("utf-8")))
    
    enc_latency = (time.perf_counter() - start_time) * 1000

    compression_pct = round((1 - (compressed_bytes / orig_bytes)) * 100, 2) if orig_bytes > 0 else 0.0

    return {
        "message_id": payload.message_id,
        "mode": payload.mode,
        "semantic_packet": packet,
        "metrics": {
            "original_size_bytes": orig_bytes,
            "raw_packet_bytes": json_bytes,
            "compressed_packet_bytes": compressed_bytes,
            "compression_percentage": compression_pct,
            "latency_ms": round(enc_latency, 3)
        }
    }

# TASK 2: DECODER ENDPOINT
@app.post("/decode")
def decode_message(payload: DecodeRequest):
    start_time = time.perf_counter()
    
    reconstructed = advanced_decode_packet(payload.packet)
    dec_latency = (time.perf_counter() - start_time) * 1000

    return {
        "reconstructed_message": reconstructed,
        "metrics": {
            "latency_ms": round(dec_latency, 3)
        }
    }

# TASK 3: MEANING VALIDATION ENDPOINT
@app.post("/validate")
def validate_meaning(payload: ValidateRequest):
    result = validate_reconstruction(payload.original, payload.reconstructed, payload.packet)
    return result

# TASK 4: END-TO-END BENCHMARK EXECUTION ENDPOINT
@app.post("/process-end-to-end")
def process_end_to_end(payload: EncodeRequest):
    enc_res = encode_message(payload)
    dec_res = decode_message(DecodeRequest(packet=enc_res["semantic_packet"]))
    val_res = validate_meaning(ValidateRequest(
        original=payload.message, 
        reconstructed=dec_res["reconstructed_message"],
        packet=enc_res["semantic_packet"]
    ))

    # Log to SQLite
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO benchmark_logs 
        (message_id, mode, original_message, original_size_bytes, packet_size_bytes, 
         compression_ratio_pct, encode_latency_ms, decode_latency_ms, 
         reconstructed_message, validation_status, validation_details)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        payload.message_id,
        payload.mode,
        payload.message,
        enc_res["metrics"]["original_size_bytes"],
        enc_res["metrics"]["compressed_packet_bytes"],
        enc_res["metrics"]["compression_percentage"],
        enc_res["metrics"]["latency_ms"],
        dec_res["metrics"]["latency_ms"],
        dec_res["reconstructed_message"],
        val_res["status"],
        json.dumps(val_res["issues"])
    ))
    conn.commit()
    conn.close()

    return {
        "encode": enc_res,
        "decode": dec_res,
        "validation": val_res
    }