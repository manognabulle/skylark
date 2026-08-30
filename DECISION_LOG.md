# Decision Log

## Architecture & LLM Provider Selection

### Why Google Gemini (`gemini-3.5-flash-lite`)?
During development and testing, Google Gemini (`gemini-3.5-flash-lite`) was selected as the primary LLM provider for several practical reasons:
1. **Cost & Rate Limits**: Gemini 3.5 Flash Lite provides 1,500 Requests Per Day (RPD) and 30 Requests Per Minute (RPM) on the Google AI Studio tier, allowing extensive multi-hop tool testing without running into restrictive rate walls.
2. **Speed & Latency**: Fast response times for interactive multi-hop tool function execution.
3. **Provider-Agnostic Design**: The core business intelligence logic — including schema resolution, query filtering, pandas aggregation, and data quality normalization — is implemented in Python tools (`agent.py`, `data_quality.py`, `monday_client.py`). The LLM is used strictly for intent classification, tool orchestration, and natural language response synthesis. Switching model providers required updating only the turn-execution function in `agent.py`; no business logic or data tools needed modification.

---

## Standalone FastAPI Backend Architecture

The primary deliverable is the standalone **FastAPI backend** (`backend/`):
* **Self-Contained & Hostable**: Runs as a standard web application deployable to Render, Railway, Fly.io, or any container host with a single `MONDAY_API_TOKEN` and `GEMINI_API_KEY`.
* **Direct monday.com Integration**: Reads directly from monday.com's live GraphQL API (`api.monday.com/v2`), using paginated queries and short-TTL caching.

---

## Key Assumptions & Business Logic

- **"Founder-level Query" Scope**: Revenue, receivables, pipeline health, sector performance, execution status, and deal comparisons. The `aggregate` and `query_records` tools cover these patterns cleanly.
- **Revenue Ambiguity**: "Revenue" in the raw data can refer to *Invoiced Value*, *Billed Value*, or *Collected Amount*. The agent defaults to *Billed Value Incl GST* as the primary revenue proxy and explicitly mentions data completeness notes when reporting numbers.
- **Corrupted Row Detection**: In `data/deals.json`, two rows (Row 50 and Row 179) are corrupted duplicate-header rows where column header names (e.g. `"Deal Status"`) leaked into data cells. `data_quality.is_header_echo_row` filters out these rows automatically before aggregation.

---

## Live Board Audit Findings

A full audit comparing monday.com live GraphQL API records against source datasets yielded exact record alignment:
* **Skylark Work Orders Board**:
  * Source JSON count: 176 records (`data/work_orders.json`).
  * Live board count after audit & cleanup: **176 items** (one un-indexed default placeholder item `"Task 1"` was identified and removed via GraphQL mutation).
* **Skylark Deals Board**:
  * Source JSON count: 346 total rows (`data/deals.json`).
  * Corrupted header rows: 2 rows (Row 50 and Row 179).
  * Valid deal records: **344 records**.
  * Live board count after audit & cleanup: **344 items** (one default placeholder item `"Task 1"` was removed via GraphQL mutation).

---

## Trade-offs & Engineering Decisions

1. **Python Tools for Arithmetic, LLM for Reasoning**: Sums, averages, and group-bys are calculated via pandas inside the `aggregate` tool rather than relying on LLM mental math.
2. **Short TTL In-Process Cache (120s)**: monday.com API queries are cached in memory for 2 minutes to keep multi-turn conversations fast without hammering rate limits, while staying live for real-time interaction.
3. **Data Normalization & Null Safety**: Null values are handled cleanly as `pd.NA`/`None` rather than string `"nan"`. Status casing variants (e.g. `"BIlled"` vs `"Billed"`) are mapped to canonical categories.

---

## Retrospective & Future Improvements

1. **Persistent Session Storage**: Swap the in-memory FastAPI session dictionary for Redis for multi-instance production scaling.
2. **Dedicated Cross-Board Join Tool**: Implement a dedicated `join_boards` tool to optimize queries comparing pipeline deals directly against active work orders.
3. **Webhook Cash Invalidation**: Implement monday.com webhooks to instantly invalidate local TTL cache on item updates.
