"""
Thin client around monday.com's GraphQL API (api.monday.com/v2).

Read-only by design for the BI agent's runtime path — the agent never writes
to monday.com. Board/item creation lives separately in scripts/import_csv_to_monday.py,
used only for the one-time data import described in the assignment.
"""
import logging
import time
import requests
from . import config, mock_data

logger = logging.getLogger(__name__)

HEADERS = {
    "Authorization": config.MONDAY_API_TOKEN,
    "Content-Type": "application/json",
    "API-Version": "2024-10",
}

LAST_DATA_SOURCE: str = "unknown"


class MondayError(Exception):
    pass


def get_last_data_source() -> str:
    return LAST_DATA_SOURCE


def _post(query: str, variables: dict | None = None) -> dict:
    if not config.MONDAY_API_TOKEN:
        raise MondayError("MONDAY_API_TOKEN is not configured")
    headers = {
        "Authorization": config.MONDAY_API_TOKEN,
        "Content-Type": "application/json",
        "API-Version": "2024-10",
    }
    resp = requests.post(
        config.MONDAY_API_URL,
        json={"query": query, "variables": variables or {}},
        headers=headers,
        timeout=30,
    )
    data = resp.json()
    if "errors" in data:
        raise MondayError(str(data["errors"]))
    return data["data"]


def get_boards() -> list[dict]:
    """List boards visible to the token — used to resolve board ids by name."""
    global LAST_DATA_SOURCE
    try:
        q = """
        query {
          boards (limit: 100) {
            id
            name
            items_count
          }
        }
        """
        boards = _post(q)["boards"]
        LAST_DATA_SOURCE = "live_monday_api"
        return boards
    except Exception as e:
        logger.warning(f"[DATA SOURCE WARNING] monday.com API call failed ({e}). Falling back to local offline JSON dataset.")
        LAST_DATA_SOURCE = "local_fallback"
        return mock_data.get_mock_boards()


def find_board_id_by_name(name: str) -> str | None:
    for b in get_boards():
        if b["name"].strip().lower() == name.strip().lower():
            return b["id"]
    if "work orders" in name.lower():
        return config.WORK_ORDERS_BOARD_ID or "5030972709"
    if "deals" in name.lower():
        return config.DEALS_BOARD_ID or "5030972904"
    return None


def get_board_columns(board_id: str) -> list[dict]:
    try:
        q = """
        query ($boardId: [ID!]) {
          boards (ids: $boardId) {
            columns { id title type }
          }
        }
        """
        data = _post(q, {"boardId": [board_id]})
        boards = data["boards"]
        return boards[0]["columns"] if boards else []
    except Exception:
        return []


def get_all_items(board_id: str) -> list[dict]:
    """
    Page through every item on a board and return normalized
    {id, name, values: {column_title: text}} dicts.
    Falls back to local mock data if monday.com API call fails.
    """
    global LAST_DATA_SOURCE
    try:
        columns = get_board_columns(board_id)
        col_title_by_id = {c["id"]: c["title"] for c in columns}

        items: list[dict] = []
        cursor = None
        q = """
        query ($boardId: ID!, $cursor: String) {
          boards (ids: [$boardId]) {
            items_page (limit: 100, cursor: $cursor) {
              cursor
              items {
                id
                name
                column_values { id text value }
              }
            }
          }
        }
        """
        while True:
            data = _post(q, {"boardId": board_id, "cursor": cursor})
            page = data["boards"][0]["items_page"]
            for it in page["items"]:
                record = {"id": it["id"], "name": it["name"]}
                for cv in it["column_values"]:
                    title = col_title_by_id.get(cv["id"], cv["id"])
                    record[title] = cv["text"]
                items.append(record)
            cursor = page["cursor"]
            if not cursor:
                break
        LAST_DATA_SOURCE = "live_monday_api"
        return items
    except Exception as e:
        logger.warning(f"[DATA SOURCE WARNING] monday.com item fetch failed for board {board_id} ({e}). Falling back to local offline JSON dataset.")
        LAST_DATA_SOURCE = "local_fallback"
        return mock_data.get_mock_items_for_board(board_id)




# --- tiny in-process cache so a burst of follow-up questions in one
#     conversation doesn't re-hit monday.com's API for every single turn ---
_cache: dict[str, tuple[float, list[dict]]] = {}


def get_all_items_cached(board_id: str) -> list[dict]:
    now = time.time()
    hit = _cache.get(board_id)
    if hit and (now - hit[0]) < config.CACHE_TTL_SECONDS:
        return hit[1]
    items = get_all_items(board_id)
    _cache[board_id] = (now, items)
    return items


def invalidate_cache(board_id: str | None = None):
    if board_id:
        _cache.pop(board_id, None)
    else:
        _cache.clear()
