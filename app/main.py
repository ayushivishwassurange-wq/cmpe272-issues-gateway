from dotenv import load_dotenv
import os
from urllib.parse import parse_qs, urlparse, parse_qsl
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.github_client import BASE_URL, HEADERS
from app.models import CreateIssueRequest, UpdateIssueRequest, CreateCommentRequest
from app.db import SessionLocal, engine, Base, WebhookEvent
import hmac
import hashlib
import json

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "test-secret")
PORT = os.getenv("PORT")




app = FastAPI()
Base.metadata.create_all(bind=engine)


class GitHubApiError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def map_github_error(response) -> GitHubApiError:
    payload = response.json() if hasattr(response, "json") else {}
    message = payload.get("message") if isinstance(payload, dict) else str(payload)

    if response.status_code == 401:
        return GitHubApiError(401, message or "Unauthorized")
    if response.status_code == 403:
        return GitHubApiError(403, message or "Forbidden")
    if response.status_code == 404:
        return GitHubApiError(404, message or "Not Found")

    return GitHubApiError(response.status_code, message or "GitHub API error")


def parse_link_header(link_header: str | None):
    if not link_header:
        return {}

    links = {}
    for part in link_header.split(","):
        piece = part.strip()
        if ";" not in piece:
            continue
        url, rel = piece.rsplit(";", 1)
        rel = rel.strip()
        if rel.startswith('rel="') and rel.endswith('"'):
            rel_name = rel[5:-1]
            links[rel_name] = url.strip()[1:-1]
    return links


def get_next_page_number(link_header: str | None):
    links = parse_link_header(link_header)
    next_url = links.get("next")
    if not next_url:
        return None

    parsed = urlparse(next_url)
    page_value = parse_qs(parsed.query).get("page", [None])[0]
    if page_value is None:
        return None
    return int(page_value)


@app.exception_handler(GitHubApiError)
async def github_api_error_handler(request, exc: GitHubApiError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message}
    )


def _json_safe_validation_detail(exc: RequestValidationError):
    safe_errors = []
    for error in exc.errors():
        safe_error = {
            "loc": list(error.get("loc", [])),
            "msg": error.get("msg", "Invalid request")
        }
        if "type" in error:
            safe_error["type"] = error["type"]
        if "ctx" in error and error["ctx"]:
            safe_error["ctx"] = {
                key: str(value) if not isinstance(value, (str, int, float, bool, type(None))) else value
                for key, value in error["ctx"].items()
            }
        safe_errors.append(safe_error)
    return safe_errors


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"detail": _json_safe_validation_detail(exc)}
    )


def verify_signature(
    body: bytes,
    signature: str | None
):
    if WEBHOOK_SECRET is None:
        return False

    expected_signature = (
        "sha256=" +
        hmac.new(
            WEBHOOK_SECRET.encode("utf-8"),
            body,
            hashlib.sha256
        ).hexdigest()
    )

    return hmac.compare_digest(
        expected_signature,
        signature or ""
    )

@app.get("/")
def root():
    return {"message": "Service running"}



@app.get("/github-test")
def github_test():
    response = requests.get(BASE_URL, headers=HEADERS)

    return {
        "status_code": response.status_code,
        "data": response.json()
    }


@app.post("/issues", status_code=201)
def create_issue(issue: CreateIssueRequest):

    response = requests.post(
        f"{BASE_URL}/issues",
        headers=HEADERS,
        json=issue.model_dump()
    )

    if response.status_code >= 400:
        raise map_github_error(response)

    return response.json()

@app.get("/issues")
def get_issues(
    state: str = "open",
    page: int = 1,
    per_page: int = 30
):
    response = requests.get(
        f"{BASE_URL}/issues",
        headers=HEADERS,
        params={
            "state": state,
            "page": page,
            "per_page": per_page
        }
    )

    if response.status_code >= 400:
        raise map_github_error(response)

    return response.json()

@app.get("/issues/{number}")
def get_issue(number: int):

    response = requests.get(
        f"{BASE_URL}/issues/{number}",
        headers=HEADERS
    )

    if response.status_code == 404:
        raise GitHubApiError(404, "Issue not found")
    if response.status_code >= 400:
        raise map_github_error(response)

    return response.json()

from fastapi import HTTPException

@app.patch("/issues/{number}")
def update_issue(number: int, issue: UpdateIssueRequest):

    response = requests.patch(
        f"{BASE_URL}/issues/{number}",
        headers=HEADERS,
        json=issue.model_dump(exclude_none=True)
    )

    if response.status_code == 404:
        raise GitHubApiError(404, "Issue not found")
    if response.status_code >= 400:
        raise map_github_error(response)

    return response.json()
@app.post("/issues/{number}/comments", status_code=201)
def add_comment(
    number: int,
    comment: CreateCommentRequest
):

    response = requests.post(
        f"{BASE_URL}/issues/{number}/comments",
        headers=HEADERS,
        json=comment.model_dump()
    )

    if response.status_code == 404:
        raise GitHubApiError(404, "Issue not found")
    if response.status_code >= 400:
        raise map_github_error(response)

    return response.json()


@app.get("/healthz")
def health():
    return {
        "status": "healthy"
    }

@app.post("/webhook", status_code=204)
async def webhook(request: Request):

    body = await request.body()

    signature = request.headers.get("X-Hub-Signature-256")

    if not verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        form_data = parse_qs(body.decode("utf-8"))
        payload = json.loads(form_data["payload"][0])

    delivery_id = request.headers.get("X-GitHub-Delivery")
    event_type = request.headers.get("X-GitHub-Event")

    db = SessionLocal()

    webhook_event = WebhookEvent(
        delivery_id=delivery_id,
        event_type=event_type,
        action=payload.get("action"),
        issue_number=payload.get("issue", {}).get("number"),
        timestamp=payload.get("repository", {}).get("updated_at")
    )

    try:
        db.add(webhook_event)
        db.commit()
    finally:
        db.close()

    return

@app.get("/webhooks")
def get_webhooks():

    db = SessionLocal()

    events = db.query(WebhookEvent).all()

    return [
        {
            "id": e.id,
            "delivery_id": e.delivery_id,
            "event_type": e.event_type,
            "action": e.action,
            "issue_number": e.issue_number,
            "timestamp": e.timestamp
        }
        for e in events
    ]