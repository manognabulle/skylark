import json
import logging
import os
import sys
import time
import pandas as pd
from google import genai
from google.genai import types

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from . import config, monday_client, data_quality as dq

logger = logging.getLogger(__name__)


WORK_ORDER_STATUS_COLS = ["Execution Status", "Invoice Status", "WO Status billed", "Billing Status", "Document Type", "Nature of Work"]
WORK_ORDER_SECTOR_COLS = ["Sector"]
WORK_ORDER_DATE_COLS = ["Data Delivery Date", "Date of PO/LOI", "Probable Start Date", "Probable End Date", "Last invoice date", "Collection Date"]
WORK_ORDER_NUMERIC_COLS = ["Amount Excl GST", "Amount Incl GST", "Billed Value Excl GST", "Billed Value Incl GST",
                           "Collected Amount Incl GST", "Amount to be billed Excl GST", "Amount to be billed Incl GST",
                           "Amount Receivable", "Qty by Ops", "Qty as per PO", "Qty billed till date", "Balance Qty"]

DEAL_STATUS_COLS = ["Deal Status", "Closure Probability", "Deal Stage"]
DEAL_SECTOR_COLS = ["Sector/service"]
DEAL_DATE_COLS = ["Close Date (A)", "Tentative Close Date", "Created Date"]
DEAL_NUMERIC_COLS = ["Masked Deal value"]


def _board_id(board: str) -> str:
    if board == "work_orders":
        bid = config.WORK_ORDERS_BOARD_ID or monday_client.find_board_id_by_name("Skylark Work Orders")
    elif board == "deals":
        bid = config.DEALS_BOARD_ID or monday_client.find_board_id_by_name("Skylark Deals")
    else:
        raise ValueError(f"Unknown board '{board}'")
    if not bid:
        raise ValueError(f"Could not resolve monday.com board id for '{board}'. Has it been imported yet?")
    return bid


def _load_df(board: str) -> pd.DataFrame:
    bid = _board_id(board)
    records = monday_client.get_all_items_cached(bid)
    if board == "work_orders":
        return dq.clean_dataframe(records, WORK_ORDER_STATUS_COLS, WORK_ORDER_SECTOR_COLS, WORK_ORDER_DATE_COLS, WORK_ORDER_NUMERIC_COLS)
    return dq.clean_dataframe(records, DEAL_STATUS_COLS, DEAL_SECTOR_COLS, DEAL_DATE_COLS, DEAL_NUMERIC_COLS)


def _apply_filters(df: pd.DataFrame, filters: list[dict]) -> pd.DataFrame:
    for f in filters or []:
        field, op, value = f.get("field"), f.get("op", "eq"), f.get("value")
        if not field:
            continue
        # Flexible case-and-underscore-insensitive column matching
        col_name = None
        norm_field = str(field).strip().lower().replace("_", " ")
        for col in df.columns:
            if col.strip().lower().replace("_", " ") == norm_field:
                col_name = col
                break
        if not col_name:
            continue
        col = df[col_name]
        if op == "eq":
            df = df[col.astype(str).str.strip().str.lower() == str(value).strip().lower()]
        elif op == "contains":
            df = df[col.astype(str).str.contains(str(value), case=False, na=False)]
        elif op == "gte":
            df = df[pd.to_numeric(col, errors="coerce") >= float(value)] if not pd.api.types.is_datetime64_any_dtype(col) else df[col >= pd.to_datetime(value)]
        elif op == "lte":
            df = df[pd.to_numeric(col, errors="coerce") <= float(value)] if not pd.api.types.is_datetime64_any_dtype(col) else df[col <= pd.to_datetime(value)]
        elif op == "not_null":
            df = df[col.notna()]
    return df


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def tool_get_schema(board: str) -> dict:
    df = _load_df(board)
    return {"board": board, "row_count": len(df), "columns": list(df.columns), "data_source": monday_client.get_last_data_source()}


def tool_query_records(board: str, filters: list[dict] = None, limit: int = 25, sort_by: str = None, sort_order: str = "desc") -> dict:
    df = _apply_filters(_load_df(board), filters)
    total = len(df)

    if sort_by and not df.empty:
        col_name = None
        norm_sort = str(sort_by).strip().lower().replace("_", " ")
        for col in df.columns:
            if col.strip().lower().replace("_", " ") == norm_sort:
                col_name = col
                break
        if col_name:
            ascending = (str(sort_order).strip().lower() == "asc")
            s_col = df[col_name]
            if pd.api.types.is_datetime64_any_dtype(s_col) or pd.api.types.is_numeric_dtype(s_col):
                df = df.sort_values(by=col_name, ascending=ascending, na_position="last")
            else:
                num_col = pd.to_numeric(s_col, errors="coerce")
                if num_col.notna().any():
                    df = df.iloc[num_col.sort_values(ascending=ascending, na_position="last").index]
                else:
                    df = df.sort_values(by=col_name, ascending=ascending, na_position="last")

    sample = df.head(limit).copy()
    for c in sample.columns:
        if pd.api.types.is_datetime64_any_dtype(sample[c]):
            sample[c] = sample[c].dt.strftime("%Y-%m-%d")
    return {"total_matched": total, "returned": len(sample), "records": json.loads(sample.to_json(orient="records")), "data_source": monday_client.get_last_data_source()}


def tool_aggregate(board: str, filters: list[dict] = None, group_by: str = None, metric_field: str = None, agg: str = "count") -> dict:
    df = _apply_filters(_load_df(board), filters)
    if df.empty:
        return {"result": None, "note": "No matching rows after filtering.", "data_source": monday_client.get_last_data_source()}

    if agg == "count" and not metric_field:
        series_source = df
    elif metric_field:
        target_metric = metric_field
        if target_metric not in df.columns:
            norm_m = str(metric_field).strip().lower().replace("_", " ")
            found = next((c for c in df.columns if c.strip().lower().replace("_", " ") == norm_m), None)
            if found:
                target_metric = found
            else:
                return {"error": f"Unknown field '{metric_field}'"}
        metric_field = target_metric
        series_source = df

    def _agg(sub: pd.DataFrame):
        if agg == "count":
            return int(len(sub))
        vals = pd.to_numeric(sub[metric_field], errors="coerce")
        if agg == "sum":
            return float(vals.sum(skipna=True))
        if agg == "avg":
            return float(vals.mean(skipna=True)) if vals.notna().any() else None
        if agg == "min":
            return float(vals.min(skipna=True)) if vals.notna().any() else None
        if agg == "max":
            return float(vals.max(skipna=True)) if vals.notna().any() else None
        raise ValueError(f"Unknown agg '{agg}'")

    if group_by:
        target_gb = group_by
        if target_gb not in df.columns:
            norm_gb = str(group_by).strip().lower().replace("_", " ")
            found = next((c for c in df.columns if c.strip().lower().replace("_", " ") == norm_gb), None)
            if found:
                target_gb = found
            else:
                return {"error": f"Unknown group_by field '{group_by}'"}
        group_by = target_gb

        out = {}
        for key, sub in df.groupby(df[group_by].fillna("(blank)")):
            out[str(key)] = _agg(sub)
        return {"grouped_by": group_by, "result": out, "rows_considered": len(df), "data_source": monday_client.get_last_data_source()}
    return {"result": _agg(df), "rows_considered": len(df), "data_source": monday_client.get_last_data_source()}


def tool_data_quality_report(board: str) -> dict:
    df = _load_df(board)
    return {"board": board, "row_count": len(df), "null_rate_pct_by_column": dq.null_rate_report(df), "data_source": monday_client.get_last_data_source()}


TOOLS = [
    {
        "name": "get_schema",
        "description": "List the available columns for a board and current row count.",
        "input_schema": {
            "type": "object",
            "properties": {"board": {"type": "string", "enum": ["work_orders", "deals"]}},
            "required": ["board"],
        },
    },
    {
        "name": "query_records",
        "description": "Fetch raw matching rows (already cleaned/normalized) for inspection, sorting, or top N rankings. Use sort_by (field name) + sort_order ('asc'|'desc') + limit to get top / largest / smallest records.",
        "input_schema": {
            "type": "object",
            "properties": {
                "board": {"type": "string", "enum": ["work_orders", "deals"]},
                "filters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "op": {"type": "string", "enum": ["eq", "contains", "gte", "lte", "not_null"]},
                            "value": {},
                        },
                    },
                },
                "limit": {"type": "integer", "default": 25},
                "sort_by": {"type": "string", "description": "Field name to sort records by before applying limit"},
                "sort_order": {"type": "string", "enum": ["asc", "desc"], "default": "desc", "description": "Sort order: 'desc' for largest/highest, 'asc' for smallest/lowest"},
            },
            "required": ["board"],
        },
    },
    {
        "name": "aggregate",
        "description": "Reliable server-side aggregation (count/sum/avg/min/max), optionally grouped by a field. Always prefer this over doing arithmetic yourself.",
        "input_schema": {
            "type": "object",
            "properties": {
                "board": {"type": "string", "enum": ["work_orders", "deals"]},
                "filters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "op": {"type": "string", "enum": ["eq", "contains", "gte", "lte", "not_null"]},
                            "value": {},
                        },
                    },
                },
                "group_by": {"type": "string"},
                "metric_field": {"type": "string", "description": "Required unless agg=count"},
                "agg": {"type": "string", "enum": ["count", "sum", "avg", "min", "max"], "default": "count"},
            },
            "required": ["board"],
        },
    },
    {
        "name": "data_quality_report",
        "description": "Null-rate per column for a board, useful when the user asks about data completeness/quality or when you need to caveat an answer.",
        "input_schema": {
            "type": "object",
            "properties": {"board": {"type": "string", "enum": ["work_orders", "deals"]}},
            "required": ["board"],
        },
    },
]

TOOL_IMPL = {
    "get_schema": tool_get_schema,
    "query_records": tool_query_records,
    "aggregate": tool_aggregate,
    "data_quality_report": tool_data_quality_report,
}

SYSTEM_PROMPT = """You are Skylark Drones' internal Business Intelligence agent for founders and execs.

You have tools to query two live monday.com boards: "work_orders" (project execution: sector, type of work,
execution status, PO/LOI + delivery dates, invoiced/billed/collected amounts, receivables, invoice status) and
"deals" (sales pipeline: owner, client, deal status Open/Won/Dead/On Hold, deal stage — a lettered funnel A→O,
deal value, closure probability, sector/service, dates).

Rules:
1. Ambiguous Queries: Evaluate query clarity BEFORE calling tools. If a query uses an ambiguous relative timeframe without a reference date (such as "this quarter", "this month", or "recent"), do NOT start calling tools repeatedly. Immediately ask ONE short clarifying question (e.g. "Which quarter or date range are you looking for?").
2. Ranking / Top N Queries: To answer "top N", "largest", or "smallest" questions (e.g. "top 5 largest open deals"), use `query_records` with `sort_by` (e.g. "Masked Deal value"), `sort_order` ("desc" for largest/top, "asc" for smallest), and `limit`.
3. Tool Usage: Always call tools to get live data for specific questions — never answer from memory.
4. Clean & Normalize: This is real messy operational data — nulls, casing/typos, corrupted duplicate-header rows.
   The tools normalize known variants and drop corrupted rows, but sanity-check with query_records before trusting a grouping if a field looks inconsistent, and mention material caveats.
5. Prefer Math Tools: Prefer the `aggregate` tool for any math — never eyeball-sum numbers yourself.
6. Context & Scale: Give context, not just a number: scale (e.g. "12 of 40"), and one caveat about data completeness when relevant.
7. Leadership Updates: For "leadership update" / "exec summary" requests: structure tightly — Pipeline health, Revenue/collections status, Operational execution by sector, Data quality flags. Short lines, skimmable, no fluff.
8. Conciseness: Keep answers concise. Plain text or a tight list, minimal markdown.
9. Board Resolution: If a board can't be resolved, say so plainly and point to the import script — never fabricate numbers.
"""


def _get_gemini_client() -> genai.Client:
    return genai.Client(api_key=config.GEMINI_API_KEY)


def _get_gemini_tools() -> list[types.Tool]:
    function_declarations = []
    for t in TOOLS:
        fn = types.FunctionDeclaration(
            name=t["name"],
            description=t["description"],
            parameters=t["input_schema"],
        )
        function_declarations.append(fn)
    return [types.Tool(function_declarations=function_declarations)]


DEBUG = os.environ.get("AGENT_DEBUG", "false").lower() in ("true", "1")


def _safe_log(msg: str):
    safe_msg = str(msg).encode("utf-8", errors="replace").decode("utf-8")
    try:
        print(safe_msg)
    except Exception:
        logger.debug(safe_msg)


def run_agent_turn(history: list[dict]) -> tuple[str, list[dict]]:
    """
    history: list of {"role": "user"|"assistant", "content": str|list} — full
    conversation history so far.

    Returns (assistant_text, updated_history).
    """
    client = _get_gemini_client()
    gemini_tools = _get_gemini_tools()

    config_obj = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=gemini_tools,
        temperature=0.0,
    )

    # Convert history into Gemini types.Content objects
    contents: list[types.Content] = []
    for item in history:
        role = "user" if item["role"] == "user" else "model"
        raw_content = item.get("content")
        if isinstance(raw_content, str):
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=raw_content)]))
        elif isinstance(raw_content, list):
            parts = []
            for part_item in raw_content:
                if isinstance(part_item, str):
                    parts.append(types.Part.from_text(text=part_item))
                elif isinstance(part_item, dict):
                    if part_item.get("type") == "tool_result":
                        parts.append(types.Part.from_function_response(
                            name=part_item.get("name", "tool"),
                            response={"result": json.loads(part_item.get("content", "{}"))} if isinstance(part_item.get("content"), str) else part_item.get("content", {})
                        ))
                    elif "text" in part_item:
                        parts.append(types.Part.from_text(text=part_item["text"]))
            if parts:
                contents.append(types.Content(role=role, parts=parts))

    # Multi-hop tool execution loop (capped at 6 hops)
    updated_history = list(history)

    for hop in range(1, 7):
        if DEBUG:
            _safe_log(f"\n--- [DEBUG HOP {hop}] ---")
            _safe_log(f"[DEBUG] Sending contents to Gemini ({len(contents)} messages)...")

        if hop > 1:
            time.sleep(2.0)

        # Generate content with automatic backoff retry for 429 / 503 / API errors
        resp = None
        for attempt in range(4):
            try:
                resp = client.models.generate_content(
                    model=config.GEMINI_MODEL,
                    contents=contents,
                    config=config_obj,
                )
                break
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "UNAVAILABLE" in err_str:
                    if DEBUG:
                        _safe_log(f"[DEBUG HOP {hop}] Rate limit / high demand (attempt {attempt+1}/4): {err_str[:150]}. Sleeping 5s...")
                    time.sleep(5.0 * (attempt + 1))
                else:
                    if DEBUG:
                        _safe_log(f"[DEBUG HOP {hop}] Error: {e}")
                    return f"Encountered Gemini API error: {err_str}", updated_history

        if not resp:
            return "The Gemini API rate limit or quota limit was reached for this model. Please try again in a few seconds.", updated_history

        # Check if model requested function calls
        if resp.function_calls:
            if DEBUG:
                _safe_log(f"[DEBUG HOP {hop}] Model requested {len(resp.function_calls)} function call(s):")
                for fc in resp.function_calls:
                    _safe_log(f"  -> Tool: {fc.name}, Args: {fc.args}")

            # Append model's response candidate content to Gemini contents list
            if resp.candidates and resp.candidates[0].content:
                contents.append(resp.candidates[0].content)

            tool_response_parts = []
            for call in resp.function_calls:
                impl = TOOL_IMPL.get(call.name)
                args = call.args or {}
                try:
                    result = impl(**args) if impl else {"error": f"Unknown tool {call.name}"}
                except Exception as e:
                    result = {"error": str(e)}

                if DEBUG:
                    res_str = str(result)
                    _safe_log(f"  <- Tool {call.name} Result (len {len(res_str)}): {res_str[:300]}...")

                tool_response_parts.append(types.Part.from_function_response(
                    name=call.name,
                    response={"result": result},
                ))

            # Append function execution results back to Gemini contents
            contents.append(types.Content(role="user", parts=tool_response_parts))
        else:
            final_text = resp.text or ""
            if DEBUG:
                _safe_log(f"[DEBUG HOP {hop}] No function calls requested. Returned text: '{final_text}'")
            updated_history.append({"role": "assistant", "content": final_text})
            return final_text, updated_history

    return "I hit my tool-call limit for this turn — try narrowing the question a bit.", updated_history



