# Skylark BI Agent

A conversational BI agent that answers founder-level questions across two monday.com boards — **Work Orders** (project execution) and **Deals** (sales pipeline) — by querying monday.com live, cleaning messy real-world data on the fly, and giving context-rich answers instead of raw numbers.

The system is built around a **FastAPI backend** that connects directly to monday.com's live GraphQL API (`api.monday.com/v2`), using **Google Gemini (`gemini-3.5-flash-lite`)** for intelligent function calling, query understanding, and conversational reasoning.

---

## 1. Architecture

```
                     ┌─────────────────────────┐
   founder asks  ──▶ │   Google Gemini         │
   a question        │ (gemini-3.5-flash-lite) │
                     │ decides board & filters │
                     └───────────┬─────────────┘
                                 │ calls tools
                     ┌───────────┴─────────────┐
                     │ get_schema              │
                     │ query_records           │  (backend/app/agent.py)
                     │ aggregate               │
                     │ data_quality_report     │
                     └───────────┬─────────────┘
                                 │
                     ┌───────────┴─────────────┐
                     │ data_quality.py         │  cleans / normalizes /
                     │ (pandas)                │  drops corrupted rows
                     └───────────┬─────────────┘
                                 │
                     ┌───────────┴─────────────┐
                     │ monday_client.py        │  GraphQL, paginated,
                     │ (api.monday.com/v2)     │  short TTL cache
                     └─────────────────────────┘
```

### Provider-Agnostic Design & LLM Choice
* **LLM Provider**: Built using **Google Gemini (`gemini-3.5-flash-lite`)**. Gemini was chosen during development for its cost efficiency, fast response latency, and generous free-tier rate limits (1,500 requests/day).
* **Provider Agnostic**: The tool architecture (`get_schema`, `query_records`, `aggregate`, `data_quality_report`), data cleaning pipelines, and monday.com integration are completely provider-agnostic. Switching from Claude to Gemini required updating only the LLM turn-execution function in `agent.py`.
* **Deterministic Arithmetic**: Numerical calculations (sums, averages, counts, group-bys) are performed by pandas inside Python (`aggregate` tool), preventing LLM arithmetic hallucination. The LLM handles intent classification, parameter extraction, and conversational synthesis.

---

## 2. Repo Layout

```
backend/
  app/
    main.py               FastAPI application (/chat, /health, /reset, static UI mount)
    agent.py              Gemini multi-hop tool-calling loop & tool implementations
    monday_client.py      monday.com GraphQL client (read-only, paginated, TTL cached)
    data_quality.py       Data cleaning, normalization, and corrupted-row detection
    config.py             Environment configuration loading
  frontend/
    index.html            Clean, responsive web chat interface
  tests/
    test_agent_tools.py   Unit tests for tool functions
    test_data_quality.py  Unit tests for data cleaning & normalization
    test_monday_client.py Unit tests for monday API client & caching
    test_main.py          Integration tests for FastAPI endpoints
  requirements.txt, pytest.ini, .env.example

scripts/
  import_csv_to_monday.py  One-time board creation & CSV dataset import script
  json_to_csv.py           Utility script converting source JSON files to CSV

data/
  work_orders.json         Source Work Orders dataset (176 records)
  deals.json               Source Deals dataset (346 raw rows)

README.md
DECISION_LOG.md
```

---

## 3. Running the Backend

### a) Setup Environment & Dependencies
1. Clone/navigate to the project directory:
   ```bash
   cd project/backend
   ```
2. Create and activate a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### b) Configure Environment Variables
Create a `.env` file inside `backend/` from `.env.example`:
```bash
GEMINI_API_KEY=your_google_gemini_api_key
GEMINI_MODEL=gemini-3.5-flash-lite
MONDAY_API_TOKEN=your_monday_api_token
MONDAY_WORK_ORDERS_BOARD_ID=5030972709
MONDAY_DEALS_BOARD_ID=5030972904
CACHE_TTL_SECONDS=120
```

### c) Run the FastAPI Server
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Open `http://localhost:8000` to access the chat UI.
Visiting `http://localhost:8000/health` reports system health, active LLM configuration, and live monday.com board connectivity.

---

## 4. Test Suite

Run full automated unit and integration tests using pytest:
```bash
pytest backend
```

All 18 test cases cover tool function correctness, date/numeric parsing, status normalization, header-echo row filtering, caching, and FastAPI endpoints.

---

## 5. Example Queries

* **Pipeline Health**: *"How's our pipeline looking for the mining sector this quarter?"*
* **Receivables & Revenue**: *"What's our total receivable amount right now, and how confident should I be in that number?"*
* **Billed Value**: *"What is the total billed value including GST across all work orders?"*
* **Execution Status**: *"Which sector has the most work orders stuck in execution?"*
* **Leadership Updates**: *"Prepare this week's leadership update."*

---

## 6. Data Quality & Board Audit Features

* **Corrupted-Row Filtering**: Excludes 2 corrupted duplicate-header rows in `deals.json` (where column names like `"Deal Status"` appeared as data values). Clean dataset yields **344 valid deal records** out of 346 raw rows.
* **Board Count Alignment**: Live monday.com GraphQL API audit confirmed exact record alignment across both boards:
  * **Work Orders Board**: 176 live items (matching `data/work_orders.json` 100%).
  * **Deals Board**: 344 live valid items (matching valid `data/deals.json` records 100%).
* **Casing & Status Normalization**: Normalizes typos (e.g. `"BIlled"` vs `"Billed"`) to canonical status categories.
* **Null-Safe Operations**: Preserves `NaN`/`None` values cleanly without converting them to `"nan"` strings.
* **`data_quality_report` Tool**: Enables the agent to inspect and report null rates and data completeness per column.
