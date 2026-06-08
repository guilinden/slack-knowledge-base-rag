from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

import config

_SYSTEM = (
    'You are a precise code editor. Apply the requested change to the file. '
    'Return ONLY the complete new file content — no explanations, no markdown fences, no commentary. '
    'Preserve all formatting, indentation, and unrelated content exactly as-is.'
)


def _llm() -> ChatAnthropic:
    return ChatAnthropic(
        model=config.CLAUDE_MODEL,
        api_key=config.ANTHROPIC_API_KEY,
        max_tokens=8096,
    )


def apply_change(task: str, filepath: str, current_content: str) -> str:
    chain = _llm() | StrOutputParser()
    return chain.invoke([
        SystemMessage(content=[{'type': 'text', 'text': _SYSTEM, 'cache_control': {'type': 'ephemeral'}}]),
        HumanMessage(content=f'Task: {task}\n\nFile: {filepath}\n\nCurrent content:\n{current_content}'),
    ])
