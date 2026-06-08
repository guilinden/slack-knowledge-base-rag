import time

_TTL_SECONDS = 30 * 60
_store: dict[str, dict] = {}


def save(draft_id: str, draft: dict) -> None:
    draft['_expires'] = time.time() + _TTL_SECONDS
    _store[draft_id] = draft


def get(draft_id: str) -> dict | None:
    draft = _store.get(draft_id)
    if not draft:
        return None
    if draft['_expires'] < time.time():
        del _store[draft_id]
        return None
    return draft


def delete(draft_id: str) -> None:
    _store.pop(draft_id, None)
