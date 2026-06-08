# API Reference

## Services

| Service | Base URL |
|---|---|
| knowledge-base | `http://localhost:8000` |
| repo-service | `http://localhost:8001` |
| coder-agent | `http://localhost:8002` |

---

## Health

### GET /health *(all services)*

```bash
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
```

**Response 200** — knowledge-base
```json
{ "status": "ok", "qdrant": "connected" }
```

**Response 503** — Qdrant unreachable (knowledge-base only)
```json
{ "status": "degraded", "qdrant": "unreachable" }
```

**Response 200** — repo-service / coder-agent
```json
{ "status": "ok" }
```

---

## Knowledge — `http://localhost:8000`

### POST /knowledge/save

Summarize a Slack thread and store it in Qdrant. `topic` and `git_repo` are optional.

```bash
curl -X POST http://localhost:8000/knowledge/save \
  -H 'Content-Type: application/json' \
  -d '{
    "thread_id": "C01234-1717000000.000100",
    "channel": "engineering",
    "topic": "infrastructure",
    "git_repo": "myorg/platform",
    "messages": [
      {"author": "ana",   "text": "Should we use Kafka or RabbitMQ?",              "timestamp": "2024-01-10T10:00:00Z"},
      {"author": "pedro", "text": "Kafka makes more sense given our volume needs.", "timestamp": "2024-01-10T10:05:00Z"},
      {"author": "ana",   "text": "Agreed, lets go with Kafka then.",              "timestamp": "2024-01-10T10:08:00Z"}
    ],
    "saved_by": "ana"
  }'
```

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `thread_id` | string | yes | Unique identifier for the Slack thread |
| `channel` | string | yes | Slack channel name |
| `messages` | array | yes | List of `{author, text, timestamp}` objects |
| `saved_by` | string | yes | User who triggered the save |
| `topic` | string | no | Topic or category (e.g. `infrastructure`, `backend`) |
| `git_repo` | string | no | Related git repository (e.g. `myorg/platform`) |

**Response 200**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "summary": "The team decided to use Kafka over RabbitMQ for their messaging infrastructure, driven by volume requirements.",
  "tags": ["kafka", "rabbitmq", "messaging", "architecture", "decision"],
  "topic": "infrastructure",
  "git_repo": "myorg/platform",
  "stored": true
}
```

**Error responses**

| Status | Meaning |
|---|---|
| 502 | LLM summarization failed or returned empty result |
| 500 | Embedding or Qdrant storage failed |

---

### GET /knowledge/search

Semantic search over stored knowledge. Filter by `topic` to scope results.

```bash
# Search across all topics
curl 'http://localhost:8000/knowledge/search?q=kafka&limit=5'

# Scope to a topic
curl 'http://localhost:8000/knowledge/search?q=kafka&topic=infrastructure&limit=5'
```

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `q` | string | required | Search query (min length 1) |
| `limit` | integer | `5` | Max results (1–20) |
| `topic` | string | — | Filter results to a specific topic |

**Response 200**
```json
{
  "results": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "summary": "The team decided to use Kafka over RabbitMQ ...",
      "tags": ["kafka", "messaging", "architecture"],
      "topic": "infrastructure",
      "git_repo": "myorg/platform",
      "channel": "engineering",
      "saved_by": "ana",
      "thread_url": "slack://engineering/C01234-1717000000.000100",
      "score": 0.91,
      "created_at": "2024-01-10T10:10:00.000000+00:00"
    }
  ]
}
```

---

## Chat — `http://localhost:8000`

### POST /chat/query

Ask a natural language question or request an action. The service classifies the intent automatically:

- **`question`** — searches the knowledge base and returns an LLM answer with sources
- **`action`** — delegates the task to the coder-agent, which opens a GitHub PR

```bash
curl -X POST http://localhost:8000/chat/query \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "What did we decide about our messaging infrastructure?",
    "user": "joao",
    "top_k": 3,
    "topic": "infrastructure"
  }'
```

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `question` | string | required | Natural language question or action request |
| `user` | string | required | User asking the question |
| `top_k` | integer | `3` | Number of knowledge chunks to use as context |
| `topic` | string | — | Restrict context retrieval to a specific topic |

**Response 200 — answer**
```json
{
  "type": "answer",
  "answer": "Your team decided to use Kafka over RabbitMQ for your messaging infrastructure. The decision was driven by volume requirements.",
  "sources": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "summary": "The team decided to use Kafka over RabbitMQ ...",
      "score": 0.91,
      "topic": "infrastructure",
      "channel": "engineering",
      "created_at": "2024-01-10T10:10:00.000000+00:00",
      "thread_url": "slack://engineering/1717000000.000100"
    }
  ],
  "repos": [
    {
      "id": "a1b2c3d4-...",
      "github_url": "https://github.com/myorg/platform",
      "name": "platform",
      "description": "Core infrastructure platform",
      "usage_notes": "Use for all infra changes",
      "topics": ["infrastructure", "kafka"]
    }
  ]
}
```

**Response 200 — action** (when the question is interpreted as a task to perform)
```json
{
  "type": "action",
  "sources": [...],
  "repos": [...],
  "pr_url": "https://github.com/myorg/platform/pull/42",
  "pr_title": "Update Kafka consumer config",
  "files_changed": ["config/kafka.yaml"],
  "reasoning": "Changed max.poll.records to 500 based on the team's decision to increase throughput."
}
```

**Error responses**

| Status | Meaning |
|---|---|
| 500 | Embedding failed |
| 500 | Qdrant search failed |
| 502 | LLM answer generation failed |
| 502 | Coder-agent delegation failed |
| 422 | Action requested but no repos are registered |

---

## Slack — `http://localhost:8000`

### POST /slack/save

Receives the `/learn-it` slash command. Configure this URL in your Slack App's slash command settings.

Responds immediately (within Slack's 3-second window) and processes the thread in the background. The result is a draft posted back to the user with **Confirm**, **Edit**, and **Cancel** buttons before anything is saved to the knowledge base.

**Usage in Slack**

```
/learn-it <thread-link>           # saves with no topic
/learn-it <thread-link> infra     # saves and tags with topic "infra"
```

Right-click any message → Copy link, then paste it after `/learn-it`.

**Immediate response (ephemeral)**
```json
{ "response_type": "ephemeral", "text": "Summarizing thread... I'll send a draft for your review." }
```

**Delayed response** — sent via `response_url` once summarization completes

Slack block message with the generated summary, tags, detected repository, and three action buttons:

- **Confirm** — saves the draft to the knowledge base as-is
- **Edit** — opens a modal to edit summary, tags, and repository before saving
- **Cancel** — discards the draft

---

### POST /slack/events

Events API endpoint. Configure this URL in your Slack App's **Event Subscriptions** settings and subscribe to `app_mention`.

When the bot is mentioned inside a thread, it saves that thread to the knowledge base (same draft review flow as `/learn-it`). Mentioning the bot outside a thread returns an ephemeral guidance message.

Handles Slack's one-time URL verification challenge automatically.

**Slack app setup**

1. Enable **Event Subscriptions** and set the Request URL to `https://<your-host>/slack/events`
2. Subscribe to the `app_mention` bot event
3. Re-install the app after saving

---

### POST /slack/interact

Interactivity endpoint. Configure this URL in your Slack App's **Interactivity & Shortcuts** settings.

Handles:
- **`block_actions`** — Confirm / Edit / Cancel button clicks on draft review messages
- **`view_submission`** — Modal submit after editing a draft

**Slack app setup**

1. Enable **Interactivity** and set the Request URL to `https://<your-host>/slack/interact`

---

### Slack app full setup

1. Create a Slack App at [api.slack.com/apps](https://api.slack.com/apps)
2. Under **OAuth & Permissions**, add bot scopes: `channels:history`, `groups:history`, `chat:write`, `chat:write.public`
3. Install the app to your workspace and copy the **Bot User OAuth Token** → `SLACK_BOT_TOKEN` in `.env`
4. Under **Basic Information**, copy the **Signing Secret** → `SLACK_SIGNING_SECRET` in `.env`
5. Under **Slash Commands**, create `/learn-it` pointing to `https://<your-host>/slack/save`
6. Under **Event Subscriptions**, set Request URL to `https://<your-host>/slack/events`, subscribe to `app_mention`
7. Under **Interactivity & Shortcuts**, set Request URL to `https://<your-host>/slack/interact`

---

## Repo Service — `http://localhost:8001`

Stores GitHub repository metadata (README, CLAUDE.md, AGENTS.md, description, topics) in PostgreSQL. The knowledge-base service calls it to enrich chat responses with repo context.

### POST /repos/

Register a GitHub repository. Fetches metadata from the GitHub API on first registration. If the URL is already registered, returns the existing record.

```bash
curl -X POST http://localhost:8001/repos/ \
  -H 'Content-Type: application/json' \
  -d '{"github_url": "myorg/platform"}'
```

Accepts full URLs (`https://github.com/myorg/platform`), short slugs (`myorg/platform`), or anything with `github.com` in it — all are normalized to `https://github.com/owner/name`.

**Response 200**
```json
{
  "id": "a1b2c3d4-...",
  "github_url": "https://github.com/myorg/platform",
  "owner": "myorg",
  "name": "platform",
  "description": "Core infrastructure platform",
  "readme": "# platform\n...",
  "claude_md": null,
  "agents_md": null,
  "usage_notes": null,
  "topics": ["infrastructure"],
  "created_at": "2024-01-10T10:00:00",
  "updated_at": "2024-01-10T10:00:00"
}
```

**Error responses**

| Status | Meaning |
|---|---|
| 400 | Invalid or unparseable GitHub URL |
| 502 | GitHub API fetch failed |

---

### GET /repos/

List all registered repositories. Filter by exact URL with `github_url`.

```bash
curl http://localhost:8001/repos/
curl 'http://localhost:8001/repos/?github_url=https://github.com/myorg/platform'
```

**Response 200** — array of repo objects (same shape as POST response)

---

### GET /repos/{repo_id}

Fetch a single repository by its UUID.

```bash
curl http://localhost:8001/repos/a1b2c3d4-5717-4562-b3fc-2c963f66afa6
```

**Response 404**
```json
{ "detail": "Repo not found" }
```

---

### PATCH /repos/{repo_id}

Update the team's usage notes or topic tags. These are the only fields editable after registration — all other fields come from GitHub and are refreshed via `/sync`.

```bash
curl -X PATCH http://localhost:8001/repos/a1b2c3d4-... \
  -H 'Content-Type: application/json' \
  -d '{"usage_notes": "Use for all infra changes.", "topics": ["infrastructure", "kafka"]}'
```

**Request body** (all fields optional)

| Field | Type | Description |
|---|---|---|
| `usage_notes` | string | Free-text team notes surfaced in chat context |
| `topics` | array of strings | Topic tags for filtering |

---

### POST /repos/{repo_id}/sync

Re-fetch README, CLAUDE.md, AGENTS.md, description, and topics from GitHub. Use after a repo's docs change significantly.

```bash
curl -X POST http://localhost:8001/repos/a1b2c3d4-.../sync
```

---

## Coder Agent — `http://localhost:8002`

Turns natural language tasks into GitHub PRs. Called automatically by the knowledge-base when `/chat/query` classifies intent as `action`. Can also be called directly.

### POST /agent/task

```bash
curl -X POST http://localhost:8002/agent/task \
  -H 'Content-Type: application/json' \
  -d '{
    "task": "Increase Kafka max.poll.records to 500 in the consumer config",
    "context": [
      "Team decided to increase Kafka throughput in the 2024-01-10 infra discussion."
    ],
    "repos": [
      {
        "github_url": "https://github.com/myorg/platform",
        "name": "platform",
        "description": "Core infrastructure platform",
        "usage_notes": "Use for all infra changes.",
        "readme": "# platform\n...",
        "claude_md": null,
        "agents_md": null
      }
    ]
  }'
```

**Request body**

| Field | Type | Description |
|---|---|---|
| `task` | string | Natural language description of what to change |
| `context` | array of strings | Relevant knowledge base summaries (optional) |
| `repos` | array | Repo objects with `github_url`, `name`, and optional `description`, `usage_notes`, `readme`, `claude_md`, `agents_md` |

The first repo in the array is used as the target. The knowledge-base selects the most relevant repo before calling this endpoint.

**Response 200**
```json
{
  "pr_url": "https://github.com/myorg/platform/pull/42",
  "pr_title": "Update Kafka consumer config",
  "files_changed": ["config/kafka.yaml"],
  "reasoning": "Changed max.poll.records from 100 to 500 based on the team's throughput decision."
}
```

**Error responses**

| Status | Meaning |
|---|---|
| 400 | No repos provided or unparseable GitHub URL |
| 422 | Planner could not identify files to change |
| 502 | GitHub API error (read, branch, commit, or PR) |
| 502 | Planning or code generation failed |
