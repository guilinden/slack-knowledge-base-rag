import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

import config
from services import (
    embedding_service,
    llm_service,
    pending_store,
    qdrant_service,
    repo_client,
    slack_blocks,
    slack_service,
)

router = APIRouter(prefix='/slack', tags=['slack'])

_THREAD_URL_RE = re.compile(r'/archives/([A-Z0-9]+)/p(\d{16})')
_USAGE = 'Usage: `/learn-it <thread-link> [topic]`\nRight-click any message → Copy link, then paste it here.'

# Deduplicates Slack event deliveries (Slack may send the same event_id twice).
# Maps event_id → received_at timestamp; entries expire after 60 seconds.
_seen_events: dict[str, float] = {}


def _is_duplicate_event(event_id: str) -> bool:
    now = time.time()
    expired = [k for k, v in _seen_events.items() if now - v > 60]
    for k in expired:
        del _seen_events[k]
    if event_id in _seen_events:
        return True
    _seen_events[event_id] = now
    return False


def _parse_thread_link(text: str) -> tuple[str, str] | None:
    m = _THREAD_URL_RE.search(text)
    if not m:
        return None
    channel_id = m.group(1)
    raw_ts = m.group(2)
    thread_ts = f'{raw_ts[:-6]}.{raw_ts[-6:]}'
    return channel_id, thread_ts


# --- Slash command: /learn-it <thread-link> [topic] ---

@router.post('/save')
async def slack_save(
    background_tasks: BackgroundTasks,
    request: Request,
    x_slack_request_timestamp: str = Header(...),
    x_slack_signature: str = Header(...),
) -> dict:
    raw_body = await request.body()

    if config.SLACK_SIGNING_SECRET:
        if not slack_service.verify_signature(raw_body, x_slack_request_timestamp, x_slack_signature):
            raise HTTPException(status_code=401, detail='Invalid Slack signature')

    form = parse_qs(raw_body.decode())
    post_channel_id = form.get('channel_id', [''])[0]
    channel_name = form.get('channel_name', ['unknown'])[0]
    user_id = form.get('user_id', [''])[0]
    user_name = form.get('user_name', ['unknown'])[0]
    response_url = form.get('response_url', [''])[0]
    text = form.get('text', [''])[0].strip()

    parsed = _parse_thread_link(text)
    if not parsed:
        return {'response_type': 'ephemeral', 'text': f'No thread link found. {_USAGE}'}

    thread_channel_id, thread_ts = parsed
    thread_url = re.search(r'https://\S+', text)
    thread_url = thread_url.group(0).rstrip('>') if thread_url else ''
    topic = _THREAD_URL_RE.sub('', text).strip() or None

    background_tasks.add_task(
        _process_save,
        thread_channel_id=thread_channel_id,
        post_channel_id=post_channel_id,
        channel_name=channel_name,
        user_id=user_id,
        user_name=user_name,
        thread_ts=thread_ts,
        thread_url=thread_url,
        topic=topic,
        response_url=response_url,
        reply_thread_ts=None,
    )

    return {'response_type': 'ephemeral', 'text': 'Summarizing thread... I\'ll send a draft for your review.'}


# --- Events API: bot mention in thread ---

@router.post('/events')
async def slack_events(
    background_tasks: BackgroundTasks,
    request: Request,
    x_slack_request_timestamp: str = Header(...),
    x_slack_signature: str = Header(...),
) -> dict:
    raw_body = await request.body()

    if config.SLACK_SIGNING_SECRET:
        if not slack_service.verify_signature(raw_body, x_slack_request_timestamp, x_slack_signature):
            raise HTTPException(status_code=401, detail='Invalid Slack signature')

    body = json.loads(raw_body)
    print(f'[kb] /events body type={body.get("type")!r} event_type={body.get("event", {}).get("type")!r}', flush=True)

    # One-time URL verification when configuring the Events API in Slack app settings
    if body.get('type') == 'url_verification':
        return {'challenge': body['challenge']}

    if body.get('type') != 'event_callback':
        print(f'[kb] /events skip: not event_callback', flush=True)
        return {}

    event_id = body.get('event_id', '')
    if _is_duplicate_event(event_id):
        print(f'[kb] /events skip: duplicate event_id={event_id!r}', flush=True)
        return {}

    event = body.get('event', {})
    print(f'[kb] /events event type={event.get("type")!r} bot_id={event.get("bot_id")!r} thread_ts={event.get("thread_ts")!r} user={event.get("user")!r}', flush=True)

    if event.get('type') != 'app_mention':
        print(f'[kb] /events skip: not app_mention', flush=True)
        return {}

    # Ignore bot's own messages
    if event.get('bot_id'):
        print(f'[kb] /events skip: bot_id present', flush=True)
        return {}

    thread_ts: str | None = event.get('thread_ts')
    if not thread_ts:
        print(f'[kb] /events not in thread, sending guidance', flush=True)
        background_tasks.add_task(
            slack_service.post_message,
            event['channel'],
            'Mention me inside a thread and I\'ll save the conversation to the knowledge base.',
        )
        return {}

    channel_id: str = event['channel']
    user_id: str = event.get('user', '')
    mention_text: str = event.get('text', '')
    topic = re.sub(r'<@[A-Z0-9]+>', '', mention_text).strip() or None

    print(f'[kb] /events dispatching _process_save channel={channel_id!r} thread_ts={thread_ts!r} user={user_id!r}', flush=True)
    background_tasks.add_task(
        _process_save,
        thread_channel_id=channel_id,
        post_channel_id=channel_id,
        channel_name=channel_id,
        user_id=user_id,
        user_name=user_id,
        thread_ts=thread_ts,
        thread_url=f'slack://{channel_id}/{thread_ts}',
        topic=topic,
        response_url='',
        reply_thread_ts=thread_ts,
    )

    return {}


# --- Button / modal interactions ---

@router.post('/interact')
async def slack_interact(
    background_tasks: BackgroundTasks,
    request: Request,
    x_slack_request_timestamp: str = Header(...),
    x_slack_signature: str = Header(...),
) -> dict:
    raw_body = await request.body()

    if config.SLACK_SIGNING_SECRET:
        if not slack_service.verify_signature(raw_body, x_slack_request_timestamp, x_slack_signature):
            raise HTTPException(status_code=401, detail='Invalid Slack signature')

    form = parse_qs(raw_body.decode())
    payload = json.loads(form.get('payload', ['{}'])[0])
    payload_type = payload.get('type')

    if payload_type == 'block_actions':
        actions = payload.get('actions', [])
        if not actions:
            return {}
        action_id: str = actions[0].get('action_id', '')
        response_url: str = payload.get('response_url', '')
        trigger_id: str = payload.get('trigger_id', '')

        if ':' not in action_id:
            return {}
        prefix, draft_id = action_id.split(':', 1)

        if prefix == 'kb_confirm':
            background_tasks.add_task(_handle_confirm, draft_id, response_url)
        elif prefix == 'kb_edit':
            background_tasks.add_task(_handle_edit, draft_id, trigger_id, response_url)
        elif prefix == 'kb_cancel':
            background_tasks.add_task(_handle_cancel, draft_id, response_url)

    elif payload_type == 'view_submission':
        callback_id: str = payload.get('view', {}).get('callback_id', '')
        if callback_id.startswith('kb_modal:'):
            draft_id = callback_id.split(':', 1)[1]
            values = payload['view']['state']['values']
            background_tasks.add_task(_handle_modal_submit, draft_id, values)

    return {}


# --- Background task helpers ---

async def _process_save(
    thread_channel_id: str,
    post_channel_id: str,
    channel_name: str,
    user_id: str,
    user_name: str,
    thread_ts: str,
    thread_url: str,
    topic: str | None,
    response_url: str,
    reply_thread_ts: str | None,
) -> None:
    print(f'[kb] _process_save start channel={thread_channel_id} thread_ts={thread_ts}', flush=True)

    async def _notify(text: str, blocks: list | None = None) -> None:
        try:
            if response_url:
                if blocks:
                    await slack_service.post_blocks(response_url, blocks, replace_original=True)
                else:
                    await slack_service.post_response(response_url, text)
            else:
                await slack_service.post_message(
                    post_channel_id, text=text, blocks=blocks, thread_ts=reply_thread_ts
                )
        except Exception as notify_err:
            print(f'[kb] _notify failed: {notify_err}', flush=True)

    try:
        messages = await slack_service.fetch_thread_messages(thread_channel_id, thread_ts)
        print(f'[kb] fetched {len(messages)} messages', flush=True)

        result = await asyncio.to_thread(llm_service.summarize_thread, messages)
        summary: str = result.get('summary', '')
        tags: list[str] = result.get('tags', [])
        print(f'[kb] summary done, tags={tags}', flush=True)

        vector = await asyncio.to_thread(embedding_service.embed_text, summary)

        repo_hits = await asyncio.to_thread(qdrant_service.search_repos, vector, 1)
        git_repo: str | None = None
        if repo_hits and repo_hits[0].score > 0.6:
            git_repo = repo_hits[0].payload.get('github_url')

        draft_id = str(uuid.uuid4())
        pending_store.save(draft_id, {
            'id': draft_id,
            'summary': summary,
            'tags': tags,
            'topic': topic,
            'git_repo': git_repo,
            'channel': channel_name,
            'channel_id': post_channel_id,
            'thread_id': thread_ts,
            'saved_by': user_name,
            'thread_url': thread_url,
            'raw_messages': messages,
            'reply_thread_ts': reply_thread_ts,
        })

        blocks = slack_blocks.draft_review_blocks(draft_id, summary, tags, git_repo)
        await _notify('Knowledge draft ready — review below.', blocks=blocks)
        print(f'[kb] draft sent draft_id={draft_id}', flush=True)

    except Exception as e:
        print(f'[kb] _process_save error: {e}', flush=True)
        await _notify(f'Failed to process thread: {e}')


async def _handle_confirm(draft_id: str, response_url: str) -> None:
    draft = pending_store.get(draft_id)
    if not draft:
        await slack_service.post_response(
            response_url, 'Draft expired or already saved.', replace_original=True
        )
        return

    try:
        await _commit_draft(draft)
    except Exception as e:
        await slack_service.post_response(response_url, f'Failed to save: {e}', replace_original=True)
        return

    pending_store.delete(draft_id)
    await slack_service.post_response(response_url, 'Saved!', replace_original=True)
    repo_line = f'\nRepository: {draft["git_repo"]}' if draft.get('git_repo') else ''
    await slack_service.post_message(
        draft['channel_id'],
        text=f'Knowledge saved!\nSummary: {draft["summary"]}\nTags: {", ".join(draft["tags"])}{repo_line}',
        thread_ts=draft.get('reply_thread_ts'),
    )


async def _handle_edit(draft_id: str, trigger_id: str, response_url: str) -> None:
    draft = pending_store.get(draft_id)
    if not draft:
        await slack_service.post_response(
            response_url, 'Draft expired or already saved.', replace_original=True
        )
        return
    # Store response_url so the modal submit can update the buttons message
    draft['response_url'] = response_url
    pending_store.save(draft_id, draft)
    view = slack_blocks.edit_modal(draft_id, draft['summary'], draft['tags'], draft.get('git_repo'))
    await slack_service.open_modal(trigger_id, view)


async def _handle_cancel(draft_id: str, response_url: str) -> None:
    pending_store.delete(draft_id)
    await slack_service.post_response(
        response_url, 'Knowledge not saved.', response_type='ephemeral', replace_original=True
    )


async def _handle_modal_submit(draft_id: str, values: dict) -> None:
    draft = pending_store.get(draft_id)
    if not draft:
        return

    summary = values['summary_block']['summary_input']['value']
    tags_raw = values['tags_block']['tags_input']['value']
    tags = [t.strip() for t in tags_raw.split(',') if t.strip()]
    repo_raw = (values.get('repo_block', {}).get('repo_input', {}).get('value') or '').strip()
    git_repo = repo_raw or None

    draft['summary'] = summary
    draft['tags'] = tags
    draft['git_repo'] = git_repo

    response_url = draft.get('response_url', '')

    try:
        await _commit_draft(draft)
    except Exception as e:
        if response_url:
            await slack_service.post_response(response_url, f'Failed to save: {e}', replace_original=True)
        return

    pending_store.delete(draft_id)
    if response_url:
        await slack_service.post_response(response_url, 'Saved!', replace_original=True)
    repo_line = f'\nRepository: {git_repo}' if git_repo else ''
    await slack_service.post_message(
        draft['channel_id'],
        text=f'Knowledge saved (with your edits)!\nSummary: {summary}\nTags: {", ".join(tags)}{repo_line}',
        thread_ts=draft.get('reply_thread_ts'),
    )


async def _commit_draft(draft: dict) -> None:
    vector = await asyncio.to_thread(embedding_service.embed_text, draft['summary'])
    payload = {
        'summary': draft['summary'],
        'raw_messages': draft['raw_messages'],
        'tags': draft['tags'],
        'topic': draft['topic'],
        'git_repo': draft.get('git_repo'),
        'channel': draft['channel'],
        'thread_id': draft['thread_id'],
        'saved_by': draft['saved_by'],
        'created_at': datetime.now(timezone.utc).isoformat(),
        'thread_url': draft['thread_url'],
    }
    await asyncio.to_thread(qdrant_service.upsert_point, draft['id'], vector, payload)
    if draft.get('git_repo'):
        await repo_client.register_repo(draft['git_repo'])
