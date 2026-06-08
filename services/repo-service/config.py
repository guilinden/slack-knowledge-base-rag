import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.getenv(
    'DATABASE_URL',
    'postgresql+asyncpg://postgres:postgres@localhost/repos',
)
GITHUB_PAT: str = os.getenv('GITHUB_PAT', '')
APP_URL: str = os.getenv('APP_URL', '')
