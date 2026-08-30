"""
Offline mock data provider. Loads source JSON datasets directly
so the application can run in offline mode without requiring live
monday.com API credentials.
"""
import json
from pathlib import Path

# Paths to data source files relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

_MOCK_BOARDS = {
    "Skylark Work Orders": "mock_work_orders_5030972709",
    "Skylark Deals": "mock_deals_5030972904",
}


def load_mock_work_orders() -> list[dict]:
    path = DATA_DIR / "work_orders.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        raw_records = json.load(f)
    items = []
    for idx, rec in enumerate(raw_records):
        item = {
            "id": str(idx + 1000),
            "name": str(rec.get("Deal name masked") or f"Work Order {idx + 1}"),
        }
        item.update(rec)
        items.append(item)
    return items


def load_mock_deals() -> list[dict]:
    path = DATA_DIR / "deals.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        raw_records = json.load(f)
    items = []
    for idx, rec in enumerate(raw_records):
        item = {
            "id": str(idx + 2000),
            "name": str(rec.get("Deal Name") or f"Deal {idx + 1}"),
        }
        item.update(rec)
        items.append(item)
    return items


def get_mock_items_for_board(board_id: str) -> list[dict]:
    # Check if board_id matches work orders or deals (mock or numeric)
    bid = str(board_id).strip()
    if "work_orders" in bid.lower() or "5030972709" in bid:
        return load_mock_work_orders()
    if "deals" in bid.lower() or "5030972904" in bid:
        return load_mock_deals()
    # Default fallback: try work orders first, then deals
    wo = load_mock_work_orders()
    return wo if wo else load_mock_deals()


def get_mock_boards() -> list[dict]:
    return [
        {"id": "5030972709", "name": "Skylark Work Orders", "items_count": len(load_mock_work_orders())},
        {"id": "5030972904", "name": "Skylark Deals", "items_count": len(load_mock_deals())},
    ]
