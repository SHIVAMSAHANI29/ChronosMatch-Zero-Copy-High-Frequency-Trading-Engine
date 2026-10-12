from fastapi.testclient import TestClient

from src.api import create_app
from src.matching_engine import MatchingEngine


def client():
    return TestClient(create_app(MatchingEngine(), persist=False))


def test_health_and_root():
    c = client()
    assert c.get("/health").json()["status"] == "ok"
    assert c.get("/").status_code == 200


def test_submit_order_and_fetch_it():
    c = client()
    response = c.post(
        "/orders",
        json={"symbol": "aapl", "side": "buy", "price": "100.25", "quantity": 4, "order_id": "B1"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["order"]["symbol"] == "AAPL"
    assert data["order"]["price"] == "100.2500"
    assert c.get("/orders/B1").json()["remaining"] == 4


def test_matching_and_trade_endpoint():
    c = client()
    c.post("/orders", json={"symbol": "AAPL", "side": "SELL", "price": "100", "quantity": 3, "order_id": "S1"})
    response = c.post(
        "/orders", json={"symbol": "AAPL", "side": "BUY", "price": "101", "quantity": 2, "order_id": "B1"}
    )
    assert response.status_code == 201
    assert response.json()["trades"][0]["price"] == "100.0000"
    assert response.json()["trades"][0]["quantity"] == 2
    trades = c.get("/trades", params={"symbol": "AAPL"}).json()["trades"]
    assert len(trades) == 1


def test_duplicate_order_id_returns_409():
    c = client()
    body = {"symbol": "AAPL", "side": "BUY", "price": "100", "quantity": 1, "order_id": "same"}
    assert c.post("/orders", json=body).status_code == 201
    assert c.post("/orders", json=body).status_code == 409


def test_invalid_order_returns_422():
    c = client()
    response = c.post("/orders", json={"symbol": "AAPL", "side": "BUY", "price": "0", "quantity": 1})
    assert response.status_code == 422


def test_cancel_order_and_missing_order():
    c = client()
    c.post("/orders", json={"symbol": "AAPL", "side": "BUY", "price": "100", "quantity": 2, "order_id": "B1"})
    assert c.delete("/orders/B1").status_code == 200
    assert c.delete("/orders/B1").status_code == 409
    assert c.delete("/orders/missing").status_code == 404


def test_order_book_symbols_and_stats():
    c = client()
    c.post("/orders", json={"symbol": "MSFT", "side": "BUY", "price": "10", "quantity": 2})
    assert c.get("/order-book/MSFT").json()["bids"]
    assert c.get("/symbols").json()["symbols"] == ["MSFT"]
    assert c.get("/stats").json()["active_orders"] == 1


def test_list_orders_filter():
    c = client()
    c.post("/orders", json={"symbol": "AAPL", "side": "BUY", "price": "10", "quantity": 1})
    c.post("/orders", json={"symbol": "MSFT", "side": "SELL", "price": "20", "quantity": 1})
    response = c.get("/orders", params={"symbol": "aapl", "side": "buy"})
    assert response.status_code == 200
    assert len(response.json()["orders"]) == 1
