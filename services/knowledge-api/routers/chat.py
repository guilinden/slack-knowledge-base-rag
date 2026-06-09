services/knowledge-api/routers/chat.py
```python
import asyncio

from fastapi import APIRouter, HTTPException

from models.schemas import ChatQueryRequest, ChatQueryResponse, ChatSource, RepoInfo
from services import (
    coder_agent_client,
    embedding_service,
    llm_service,
    qdrant_service,
    repo_client,
)

router = APIRouter(prefix='/chat', tags=['chat'])


@router.post('/query', response_model=ChatQueryResponse)
async def chat_query(body: ChatQueryRequest) -> ChatQueryResponse:
    # Classify intent before anything else
    try:
        intent = await asyncio.to_thread(llm_service.classify_intent, body.question)
    except Exception:
        intent = 'question'

    # --- HyDE: generate a hypothetical answer and embed it for richer retrieval ---
    try:
        hypothetical_answer = await asyncio.to_thread(
            llm_service.generate_hypothetical_answer, body.question
        )
        hyde_text = f"{body.question}\n\n{hypothetical_answer}"
        vector = await asyncio.to_thread(embedding_service.embed_text, hyde_text)
    except Exception:
        # Fall back to plain question embedding if HyDE fails
        try:
            vector = await asyncio.to_thread(embedding_service.embed_text, body.question)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'Embedding failed: {e}')

    try:
        hits = await asyncio.to_thread(qdrant_service.search_points, vector, body.top_k, body.topic)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Search failed: {e}')

    sources = [
        ChatSource(
            id=str(hit.id),
            summary=hit.payload.get('summary', ''),
            score=hit.score,
            topic=hit.payload.get('topic'),
            channel=hit.payload.get('channel', ''),
            created_at=hit.payload.get('created_at', ''),
            thread_url=hit.payload.get('thread_url'),
        )
        for hit in hits
    ]

    # Fetch repo details for all git_repo refs found in results
    git_refs = [hit.payload.get('git_repo') for hit in hits if hit.payload.get('git_repo')]
    raw_repos = await repo_client.get_repos_for_refs(git_refs)
    repos = [
        RepoInfo(
            id=str(r['id']),
            github_url=r['github_url'],
            name=r['name'],
            description=r.get('description'),
            usage_notes=r.get('usage_notes'),
            topics=r.get('topics', []),
        )
        for r in raw_repos
    ]

    if intent == 'action':
        # Find relevant repos via vector similarity search
        repo_hits = await asyncio.to_thread(qdrant_service.search_repos, vector, 3)
        if repo_hits:
            github_urls = [h.payload['github_url'] for h in repo_hits]
            raw_repos = await repo_client.get_repos_for_refs(github_urls)
        if not raw_repos:
            raw_repos = await repo_client.get_all_repos()
        repos = [
            RepoInfo(
                id=str(r['id']),
                github_url=r['github_url'],
                name=r['name'],
                description=r.get('description'),
                usage_notes=r.get('usage_notes'),
                topics=r.get('topics', []),
            )
            for r in raw_repos
        ]
        return await _handle_action(body.question, hits, raw_repos, sources, repos)

    return await _handle_question(body.question, hits, raw_repos, sources, repos)


async def _handle_question(
    question: str,
    hits: list,
    raw_repos: list[dict],
    sources: list[ChatSource],
    repos: list[RepoInfo],
) -> ChatQueryResponse:
    context_chunks = [{'summary': hit.payload.get('summary', '')} for hit in hits]
    repo_context = _build_repo_context(raw_repos)

    try:
        answer = await asyncio.to_thread(
            llm_service.answer_query, question, context_chunks, repo_context
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f'LLM query failed: {e}')

    return ChatQueryResponse(type='answer', answer=answer, sources=sources, repos=repos)


async def _handle_action(
    task: str,
    hits: list,
    raw_repos: list[dict],
    sources: list[ChatSource],
    repos: list[RepoInfo],
) -> ChatQueryResponse:
    context = [hit.payload.get('summary', '') for hit in hits if hit.payload.get('summary')]

    if not raw_repos:
        raise HTTPException(
            status_code=422,
            detail='No repos registered. Register a repo first via the repo service.',
        )

    try:
        result = await coder_agent_client.delegate(task, context, raw_repos)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f'Coder agent failed: {e}')

    return ChatQueryResponse(
        type='action',
        sources=sources,
        repos=repos,
        pr_url=result.get('pr_url'),
        pr_title=result.get('pr_title'),
        files_changed=result.get('files_changed', []),
        reasoning=result.get('reasoning'),
    )


def _build_repo_context(raw_repos: list[dict]) -> list[dict]:
    return [
        {
            'name': r['name'],
            'github_url': r['github_url'],
            'description': r.get('description'),
            'usage_notes': r.get('usage_notes'),
            'readme': r.get('readme'),
        }
        for r in raw_repos
    ]
```