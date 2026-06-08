# Agents Guide

Instructions for AI agents working with this repository.

## What this repo is

A multi-service knowledge base system with three FastAPI services, Qdrant (vector search), and PostgreSQL. Everything runs via `docker-compose up --build` from the project root.

## Services

| Service | Port | Purpose |
|---|---|---|
| `knowledge-base` | 8000 | Receives Slack threads, summarizes with Claude, stores embeddings in Qdrant, answers questions via RAG |
| `repo-service` | 8001 | Stores GitHub repo metadata (README, CLAUDE.md, AGENTS.md, usage notes) in PostgreSQL |
| `coder-agent` | 8002 | Turns natural language tasks into GitHub PRs: plans with Claude, edits files, opens PR |
| Qdrant | 6333 | Vector database for knowledge embeddings and repo embeddings |
| PostgreSQL | 5432 | Relational store for repo metadata |

## How the services talk to each other

```
User → POST /chat/query (knowledge-base)
  → classify intent (Claude)
  → embed question + search Qdrant (knowledge collection)
  → GET /repos/ (repo-service) — fetch repo context for matched git refs
  → if action:
      → search Qdrant (repos collection) — find most relevant repo by embedding
      → POST /agent/task (coder-agent)
          → GitHub API: get default branch, file tree
          → Claude: plan which files to change
          → GitHub API: fetch file content
          → Claude: apply change
          → GitHub API: commit + create PR

User → /learn-it <thread-link> (Slack slash command → POST /slack/save)
  → fetch thread (Slack API)
  → summarize (Claude)
  → embed summary + search repos collection (Qdrant) — auto-detect related repo
  → post draft review to user (confirm / edit / cancel)
  → on confirm: upsert to Qdrant + register repo (repo-service)
```

Knowledge-base calls repo-service and coder-agent via HTTP (`httpx`). All URLs are configured via environment variables: `REPO_SERVICE_URL`, `CODER_AGENT_URL`.

## Key files to know

```
knowledge-base/
├── main.py                        # FastAPI app, lifespan: warm embeddings + ensure Qdrant collections + index repos
├── config.py                      # All env vars in one place
├── routers/
│   ├── knowledge.py               # POST /knowledge/save, GET /knowledge/search
│   ├── chat.py                    # POST /chat/query — intent detection + RAG + action delegation
│   ├── slack.py                   # POST /slack/save, /slack/events, /slack/interact
│   └── internal.py                # POST /internal/index-repo/{repo_id} — index a repo into Qdrant repos collection
├── services/
│   ├── llm_service.py             # Claude: summarize_thread, classify_intent, answer_query
│   ├── embedding_service.py       # sentence-transformers all-MiniLM-L6-v2 (384-dim), lazy-loaded singleton
│   ├── qdrant_service.py          # Qdrant: upsert/search knowledge collection + repos collection
│   ├── repo_client.py             # HTTP client → repo-service (register, list, filter by URL)
│   ├── coder_agent_client.py      # HTTP client → coder-agent (delegate task)
│   ├── slack_service.py           # Slack API calls: fetch thread, post message/blocks/ephemeral, open modal
│   ├── slack_blocks.py            # Builds Slack Block Kit payloads for draft review and edit modal
│   └── pending_store.py           # In-memory TTL store for Slack draft reviews (30 min TTL)
└── models/schemas.py              # All Pydantic request/response models

repo-service/
├── main.py
├── database.py                    # SQLAlchemy async engine, Base, get_session
├── models/
│   ├── db_models.py               # Repo ORM model (postgres table)
│   └── schemas.py                 # Pydantic RepoResponse, RepoRegister, RepoUpdate
├── services/github_service.py     # Fetches README, CLAUDE.md, AGENTS.md from GitHub API
└── routers/repos.py               # CRUD: POST /, GET /, GET /{id}, PATCH /{id}, POST /{id}/sync

coder-agent/
├── main.py
├── models/schemas.py              # AgentTask, AgentResult, RepoContext
├── services/
│   ├── github_service.py          # Read/write GitHub: default branch, file tree, content, branch, commit, PR
│   ├── planner_service.py         # Claude: decides which files to change, returns files_to_change + pr_title + commit_message
│   └── coder_service.py           # Claude: applies the actual code change, returns full new file content
└── routers/agent.py               # POST /agent/task — orchestrates plan → fetch → apply → commit → PR
```

## Making changes

### Adding a new endpoint

1. Add Pydantic models to the relevant `models/schemas.py`
2. Add the route function to the relevant `routers/` file with a return type annotation
3. Register it in `main.py` if it's a new router

### Adding a new service dependency

1. Add to `requirements.txt`
2. Import and use — pip installs on `docker-compose up --build`

### Adding a new environment variable

1. Add to `config.py` with `os.getenv('VAR_NAME', 'default')`
2. Add to `.env.example` with an empty or example value
3. Add to the relevant service's `environment:` block in `docker-compose.yml` if it needs to be overridden per-container (e.g. internal Docker hostnames)

### Changing the Qdrant collection schema

Qdrant is schemaless for payload fields — add new fields to the `payload` dict in the relevant router or service. No migration needed. Two collections exist: `knowledge` (from `config.COLLECTION_NAME`) and `repos`.

### Changing the PostgreSQL schema

The schema is created by `Base.metadata.create_all` on startup. Adding new nullable columns to `repo-service/models/db_models.py` requires resetting the volume:

```bash
docker-compose down -v
docker-compose up --build
```

For production, use Alembic migrations instead.

## Conventions

### FastAPI

- Always use `Annotated` style for Query params and dependencies — never use `= Query(...)` or `= Depends(...)` directly on the parameter default
- Create a named type alias for reused dependencies: `SessionDep = Annotated[AsyncSession, Depends(get_session)]`
- Always include a return type annotation on route functions; omit `response_model=` on the decorator when the return type matches exactly
- Use `async def` route functions only when the body actually awaits async calls; use plain `def` for sync-only logic (runs in threadpool automatically)
- Register prefix, tags, and shared dependencies on the `APIRouter` itself, not in `include_router()`

### Async / threading

- Wrap all sync blocking calls (Claude SDK via LangChain, sentence-transformers, Qdrant client) with `asyncio.to_thread()` — never call them directly inside `async def`
- Inter-service HTTP calls use `httpx.AsyncClient` with explicit timeouts

### Error handling

- Try blocks must be as small as possible — one operation per try block
- Every `except` block must act: raise `HTTPException`, log with `print(..., flush=True)`, return a fallback value, or post a notification. Never use bare `except: pass`
- Use specific exception types where available (`ValueError`, `httpx.HTTPStatusError`) instead of catching `Exception`
- In background tasks (Slack handlers), log failures with `[service] function: detail` prefix and continue or notify the user

### Graceful degradation

- `repo-service` and `coder-agent` being unreachable must never break knowledge-base core functionality
- `repo_client.py` functions return empty lists on failure (with a log) rather than raising
- Startup indexing (`index_all_repos`) logs failures per-repo and continues

### LLM / Claude

- Claude calls include `cache_control: ephemeral` on system prompts
- LLM clients are instantiated per-call (stateless); no global LLM singleton
- Structured output via `.with_structured_output(PydanticModel)` for JSON responses; `StrOutputParser` for free-text

### Configuration

- All environment variables are loaded via `config.py` — never call `os.getenv()` directly in service or router files

## PR conventions (for coder-agent)

- Branch prefix: `claude-agent/`
- Commit messages: `claude-agent: <short description>`
- Keep PRs focused — one logical change per PR, max 5 files
- PR description must explain what changed and why, not just what
- Never modify `docker-compose.yml`, `.env`, or `AGENTS.md` autonomously
