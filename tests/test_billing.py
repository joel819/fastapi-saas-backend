def _path(url: str) -> str:
    return url.replace("http://localhost:8000", "")


def test_checkout_requires_auth(client):
    assert client.post("/billing/checkout", json={"plan": "pro"}).status_code == 401


def test_checkout_rejects_unknown_plan(client, auth_headers):
    r = client.post("/billing/checkout", json={"plan": "platinum"}, headers=auth_headers)
    assert r.status_code == 422


def test_checkout_uses_mock_provider_in_demo_mode(client, auth_headers):
    r = client.post("/billing/checkout", json={"plan": "basic"}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "mock"
    assert body["session_id"].startswith("cs_mock_")


def test_idempotency_key_returns_same_session(client, auth_headers):
    h = {**auth_headers, "Idempotency-Key": "abc-123"}
    a = client.post("/billing/checkout", json={"plan": "pro"}, headers=h).json()
    b = client.post("/billing/checkout", json={"plan": "pro"}, headers=h).json()
    assert a == b


def test_idempotency_key_reused_with_different_body_conflicts(client, auth_headers):
    h = {**auth_headers, "Idempotency-Key": "abc-123"}
    client.post("/billing/checkout", json={"plan": "pro"}, headers=h)
    r = client.post("/billing/checkout", json={"plan": "basic"}, headers=h)
    assert r.status_code == 409


def test_without_idempotency_key_sessions_differ(client, auth_headers):
    a = client.post("/billing/checkout", json={"plan": "pro"}, headers=auth_headers).json()
    b = client.post("/billing/checkout", json={"plan": "pro"}, headers=auth_headers).json()
    assert a["session_id"] != b["session_id"]


def test_mock_checkout_activates_subscription(client, auth_headers):
    url = client.post("/billing/checkout", json={"plan": "basic"}, headers=auth_headers).json()["checkout_url"]
    r = client.get(_path(url))
    assert r.status_code == 200
    assert r.json()["outcome"] == "subscription_activated"

    sub = client.get("/billing/subscription", headers=auth_headers).json()
    assert sub["plan"] == "basic"
    assert sub["status"] == "active"
    assert sub["is_entitled"] is True

    # A completed session can't be completed twice.
    assert client.get(_path(url)).status_code == 404


def test_unknown_mock_session_404(client):
    assert client.get("/billing/mock-checkout/cs_mock_nope").status_code == 404
