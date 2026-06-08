import httpx

import config


async def delegate(task: str, context: list[str], repos: list[dict]) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f'{config.CODER_AGENT_URL}/agent/task',
            json={
                'task': task,
                'context': context,
                'repos': [
                    {
                        'github_url': r['github_url'],
                        'name': r['name'],
                        'description': r.get('description'),
                        'usage_notes': r.get('usage_notes'),
                        'readme': r.get('readme'),
                        'claude_md': r.get('claude_md'),
                        'agents_md': r.get('agents_md'),
                    }
                    for r in repos
                ],
            },
            timeout=180.0,
        )
        resp.raise_for_status()
        return resp.json()
