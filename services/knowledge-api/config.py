import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY: str = os.getenv('ANTHROPIC_API_KEY', '')
QDRANT_HOST: str = os.getenv('QDRANT_HOST', 'localhost')
QDRANT_PORT: int = int(os.getenv('QDRANT_PORT', '6333'))
CLAUDE_MODEL: str = os.getenv('CLAUDE_MODEL', 'claude-haiku-4-5-20251001')
COLLECTION_NAME: str = os.getenv('COLLECTION_NAME', 'knowledge')
SLACK_BOT_TOKEN: str = os.getenv('SLACK_BOT_TOKEN', '')
SLACK_SIGNING_SECRET: str = os.getenv('SLACK_SIGNING_SECRET', '')
REPO_SERVICE_URL: str = os.getenv('REPO_SERVICE_URL', '')
CODER_AGENT_URL: str = os.getenv('CODER_AGENT_URL', '')
