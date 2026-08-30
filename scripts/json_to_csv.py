"""
Convert source JSON data (data/work_orders.json and data/deals.json)
to CSV format (data/work_orders.csv and data/deals.csv).
"""
import json
import os
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

def convert_json_to_csv(json_path: Path, csv_path: Path):
    if not json_path.exists():
        print(f"Error: {json_path} does not exist.")
        return
    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    
    df = pd.DataFrame.from_records(records)
    df.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"Successfully generated {csv_path.name} ({len(df)} rows, {len(df.columns)} columns)")

def main():
    wo_json = DATA_DIR / "work_orders.json"
    wo_csv = DATA_DIR / "work_orders.csv"
    deals_json = DATA_DIR / "deals.json"
    deals_csv = DATA_DIR / "deals.csv"

    print("Generating CSV datasets from JSON source files...")
    convert_json_to_csv(wo_json, wo_csv)
    convert_json_to_csv(deals_json, deals_csv)
    print("CSV generation complete.")

if __name__ == "__main__":
    main()
