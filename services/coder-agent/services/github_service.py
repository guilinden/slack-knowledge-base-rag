import base64

import httpx

import config

_BASE = 'https://api.github.com'


def _headers() -> dict:
    return {
        'Authorization': f'Bearer {config.GITHUB_PAT}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }


def parse_owner_name(github_url: str) -> tuple[str, str]:
    url = github_url.strip().rstrip('/')
    url = url.removeprefix('https://').removeprefix('http://')
    parts = [p for p in url.split('/') if p]
    for i, part in enumerate(parts):
        if 'github.com' in part and i + 2 <= len(parts):
            return parts[i + 1], parts[i + 2]
    raise ValueError(f'Cannot parse GitHub URL: {github_url}')


async def get_default_branch(owner: str, name: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f'{_BASE}/repos/{owner}/{name}', headers=_headers(), timeout=15.0)
        resp.raise_for_status()
        return resp.json()['default_branch']


async def get_branch_sha(owner: str, name: str, branch: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f'{_BASE}/repos/{owner}/{name}/git/ref/heads/{branch}',
            headers=_headers(),
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()['object']['sha']


async def get_file_tree(owner: str, name: str, sha: str) -> list[str]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f'{_BASE}/repos/{owner}/{name}/git/trees/{sha}',
            headers=_headers(),
            params={'recursive': '1'},
            timeout=30.0,
        )
        resp.raise_for_status()
        return [
            item['path']
            for item in resp.json().get('tree', [])
            if item['type'] == 'blob'
        ]


async def get_file_content(owner: str, name: str, path: str) -> tuple[str, str]:
    """Returns (decoded content, file sha)."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f'{_BASE}/repos/{owner}/{name}/contents/{path}',
            headers=_headers(),
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        content = base64.b64decode(data['content']).decode('utf-8', errors='replace')
        return content, data['sha']


async def create_branch(owner: str, name: str, branch: str, sha: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f'{_BASE}/repos/{owner}/{name}/git/refs',
            headers=_headers(),
            json={'ref': f'refs/heads/{branch}', 'sha': sha},
            timeout=15.0,
        )
        resp.raise_for_status()


async def commit_file(
    owner: str,
    name: str,
    path: str,
    content: str,
    file_sha: str,
    branch: str,
    message: str,
) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f'{_BASE}/repos/{owner}/{name}/contents/{path}',
            headers=_headers(),
            json={
                'message': message,
                'content': base64.b64encode(content.encode()).decode(),
                'sha': file_sha,
                'branch': branch,
            },
            timeout=15.0,
        )
        resp.raise_for_status()


async def create_pr(
    owner: str,
    name: str,
    title: str,
    body: str,
    head: str,
    base: str,
) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f'{_BASE}/repos/{owner}/{name}/pulls',
            headers=_headers(),
            json={'title': title, 'body': body, 'head': head, 'base': base},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()['html_url']
