import json
import os

import pytest
from fastapi.testclient import TestClient

from app.main import app, verify_signature
from app.db import Base, SessionLocal
from app.db import engine


pytestmark = pytest.mark.integration


github_token = os.getenv("GITHUB_TOKEN")
github_owner = os.getenv("GITHUB_OWNER")
github_repo = os.getenv("GITHUB_REPO")
webhook_secret = os.getenv("WEBHOOK_SECRET")

skip_live_tests = not all([github_token, github_owner, github_repo])


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.skipif(skip_live_tests, reason="GitHub live API credentials are not configured")
def test_create_and_get_issue():
    headers = {"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"}
    payload = {"title": "Integration test issue", "body": "Created by pytest"}

    response = __import__("requests").post(
        f"https://api.github.com/repos/{github_owner}/{github_repo}/issues",
        headers=headers,
        json=payload,
        timeout=30,
    )

    assert response.status_code == 201, response.text
    issue = response.json()
    number = issue["number"]

    get_response = __import__("requests").get(
        f"https://api.github.com/repos/{github_owner}/{github_repo}/issues/{number}",
        headers=headers,
        timeout=30,
    )

    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["number"] == number


@pytest.mark.skipif(skip_live_tests, reason="GitHub live API credentials are not configured")
def test_update_issue_and_comment_flow():
    headers = {"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"}
    create_response = __import__("requests").post(
        f"https://api.github.com/repos/{github_owner}/{github_repo}/issues",
        headers=headers,
        json={"title": "Update test issue", "body": "Initial body"},
        timeout=30,
    )
    issue_number = create_response.json()["number"]

    update_response = __import__("requests").patch(
        f"https://api.github.com/repos/{github_owner}/{github_repo}/issues/{issue_number}",
        headers=headers,
        json={"title": "Updated title", "body": "Updated body", "state": "closed"},
        timeout=30,
    )
    assert update_response.status_code == 200, update_response.text

    reopen_response = __import__("requests").patch(
        f"https://api.github.com/repos/{github_owner}/{github_repo}/issues/{issue_number}",
        headers=headers,
        json={"state": "open"},
        timeout=30,
    )
    assert reopen_response.status_code == 200, reopen_response.text

    comment_response = __import__("requests").post(
        f"https://api.github.com/repos/{github_owner}/{github_repo}/issues/{issue_number}/comments",
        headers=headers,
        json={"body": "Integration test comment"},
        timeout=30,
    )
    assert comment_response.status_code == 201, comment_response.text

    comments_response = __import__("requests").get(
        f"https://api.github.com/repos/{github_owner}/{github_repo}/issues/{issue_number}/comments",
        headers=headers,
        timeout=30,
    )
    assert comments_response.status_code == 200, comments_response.text
    assert any(item["body"] == "Integration test comment" for item in comments_response.json())


@pytest.mark.skipif(not webhook_secret, reason="WEBHOOK_SECRET is not configured")
def test_webhook_route_accepts_signed_payload_and_stores_event(client, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app import main as main_module

    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    main_module.Base.metadata.create_all(bind=test_engine)
    monkeypatch.setattr(main_module, "SessionLocal", TestSession)

    payload = {
        "action": "opened",
        "issue": {"number": 42, "created_at": "2024-01-01T00:00:00Z"},
        "repository": {"updated_at": "2024-01-01T00:00:00Z"},
    }
    body = json.dumps(payload).encode("utf-8")
    signature = "sha256=" + __import__('hmac').new(
        webhook_secret.encode("utf-8"),
        body,
        __import__('hashlib').sha256,
    ).hexdigest()

    response = client.post(
        "/webhook",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
            "X-GitHub-Delivery": "abc123",
            "X-GitHub-Event": "issues",
        },
    )

    assert response.status_code == 204
    stored = TestSession().query(main_module.WebhookEvent).all()
    assert len(stored) == 1
    assert stored[0].delivery_id == "abc123"
    assert stored[0].event_type == "issues"
    assert stored[0].issue_number == 42

    listings = client.get("/webhooks")
    assert listings.status_code == 200
    assert listings.json()[0]["delivery_id"] == "abc123"
