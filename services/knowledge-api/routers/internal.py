import asyncio

from fastapi import APIRouter

from services import embedding_service, qdrant_service, repo_client

router = APIRouter(prefix='/internal', tags=['internal'])


@router.post('/index-repo/{repo_id}')
async def index_repo(repo_id: str) -> dict:
    repos = await repo_client.get_all_repos()
    repo = next((r for r in repos if str(r['id']) == repo_id), None)
    if not repo:
        return {'status': 'not_found'}
    await _index_one(repo)
    return {'status': 'indexed', 'name': repo['name']}


async def index_all_repos() -> None:
    try:
        repos = await repo_client.get_all_repos()
    except Exception as e:
        print(f'[internal] index_all_repos: failed to fetch repos: {e}', flush=True)
        return
    for repo in repos:
        try:
            await _index_one(repo)
        except Exception as e:
            print(f'[internal] index_all_repos: failed to index repo {repo.get("name")}: {e}', flush=True)


async def _index_one(repo: dict) -> None:
    text = _repo_text(repo)
    vector = await asyncio.to_thread(embedding_service.embed_text, text)
    payload = {
        'github_url': repo['github_url'],
        'name': repo['name'],
        'description': repo.get('description'),
        'repo_id': str(repo['id']),
    }
    await asyncio.to_thread(qdrant_service.upsert_repo_point, str(repo['id']), vector, payload)


def _repo_text(repo: dict) -> str:
    parts = [repo['name']]
    if repo.get('description'):
        parts.append(repo['description'])
    if repo.get('usage_notes'):
        parts.append(repo['usage_notes'])
    if repo.get('readme'):
        parts.append(repo['readme'][:800])
    return '\n'.join(parts)
