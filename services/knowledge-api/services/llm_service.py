from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel

import config


class _ThreadSummary(BaseModel):
    summary: str
    tags: list[str]


def _llm(max_tokens: int = 1024) -> ChatAnthropic:
    return ChatAnthropic(
        model=config.CLAUDE_MODEL,
        api_key=config.ANTHROPIC_API_KEY,
        max_tokens=max_tokens,
    )


def _cached_system(text: str) -> SystemMessage:
    return SystemMessage(content=[{
        'type': 'text',
        'text': text,
        'cache_control': {'type': 'ephemeral'},
    }])


_SUMMARIZE_SYSTEM = (
    'You are a technical knowledge base assistant. Your job is to extract durable team'
    ' decisions, architectural choices, and important context from Slack threads.'
    ' Be concise and factual.'
)

_ANSWER_SYSTEM = (
    'You are a helpful assistant for a software development team. Answer questions using'
    ' only the provided knowledge base context. If the context does not contain enough'
    ' information, say so. Always be concise.'
)

_CLASSIFY_SYSTEM = (
    'Classify the user\'s intent. Reply with exactly one word: '
    '"action" if the request asks to make a change, create something, modify infrastructure, or perform an operation. '
    '"question" if it is asking for information or an explanation.'
)

_HYDE_SYSTEM = (
    'You are a technical knowledge base assistant for a software development team.'
    ' Your job is to write a hypothetical knowledge base entry that would perfectly'
    ' answer the user\'s question. Write it as if it were an actual entry extracted'
    ' from a Slack thread — concise, factual, and in the style of a team decision'
    ' or architectural note. Do not answer the question directly; instead, produce'
    ' the kind of document that, if it existed, would contain the answer.'
)


def summarize_thread(messages: list[dict]) -> dict:
    thread_text = '\n'.join(f'{m["author"]}: {m["text"]}' for m in messages)
    result = _llm().with_structured_output(_ThreadSummary).invoke([
        _cached_system(_SUMMARIZE_SYSTEM),
        HumanMessage(content=(
            f'{thread_text}\n\n'
            'Return JSON with two fields: summary (2-4 sentences capturing the'
            ' decision or knowledge) and tags (3-6 lowercase keywords).'
        )),
    ])
    return result.model_dump()


def answer_query(
    question: str,
    context_chunks: list[dict],
    repo_context: list[dict] | None = None,
) -> str:
    context = '\n\n'.join(
        f'{i + 1}. {chunk["summary"]}' for i, chunk in enumerate(context_chunks)
    )

    repo_section = ''
    if repo_context:
        lines = []
        for r in repo_context:
            line = f'- {r["name"]} ({r["github_url"]})'
            if r.get('description'):
                line += f': {r["description"]}'
            if r.get('usage_notes'):
                line += f'. Team usage: {r["usage_notes"]}'
            if r.get('readme'):
                excerpt = r['readme'][:600].replace('\n', ' ')
                line += f'\n  README: {excerpt}...'
            lines.append(line)
        repo_section = '\n\nRepository context:\n' + '\n'.join(lines)

    chain = _llm() | StrOutputParser()
    return chain.invoke([
        _cached_system(_ANSWER_SYSTEM),
        HumanMessage(content=f'Knowledge base context:\n{context}{repo_section}\n\nQuestion: {question}'),
    ])


def classify_intent(question: str) -> str:
    chain = _llm(max_tokens=5) | StrOutputParser()
    text = chain.invoke([
        SystemMessage(content=_CLASSIFY_SYSTEM),
        HumanMessage(content=question),
    ]).strip().lower()
    return 'action' if 'action' in text else 'question'


def generate_hyde_document(question: str) -> str:
    chain = _llm() | StrOutputParser()
    return chain.invoke([
        _cached_system(_HYDE_SYSTEM),
        HumanMessage(content=question),
    ]).strip()