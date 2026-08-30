import math
import numpy as np
import pandas as pd
import pytest

from app.data_quality import (
    _is_blank,
    normalize_status,
    normalize_sector,
    parse_date,
    to_numeric,
    is_header_echo_row,
    clean_dataframe,
    null_rate_report,
)


def test_is_blank():
    assert _is_blank(None) is True
    assert _is_blank(float("nan")) is True
    assert _is_blank(np.nan) is True
    assert _is_blank("") is True
    assert _is_blank("   ") is True
    assert _is_blank("Billed") is False
    assert _is_blank(0) is False
    assert _is_blank(123.45) is False


def test_normalize_status():
    assert normalize_status("billed") == "Billed"
    assert normalize_status("bIlled") == "Billed"
    assert normalize_status("fully billed") == "Fully Billed"
    assert normalize_status("  won  ") == "Won"
    assert normalize_status("dead") == "Dead"
    assert normalize_status("on hold") == "On Hold"
    assert normalize_status("Custom Status") == "Custom Status"
    assert normalize_status(None) is None
    assert normalize_status("") is None


def test_normalize_sector():
    assert normalize_sector("mining") == "Mining"
    assert normalize_sector("power & utilities") == "Power & utilities"
    assert normalize_sector("DSP") == "DSP"
    assert normalize_sector("  dsp  ") == "DSP"
    assert normalize_sector(None) is None


def test_parse_date():
    dt = parse_date("2026-08-30")
    assert pd.notna(dt)
    assert dt.year == 2026 and dt.month == 8 and dt.day == 30

    assert pd.isna(parse_date(""))
    assert pd.isna(parse_date(None))
    assert pd.isna(parse_date("not-a-date"))


def test_to_numeric():
    assert to_numeric("123.45") == 123.45
    assert to_numeric("5360 HA") == 5360.0
    assert to_numeric("$10,000.50") == 10000.50
    assert to_numeric("-50") == -50.0
    assert to_numeric(None) is None
    assert to_numeric("") is None
    assert to_numeric("abc") is None
    assert to_numeric("-") is None


def test_is_header_echo_row():
    bad_row = {"Deal Status": "Deal Status", "Sector": "Mining", "Amount": "100"}
    good_row = {"Deal Status": "Won", "Sector": "Mining", "Amount": "100"}

    assert is_header_echo_row(bad_row) is True
    assert is_header_echo_row(good_row) is False


def test_clean_dataframe():
    raw_records = [
        {"Execution Status": "stuck", "Sector": "mining", "Amount": "1000 INR", "Date": "2026-01-15"},
        {"Execution Status": "Execution Status", "Sector": "mining", "Amount": "1000", "Date": "2026-01-15"},  # corrupted header echo
        {"Execution Status": "bIlled", "Sector": "DSP", "Amount": None, "Date": ""},
    ]

    cleaned_df = clean_dataframe(
        raw_records,
        status_cols=["Execution Status"],
        sector_cols=["Sector"],
        date_cols=["Date"],
        numeric_cols=["Amount"],
    )

    # 1 corrupted row dropped -> 2 rows remaining
    assert len(cleaned_df) == 2
    assert cleaned_df.loc[0, "Execution Status"] == "Stuck"
    assert cleaned_df.loc[0, "Sector"] == "Mining"
    assert cleaned_df.loc[0, "Amount"] == 1000.0

    assert cleaned_df.loc[1, "Execution Status"] == "Billed"
    assert cleaned_df.loc[1, "Sector"] == "DSP"
    assert pd.isna(cleaned_df.loc[1, "Amount"])


def test_null_rate_report():
    df = pd.DataFrame({
        "col_a": [1, None, 3, 4],
        "col_b": ["a", "b", "c", "d"],
        "col_c": [None, None, None, None],
    })
    report = null_rate_report(df)
    assert report["col_a"] == 25.0
    assert report["col_b"] == 0.0
    assert report["col_c"] == 100.0

    empty_report = null_rate_report(pd.DataFrame())
    assert empty_report == {}
