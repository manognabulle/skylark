import time
import pytest
from app import monday_client


def test_find_board_id_by_name():
    wo_id = monday_client.find_board_id_by_name("Skylark Work Orders")
    assert wo_id is not None

    deals_id = monday_client.find_board_id_by_name("Skylark Deals")
    assert deals_id is not None


def test_get_all_items_cached_and_invalidate():
    board_id = "5030972709"
    # First fetch populates cache
    items1 = monday_client.get_all_items_cached(board_id)
    assert len(items1) > 0

    # Second fetch hits cache
    items2 = monday_client.get_all_items_cached(board_id)
    assert items1 == items2

    # Invalidate cache
    monday_client.invalidate_cache(board_id)
    assert board_id not in monday_client._cache
