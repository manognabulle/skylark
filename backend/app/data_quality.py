"""
Data-resilience helpers. monday.com hands us text for every column (that's
how the API surfaces most column types), so all cleaning happens here in one
place rather than being re-implemented per query.
"""
import re
import pandas as pd

# Known typos / casing variants seen in the real dataset, grouped to a
# canonical label. Extend this map as new variants show up — it is the
# single place normalization rules live.
STATUS_ALIASES = {
    "billed": "Billed",
    "bIlled".lower(): "Billed",
    "fully billed": "Fully Billed",
    "partially billed": "Partially Billed",
    "not billed yet": "Not Billed Yet",
    "update required": "Update Required",
    "not billable": "Not Billable",
    "stuck": "Stuck",
    "open": "Open",
    "closed": "Closed",
    "won": "Won",
    "dead": "Dead",
    "on hold": "On Hold",
}


def _is_blank(value) -> bool:
    """True for None, NaN/NaT (pandas turns missing cells into these when a
    column is mixed null/non-null), and empty/whitespace-only strings."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def normalize_status(value):
    if _is_blank(value):
        return None
    v = str(value).strip()
    key = v.lower()
    return STATUS_ALIASES.get(key, v)


def normalize_sector(value):
    if _is_blank(value):
        return None
    v = str(value).strip()
    # Title-case but keep known acronyms as-is
    if v.upper() in {"DSP"}:
        return v.upper()
    return v[:1].upper() + v[1:]


def parse_date(value):
    if _is_blank(value):
        return pd.NaT
    return pd.to_datetime(value, errors="coerce", dayfirst=False)


def to_numeric(value):
    if _is_blank(value):
        return None
    s = str(value).strip()
    if s == "":
        return None
    s = re.sub(r"[^0-9.\-]", "", s)  # strips stray units like "5360 HA" -> 5360... but bare units are non-numeric, see note below
    if s in ("", "-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def is_header_echo_row(row: dict) -> bool:
    """
    Real-world artifact in this dataset: a handful of rows are corrupted
    duplicate header rows (e.g. the 'Deal Status' column literally contains
    the text 'Deal Status'). These must never enter aggregates.
    """
    for col, val in row.items():
        if not _is_blank(val) and str(val).strip() == str(col).strip():
            return True
    return False


def clean_dataframe(records: list[dict], status_cols=(), sector_cols=(), date_cols=(), numeric_cols=()) -> pd.DataFrame:
    df = pd.DataFrame.from_records(records)
    if df.empty:
        return df

    # Drop corrupted duplicate-header rows before anything else
    mask_bad = df.apply(lambda r: is_header_echo_row(r.to_dict()), axis=1)
    df = df[~mask_bad].copy()

    for c in status_cols:
        if c in df.columns:
            df[c] = df[c].apply(normalize_status)
    for c in sector_cols:
        if c in df.columns:
            df[c] = df[c].apply(normalize_sector)
    for c in date_cols:
        if c in df.columns:
            df[c] = df[c].apply(parse_date)
    for c in numeric_cols:
        if c in df.columns:
            df[c] = df[c].apply(to_numeric)

    return df.reset_index(drop=True)


def null_rate_report(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    return (df.isna().mean() * 100).round(1).to_dict()
