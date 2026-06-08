import httpx

import config


def _normalize_url(git_repo: str) -> str:
    git_repo = git_repo.strip().rstrip('/')
    if git_repo.startswith('http'):
        return git_repo
    if 'github.com' in git_repo:
        return f'https://{git_repo}'
    return f'https://github.com/{git_repo}'


async def register_repo(git_repo: str) -> None:
    if not config.REPO_SERVICE_URL:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f'{config.REPO_SERVICE_URL}/repos/',
                json={'github_url': _normalize_url(git_repo)},
                timeout=10.0,
            )
    except Exception as e:
        print(f'[repo-client] register_repo failed for {git_repo}: {e}', flush=True)


async def get_all_repos() -> list[dict]:
    if not config.REPO_SERVICE_URL:
        return []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f'{config.REPO_SERVICE_URL}/repos/', timeout=5.0)
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        print(f'[repo-client] get_all_repos failed: {e}', flush=True)
    return []


async def get_repos_for_refs(git_repos: list[str]) -> list[dict]:
    if not config.REPO_SERVICE_URL or not git_repos:
        return []

    urls = list({_normalize_url(r) for r in git_repos if r})
    results = []

    async with httpx.AsyncClient() as client:
        for url in urls:
            try:
                resp = await client.get(
                    f'{config.REPO_SERVICE_URL}/repos/',
                    params={'github_url': url},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    repos = resp.json()
                    if repos:
                        results.append(repos[0])
            except Exception as e:
                print(f'[repo-client] get_repos_for_refs failed for {url}: {e}', flush=True)

    return results
