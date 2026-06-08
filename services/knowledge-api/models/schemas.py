from pydantic import BaseModel


class MessageItem(BaseModel):
    author: str
    text: str
    timestamp: str


class SaveKnowledgeRequest(BaseModel):
    thread_id: str
    channel: str
    messages: list[MessageItem]
    saved_by: str
    topic: str | None = None
    git_repo: str | None = None


class SaveKnowledgeResponse(BaseModel):
    id: str
    summary: str
    tags: list[str]
    topic: str | None
    git_repo: str | None
    stored: bool


class SearchResult(BaseModel):
    id: str
    summary: str
    tags: list[str]
    topic: str | None
    git_repo: str | None
    channel: str
    saved_by: str
    thread_url: str
    score: float
    created_at: str


class SearchResponse(BaseModel):
    results: list[SearchResult]


class ChatQueryRequest(BaseModel):
    question: str
    user: str
    top_k: int = 3
    topic: str | None = None


class ChatSource(BaseModel):
    id: str
    summary: str
    score: float
    topic: str | None
    channel: str
    created_at: str
    thread_url: str | None = None


class RepoInfo(BaseModel):
    id: str
    github_url: str
    name: str
    description: str | None
    usage_notes: str | None
    topics: list


class ChatQueryResponse(BaseModel):
    type: str = 'answer'  # 'answer' | 'action'
    answer: str | None = None
    sources: list[ChatSource] = []
    repos: list[RepoInfo] = []
    pr_url: str | None = None
    pr_title: str | None = None
    files_changed: list[str] = []
    reasoning: str | None = None
