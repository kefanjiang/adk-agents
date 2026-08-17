import os

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

from a2a.types import AgentCapabilities, AgentCard, AgentSkill  # noqa: E402
from starlette.routing import Route  # noqa: E402
import uvicorn  # noqa: E402
from google.adk.a2a.utils.agent_to_a2a import to_a2a  # noqa: E402

from .agent import root_agent  # noqa: E402
from .callback_page import oauth_callback  # noqa: E402

HOST = os.getenv("HOST", "0.0.0.0")
PORT = 9020
DOMAIN = os.getenv("DOMAIN", "localhost")

agent_card = AgentCard(
    name="LinkedIn Post Writer",
    description=(
        "Drafts and publishes LinkedIn posts from a user brief or article URL. "
        "Reads pages via Jina Reader (primary) and Apify Web Scraper (fallback). "
        "Supports recruiting/HR, individual career and networking, and company "
        "product or service promotion voices. Can publish directly to LinkedIn "
        "via OAuth 2.0."
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
            id="draft_linkedin_post",
            name="Draft LinkedIn post",
            description=(
                "Write a LinkedIn post from user instructions or from content at a "
                "given URL, with optional tone, length, and format constraints."
            ),
            tags=["linkedin", "social", "career", "recruiting", "marketing"],
        ),
        AgentSkill(
            id="publish_linkedin_post",
            name="Publish to LinkedIn",
            description=(
                "Publish a drafted post directly to the user's LinkedIn profile. "
                "Requires OAuth 2.0 authorization. Supports PUBLIC and CONNECTIONS "
                "visibility, optional article link attachments."
            ),
            tags=["linkedin", "publish", "social", "oauth"],
        ),
    ],
)


app = to_a2a(root_agent, host=HOST, port=PORT, agent_card=agent_card)
app.routes.append(Route("/callback", oauth_callback, methods=["GET"]))

uvicorn.run(app, host=HOST, port=PORT)
