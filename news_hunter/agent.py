import pathlib

from dotenv import load_dotenv
from google.adk.agents import Agent
from tools import search_news, get_top_headlines, scrape_article, read_article

load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

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
    name="news_hunter",
    description=(
        "An agent that searches for news articles, gets top headlines, and "
        "reads full article content from the internet. It can find articles, "
        "extract their content, and provide summaries. It uses Jina Reader API "
        "as the primary reader and Apify Web Scraper as a fallback."
    ),
    instruction=_load_skill_instructions(_SKILL_MD),
    tools=[search_news, get_top_headlines, scrape_article, read_article],
)
