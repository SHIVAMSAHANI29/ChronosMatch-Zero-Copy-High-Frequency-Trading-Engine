from fastapi.testclient import TestClient

from src.api import create_app


def test_sqlite_journal_restores_orders_and_trades(tmp_path):
    db = tmp_path / "chronos-test.db"
    with TestClient(create_app(db_path=db, persist=True)) as c:
        sell = c.post("/orders", json={
            "symbol": "TEST", "side": "SELL", "price": "50", "quantity": 5, "order_id": "S1"
        })
        assert sell.status_code == 201
        buy = c.post("/orders", json={
            "symbol": "TEST", "side": "BUY", "price": "55", "quantity": 2, "order_id": "B1"
        })
        assert buy.status_code == 201
        assert len(buy.json()["trades"]) == 1

    # A new app instance replays the journal into a fresh engine.
    with TestClient(create_app(db_path=db, persist=True)) as c:
        assert c.get("/orders/S1").json()["remaining"] == 3
        assert c.get("/orders/B1").json()["status"] == "FILLED"
        assert c.get("/trades").json()["count"] == 1
        assert c.get("/health").json()["replayed_commands"] == 2


def test_sqlite_journal_restores_cancellations(tmp_path):
    db = tmp_path / "cancel-test.db"
    with TestClient(create_app(db_path=db, persist=True)) as c:
        response = c.post("/orders", json={
            "symbol": "TEST", "side": "BUY", "price": "25", "quantity": 3, "order_id": "B-CANCEL"
        })
        assert response.status_code == 201
        assert c.delete("/orders/B-CANCEL").status_code == 200

    with TestClient(create_app(db_path=db, persist=True)) as c:
        assert c.get("/orders/B-CANCEL").json()["status"] == "CANCELLED"
        assert c.get("/orders").json()["count"] == 0
