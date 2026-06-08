import asyncio
import uuid
from datetime import datetime, timezone

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from models.schemas import (
    SaveKnowledgeRequest,
    SaveKnowledgeResponse,
    SearchResponse,
    SearchResult,
)
from services import embedding_service, llm_service, qdrant_service, repo_client

router = APIRouter(prefix='/knowledge', tags=['knowledge'])


@router.post('/save', response_model=SaveKnowledgeResponse)
async def save_knowledge(body: SaveKnowledgeRequest) -> SaveKnowledgeResponse:
    messages = [m.model_dump() for m in body.messages]

    try:
        result = await asyncio.to_thread(llm_service.summarize_thread, messages)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f'LLM summarization failed: {e}')

    summary: str = result.get('summary', '')
    tags: list[str] = result.get('tags', [])

    if not summary:
        raise HTTPException(status_code=502, detail='LLM returned empty summary')

    try:
        vector = await asyncio.to_thread(embedding_service.embed_text, summary)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Embedding failed: {e}')

    point_id = str(uuid.uuid4())
    payload = {
        'summary': summary,
        'raw_messages': messages,
        'tags': tags,
        'topic': body.topic,
        'git_repo': body.git_repo,
        'channel': body.channel,
        'thread_id': body.thread_id,
        'saved_by': body.saved_by,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'thread_url': f'slack://{body.channel}/{body.thread_id}',
    }

    try:
        await asyncio.to_thread(qdrant_service.upsert_point, point_id, vector, payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Storage failed: {e}')

    if body.git_repo:
        await repo_client.register_repo(body.git_repo)

    return SaveKnowledgeResponse(
        id=point_id,
        summary=summary,
        tags=tags,
        topic=body.topic,
        git_repo=body.git_repo,
        stored=True,
    )


@router.get('/search', response_model=SearchResponse)
async def search_knowledge(
    q: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    topic: Annotated[str | None, Query()] = None,
) -> SearchResponse:
    try:
        vector = await asyncio.to_thread(embedding_service.embed_text, q)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Embedding failed: {e}')

    try:
        hits = await asyncio.to_thread(qdrant_service.search_points, vector, limit, topic)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Search failed: {e}')

    results = [
        SearchResult(
            id=str(hit.id),
            summary=hit.payload.get('summary', ''),
            tags=hit.payload.get('tags', []),
            topic=hit.payload.get('topic'),
            git_repo=hit.payload.get('git_repo'),
            channel=hit.payload.get('channel', ''),
            saved_by=hit.payload.get('saved_by', ''),
            thread_url=hit.payload.get('thread_url', ''),
            score=hit.score,
            created_at=hit.payload.get('created_at', ''),
        )
        for hit in hits
    ]

    return SearchResponse(results=results)
