# ChronosMatch Phase 3 — API, Dashboard, Persistence

## Requirements
- Python 3.11+
- Dependencies from `requirements.txt`

## Windows / VS Code setup

Open this folder (the one containing `src`, `tests`, `frontend`, and `requirements.txt`) in VS Code.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m src.main
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` and then `.\.venv\Scripts\python.exe -m src.main`.

Open:
- Dashboard: http://127.0.0.1:8000/
- Swagger API docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

Alternative startup:
```powershell
python -m uvicorn src.api:app --reload
```
`src.main` uses settings from `.env`; `uvicorn --reload` is useful during development.

## Routes

| Method | Path | Description |
|---|---|---|
| GET | `/` | Dashboard |
| GET | `/api` | API metadata |
| GET | `/health` | API and persistence status |
| POST | `/orders` | Submit a limit order |
| GET | `/orders` | List orders; `symbol`, `side`, `active_only` filters |
| GET | `/orders/{order_id}` | Read one order |
| DELETE | `/orders/{order_id}` | Cancel active order |
| GET | `/order-book/{symbol}` | Aggregated order book; `depth` filter |
| GET | `/trades` | Recent executions; `symbol`, `limit` filters |
| GET | `/symbols` | Symbols known to the engine |
| GET | `/stats` | Engine counters |

## Example order

```json
{
  "symbol": "AAPL",
  "side": "BUY",
  "price": "100.2500",
  "quantity": 10,
  "order_id": "BUY-001"
}
```

Use a decimal string for `price` to avoid floating-point precision issues. Order IDs are lifetime-unique.

## SQLite persistence and recovery

Accepted order submissions and successful cancellations are appended to `chronosmatch.db` (or `CHRONOS_DB_PATH`). On startup, the application replays this command journal into a fresh matching engine. It reconstructs order books, fills, trades and sequence priority. SQLite uses WAL mode.

This is a simple local journal for an educational simulator, not a transactional exchange ledger. Back up the database before manual edits. Do not expose this development server publicly without authentication, authorization, rate limiting, TLS and production deployment hardening.

## Tests

```powershell
python -m pytest -v
```

The API tests use an injected in-memory engine and do not touch your normal SQLite database.
