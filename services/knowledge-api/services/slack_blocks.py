def draft_review_blocks(draft_id: str, summary: str, tags: list[str], git_repo: str | None) -> list[dict]:
    repo_text = git_repo or '_No repository inferred — click Edit to add one_'
    tags_text = ', '.join(tags) if tags else '_None_'
    return [
        {
            'type': 'header',
            'text': {'type': 'plain_text', 'text': 'Knowledge Draft — Review before saving'},
        },
        {
            'type': 'section',
            'text': {'type': 'mrkdwn', 'text': f'*Summary*\n{summary}'},
        },
        {
            'type': 'section',
            'fields': [
                {'type': 'mrkdwn', 'text': f'*Tags*\n{tags_text}'},
                {'type': 'mrkdwn', 'text': f'*Repository*\n{repo_text}'},
            ],
        },
        {'type': 'divider'},
        {
            'type': 'actions',
            'elements': [
                {
                    'type': 'button',
                    'text': {'type': 'plain_text', 'text': 'Confirm'},
                    'style': 'primary',
                    'action_id': f'kb_confirm:{draft_id}',
                },
                {
                    'type': 'button',
                    'text': {'type': 'plain_text', 'text': 'Edit'},
                    'action_id': f'kb_edit:{draft_id}',
                },
                {
                    'type': 'button',
                    'text': {'type': 'plain_text', 'text': 'Cancel'},
                    'style': 'danger',
                    'action_id': f'kb_cancel:{draft_id}',
                    'confirm': {
                        'title': {'type': 'plain_text', 'text': 'Cancel saving?'},
                        'text': {'type': 'mrkdwn', 'text': 'This knowledge will not be saved.'},
                        'confirm': {'type': 'plain_text', 'text': 'Yes, cancel'},
                        'deny': {'type': 'plain_text', 'text': 'Keep'},
                    },
                },
            ],
        },
    ]


def edit_modal(draft_id: str, summary: str, tags: list[str], git_repo: str | None) -> dict:
    return {
        'type': 'modal',
        'callback_id': f'kb_modal:{draft_id}',
        'title': {'type': 'plain_text', 'text': 'Edit Knowledge'},
        'submit': {'type': 'plain_text', 'text': 'Save'},
        'close': {'type': 'plain_text', 'text': 'Back'},
        'blocks': [
            {
                'type': 'input',
                'block_id': 'summary_block',
                'label': {'type': 'plain_text', 'text': 'Summary'},
                'element': {
                    'type': 'plain_text_input',
                    'action_id': 'summary_input',
                    'multiline': True,
                    'initial_value': summary,
                },
            },
            {
                'type': 'input',
                'block_id': 'tags_block',
                'label': {'type': 'plain_text', 'text': 'Tags (comma-separated)'},
                'element': {
                    'type': 'plain_text_input',
                    'action_id': 'tags_input',
                    'initial_value': ', '.join(tags),
                    'placeholder': {'type': 'plain_text', 'text': 'kafka, messaging, architecture'},
                },
            },
            {
                'type': 'input',
                'block_id': 'repo_block',
                'label': {'type': 'plain_text', 'text': 'Repository URL (optional)'},
                'optional': True,
                'element': {
                    'type': 'plain_text_input',
                    'action_id': 'repo_input',
                    'initial_value': git_repo or '',
                    'placeholder': {'type': 'plain_text', 'text': 'https://github.com/org/repo'},
                },
            },
        ],
    }
