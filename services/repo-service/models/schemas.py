import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RepoRegister(BaseModel):
    github_url: str


class RepoUpdate(BaseModel):
    usage_notes: str | None = None
    topics: list[str] | None = None


class RepoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    github_url: str
    owner: str
    name: str
    readme: str | None
    claude_md: str | None
    agents_md: str | None
    description: str | None
    usage_notes: str | None
    topics: list
    created_at: datetime
    updated_at: datetime
