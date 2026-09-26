def test_me_requires_auth(client):
    assert client.get("/users/me").status_code == 401


def test_me_rejects_bad_token(client):
    r = client.get("/users/me", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_me_returns_profile(client, auth_headers):
    r = client.get("/users/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "user@example.com"


def test_premium_blocked_on_free_plan(client, auth_headers):
    r = client.get("/users/me/premium", headers=auth_headers)
    assert r.status_code == 402


def test_premium_allowed_after_checkout(client, auth_headers):
    url = client.post("/billing/checkout", json={"plan": "pro"}, headers=auth_headers).json()["checkout_url"]
    client.get(url.replace("http://localhost:8000", ""))
    r = client.get("/users/me/premium", headers=auth_headers)
    assert r.status_code == 200
    assert "pro" in r.json()["message"]
