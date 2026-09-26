def test_login_rate_limited(client):
    body = {"email": "x@example.com", "password": "whatever-pass"}
    codes = [client.post("/auth/login", json=body).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5
    assert codes[5] == 429


def test_health_is_not_rate_limited(client):
    codes = {client.get("/health").status_code for _ in range(20)}
    assert codes == {200}


def test_health_reports_demo_mode(client):
    body = client.get("/health").json()
    assert body["demo_mode"] is True
    assert body["payments_provider"] == "mock"
