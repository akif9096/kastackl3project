import sys
import os
import sqlite3
import json
import csv
from fastapi.testclient import TestClient

# 1. Add the parent directory (project root) to sys.path so Python can find main.py
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from main import app  

# 2. Initialize the test client (This fixes your NameError!)
client = TestClient(app)

# 3. Define file paths relative to the project root
DB_FILE = "semantic_benchmarks.db"
CSV_FILE = os.path.join(project_root, "data", "semantic_messages.csv")

def load_test_messages():
    """Reads test messages from the CSV file."""
    messages = []
    try:
        with open(CSV_FILE, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                
                msg_id = row.get('message_id', row.get('id', 'UNKNOWN_ID'))
                text = row.get('message', row.get('text', ''))
                
                if text:
                    messages.append({"id": msg_id, "text": text})
        
        print(f"Successfully loaded {len(messages)} messages from {CSV_FILE}")
    except FileNotFoundError:
        print(f"Error: Could not find {CSV_FILE}. Please ensure the file exists.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        sys.exit(1)
        
    return messages

def clear_previous_benchmarks():
    """Clears the database so we only see results from the current run."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Ensure the table exists in case main.py hasn't created it yet
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS benchmark_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT, mode TEXT, original_message TEXT,
            original_size_bytes INTEGER, packet_size_bytes INTEGER,
            compression_ratio_pct REAL, encode_latency_ms REAL,
            decode_latency_ms REAL, reconstructed_message TEXT,
            validation_status TEXT, validation_details TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("DELETE FROM benchmark_logs")
    conn.commit()
    conn.close()

def run_benchmarks():
    print("Starting Semantic Engine Benchmarks...\n")
    
    # Load from CSV
    test_messages = load_test_messages()
    if not test_messages:
        print("No messages found in the CSV. Exiting.")
        return

    clear_previous_benchmarks()

    for mode in ["normal", "low_resource"]:
        print(f"\n--- Processing in {mode.upper()} mode ---")
        for msg in test_messages:
            payload = {
                "message_id": msg["id"],
                "message": msg["text"],
                "mode": mode
            }
            
            response = client.post("/process-end-to-end", json=payload)
            
            if response.status_code == 200:
                data = response.json()
                val_status = data["validation"]["status"]
                print(f"Processed {msg['id']} -> Validation: {val_status.upper()}")
            else:
                print(f"Error processing {msg['id']}: {response.text}")
    
    print("\nBenchmarking completed. Generating metrics report...\n")
    generate_report()

def generate_report():
    """Queries the SQLite DB and prints an aggregated metrics table."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    query = """
    SELECT 
        mode,
        COUNT(*) as total_msgs,
        AVG(original_size_bytes) as avg_orig_size,
        AVG(packet_size_bytes) as avg_packet_size,
        AVG(compression_ratio_pct) as avg_compression,
        AVG(encode_latency_ms) as avg_enc_latency,
        AVG(decode_latency_ms) as avg_dec_latency,
        SUM(CASE WHEN validation_status = 'safe' THEN 1 ELSE 0 END) as safe_count,
        SUM(CASE WHEN validation_status != 'safe' THEN 1 ELSE 0 END) as issue_count
    FROM benchmark_logs
    GROUP BY mode
    """
    
    cursor.execute(query)
    results = cursor.fetchall()
    
    # Print Summary Table
    print("=" * 115)
    print(f"{'Mode':<15} | {'Total':<5} | {'Orig Size (B)':<15} | {'Pkt Size (B)':<15} | {'Comp (%)':<10} | {'Enc Lat (ms)':<13} | {'Dec Lat (ms)':<13} | {'Pass':<5} | {'Fail/Warn':<9}")
    print("-" * 115)
    
    for row in results:
        mode, total, orig_sz, pkt_sz, comp, enc, dec, safe, issues = row
        print(f"{mode:<15} | {total:<5} | {orig_sz:<15.2f} | {pkt_sz:<15.2f} | {comp:<10.2f} | {enc:<13.3f} | {dec:<13.3f} | {safe:<5} | {issues:<9}")
    print("=" * 115)

    # Print Validation Issues
    cursor.execute("SELECT message_id, mode, validation_status, validation_details FROM benchmark_logs WHERE validation_status != 'safe'")
    failed_results = cursor.fetchall()
    
    if failed_results:
        print("\n⚠️  Validation Warnings / Failures Detected:")
        for msg_id, mode, status, details_json in failed_results:
            details = json.loads(details_json)
            print(f" - [{mode.upper()}] {msg_id} ({status}): {', '.join(details)}")
    else:
        print("\n✅ All semantic validations passed successfully across all modes.")
        
    conn.close()

if __name__ == "__main__":
    run_benchmarks()