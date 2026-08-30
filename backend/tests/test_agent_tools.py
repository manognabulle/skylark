import pytest
from app.agent import (
    tool_get_schema,
    tool_query_records,
    tool_aggregate,
    tool_data_quality_report,
)


def test_tool_get_schema():
    res_wo = tool_get_schema("work_orders")
    assert res_wo["board"] == "work_orders"
    assert res_wo["row_count"] > 0
    assert "Sector" in res_wo["columns"]

    res_deals = tool_get_schema("deals")
    assert res_deals["board"] == "deals"
    assert res_deals["row_count"] > 0
    assert "Deal Status" in res_deals["columns"]


def test_tool_query_records():
    # Fetch work orders with limit
    res = tool_query_records("work_orders", limit=5)
    assert res["returned"] == 5
    assert len(res["records"]) == 5

    # Filter with eq
    res_filtered = tool_query_records(
        "work_orders",
        filters=[{"field": "Sector", "op": "eq", "value": "Mining"}],
        limit=10,
    )
    assert res_filtered["total_matched"] >= 0
    for rec in res_filtered["records"]:
        assert rec["Sector"].lower() == "mining"


def test_tool_query_records_sorting():
    # Sort deals by Masked Deal value descending
    res_top = tool_query_records(
        "deals",
        filters=[{"field": "Deal Status", "op": "eq", "value": "Open"}],
        limit=5,
        sort_by="Masked Deal value",
        sort_order="desc",
    )
    assert res_top["returned"] == 5
    records = res_top["records"]
    values = [r.get("Masked Deal value") for r in records if r.get("Masked Deal value") is not None]
    # Verify values are sorted descending
    assert values == sorted(values, reverse=True)



def test_tool_aggregate_count_and_sum():
    # Count total work orders
    count_res = tool_aggregate("work_orders", agg="count")
    assert count_res["result"] > 0

    # Grouped aggregate
    group_res = tool_aggregate(
        "work_orders",
        group_by="Sector",
        metric_field="Billed Value Excl GST",
        agg="sum",
    )
    assert "grouped_by" in group_res
    assert group_res["grouped_by"] == "Sector"
    assert isinstance(group_res["result"], dict)

    # Aggregation with filter
    filter_agg = tool_aggregate(
        "deals",
        filters=[{"field": "Deal Status", "op": "eq", "value": "Won"}],
        metric_field="Masked Deal value",
        agg="sum",
    )
    assert filter_agg["result"] is not None
    assert filter_agg["result"] >= 0


def test_tool_data_quality_report():
    report = tool_data_quality_report("deals")
    assert report["board"] == "deals"
    assert report["row_count"] > 0
    assert "null_rate_pct_by_column" in report
    assert "Deal Status" in report["null_rate_pct_by_column"]
