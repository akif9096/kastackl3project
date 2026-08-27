import csv
import io
import json
import sqlite3
import time
import zlib
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.encoder import encode_message_logic
from decode.decoder import advanced_decode_packet
from meaning_validation.validator import validate

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "semantic_benchmarks.db"
app = FastAPI(title="Semantic Communication Engine", version="1.0.0")


def init_db() -> None:
    with sqlite3.connect(DB_FILE) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS benchmark_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, message_id TEXT, mode TEXT,
                original_message TEXT, original_size_bytes INTEGER, packet_size_bytes INTEGER,
                compression_ratio_pct REAL, encode_latency_ms REAL, decode_latency_ms REAL,
                reconstructed_message TEXT, validation_status TEXT, validation_details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )"""
        )


init_db()


class EncodeRequest(BaseModel):
    message_id: Optional[str] = "CUSTOM"
    message: str = Field(min_length=1)
    mode: str = "normal"


class DecodeRequest(BaseModel):
    packet: Dict[str, Any]


class ValidateRequest(BaseModel):
    original: str
    reconstructed: str
    packet: Optional[Dict[str, Any]] = None


def _mode(value: Optional[str]) -> str:
    return "low_resource" if (value or "normal").lower() == "low_resource" else "normal"


def _encode(payload: EncodeRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    selected_mode = _mode(payload.mode)
    packet = encode_message_logic(payload.message, selected_mode)
    raw = json.dumps(packet, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    original_size = len(payload.message.encode("utf-8"))
    compressed_size = len(zlib.compress(raw))
    return {
        "message_id": payload.message_id,
        "mode": selected_mode,
        "semantic_packet": packet,
        "metrics": {
            "original_size_bytes": original_size,
            "raw_packet_bytes": len(raw),
            "compressed_packet_bytes": compressed_size,
            "compression_percentage": round((1 - compressed_size / original_size) * 100, 2),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        },
    }


def _decode(packet: Dict[str, Any]) -> Dict[str, Any]:
    started = time.perf_counter()
    return {
        "reconstructed_message": advanced_decode_packet(packet),
        "metrics": {"latency_ms": round((time.perf_counter() - started) * 1000, 3)},
    }


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "encoder": "app.encoder", "decoder": "decode.decoder", "validator": "meaning_validation.validator"}


@app.get("/", response_class=HTMLResponse)
def gui() -> str:
    return GUI_HTML.replace("</body>", CSV_GUI_HTML + "</body>")


CSV_GUI_HTML = r'''<div class="panel wide"><h2>Batch CSV relay</h2><div class="controls"><input id="csvFile" type="file" accept=".csv"><button id="csvRun">Process CSV</button></div><div id="csvSummary" class="status">Upload a CSV with a message, original, or text column.</div><div id="csvResults" class="csv-results"></div></div><script>
document.getElementById('csvRun').onclick=async()=>{const file=document.getElementById('csvFile').files[0];const summary=document.getElementById('csvSummary');if(!file){summary.textContent='Choose a CSV file first.';return}const form=new FormData();form.append('file',file);form.append('mode',document.getElementById('mode').value);summary.textContent='Processing CSV...';try{const response=await fetch('/process-csv',{method:'POST',body:form});const data=await response.json();if(data.error){summary.textContent=data.error;return}summary.textContent=data.filename+' - '+data.total+' messages: '+data.counts.safe+' safe, '+data.counts['review required']+' review, '+data.counts.failed+' failed';document.getElementById('csvResults').innerHTML='<table><thead><tr><th>Row</th><th>Status</th><th>Compression</th><th>Reconstructed message</th></tr></thead><tbody>'+data.results.map(row=>'<tr><td>'+row.row+'</td><td>'+row.status+'</td><td>'+row.compression_percentage+'%</td><td>'+row.reconstructed_message+'</td></tr>').join('')+'</tbody></table>'}catch(error){summary.textContent='Upload failed: '+error.message}};
</script>'''


@app.post("/encode")
def encode_message(payload: EncodeRequest) -> Dict[str, Any]:
    return _encode(payload)


@app.post("/decode")
def decode_message(payload: DecodeRequest) -> Dict[str, Any]:
    return _decode(payload.packet)


@app.post("/validate")
def validate_meaning(payload: ValidateRequest) -> Dict[str, Any]:
    return validate(payload.original, payload.reconstructed, packet=payload.packet)


@app.post("/process-end-to-end")
def process_end_to_end(payload: EncodeRequest) -> Dict[str, Any]:
    encoded = _encode(payload)
    decoded = _decode(encoded["semantic_packet"])
    verdict = validate(payload.message, decoded["reconstructed_message"], encoded["semantic_packet"])
    benchmark = {
        "encode_latency_ms": encoded["metrics"]["latency_ms"],
        "decode_latency_ms": decoded["metrics"]["latency_ms"],
        "compression_percentage": encoded["metrics"]["compression_percentage"],
        "original_size_bytes": encoded["metrics"]["original_size_bytes"],
        "packet_size_bytes": encoded["metrics"]["compressed_packet_bytes"],
    }
    with sqlite3.connect(DB_FILE) as connection:
        connection.execute(
            """INSERT INTO benchmark_logs
            (message_id, mode, original_message, original_size_bytes, packet_size_bytes,
             compression_ratio_pct, encode_latency_ms, decode_latency_ms,
             reconstructed_message, validation_status, validation_details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (payload.message_id, encoded["mode"], payload.message,
             benchmark["original_size_bytes"], benchmark["packet_size_bytes"],
             benchmark["compression_percentage"], benchmark["encode_latency_ms"],
             benchmark["decode_latency_ms"], decoded["reconstructed_message"],
             verdict["status"], json.dumps(verdict["issues"])),
        )
    return {"encode": encoded, "decode": decoded, "validation": verdict, "benchmark": benchmark}


@app.post("/process-csv")
async def process_csv(file: UploadFile = File(...), mode: str = Form("normal")) -> Dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return {"error": "Please upload a CSV file.", "results": []}
    content = await file.read()
    try:
        rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error):
        return {"error": "The CSV must be UTF-8 encoded and readable.", "results": []}
    if not rows:
        return {"error": "The CSV has no data rows.", "results": []}
    columns = list(rows[0])
    message_column = next((name for name in ("message", "original", "original_message", "text") if name in columns), None)
    if message_column is None:
        return {"error": "CSV needs a message, original, original_message, or text column.", "results": []}
    results = []
    for row_number, row in enumerate(rows, start=2):
        message = (row.get(message_column) or "").strip()
        if not message:
            continue
        payload = EncodeRequest(message_id=row.get("message_id") or f"CSV-{row_number}", message=message, mode=mode)
        outcome = process_end_to_end(payload)
        results.append({"row": row_number, "message": message, "status": outcome["validation"]["status"],
                        "compression_percentage": outcome["benchmark"]["compression_percentage"],
                        "encode_latency_ms": outcome["benchmark"]["encode_latency_ms"],
                        "decode_latency_ms": outcome["benchmark"]["decode_latency_ms"],
                        "reconstructed_message": outcome["decode"]["reconstructed_message"]})
    counts = {status: sum(result["status"] == status for result in results) for status in ("safe", "review required", "failed")}
    return {"filename": file.filename, "mode": _mode(mode), "total": len(results), "counts": counts, "results": results}


GUI_HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Semantic Relay</title><style>
:root{font-family:Georgia,serif;color:#18312f;background:#edf3ee;--ink:#18312f;--mint:#b9e4cf;--coral:#d66b55;--cream:#fffdf5}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 85% 8%,#f6c987 0 12%,transparent 33%),linear-gradient(135deg,#edf3ee,#dce9e1)}main{max-width:1180px;margin:auto;padding:34px 22px 60px}header{display:flex;justify-content:space-between;gap:20px;align-items:end;margin-bottom:28px}h1{font-size:clamp(2.4rem,6vw,5.6rem);line-height:.9;margin:0;font-weight:500}header p{max-width:310px;margin:0;font:15px/1.5 Arial,sans-serif}.eyebrow{font:12px Arial,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:#b14c3a;margin-bottom:12px}.workspace{display:grid;grid-template-columns:1fr 1fr;gap:18px}.panel{background:var(--cream);border:1px solid #c5d5ca;padding:22px;box-shadow:7px 7px 0 #c7dace}.panel h2{margin:0 0 14px;font-size:24px;font-weight:500}.controls{display:flex;gap:10px;margin:14px 0}select,button,textarea,input{font:15px Arial,sans-serif}select,textarea,input{border:1px solid #afc5b8;background:#fff;padding:11px}select{width:170px}textarea{width:100%;min-height:158px;resize:vertical;line-height:1.45}button{border:0;background:var(--ink);color:#fff;padding:12px 18px;cursor:pointer}button:hover{background:var(--coral)}.output{min-height:158px;background:#e8f1e9;padding:15px;font:14px/1.55 Consolas,monospace;white-space:pre-wrap;overflow:auto}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:18px}.metric{background:#18312f;color:#fff;padding:12px 10px}.metric b{display:block;font:21px Georgia,serif;color:var(--mint)}.metric span{font:10px Arial,sans-serif;text-transform:uppercase;letter-spacing:.08em}.status{margin-top:16px;padding:12px 14px;font:700 14px Arial,sans-serif;border-left:5px solid var(--coral);background:#f7dfd5}.status.safe{border-color:#3d9470;background:#d9f0e1}.status.review{border-color:#d69735;background:#f8ebc9}.wide{grid-column:1/-1}.samples{display:flex;gap:8px;flex-wrap:wrap}.samples button{background:#dbe8de;color:var(--ink);font-size:12px;padding:8px 10px}.hint{font:12px Arial,sans-serif;color:#536b62;margin:8px 0}.csv-results{margin-top:14px;max-height:330px;overflow:auto;font:12px Arial,sans-serif}.csv-results table{width:100%;border-collapse:collapse}.csv-results th,.csv-results td{padding:8px;text-align:left;border-bottom:1px solid #c5d5ca}.csv-results th{color:#b14c3a}@media(max-width:760px){header{display:block}header p{margin-top:18px}.workspace{grid-template-columns:1fr}.wide{grid-column:auto}.metrics{grid-template-columns:repeat(2,1fr)}main{padding:24px 14px 40px}}
+</style></head><body><main><header><div><div class="eyebrow">Offline semantic communication</div><h1>Semantic<br>Relay</h1></div><p>Transmit the meaning that matters. Inspect the packet, reconstruction, validation verdict, and bandwidth cost in one place.</p></header><section class="workspace"><div class="panel"><h2>Message in</h2><textarea id="message">Meet Riya outside Gate 2 at 4:30 PM today.</textarea><div class="samples"><button data-message="Send the report to Rahul.">Simple action</button><button data-message="Deliver 3 packages to Gate 2 at 5 PM.">Time + quantity</button><button data-message="Do not upload the customer file; send only the anonymized summary.">Negation</button><button data-message="The kitchen smells like gas; leave the room and alert the building security desk.">Safety</button></div><div class="controls"><select id="mode"><option value="normal">Normal mode</option><option value="low_resource">Low-resource mode</option></select><button id="run">Encode and decode</button></div><p class="hint">Runs locally without an external AI API.</p></div><div class="panel"><h2>Reconstructed meaning</h2><div class="output" id="reconstructed">Run a message to see the receiver output.</div><div id="status" class="status">Waiting for a message</div><div class="metrics"><div class="metric"><b id="compression">-</b><span>compression</span></div><div class="metric"><b id="packet">-</b><span>packet bytes</span></div><div class="metric"><b id="encodeMs">-</b><span>encode ms</span></div><div class="metric"><b id="decodeMs">-</b><span>decode ms</span></div></div></div><div class="panel wide"><h2>Semantic packet</h2><div class="output" id="packetOutput">The structured packet will appear here.</div></div></section></main><script>
const $=id=>document.getElementById(id);document.querySelectorAll('[data-message]').forEach(b=>b.onclick=()=>{$('message').value=b.dataset.message});async function run(){const message=$('message').value.trim();if(!message){$('status').textContent='Enter a message first.';return}$('run').disabled=true;$('status').textContent='Processing...';try{const r=await fetch('/process-end-to-end',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message_id:'GUI',message,mode:$('mode').value})});const d=await r.json();$('reconstructed').textContent=d.decode.reconstructed_message;$('packetOutput').textContent=JSON.stringify(d.encode.semantic_packet,null,2);$('compression').textContent=d.benchmark.compression_percentage+'%';$('packet').textContent=d.benchmark.packet_size_bytes;$('encodeMs').textContent=d.benchmark.encode_latency_ms;$('decodeMs').textContent=d.benchmark.decode_latency_ms;const s=d.validation.status;$('status').textContent=s.toUpperCase()+' - '+d.validation.summary;$('status').className='status '+(s==='safe'?'safe':s==='review required'?'review':'')}catch(e){$('status').textContent='Request failed: '+e.message}finally{$('run').disabled=false}}$('run').onclick=run;</script></body></html>'''
