from pydantic import BaseModel


class RepoContext(BaseModel):
    github_url: str
    name: str
    description: str | None = None
    usage_notes: str | None = None
    readme: str | None = None
    claude_md: str | None = None
    agents_md: str | None = None


class AgentTask(BaseModel):
    task: str
    context: list[str] = []
    repos: list[RepoContext] = []


class AgentResult(BaseModel):
    pr_url: str
    pr_title: str
    files_changed: list[str]
    reasoning: str
