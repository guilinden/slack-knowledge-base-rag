from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel

import config


class _Plan(BaseModel):
    files_to_change: list[str]
    reasoning: str
    pr_title: str
    pr_description: str
    commit_message: str


_SYSTEM = (
    'You are a code change planner for a software engineering team. '
    'Given a task and repository context, identify the minimum set of files to modify '
    'and describe exactly what to change. Be conservative — only change what is necessary.'
)


def _llm(max_tokens: int = 1024) -> ChatAnthropic:
    return ChatAnthropic(
        model=config.CLAUDE_MODEL,
        api_key=config.ANTHROPIC_API_KEY,
        max_tokens=max_tokens,
    )


def select_repo(task: str, context: list[str], repos: list[dict]) -> dict:
    context_block = '\n'.join(f'- {c}' for c in context) if context else 'None.'
    repos_block = '\n'.join(
        f'- {r["name"]} ({r["github_url"]}): {r.get("description") or "No description"}'
        for r in repos
    )
    chain = _llm(max_tokens=50) | StrOutputParser()
    selected_name = chain.invoke([
        HumanMessage(content=f"""Select the single most relevant repository for this task.

Task: {task}

Knowledge base context:
{context_block}

Available repositories:
{repos_block}

Reply with ONLY the exact repository name (e.g. "pmn-demo"). No explanation."""),
    ]).strip().strip('"').strip("'")
    for r in repos:
        if r['name'].lower() == selected_name.lower():
            return r
    return repos[0]


def plan(
    task: str,
    context: list[str],
    repo_name: str,
    description: str | None,
    usage_notes: str | None,
    readme: str | None,
    claude_md: str | None,
    agents_md: str | None,
    file_tree: list[str],
) -> dict:
    context_block = '\n'.join(f'- {c}' for c in context) if context else 'None provided.'
    tree_block = '\n'.join(file_tree[:200])
    readme_excerpt = (readme or '')[:800]
    claude_md_block = f'\nCLAUDE.md (coding conventions):\n{claude_md}' if claude_md else ''
    agents_md_block = f'\nAGENTS.md (agent instructions):\n{agents_md}' if agents_md else ''

    result = _llm().with_structured_output(_Plan).invoke([
        SystemMessage(content=[{'type': 'text', 'text': _SYSTEM, 'cache_control': {'type': 'ephemeral'}}]),
        HumanMessage(content=f"""Task: {task}

Knowledge base context:
{context_block}

Repository: {repo_name}
Description: {description or 'N/A'}
Team usage notes: {usage_notes or 'N/A'}

README excerpt:
{readme_excerpt}{claude_md_block}{agents_md_block}

File tree:
{tree_block}

Return JSON with these fields:
- files_to_change: list of file paths to modify (max 5)
- reasoning: what needs to change and why
- pr_title: concise PR title under 72 characters
- pr_description: markdown PR body with context and what changed
- commit_message: git commit message"""),
    ])
    return result.model_dump()
