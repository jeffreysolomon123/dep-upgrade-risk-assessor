import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_MAX_TOKENS = 500

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_HEADERS = {"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}