"""
Auth and multi-tenancy tests against the real FastAPI app (via TestClient,
which drives the actual routes/dependencies -- not a reimplementation).
Mirrors the manual end-to-end auth verification, as an automated
regression suite so future changes can't silently reintroduce a
cross-user data leak.
"""


def signup(client, email="alice@acme.test", password="CorrectHorse123!", name="Alice"):
    resp = client.post("/api/auth/signup", json={"email": email, "password": password, "name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_signup_returns_token_and_user(client):
    resp = client.post("/api/auth/signup", json={"email": "new@acme.test", "password": "CorrectHorse123!", "name": "New"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == "new@acme.test"
    assert body["access_token"]


def test_signup_rejects_duplicate_email(client):
    signup(client, email="dup@acme.test")
    resp = client.post("/api/auth/signup", json={"email": "dup@acme.test", "password": "AnotherPassword1!"})
    assert resp.status_code == 409


def test_signup_rejects_weak_password(client):
    resp = client.post("/api/auth/signup", json={"email": "weak@acme.test", "password": "short"})
    assert resp.status_code == 400


def test_signup_rejects_invalid_email(client):
    resp = client.post("/api/auth/signup", json={"email": "not-an-email", "password": "CorrectHorse123!"})
    assert resp.status_code == 400


def test_login_with_correct_password(client):
    signup(client, email="login@acme.test", password="CorrectHorse123!")
    resp = client.post("/api/auth/login", json={"email": "login@acme.test", "password": "CorrectHorse123!"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_with_wrong_password_rejected(client):
    signup(client, email="login2@acme.test", password="CorrectHorse123!")
    resp = client.post("/api/auth/login", json={"email": "login2@acme.test", "password": "wrongpassword"})
    assert resp.status_code == 401


def test_login_nonexistent_user_same_error_as_wrong_password(client):
    """Same 401 for both cases so login can't be used to enumerate emails."""
    resp = client.post("/api/auth/login", json={"email": "nobody@acme.test", "password": "whatever123"})
    assert resp.status_code == 401
    assert "incorrect" in resp.json()["detail"].lower()


def test_me_requires_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_with_valid_token(client):
    token = signup(client, email="me@acme.test")
    resp = client.get("/api/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@acme.test"


def test_garbage_token_rejected(client):
    resp = client.get("/api/projects", headers=auth_headers("garbage.token.value"))
    assert resp.status_code == 401


def test_projects_require_auth(client):
    resp = client.get("/api/projects")
    assert resp.status_code == 401


def test_user_sees_only_their_own_projects(client):
    token_a = signup(client, email="alice2@acme.test")
    token_b = signup(client, email="bob2@blueridge.test")

    client.post("/api/projects", json={"name": "Alice's Deal"}, headers=auth_headers(token_a))
    client.post("/api/projects", json={"name": "Bob's Deal"}, headers=auth_headers(token_b))

    resp = client.get("/api/projects", headers=auth_headers(token_a))
    names = [p["name"] for p in resp.json()]
    assert names == ["Alice's Deal"]


def test_cross_user_project_access_returns_404_not_403(client):
    """404, not 403 -- so a guessed/enumerated ID can't be used to
    confirm a resource exists but belongs to someone else."""
    token_a = signup(client, email="alice3@acme.test")
    token_b = signup(client, email="bob3@blueridge.test")

    create_resp = client.post("/api/projects", json={"name": "Alice's Deal"}, headers=auth_headers(token_a))
    project_id = create_resp.json()["id"]

    resp = client.get(f"/api/projects/{project_id}", headers=auth_headers(token_b))
    assert resp.status_code == 404


def test_cross_user_document_upload_rejected(client):
    token_a = signup(client, email="alice4@acme.test")
    token_b = signup(client, email="bob4@blueridge.test")

    create_resp = client.post("/api/projects", json={"name": "Alice's Deal"}, headers=auth_headers(token_a))
    project_id = create_resp.json()["id"]

    resp = client.post(
        "/api/documents/upload",
        params={"project_id": project_id},
        files={"file": ("test.pdf", b"%PDF-1.4 fake")},
        headers=auth_headers(token_b),
    )
    assert resp.status_code == 404


def test_own_project_access_succeeds(client):
    token = signup(client, email="alice5@acme.test")
    create_resp = client.post("/api/projects", json={"name": "My Deal"}, headers=auth_headers(token))
    project_id = create_resp.json()["id"]

    resp = client.get(f"/api/projects/{project_id}", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["name"] == "My Deal"
