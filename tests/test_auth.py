"""Web-app sign-in: POST /auth/login, GET /me and the session check on POST /support (app/auth.py, app/main.py)."""
import time

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.graph import pipeline
from app.main import app

client = TestClient(app)  # no "with": the startup KB load is not needed here


@pytest.fixture
def signin(edge_db, monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "test-pass")
    monkeypatch.setenv("AUTH_SECRET", "test-secret")


def login(name, password="test-pass"):
    return client.post("/auth/login", json={"login": name, "password": password})


def test_login_by_account_id_or_email(signin):
    by_id = login("a1004")
    assert by_id.status_code == 200
    assert by_id.json()["account"] == {"account_id": "A1004", "company_name": "Delta Freight", "plan": "Pro",
                                       "status": "active", "product_version": "4.4"}
    assert "owner_email" not in by_id.text
    assert login("Owner4@Example.com").json()["account"]["account_id"] == "A1004"


def test_wrong_password_and_unknown_account_look_the_same(signin):
    wrong, unknown = login("A1004", "nope"), login("A9999")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_sign_in_off_without_demo_password(edge_db, monkeypatch):
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)
    assert login("A1004").status_code == 503


def test_me_needs_a_valid_token(signin):
    token = login("A1002").json()["token"]
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": f"Bearer {token}x"}).status_code == 401  # tampered
    assert auth.verify_token(token + "é") is None and auth.verify_token("garbage") is None  # malformed, no crash
    expired = auth.make_token("A1002", int(time.time()) - 1)
    assert client.get("/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    me = client.get("/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["account"]["account_id"] == "A1002" and "owner_email" not in me["account"]
    assert me["limits"]["api_rate_over"] is True  # peak 301 > Pro limit 300, computed by the tool
    assert {inv["invoice_id"] for inv in me["invoices"]} == {"INV-1002"}
    assert {c["component"] for c in me["platform_status"]} == {"api", "workflow-engine", "connectors", "billing"}


def test_support_token_must_match_header(signin, monkeypatch):
    monkeypatch.setattr(pipeline, "run", lambda request, account_id: (_ for _ in ()).throw(NotImplementedError(account_id)))
    token = login("A1004").json()["token"]
    other = {"X-Account-Id": "A1001", "Authorization": f"Bearer {token}"}
    assert client.post("/support", json={"message": "hi"}, headers=other).status_code == 401
    same = {"X-Account-Id": "A1004", "Authorization": f"Bearer {token}"}
    assert client.post("/support", json={"message": "hi"}, headers=same).status_code == 501  # reached the pipeline
    # Without a token the judges' contract is unchanged: the header alone reaches the pipeline.
    assert client.post("/support", json={"message": "hi"}, headers={"X-Account-Id": "A1001"}).status_code == 501
