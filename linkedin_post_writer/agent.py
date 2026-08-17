import pathlib

from dotenv import load_dotenv, find_dotenv
from google.adk.agents import Agent
from .linkedin_api import (
    comment_on_linkedin_post,
    linkedin_auth_status,
    linkedin_connect_account,
    linkedin_disconnect,
    linkedin_exchange_code,
    publish_to_linkedin,
)
from tools import read_article, scrape_article

load_dotenv(find_dotenv())

_SKILL_MD = pathlib.Path(__file__).parent / "SKILL.md"


def _load_skill_instructions(path: pathlib.Path) -> str:
    """Load the instruction body from a SKILL.md file, skipping YAML frontmatter."""
    content = path.read_text(encoding="utf-8")
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content


root_agent = Agent(
    model="gemini-2.5-flash",
    name="linkedin_post_writer",
    description=(
        "Drafts LinkedIn posts from a user's brief or from an article URL. "
        "When a URL is given, reads the page (Jina Reader first, Apify Web Scraper "
        "as fallback), then writes in the voice of recruiting/HR, individual career "
        "networking, or company promotion as appropriate. A2A-compatible when run "
        "as an HTTP server."
    ),
    instruction=_load_skill_instructions(_SKILL_MD),
    tools=[
        read_article,
        scrape_article,
        linkedin_auth_status,
        linkedin_disconnect,
        linkedin_connect_account,
        linkedin_exchange_code,
        publish_to_linkedin,
        comment_on_linkedin_post,
    ],
)
