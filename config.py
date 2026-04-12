"""
config.py — Configuration and environment variable management.
Loads all API keys and settings from a .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "anthropic")

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

MCP_SERVER_SCRIPT: str = os.path.join(os.path.dirname(__file__), "mcp_server.py")

REPORTS_DIR: str = os.path.join(os.path.dirname(__file__), "reports")
