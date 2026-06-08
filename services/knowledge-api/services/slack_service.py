import hashlib
import hmac
import time

import httpx

import config


def verify_signature(raw_body: bytes, timestamp: str, signature: str) -> bool:
    if abs(time.time() - int(timestamp)) > 300:
        return False
    sig_basestring = f'v0:{timestamp}:{raw_body.decode()}'
    expected = 'v0=' + hmac.new(
        config.SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _check_ok(data: dict, fn_name: str) -> None:
    if not data.get('ok'):
        error = data.get('error', 'unknown')
        print(f'[slack] {fn_name} failed: {error} — full response: {data}', flush=True)
        raise ValueError(f'Slack API {fn_name} error: {error}')


async def fetch_thread_messages(channel_id: str, thread_ts: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            'https://slack.com/api/conversations.replies',
            headers={'Authorization': f'Bearer {config.SLACK_BOT_TOKEN}'},
            params={'channel': channel_id, 'ts': thread_ts},
        )
    data = response.json()
    _check_ok(data, 'conversations.replies')
    return [
        {
            'author': m.get('user', 'unknown'),
            'text': m.get('text', ''),
            'timestamp': m.get('ts', ''),
        }
        for m in data.get('messages', [])
        if m.get('text')
    ]


async def post_response(
    response_url: str,
    text: str,
    response_type: str = 'in_channel',
    replace_original: bool = False,
) -> None:
    payload: dict = {'text': text, 'response_type': response_type}
    if replace_original:
        payload['replace_original'] = True
    async with httpx.AsyncClient() as client:
        await client.post(response_url, json=payload)


async def post_blocks(
    response_url: str,
    blocks: list[dict],
    replace_original: bool = False,
) -> None:
    payload: dict = {'blocks': blocks, 'response_type': 'ephemeral'}
    if replace_original:
        payload['replace_original'] = True
    async with httpx.AsyncClient() as client:
        await client.post(response_url, json=payload)


async def open_modal(trigger_id: str, view: dict) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            'https://slack.com/api/views.open',
            headers={'Authorization': f'Bearer {config.SLACK_BOT_TOKEN}'},
            json={'trigger_id': trigger_id, 'view': view},
        )
    _check_ok(resp.json(), 'views.open')


async def post_message(
    channel_id: str,
    text: str = '',
    blocks: list[dict] | None = None,
    thread_ts: str | None = None,
) -> None:
    payload: dict = {'channel': channel_id}
    if text:
        payload['text'] = text
    if blocks:
        payload['blocks'] = blocks
    if thread_ts:
        payload['thread_ts'] = thread_ts
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            'https://slack.com/api/chat.postMessage',
            headers={'Authorization': f'Bearer {config.SLACK_BOT_TOKEN}'},
            json=payload,
        )
    _check_ok(resp.json(), 'chat.postMessage')


async def post_ephemeral(
    channel_id: str,
    user_id: str,
    text: str = '',
    blocks: list[dict] | None = None,
    thread_ts: str | None = None,
) -> None:
    payload: dict = {'channel': channel_id, 'user': user_id}
    if text:
        payload['text'] = text
    if blocks:
        payload['blocks'] = blocks
    if thread_ts:
        payload['thread_ts'] = thread_ts
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            'https://slack.com/api/chat.postEphemeral',
            headers={'Authorization': f'Bearer {config.SLACK_BOT_TOKEN}'},
            json=payload,
        )
    _check_ok(resp.json(), 'chat.postEphemeral')
