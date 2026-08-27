import csv
import json
import os
import sqlite3
import time
import zlib
from app.encoder import encode_message_logic

DB_NAME = "semantic_benchmarks.db"
CSV_PATH = os.path.join("data", "semantic_messages.csv")
TOTAL_RUNS = 120


def init_db():
    """Initialize the SQLite database schema for persisting benchmark data."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS benchmark_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            mode TEXT NOT NULL,
            orig_bytes REAL NOT NULL,
            packet_bytes REAL NOT NULL,
            compression_pct REAL NOT NULL,
            encode_lat_ms REAL NOT NULL,
            decode_lat_ms REAL NOT NULL,
            safe_pass_rate REAL NOT NULL
        )
    """
    )
    conn.commit()
    conn.close()


def load_dataset():
    """Load test messages from the CSV data file."""
    messages = []
    if not os.path.exists(CSV_PATH):
        # Fallback to current directory if data/ folder path isn't present
        filepath = "semantic_messages.csv"
    else:
        filepath = CSV_PATH

    with open(filepath, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            msg = list(row.values())[1] if len(row) > 1 else list(row.values())[0]
            if msg and msg.strip():
                messages.append(msg.strip())
    return messages


def run_benchmark(mode: str, messages: list):
    """Execute evaluation loop for a given operational mode."""
    total_orig_bytes = 0
    total_packet_bytes = 0
    total_comp_pct = 0.0
    total_enc_lat_ms = 0.0
    total_dec_lat_ms = 0.0
    safe_passes = 0
    count = 0

    for i in range(TOTAL_RUNS):
        msg = messages[i % len(messages)]
        orig_bytes = len(msg.encode("utf-8"))

        # Measure Encoding Latency
        t0 = time.perf_counter()
        packet = encode_message_logic(msg, mode=mode)
        t1 = time.perf_counter()
        enc_lat = (t1 - t0) * 1000.0

        # Serialized & Compressed Packet Size
        json_bytes = json.dumps(packet).encode("utf-8")
        compressed = zlib.compress(json_bytes)
        packet_bytes = len(compressed)

        comp_pct = (
            ((orig_bytes - packet_bytes) / orig_bytes) * 100.0 if orig_bytes > 0 else 0.0
        )

        # Measure Decoding/Parsing Latency
        t2 = time.perf_counter()
        parsed_packet = json.loads(json.dumps(packet))
        t3 = time.perf_counter()
        dec_lat = (t3 - t2) * 1000.0

        # Safety / Structure Assertion Check
        is_safe = isinstance(parsed_packet, dict) and "act" in parsed_packet
        if is_safe:
            safe_passes += 1

        total_orig_bytes += orig_bytes
        total_packet_bytes += packet_bytes
        total_comp_pct += comp_pct
        total_enc_lat_ms += enc_lat
        total_dec_lat_ms += dec_lat
        count += 1

    avg_orig = total_orig_bytes / count
    avg_packet = total_packet_bytes / count
    avg_comp = total_comp_pct / count
    avg_enc_lat = total_enc_lat_ms / count
    avg_dec_lat = total_dec_lat_ms / count
    safe_rate = (safe_passes / count) * 100.0

    # Persist metrics into SQLite
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO benchmark_runs 
        (mode, orig_bytes, packet_bytes, compression_pct, encode_lat_ms, decode_lat_ms, safe_pass_rate)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (mode, avg_orig, avg_packet, avg_comp, avg_enc_lat, avg_dec_lat, safe_rate),
    )
    conn.commit()
    conn.close()

    return {
        "mode": mode,
        "avg_orig_bytes": avg_orig,
        "avg_packet_bytes": avg_packet,
        "avg_compression_pct": avg_comp,
        "avg_encode_lat_ms": avg_enc_lat,
        "avg_decode_lat_ms": avg_dec_lat,
        "safe_pass_rate": safe_rate,
    }


def main():
    init_db()
    messages = load_dataset()

    print("=" * 75)
    print(" " * 20 + "EXECUTIVE BENCHMARK SUITE")
    print("=" * 75)

    results = []
    for mode in ["low_resource", "normal"]:
        res = run_benchmark(mode, messages)
        results.append(res)

    print(
        f"{'mode':<15} {'avg_orig':<12} {'avg_packet':<12} {'comp_%':<12} {'enc_lat(ms)':<14} {'dec_lat(ms)':<14} {'safe_rate':<10}"
    )
    print("-" * 75)
    for r in results:
        print(
            f"{r['mode']:<15} {r['avg_orig_bytes']:<12.2f} {r['avg_packet_bytes']:<12.2f} "
            f"{r['avg_compression_pct']:<12.2f} {r['avg_encode_lat_ms']:<14.4f} "
            f"{r['avg_decode_lat_ms']:<14.4f} {r['safe_pass_rate']:<10.1f}%"
        )
    print("=" * 75)
    print(f"Metrics successfully persisted to '{DB_NAME}'.")


if __name__ == "__main__":
    main()