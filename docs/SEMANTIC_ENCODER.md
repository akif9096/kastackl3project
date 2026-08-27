# Semantic Encoder

## 1. Overview

The **Semantic Encoder** is a software component responsible for extracting essential structured meaning from unstructured natural-language messages and serializing that meaning into a standardized, machine-readable **semantic packet**.

### Semantic Communication Rationale

Traditional data communication systems transmit raw character streams (ASCII, UTF-8 strings). In network-constrained environments—such as low-bandwidth radio channels, high-latency satellite connections, intermittent IoT networks, or high-cost metered cellular links—transmitting full conversational syntax, polite phrasing, filler words, and formatting introduces unnecessary payload overhead.

Semantic communication shifts the focus from transmitting exact syntactic tokens to transmitting the underlying factual intent and entities. By capturing only what actions must be performed, who is involved, where and when events take place, and any constraints or safety concerns, the payload size is minimized while preserving functional meaning.

### Natural-Language Message vs. Semantic Packet

| Attribute | Natural-Language Message | Semantic Packet |
| :--- | :--- | :--- |
| **Format** | Free-form human text (unstructured) | Structured JSON object / dictionary (schema-constrained) |
| **Content** | Full syntax, grammar, idioms, filler tokens | Atomic semantic fields (`act`, `ent`, `neg`, `urg`, `safe_crit`) |
| **Parsing** | Requires human interpretation or complex parsing | Directly consumable by automated decoders and downstream systems |
| **Transmission** | Variable length, large byte footprint | Compact representation optimized for compression and transmission |

---

## 2. System Context

The Semantic Encoder represents **Task 1** within the end-to-end Semantic Communication Engine pipeline:

```text
Natural Language Message
        ↓
   POST /encode
        ↓
  Semantic Encoder (Task 1)
        ↓
  Semantic Packet
        ↓
     Decoder (Task 2)
        ↓
Reconstructed Message
        ↓
Meaning Validation (Task 3)
        ↓
Benchmarking / SQLite (Task 4)
```

### Module Responsibilities

- **`main.py`**: The shared FastAPI entry point that defines request/response schemas (`EncodeRequest`, `DecodeRequest`, `ValidateRequest`), routing endpoints (`/encode`, `/decode`, `/validate`, `/process-end-to-end`), and database logging (`benchmark_logs`).
- **`encoder/encoder.py`**: The isolated implementation module containing the deterministic semantic parsing logic (`encode_message_logic`, `extract_negations`), keyword lookups, regular expression patterns, and entity deduplication algorithms.
- **`tests/test_encoder.py`**: Automated unit and integration test suite asserting schema compliance, evaluation scenario correctness, and endpoint performance.

---

## 3. Encoder Architecture

The execution pipeline inside `encode_message_logic(text: str, mode: str = "normal")` follows a deterministic multi-stage workflow:

```text
Input text
    ↓
Input Validation & Text Normalization
    ↓
Safety and Urgency Detection
    ↓
Negation Clause Extraction & Deduplication
    ↓
Person / Role Entity Extraction
    ↓
Location Entity Extraction
    ↓
Object Entity Extraction
    ↓
Time & Date Entity Extraction
    ↓
Quantity Entity Extraction
    ↓
Action (Verb) Extraction
    ↓
Array Deduplication & Normalization
    ↓
Semantic Packet (JSON / Dict)
```

### Pipeline Stages

1. **Input Validation & Text Normalization**:
   - Validates that the input is a non-empty string.
   - Generates lowercase representations for case-insensitive keyword searches while preserving original text offsets for span extraction.

2. **Safety and Urgency Detection**:
   - Scans against `SAFETY_KEYWORDS` (e.g., `gas`, `smoke`, `fire`, `leak`, `emergency`, `hazard`, `danger`, `toxic`, `unconscious`, `swelling`).
   - If a safety hazard is present, sets `safe_crit = True` and elevates `urg = "high"`.
   - Scans against `URGENCY_KEYWORDS` (e.g., `immediately`, `urgent`, `soon`, `now`, `asap`, `promptly`, `stat`) to set `urg = "high"`.

3. **Negation Clause Extraction & Deduplication**:
   - Matches negative restriction patterns (`do not ...`, `don't ...`, `never ...`, `not ...`, `except ...`, `avoid ...`, `cannot ...`, `stop ...`).
   - Sorts matched spans by length descending and eliminates sub-spans/substring duplicates to yield single, canonical restriction strings.

4. **Entity Extraction (Persons, Locations, Objects)**:
   - **Persons/Roles**: Longest-match span scanning across known titles and roles (`Building Security Desk`, `Dr. Shah`, `Rahul`, `Riya`, `Arjun`, etc.).
   - **Locations**: Regex matching for named locations, gates, rooms, platforms, cities, and common facilities (`Gate 2`, `Room 304`, `Pune`, `Mumbai`, `lab`, `kitchen`, `office`).
   - **Objects**: Target object matching across physical items, documents, and containers (`project notebook`, `customer file`, `packages`, `report`, `file`, `sensor`, `container`).

5. **Time & Quantity Extraction**:
   - **Times/Dates**: Matches 12-hour/24-hour time expressions (`4:30 PM`, `5 PM`, `11 AM`, `14:30`) and relative day references (`today`, `tomorrow`, `evening`). Excludes bare numbers to avoid misclassifications.
   - **Quantities**: Extracts numeric counts, measurements, and currency expressions (`3 packages`, `500 ml`, `₹750`, `6 small batteries`, `24 masks`), excluding numbers bound to locations or times.

6. **Action (Verb) Extraction**:
   - Extracts explicit functional verbs (`send`, `deliver`, `meet`, `buy`, `upload`, `lock`, `return`, `leave`, `alert`, `pack`, `open`, `bring`).

7. **Deduplication & Packet Serialization**:
   - Deduplicates all arrays (`act`, `neg`, `ent.per`, `ent.loc`, `ent.time`, `ent.qty`, `ent.obj`) and constructs the canonical dictionary.

---

## 4. Implementation Approach

The Semantic Encoder is built using **deterministic, rule-based Natural Language Processing (NLP)** implemented in Python. It does **not** rely on large language models (LLMs) or generative AI APIs during execution.

### Techniques Employed

- **Regular Expressions (`re`)**: Compiled patterns for time formats, quantity units, negation boundaries, and location identifiers.
- **Ordered Dictionaries & Keyword Sets**: Hash-based lookup tables (`SAFETY_KEYWORDS`, `URGENCY_KEYWORDS`, `KNOWN_PERSONS`, `COMMON_OBJECTS`, `ACTION_VERBS`) sorted by span length to prioritize specific composite phrases over individual words.
- **Span-Based Non-Overlapping Selection**: Interval checking to prevent multi-word names or locations from being fragmented into partial substring matches.
- **Dynamic Optional NLP Fallback**: Uses `importlib.util.find_spec("spacy")` to optionally enhance POS-tagging if spaCy is present locally, while maintaining complete functionality when spaCy is absent.

### Engineering Characteristics

- **Fully Offline**: Zero runtime dependence on external network calls or cloud services.
- **Deterministic & Reproducible**: Identical input text reliably yields identical semantic packets.
- **Zero-Hallucination**: Fields for unmentioned entities remain empty arrays (`[]`); the encoder does not infer or fabricate unstated data.
- **Low Computational Overhead**: Sub-millisecond execution times suitable for constrained host devices and real-time processing pipelines.

---

## 5. Semantic Packet Schema

Every invocation of `encode_message_logic()` produces a dictionary adhering to the following JSON schema:

```json
{
  "urg": "normal",
  "safe_crit": false,
  "neg": [],
  "ent": {
    "per": [],
    "loc": [],
    "time": [],
    "qty": [],
    "obj": []
  },
  "act": []
}
```

### Field Definitions

| Field Path | Type | Permitted Values | Description |
| :--- | :--- | :--- | :--- |
| `urg` | `string` | `"normal"`, `"high"` | Operational urgency level of the message. |
| `safe_crit` | `boolean` | `true`, `false` | Indicates whether the message contains safety-critical hazard warnings. |
| `neg` | `array[string]` | List of strings | Canonical negation or restriction clauses extracted from the message. |
| `ent.per` | `array[string]` | List of strings | Extracted person names, titles, or organizational roles. |
| `ent.loc` | `array[string]` | List of strings | Extracted geographic or facility locations, rooms, or gates. |
| `ent.time` | `array[string]` | List of strings | Extracted timestamps, deadlines, or temporal references. |
| `ent.qty` | `array[string]` | List of strings | Extracted counts, physical quantities, measurements, or currency amounts. |
| `ent.obj` | `array[string]` | List of strings | Extracted items, artifacts, files, or devices referenced in the message. |
| `act` | `array[string]` | List of strings | Extracted base actions or operations to be executed. |

---

## 6. HTTP API Specification

### Endpoint: `POST /encode`

Receives a natural-language payload and returns the semantic packet along with transmission and encoding metrics.

#### Request Schema (`EncodeRequest`)

```json
{
  "message_id": "SEM_002",
  "message": "Meet Riya outside Gate 2 at 4:30 PM today.",
  "mode": "normal"
}
```

#### Response Schema

```json
{
  "message_id": "SEM_002",
  "mode": "normal",
  "semantic_packet": {
    "urg": "normal",
    "safe_crit": false,
    "neg": [],
    "ent": {
      "per": ["Riya"],
      "loc": ["Gate 2"],
      "time": ["4:30 PM", "today"],
      "qty": [],
      "obj": []
    },
    "act": ["meet"]
  },
  "metrics": {
    "original_size_bytes": 43,
    "raw_packet_bytes": 174,
    "compressed_packet_bytes": 138,
    "compression_percentage": -220.93,
    "latency_ms": 0.312
  }
}
```

#### Metric Definitions

- `original_size_bytes`: Byte length of the raw UTF-8 input string.
- `raw_packet_bytes`: Byte length of the serialized JSON semantic packet.
- `compressed_packet_bytes`: Byte length of the zlib-compressed JSON packet payload (used for transmission).
- `compression_percentage`: Calculated bandwidth delta: `round((1 - (compressed_bytes / original_bytes)) * 100, 2)`.
- `latency_ms`: Execution duration of the encoding process measured via high-resolution monotonic timer (`time.perf_counter()`).

---

## 7. Verification & Test Suite

The test suite in [`tests/test_encoder.py`](file:///d:/Kastackl3/kastackl3project/tests/test_encoder.py) validates the encoder across baseline functional requirements, edge cases, and dataset benchmarks.

### Execution Command

```bash
python -m pytest tests/test_encoder.py -v
```

### Verified Test Cases

1. **Simple Action (`test_1_simple_action`)**:
   - Input: `"Send the report to Rahul."`
   - Verified: `act: ["send"]`, `per: ["Rahul"]`, `obj: ["report"]`, `safe_crit: False`.

2. **Time, Location & Quantity (`test_2_time_location_quantity`)**:
   - Input: `"Deliver 3 packages to Gate 2 at 5 PM."`
   - Verified: `act: ["deliver"]`, `loc: ["Gate 2"]`, `time: ["5 PM"]`, `qty: ["3 packages"]`, `obj: ["packages"]`.

3. **Critical Negation (`test_3_negation`)**:
   - Input: `"Do not send the file to Rahul."`
   - Verified: `neg: ["Do not send the file to Rahul"]`, `act: ["send"]`, `per: ["Rahul"]`, `obj: ["file"]`.

4. **Negation Deduplication (`test_no_duplicate_overlapping_negations`)**:
   - Verified: Single canonical entry returned without substring overlap.

5. **Incomplete Message / Zero Hallucination (`test_4_incomplete_message`)**:
   - Input: `"Send the documents."`
   - Verified: `act: ["send"]`, `obj: ["documents"]`, `per: []`, `loc: []`, `time: []`, `qty: []`.

6. **Safety-Sensitive Emergency (`test_5_safety_sensitive`, `test_sem_007_hazard_gas_warning`)**:
   - Input: `"The kitchen smells like gas; leave the room and alert the building security desk."`
   - Verified: `safe_crit: True`, `urg: "high"`, `loc: ["kitchen", "room"]`, `per: ["Building Security Desk"]`.

7. **Dataset Benchmarks**:
   - Validated across all 60 benchmark entries in [`data/semantic_messages.csv`](file:///d:/Kastackl3/kastackl3project/data/semantic_messages.csv).

8. **API Integration (`test_api_encode_endpoint_normal_mode`, `test_api_encode_endpoint_low_resource_mode`)**:
   - Validated HTTP 200 responses, schema structure, and metric calculations via FastAPI `TestClient`.
