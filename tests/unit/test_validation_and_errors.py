import pytest
from fastapi.testclient import TestClient

from app.main import app, GitHubApiError, map_github_error


client = TestClient(app)


def test_missing_title_returns_400():
    response = client.post("/issues", json={})
    assert response.status_code == 400


def test_invalid_state_returns_400():
    response = client.patch("/issues/1", json={"state": "pending"})
    assert response.status_code == 400


def test_map_github_error_maps_known_status_codes():
    response = type(
        "Response",
        (),
        {"status_code": 401, "json": lambda self: {"message": "Bad credentials"}}
    )()

    error = map_github_error(response)

    assert isinstance(error, GitHubApiError)
    assert error.status_code == 401
    assert error.message == "Bad credentials"

    response = type(
        "Response",
        (),
        {"status_code": 403, "json": lambda self: {"message": "API rate limit exceeded"}}
    )()

    error = map_github_error(response)
    assert error.status_code == 403
    assert error.message == "API rate limit exceeded"

    response = type(
        "Response",
        (),
        {"status_code": 404, "json": lambda self: {"message": "Not Found"}}
    )()

    error = map_github_error(response)
    assert error.status_code == 404
    assert error.message == "Not Found"
