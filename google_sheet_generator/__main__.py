import os
from pathlib import Path

from dotenv import load_dotenv

# examples/adk/.env — cwd-independent (bare load_dotenv() only searches process CWD).
_ADK_ENV = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ADK_ENV, override=False)

from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from starlette.routing import Route
import uvicorn
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .agent import root_agent
from .callback_page import oauth_callback

HOST = "127.0.0.1"
DOMAIN = os.getenv("DOMAIN", "localhost")
PORT = 19012

PUBLIC_URL= os.getenv("GOOGLE_SHEET_GENERATOR_PUBLIC_URL", f"http://{DOMAIN}:{PORT}")


agent_card = AgentCard(
    name="Google Sheet Generator",
    description=(
        "Creates and edits Google Spreadsheets on behalf of the authorized "
        "user.  Accepts tabular data (markdown tables, CSV, TSV, JSON, or "
        "natural-language lists) and materializes it as a real Sheet owned "
        "by the user.  Supports natural-language modifications: read current "
        "contents, update cells/rows/columns, insert or delete rows/columns, "
        "and clear ranges.  Returns the sheet URL."
    ),
    url= PUBLIC_URL,
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
            id="generate_sheet",
            name="Generate Google Sheet",
            description=(
                "Create a brand new Google Spreadsheet from tabular input "
                "(markdown, CSV, TSV, JSON, or natural-language lists).  "
                "The sheet is created in the authorized user's own Drive "
                "and the agent returns its URL."
            ),
            tags=["google-sheets", "spreadsheet", "create", "table", "csv", "json"],
        ),
        AgentSkill(
            id="modify_sheet",
            name="Modify Google Sheet",
            description=(
                "Edit an existing Google Spreadsheet (one previously made "
                "by this agent) based on natural-language instructions.  "
                "Supports reading current cells, updating values in cells/"
                "rows/columns, inserting and deleting rows and columns, "
                "clearing ranges, and adding new tabs."
            ),
            tags=[
                "google-sheets",
                "spreadsheet",
                "edit",
                "update",
                "insert",
                "delete",
                "clear",
            ],
        ),
    ],
)

app = to_a2a(root_agent, host=HOST, port=PORT, agent_card=agent_card)
app.routes.append(Route("/oauth/callback", oauth_callback, methods=["GET"]))

uvicorn.run(app, host=HOST, port=PORT)
