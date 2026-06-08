#!/usr/bin/env python3
"""
Repo Service — FastAPI + PostgreSQL.

Stores GitHub repo metadata (README, description, topics) and user-written usage notes.
For usage details run the server and visit /docs.

Prerequisites:
  - PostgreSQL running (docker-compose up -d)
  - GITHUB_PAT set in .env for private repo access
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import init_db
from routers import repos


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title='Repo Service', lifespan=lifespan)
app.include_router(repos.router)


@app.get('/health', tags=['health'])
async def health() -> dict:
    return {'status': 'ok'}
