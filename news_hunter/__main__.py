import os
from pathlib import Path

from dotenv import load_dotenv

# examples/adk/.env — cwd-independent (bare load_dotenv() only searches process CWD).
_ADK_ENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ADK_ENV, override=False)

from a2a.types import AgentCapabilities, AgentCard, AgentSkill  
import uvicorn  
from google.adk.a2a.utils.agent_to_a2a import to_a2a  

from .agent import root_agent  
HOST = os.getenv("HOST", "0.0.0.0")
PORT = 9011
DOMAIN = os.getenv("DOMAIN", "localhost")


agent_card = AgentCard(
    name="News Hunter",
    description=(
        "Searches news articles from the internet based on user queries using the "
        "News API. Supports keyword search, date filtering, source filtering, "
        "language selection, and result sorting."
    ),
    url=f"http://{DOMAIN}:{PORT}",
    version="1.0.0",
    capabilities=AgentCapabilities(
        **{
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False,
        }
    ),
    defaultInputModes=["text"],
    defaultOutputModes=["text"],
    skills=[
        AgentSkill(
            id="search_news",
            name="News Search",
            description=(
                "Search news articles by keywords, date range, sources, domains, "
                "language, and sorting preference. Returns article titles and URLs."
            ),
            tags=["news", "search", "read","articles", "media"],
        )
    ],
)

app = to_a2a(root_agent, host=HOST, port=PORT, agent_card=agent_card)

uvicorn.run(app, host=HOST, port=PORT)
