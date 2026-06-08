#!/usr/bin/env python3
"""
Knowledge Base API — FastAPI + Qdrant + Claude.

Exposes endpoints for saving Slack thread knowledge and querying it via chat.
For usage details run the server and visit /docs.

Prerequisites:
  - Qdrant running locally (docker-compose up -d)
  - ANTHROPIC_API_KEY set in .env
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from routers import chat, internal, knowledge, slack
from services import embedding_service, qdrant_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(embedding_service.get_embeddings)
    await asyncio.to_thread(qdrant_service.ensure_collection)
    await asyncio.to_thread(qdrant_service.ensure_repos_collection)
    await internal.index_all_repos()
    yield


app = FastAPI(title='Knowledge Base API', lifespan=lifespan)

app.include_router(knowledge.router)
app.include_router(chat.router)
app.include_router(slack.router)
app.include_router(internal.router)


@app.get('/health', tags=['health'])
async def health() -> dict:
    ok = await asyncio.to_thread(qdrant_service.health_check)
    if ok:
        return {'status': 'ok', 'qdrant': 'connected'}
    return JSONResponse(
        status_code=503,
        content={'status': 'degraded', 'qdrant': 'unreachable'},
    )
