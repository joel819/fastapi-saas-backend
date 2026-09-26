from tests.conftest import PASSWORD


def test_register_creates_user_with_free_plan(client, register):
    body = register("New@Example.com")
    assert body["email"] == "new@example.com"
    assert body["subscription"]["plan"] == "free"
    assert "hashed_password" not in body


def test_register_duplicate_email_conflicts(client, register):
    register()
    r = client.post("/auth/register", json={"email": "USER@example.com", "password": PASSWORD})
    assert r.status_code == 409


def test_register_rejects_short_password(client):
    r = client.post("/auth/register", json={"email": "a@example.com", "password": "short"})
    assert r.status_code == 422


def test_register_rejects_bad_email(client):
    r = client.post("/auth/register", json={"email": "not-an-email", "password": PASSWORD})
    assert r.status_code == 422


def test_login_returns_token_pair(tokens):
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] and tokens["refresh_token"]
    assert tokens["expires_in"] > 0


def test_login_wrong_password(client, register):
    register()
    r = client.post("/auth/login", json={"email": "user@example.com", "password": "wrong-password"})
    assert r.status_code == 401


def test_login_unknown_user(client):
    r = client.post("/auth/login", json={"email": "ghost@example.com", "password": PASSWORD})
    assert r.status_code == 401


def test_refresh_rotates_tokens(client, tokens):
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    new = r.json()
    assert new["refresh_token"] != tokens["refresh_token"]
    me = client.get("/users/me", headers={"Authorization": f"Bearer {new['access_token']}"})
    assert me.status_code == 200


def test_refresh_reuse_revokes_whole_family(client, tokens):
    first = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()
    # Replaying the already-rotated token is treated as theft...
    replay = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401
    assert "reuse" in replay.json()["detail"].lower()
    # ...so the legitimate newer token is revoked too.
    r = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 401


def test_access_token_cannot_be_used_as_refresh(client, tokens):
    r = client.post("/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert r.status_code == 401


def test_refresh_token_cannot_be_used_as_access(client, tokens):
    r = client.get("/users/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert r.status_code == 401


def test_garbage_refresh_token(client):
    r = client.post("/auth/refresh", json={"refresh_token": "not.a.jwt"})
    assert r.status_code == 401


def test_logout_revokes_refresh_token(client, tokens):
    r = client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 204
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401
