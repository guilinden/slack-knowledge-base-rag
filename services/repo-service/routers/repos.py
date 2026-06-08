import asyncio
import uuid
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from database import get_session
from models.db_models import Repo
from models.schemas import RepoRegister, RepoResponse, RepoUpdate
from services import github_service

router = APIRouter(prefix='/repos', tags=['repos'])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _notify_index(repo_id: str) -> None:
    if not config.APP_URL:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f'{config.APP_URL}/internal/index-repo/{repo_id}',
                timeout=10.0,
            )
    except Exception as e:
        print(f'[repo] _notify_index failed for repo_id={repo_id}: {e}', flush=True)


@router.post('/', response_model=RepoResponse)
async def register_repo(
    body: RepoRegister,
    session: SessionDep,
) -> Repo:
    normalized = github_service.normalize_url(body.github_url)

    result = await session.execute(select(Repo).where(Repo.github_url == normalized))
    existing = result.scalar_one_or_none()
    if existing:
        return existing

    try:
        owner, name = github_service.parse_github_url(normalized)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f'Invalid GitHub URL: {e}')

    try:
        info = await github_service.fetch_repo(owner, name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f'GitHub fetch failed: {e}')

    repo = Repo(
        id=uuid.uuid4(),
        github_url=normalized,
        owner=owner,
        name=name,
        readme=info['readme'],
        claude_md=info['claude_md'],
        agents_md=info['agents_md'],
        description=info['description'],
        topics=info['topics'],
    )
    session.add(repo)
    await session.commit()
    await session.refresh(repo)
    asyncio.create_task(_notify_index(str(repo.id)))
    return repo


@router.get('/', response_model=list[RepoResponse])
async def list_repos(
    session: SessionDep,
    github_url: Annotated[str | None, Query()] = None,
) -> list[Repo]:
    query = select(Repo)
    if github_url:
        normalized = github_service.normalize_url(github_url)
        query = query.where(Repo.github_url == normalized)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get('/{repo_id}', response_model=RepoResponse)
async def get_repo(repo_id: str, session: SessionDep) -> Repo:
    result = await session.execute(select(Repo).where(Repo.id == uuid.UUID(repo_id)))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail='Repo not found')
    return repo


@router.patch('/{repo_id}', response_model=RepoResponse)
async def update_repo(
    repo_id: str,
    body: RepoUpdate,
    session: SessionDep,
) -> Repo:
    result = await session.execute(select(Repo).where(Repo.id == uuid.UUID(repo_id)))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail='Repo not found')

    if body.usage_notes is not None:
        repo.usage_notes = body.usage_notes
    if body.topics is not None:
        repo.topics = body.topics
    repo.updated_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(repo)
    return repo


@router.post('/{repo_id}/sync', response_model=RepoResponse)
async def sync_repo(repo_id: str, session: SessionDep) -> Repo:
    result = await session.execute(select(Repo).where(Repo.id == uuid.UUID(repo_id)))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail='Repo not found')

    try:
        info = await github_service.fetch_repo(repo.owner, repo.name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f'GitHub fetch failed: {e}')

    repo.readme = info['readme']
    repo.claude_md = info['claude_md']
    repo.agents_md = info['agents_md']
    repo.description = info['description']
    repo.topics = info['topics']
    repo.updated_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(repo)
    asyncio.create_task(_notify_index(str(repo.id)))
    return repo
