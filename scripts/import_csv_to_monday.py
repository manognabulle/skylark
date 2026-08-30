"""
One-time setup: create the two monday.com boards and import the CSV data
into them, full-fidelity (all columns from the source files — the browser/MCP
demo trims columns for response-size reasons, this script does not need to).

Usage:
    export MONDAY_API_TOKEN=xxxx
    python scripts/import_csv_to_monday.py \
        --work-orders data/work_orders.json \
        --deals data/deals.json

Idempotent: re-running skips boards that already exist by name, and is safe
to re-run after a partial failure (monday.com item creation is called per
row; failures are logged and skipped rather than aborting the whole run).
"""
import argparse
import json
import os
import sys
import time
import requests

MONDAY_API_URL = "https://api.monday.com/v2"
TOKEN = os.environ.get("MONDAY_API_TOKEN", "")
HEADERS = {"Authorization": TOKEN, "Content-Type": "application/json", "API-Version": "2024-10"}

WORK_ORDERS_BOARD_NAME = "Skylark Work Orders"
DEALS_BOARD_NAME = "Skylark Deals"

# column key -> monday column type. "text" is the safe default; status/date/
# numbers give better UX (colored labels, calendar, sums) inside monday.com
# itself but are not required for the agent, which reads everything as text
# via column_values.text regardless of underlying type.
WORK_ORDER_COLUMNS = {
    "Customer Name Code": "text", "Serial #": "text", "Nature of Work": "status",
    "Last executed month of recurring project": "text", "Execution Status": "status",
    "Data Delivery Date": "date", "Date of PO/LOI": "date", "Document Type": "status",
    "Probable Start Date": "date", "Probable End Date": "date", "BD/KAM Personnel code": "text",
    "Sector": "status", "Type of Work": "text", "Has Skylark Software": "text",
    "Last invoice date": "date", "Latest invoice no": "text", "Amount Excl GST": "numbers",
    "Amount Incl GST": "numbers", "Billed Value Excl GST": "numbers", "Billed Value Incl GST": "numbers",
    "Collected Amount Incl GST": "numbers", "Amount to be billed Excl GST": "numbers",
    "Amount to be billed Incl GST": "numbers", "Amount Receivable": "numbers", "AR Priority": "status",
    "Qty by Ops": "numbers", "Qty as per PO": "text", "Qty billed till date": "numbers",
    "Balance Qty": "text", "Invoice Status": "status", "Expected Billing Month": "text",
    "Actual Billing Month": "text", "Actual Collection Month": "text", "WO Status billed": "status",
    "Collection status": "text", "Collection Date": "date", "Billing Status": "status",
}
DEAL_COLUMNS = {
    "Owner code": "text", "Client Code": "text", "Deal Status": "status", "Close Date (A)": "date",
    "Closure Probability": "status", "Masked Deal value": "numbers", "Tentative Close Date": "date",
    "Deal Stage": "status", "Product deal": "text", "Sector/service": "status", "Created Date": "date",
}


def gql(query, variables=None, _retries=6, _backoff=2.0):
    token = os.environ.get("MONDAY_API_TOKEN", "") or TOKEN
    headers = {"Authorization": token, "Content-Type": "application/json", "API-Version": "2024-10"}
    for attempt in range(1, _retries + 1):
        try:
            r = requests.post(MONDAY_API_URL, json={"query": query, "variables": variables or {}}, headers=headers, timeout=30)
        except Exception as e:
            if attempt == _retries:
                raise
            wait = _backoff ** attempt
            print(f"  … request error ({e}), retrying in {wait:.1f}s (attempt {attempt}/{_retries})", file=sys.stderr)
            time.sleep(wait)
            continue

        if r.status_code in (429, 500, 502, 503, 504):
            if attempt == _retries:
                raise RuntimeError(f"monday.com HTTP {r.status_code} error after {_retries} attempts. Body: {r.text[:300]!r}")
            wait = _backoff ** attempt
            print(f"  … HTTP {r.status_code} response, retrying in {wait:.1f}s (attempt {attempt}/{_retries})", file=sys.stderr)
            time.sleep(wait)
            continue

        # monday.com rate-limits / transient errors sometimes come back as an
        # empty body or non-JSON (e.g. a Cloudflare page) rather than a JSON
        # error object. Retry those with backoff instead of crashing.
        try:
            data = r.json()
        except ValueError:
            if attempt == _retries:
                raise RuntimeError(
                    f"monday.com returned a non-JSON response (status {r.status_code}) "
                    f"after {_retries} attempts. Body: {r.text[:300]!r}"
                )
            wait = _backoff ** attempt
            print(f"  … non-JSON response (status {r.status_code}), retrying in {wait:.1f}s "
                  f"(attempt {attempt}/{_retries})", file=sys.stderr)
            time.sleep(wait)
            continue
        if "errors" in data:
            msg = str(data["errors"])
            # complexity/rate-limit errors are retryable; anything else, fail fast
            if attempt < _retries and ("complexity" in msg.lower() or "rate limit" in msg.lower() or "limit" in msg.lower() or "429" in msg):
                wait = _backoff ** attempt
                print(f"  … rate-limited, retrying in {wait:.1f}s (attempt {attempt}/{_retries})", file=sys.stderr)
                time.sleep(wait)
                continue
            raise RuntimeError(data["errors"])
        return data["data"]



def find_board(name):
    data = gql("query { boards(limit: 200) { id name } }")
    for b in data["boards"]:
        if b["name"].strip().lower() == name.strip().lower():
            return b["id"]
    return None


def create_board(name):
    q = """
    mutation ($name: String!) {
      create_board (board_name: $name, board_kind: public) { id }
    }"""
    return gql(q, {"name": name})["create_board"]["id"]


def get_existing_columns(board_id):
    data = gql("query ($id: [ID!]) { boards(ids: $id) { columns { id title type } } }", {"id": [board_id]})
    return {c["title"]: c for c in data["boards"][0]["columns"]}


def create_column(board_id, title, col_type):
    q = """
    mutation ($board: ID!, $title: String!, $type: ColumnType!) {
      create_column (board_id: $board, title: $title, column_type: $type) { id }
    }"""
    return gql(q, {"board": board_id, "title": title, "type": col_type})["create_column"]["id"]


def ensure_board(name, column_spec):
    bid = find_board(name)
    created = False
    if not bid:
        bid = create_board(name)
        created = True
        print(f"Created board '{name}' -> {bid}")
    else:
        print(f"Found existing board '{name}' -> {bid}")

    existing = get_existing_columns(bid)
    for title, col_type in column_spec.items():
        if title not in existing:
            try:
                create_column(bid, title, col_type)
                print(f"  + column '{title}' ({col_type})")
            except Exception as e:
                print(f"  ! failed to create column '{title}': {e}", file=sys.stderr)
            time.sleep(0.3)  # avoid bursting monday's rate limit across rapid column creates
    return bid, created


def create_item(board_id, name, column_values: dict):
    q = """
    mutation ($board: ID!, $name: String!, $vals: JSON!) {
      create_item (board_id: $board, item_name: $name, column_values: $vals, create_labels_if_missing: true) { id }
    }"""
    return gql(q, {"board": board_id, "name": name, "vals": json.dumps(column_values)})


def value_for_column(col_type, raw_value):
    if raw_value is None:
        return None
    if col_type == "date":
        # monday expects {"date": "YYYY-MM-DD"}; raw_value already ISO from our export
        s = str(raw_value)[:10]
        return {"date": s} if s else None
    if col_type == "numbers":
        return str(raw_value)
    if col_type == "status":
        return {"label": str(raw_value)[:75]}  # monday auto-creates the label if unseen
    return str(raw_value)


def import_records(board_id, records, name_field, column_spec):
    ok, failed = 0, 0
    for i, rec in enumerate(records):
        item_name = str(rec.get(name_field) or f"Row {i+1}")
        col_values = {}
        existing_cols = get_existing_columns(board_id) if i == 0 else existing_cols  # fetch once
        for title, col_type in column_spec.items():
            if title == name_field or title not in rec:
                continue
            col = existing_cols.get(title)
            if not col:
                continue
            v = value_for_column(col_type, rec.get(title))
            if v is not None:
                col_values[col["id"]] = v
        try:
            create_item(board_id, item_name, col_values)
            ok += 1
        except Exception as e:
            failed += 1
            print(f"  ! row {i+1} ('{item_name}') failed: {e}", file=sys.stderr)
        if (i + 1) % 25 == 0:
            print(f"  … {i+1}/{len(records)} processed ({ok} ok, {failed} failed)")
        time.sleep(0.4)  # gentle on monday's rate limits
    print(f"Done: {ok} created, {failed} failed, out of {len(records)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-orders", default="data/work_orders.json")
    ap.add_argument("--deals", default="data/deals.json")
    args = ap.parse_args()

    if not TOKEN:
        print("Set MONDAY_API_TOKEN first.", file=sys.stderr)
        sys.exit(1)

    with open(args.work_orders) as f:
        wo_records = json.load(f)
    with open(args.deals) as f:
        deal_records = json.load(f)

    wo_id, _ = ensure_board(WORK_ORDERS_BOARD_NAME, WORK_ORDER_COLUMNS)
    print(f"Importing {len(wo_records)} work orders…")
    import_records(wo_id, wo_records, "Deal name masked", WORK_ORDER_COLUMNS)

    deal_id, _ = ensure_board(DEALS_BOARD_NAME, DEAL_COLUMNS)
    print(f"Importing {len(deal_records)} deals…")
    import_records(deal_id, deal_records, "Deal Name", DEAL_COLUMNS)

    print()
    print("Set these in your .env / deployment config:")
    print(f"MONDAY_WORK_ORDERS_BOARD_ID={wo_id}")
    print(f"MONDAY_DEALS_BOARD_ID={deal_id}")


if __name__ == "__main__":
    main()
