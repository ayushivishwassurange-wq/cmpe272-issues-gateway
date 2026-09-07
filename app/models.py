from pydantic import BaseModel, field_validator
from typing import Optional, List
from sqlalchemy import Column, Integer, String
from app.db import Base


class CreateIssueRequest(BaseModel):
    title: str
    body: Optional[str] = None
    labels: Optional[List[str]] = []


class UpdateIssueRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    state: Optional[str] = None

    @field_validator("state")
    @classmethod
    def validate_state(cls, value):
        if value is not None and value not in ["open", "closed"]:
            raise ValueError(
                "state must be 'open' or 'closed'"
            )
        return value

class CreateCommentRequest(BaseModel):
    body: str

