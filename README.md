# KastackL3Project
# 🛰️ End-to-End Semantic Communication System

An intelligent, bandwidth-efficient semantic communication pipeline designed to encode, compress, transmit, reconstruct, and autonomously validate natural language messages with zero critical semantic loss.

---

## 📌 Architecture Overview

Traditional communication pipelines optimize for bit-level fidelity, which wastes bandwidth on syntactic fluff. This system operates at the **Semantic Level**, transmitting compact semantic representations and reconstructing natural language at the receiver while enforcing a strict **Meaning Validation Gate** and **Automated Benchmarking Suite**.

```text
[ Raw Message (data/semantic_messages.csv) ]
                                            │
                                            ▼
                       ┌──────────────────────────────────────────┐
                       │        1. Semantic Encoder (app/)        │
                       │     (Logic: encode_message_logic)        │
                       │     ── Measures Encode Latency (ms)      │
                       └──────────────────────────────────────────┘
                                            │
                                            ▼
                       ┌──────────────────────────────────────────┐
                       │    2. Payload Compression & Channel      │
                       │     ── JSON Serialization                │
                       │     ── zlib.compress() Compression       │
                       │     ── Calculates Packet Size & Comp %   │
                       └──────────────────────────────────────────┘
                                            │
                                            ▼
                       ┌──────────────────────────────────────────┐
                       │     3. Decoding & Schema Parsing         │
                       │     ── Measures Parsing Latency (ms)     │
                       │     ── Structural/Safety Assertion Check │
                       └──────────────────────────────────────────┘
                                            │
                                            ▼
                       ┌──────────────────────────────────────────┐
                       │ 4. Meaning Validation (Post-Decode Gate) │
                       │    (meaning_validation/validator.py)     │
                       │    ── 6-Dimension NLP Semantic Check     │
                       └──────────────────────────────────────────┘
                                            │
                                            ▼
                       ┌──────────────────────────────────────────┐
                       │   5. Benchmarking & Persistence Suite    │
                       │             (benchmarking.py)            │
                       │    ── Aggregates Modes (low_res/normal)  │
                       │    ── Calculates Averages & Pass Rates   │
                       │    ── Persists to SQLite DB              │
                       │       (semantic_benchmarks.db)           │
                       └──────────────────────────────────────────┘
