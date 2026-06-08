import asyncio
import re
import uuid

import httpx
from fastapi import APIRouter, HTTPException

from models.schemas import AgentResult, AgentTask
from services import coder_service, github_service, planner_service

router = APIRouter(prefix='/agent', tags=['agent'])


@router.post('/task', response_model=AgentResult)
async def run_task(body: AgentTask) -> AgentResult:
    if not body.repos:
        raise HTTPException(status_code=400, detail='No repos provided.')

    repo = body.repos[0]

    try:
        owner, name = github_service.parse_owner_name(repo.github_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        default_branch = await github_service.get_default_branch(owner, name)
        head_sha = await github_service.get_branch_sha(owner, name, default_branch)
        file_tree = await github_service.get_file_tree(owner, name, head_sha)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f'GitHub API error: {e}')

    try:
        plan = await asyncio.to_thread(
            planner_service.plan,
            body.task,
            body.context,
            name,
            repo.description,
            repo.usage_notes,
            repo.readme,
            repo.claude_md,
            repo.agents_md,
            file_tree,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f'Planning failed: {e}')

    files_to_change: list[str] = plan.get('files_to_change', [])
    if not files_to_change:
        raise HTTPException(
            status_code=422,
            detail=f'Planner could not identify files to change. Reasoning: {plan.get("reasoning", "unknown")}',
        )

    new_branch = _branch_name(body.task)

    try:
        await github_service.create_branch(owner, name, new_branch, head_sha)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f'Branch creation failed: {e}')

    changed_files: list[str] = []
    commit_message = plan.get('commit_message', f'claude-agent: {body.task[:60]}')

    for filepath in files_to_change:
        try:
            content, file_sha = await github_service.get_file_content(owner, name, filepath)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f'Failed to fetch {filepath}: {e}')

        try:
            new_content = await asyncio.to_thread(
                coder_service.apply_change, body.task, filepath, content
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f'Failed to apply change to {filepath}: {e}')

        try:
            await github_service.commit_file(
                owner, name, filepath, new_content, file_sha, new_branch, commit_message
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f'Failed to commit {filepath}: {e}')

        changed_files.append(filepath)

    try:
        pr_url = await github_service.create_pr(
            owner=owner,
            name=name,
            title=plan.get('pr_title', body.task[:72]),
            body=plan.get('pr_description', ''),
            head=new_branch,
            base=default_branch,
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f'PR creation failed: {e}')

    return AgentResult(
        pr_url=pr_url,
        pr_title=plan.get('pr_title', body.task[:72]),
        files_changed=changed_files,
        reasoning=plan.get('reasoning', ''),
    )


def _branch_name(task: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', task.lower())[:50].strip('-')
    return f'claude-agent/{slug}-{uuid.uuid4().hex[:6]}'
