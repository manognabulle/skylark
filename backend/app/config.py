import os
from dotenv import load_dotenv
load_dotenv()

# --- Gemini ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")




# --- monday.com ---
MONDAY_API_TOKEN = os.environ.get("MONDAY_API_TOKEN", "")
MONDAY_API_URL = "https://api.monday.com/v2"
WORK_ORDERS_BOARD_ID = os.environ.get("MONDAY_WORK_ORDERS_BOARD_ID", "")
DEALS_BOARD_ID = os.environ.get("MONDAY_DEALS_BOARD_ID", "")

# How long fetched board data is cached in-process before re-querying
# monday.com. Keeps the agent responsive to rapid follow-up questions
# without hammering the API, while staying "live" within a short window.
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "120"))

if not GEMINI_API_KEY:
    print("[WARN] GEMINI_API_KEY not set — /chat will fail until configured.")
if not MONDAY_API_TOKEN:
    print("[WARN] MONDAY_API_TOKEN not set — monday.com calls will fail until configured.")

