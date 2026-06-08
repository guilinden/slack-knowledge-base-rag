#!/usr/bin/env python3
"""
Coder Agent — FastAPI service that turns natural language tasks into GitHub PRs.

Flow: receive task + context from knowledge-base → Claude plans which files to change
→ Claude applies the change → creates branch + commit + PR on GitHub.

Prerequisites:
  - ANTHROPIC_API_KEY and GITHUB_PAT set in .env
  - GitHub PAT needs repo read/write scope
"""

from fastapi import FastAPI

from routers import agent

app = FastAPI(title='Coder Agent', version='0.1.0')
app.include_router(agent.router)


@app.get('/health', tags=['health'])
async def health() -> dict:
    return {'status': 'ok'}
