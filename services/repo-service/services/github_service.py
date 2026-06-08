import base64

import httpx

import config


def parse_github_url(url: str) -> tuple[str, str]:
    url = url.strip().rstrip('/')
    if '/' in url and 'github.com' not in url and not url.startswith('http'):
        parts = url.split('/')
        if len(parts) == 2:
            return parts[0], parts[1]
    url = url.removeprefix('https://').removeprefix('http://')
    parts = [p for p in url.split('/') if p]
    for i, part in enumerate(parts):
        if 'github.com' in part and i + 2 < len(parts):
            return parts[i + 1], parts[i + 2]
    raise ValueError(f'Cannot parse GitHub URL: {url}')


def normalize_url(url: str) -> str:
    owner, name = parse_github_url(url)
    return f'https://github.com/{owner}/{name}'


async def _fetch_file(
    client: httpx.AsyncClient,
    owner: str,
    name: str,
    path: str,
    headers: dict,
) -> str | None:
    resp = await client.get(
        f'https://api.github.com/repos/{owner}/{name}/contents/{path}',
        headers=headers,
        timeout=15.0,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    raw = resp.json().get('content', '')
    return base64.b64decode(raw).decode('utf-8', errors='replace')


async def _fetch_first_found(
    client: httpx.AsyncClient,
    owner: str,
    name: str,
    candidates: list[str],
    headers: dict,
) -> str | None:
    for path in candidates:
        content = await _fetch_file(client, owner, name, path, headers)
        if content is not None:
            return content
    return None


async def fetch_repo(owner: str, name: str) -> dict:
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if config.GITHUB_PAT:
        headers['Authorization'] = f'Bearer {config.GITHUB_PAT}'

    async with httpx.AsyncClient() as client:
        repo_resp = await client.get(
            f'https://api.github.com/repos/{owner}/{name}',
            headers=headers,
            timeout=15.0,
        )
        repo_resp.raise_for_status()
        repo_data = repo_resp.json()

        readme_resp = await client.get(
            f'https://api.github.com/repos/{owner}/{name}/readme',
            headers=headers,
            timeout=15.0,
        )
        if readme_resp.status_code == 200:
            raw = readme_resp.json().get('content', '')
            readme = base64.b64decode(raw).decode('utf-8', errors='replace')
        else:
            readme = None

        claude_md = await _fetch_first_found(
            client, owner, name, ['CLAUDE.md', 'claude.md', '.claude/CLAUDE.md'], headers
        )
        agents_md = await _fetch_first_found(
            client, owner, name, ['AGENTS.md', 'agents.md'], headers
        )

    return {
        'description': repo_data.get('description'),
        'topics': repo_data.get('topics', []),
        'readme': readme,
        'claude_md': claude_md,
        'agents_md': agents_md,
    }
