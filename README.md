# Knowledge Base API

REST API for saving summarized Slack thread knowledge and querying it via chat. Built with FastAPI, Qdrant, and Claude.

## Setup

### 1. Start Qdrant

```bash
docker-compose up -d
```

Qdrant will be available at `http://localhost:6333`. Data persists in a named Docker volume.

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

The first run will download the `all-MiniLM-L6-v2` embedding model (~90 MB).

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your `ANTHROPIC_API_KEY`. All other defaults work for local development.

### 4. Run the server

```bash
uvicorn main:app --reload
```

Server starts at `http://localhost:8000`. Interactive docs available at `http://localhost:8000/docs`.

On startup the server will:
- Download and cache the sentence-transformer model (first run only)
- Create the `knowledge` Qdrant collection if it does not exist

---

## Endpoints

### Health check

```bash
curl http://localhost:8000/health
```

```json
{"status": "ok", "qdrant": "connected"}
```

---

### POST /knowledge/save

Save a Slack thread. Claude summarizes it, extracts tags, and stores the embedding in Qdrant.

```bash
curl -X POST http://localhost:8000/knowledge/save \
  -H 'Content-Type: application/json' \
  -d '{
    "thread_id": "C01234-1717000000.000100",
    "channel": "engineering",
    "messages": [
      {"author": "ana",   "text": "Should we use Kafka or RabbitMQ?",                "timestamp": "2024-01-10T10:00:00Z"},
      {"author": "pedro", "text": "Kafka makes more sense given our volume needs",   "timestamp": "2024-01-10T10:05:00Z"},
      {"author": "ana",   "text": "Agreed, lets go with Kafka then",                 "timestamp": "2024-01-10T10:08:00Z"}
    ],
    "saved_by": "ana"
  }'
```

```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "summary": "The team decided to use Kafka over RabbitMQ for their messaging infrastructure, driven by volume requirements.",
  "tags": ["kafka", "rabbitmq", "messaging", "architecture", "decision"],
  "stored": true
}
```

---

### GET /knowledge/search

Semantic search over stored knowledge.

```bash
curl 'http://localhost:8000/knowledge/search?q=kafka&limit=5'
```

```json
{
  "results": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "summary": "The team decided to use Kafka over RabbitMQ ...",
      "tags": ["kafka", "messaging", "architecture"],
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

### POST /chat/query

Ask a natural language question. Claude answers using retrieved knowledge as context.

```bash
curl -X POST http://localhost:8000/chat/query \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "What did we decide about our messaging infrastructure?",
    "user": "joao",
    "top_k": 3
  }'
```

```json
{
  "answer": "Your team decided to use Kafka over RabbitMQ for your messaging infrastructure. The decision was driven by volume requirements.",
  "sources": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "summary": "The team decided to use Kafka over RabbitMQ ...",
      "score": 0.91,
      "channel": "engineering",
      "created_at": "2024-01-10T10:10:00.000000+00:00"
    }
  ]
}
```

---

## Architecture

```
POST /knowledge/save  →  Claude (summarize + tag)  →  all-MiniLM-L6-v2 (embed)  →  Qdrant (store)
GET  /knowledge/search →  all-MiniLM-L6-v2 (embed)  →  Qdrant (cosine search)
POST /chat/query      →  all-MiniLM-L6-v2 (embed)  →  Qdrant (top-k)  →  Claude (answer with context)
```

Qdrant collection: `knowledge`, vector size 384, cosine distance.
