import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY: str = os.getenv('ANTHROPIC_API_KEY', '')
CLAUDE_MODEL: str = os.getenv('CLAUDE_MODEL', 'claude-haiku-4-5-20251001')
GITHUB_PAT: str = os.getenv('GITHUB_PAT', '')
