"""
Main pipeline - processes all deletion requests and produces output.csv.
"""
import csv
import json
import os
import sys
import tempfile
import shutil
import time
import argparse
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from code.agent import DeletionAuditAgent
from code.usage import UsageLogger
from code.validator import validate_output


def load_requests(filepath: str) -> List[dict]:
    """Load deletion requests from CSV."""
    requests = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            requests.append(dict(row))
    return requests


def write_output_atomic(rows: List[dict], output_path: str):
    """Write output.csv atomically - write to temp file then move."""
    # Sort rows by case_id numerically
    rows.sort(key=lambda r: int(r["case_id"].replace("case_", "")))

    temp_fd, temp_path = tempfile.mkstemp(suffix=".csv", dir=os.path.dirname(output_path) or ".")
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        # Atomic replace
        if os.path.exists(output_path):
            os.replace(temp_path, output_path)
        else:
            shutil.move(temp_path, output_path)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def main():
    parser = argparse.ArgumentParser(description="Ghost Data Still Exists - Deletion Audit Agent")
    parser.add_argument("--input", default="dataset/deletion_requests.csv", help="Input deletion requests CSV")
    parser.add_argument("--out", default="dataset/output.csv", help="Output CSV path")
    parser.add_argument("--dataset-dir", default="dataset", help="Dataset directory")
    parser.add_argument("--concurrency", type=int, default=5, help="Number of concurrent LLM calls")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of cases to process (0=all)")
    parser.add_argument("--sample-only", action="store_true", help="Process only sample cases")
    args = parser.parse_args()

    # Resolve paths relative to repo root
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dataset_dir = os.path.join(repo_root, args.dataset_dir)
    input_path = os.path.join(repo_root, args.input)
    output_path = os.path.join(repo_root, args.out)

    print(f"Dataset dir: {dataset_dir}")
    print(f"Input: {input_path}")
    print(f"Output: {output_path}")

    # Initialize
    usage = UsageLogger()
    agent = DeletionAuditAgent(dataset_dir, usage)

    # Load requests
    requests = load_requests(input_path)
    print(f"Loaded {len(requests)} deletion requests")

    if args.sample_only:
        sample_path = os.path.join(dataset_dir, "sample_deletion_requests.csv")
        requests = load_requests(sample_path)
        print(f"Using {len(requests)} sample requests")

    if args.limit > 0:
        requests = requests[:args.limit]
        print(f"Limited to {len(requests)} requests")

    # Process cases
    results = []
    start_time = time.time()

    for i, case in enumerate(requests):
        try:
            result = agent.process_case(case)
            results.append(result)
            if (i + 1) % 10 == 0 or (i + 1) == len(requests):
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                print(f"  Processed {i+1}/{len(requests)} cases ({rate:.1f} cases/sec)")
        except Exception as e:
            print(f"  ERROR processing {case['case_id']}: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "case_id": case["case_id"],
                "deletion_status": "INCOMPLETE",
                "steps_json": "[]",
            })

    # Write output atomically
    write_output_atomic(results, output_path)
    print(f"\nWrote {len(results)} results to {output_path}")

    # Validate
    errors = validate_output(output_path, expected_count=len(requests))
    if errors:
        print(f"\nValidation found {len(errors)} errors:")
        for err in errors[:20]:
            print(f"  - {err}")
    else:
        print("\nOutput validation: PASSED")

    # Save usage report
    elapsed = time.time() - start_time
    summary = usage.get_summary()
    print(f"\nUsage summary:")
    print(f"  Total calls: {summary['total_calls']}")
    print(f"  Total tokens: {summary['total_tokens']}")
    print(f"  Total cost: ${summary['total_cost']:.4f}")
    print(f"  Elapsed: {elapsed:.1f}s")

    usage.save_report(os.path.join(repo_root, "evaluation", "usage_data.json"))


if __name__ == "__main__":
    main()
