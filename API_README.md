# ChronosMatch FastAPI REST API

## Install

Use Python 3.11 or newer. From the `ChronosMatch` project directory:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Start the API

Run from the `ChronosMatch` project root (the directory containing `src`):

```bash
python -m uvicorn src.api:app --reload
```

Open:
- Interactive Swagger docs: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- Health check: http://127.0.0.1:8000/health

## Routes

| Method | Route | Purpose |
|---|---|---|
| `GET` | `/` | API info |
| `GET` | `/health` | Health check |
| `POST` | `/orders` | Submit a limit order |
| `GET` | `/orders` | List orders; optional `symbol`, `side`, `active_only` filters |
| `GET` | `/orders/{order_id}` | Get one order |
| `DELETE` | `/orders/{order_id}` | Cancel an active order |
| `GET` | `/order-book/{symbol}` | Get order-book snapshot; optional `depth` |
| `GET` | `/trades` | Recent trades; optional `symbol`, `limit` |
| `GET` | `/symbols` | Symbols seen by the engine |
| `GET` | `/stats` | Engine counters and active-order statistics |

## Example request

```http
POST /orders
Content-Type: application/json
```

```json
{
  "symbol": "AAPL",
  "side": "BUY",
  "price": "100.2500",
  "quantity": 10,
  "order_id": "BUY-001"
}
```

Price should be sent as a decimal string to preserve exact precision. `order_id` is optional; the engine generates one when omitted.

## Error responses

- `422 Unprocessable Entity`: invalid order fields or query parameters.
- `404 Not Found`: order does not exist.
- `409 Conflict`: duplicate order ID, or cancellation of an already filled/cancelled order.

## Run tests

```bash
python -m pytest -v
```

The API currently uses an in-memory matching engine. Orders and trades are lost when the server restarts; database persistence and authentication are not implemented in this API layer.
