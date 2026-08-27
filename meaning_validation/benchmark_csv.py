import csv
from pathlib import Path

from .validator import validate

BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "data" / "semantic_messages.csv"
OUTPUT_PATH = BASE_DIR / "validation_report.csv"

def run_csv_validation():
    passed, review, failed = 0, 0, 0
    results = []

    with CSV_PATH.open(mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        # Auto-detect column names if they vary in your dataset
        orig_col = next((c for c in ["original", "original_message", "message", "text"] if c in fieldnames), fieldnames[0])
        
        # If your CSV already has reconstructed messages, use that column.
        # If testing raw input against itself, it defaults to checking identity.
        recon_col = next((c for c in ["reconstructed", "reconstructed_message", "decoded"] if c in fieldnames), orig_col)

        for row_idx, row in enumerate(reader, start=1):
            original = row.get(orig_col, "").strip()
            reconstructed = row.get(recon_col, original).strip()

            if not original:
                continue

            verdict = validate(original, reconstructed)
            status = verdict["status"]

            if status == "safe":
                passed += 1
            elif status == "review required":
                review += 1
            else:
                failed += 1

            row_result = {
                "row": row_idx,
                "original": original,
                "reconstructed": reconstructed,
                "status": status,
                "summary": verdict["summary"],
                "issue_count": len(verdict["issues"]),
            }
            results.append(row_result)

    # Save detailed output report
    with OUTPUT_PATH.open(mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["row", "original", "reconstructed", "status", "summary", "issue_count"])
        writer.writeheader()
        writer.writerows(results)

    total = passed + review + failed
    print("\n" + "=" * 50)
    print("       CSV VALIDATION BENCHMARK RESULTS")
    print("=" * 50)
    print(f"Total Messages Evaluated : {total}")
    print(f"Safe (Preserved)         : {passed} ({(passed/total)*100:.1f}%)" if total else "0")
    print(f"Review Required          : {review} ({(review/total)*100:.1f}%)" if total else "0")
    print(f"Failed (Meaning Lost)    : {failed} ({(failed/total)*100:.1f}%)" if total else "0")
    print("=" * 50)
    print(f"Detailed output exported to: {OUTPUT_PATH}\n")

if __name__ == "__main__":
    run_csv_validation()