import pathlib

from dotenv import find_dotenv, load_dotenv
from google.adk.agents import Agent

from .oauth_client import (
    google_auth_status,
    google_connect_account,
    google_disconnect,
    google_exchange_code,
)
from .sheets_api import (
    add_worksheet_tab,
    clear_range,
    create_google_sheet,
    delete_columns,
    delete_rows,
    insert_columns,
    insert_rows,
    read_sheet_contents,
    update_range,
)

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
    name="google_sheet_generator",
    description=(
        "Creates and edits Google Spreadsheets on behalf of the authorized "
        "user.  Accepts tabular data (markdown, CSV/TSV, JSON, or natural "
        "language) and turns it into a real Sheet owned by the user.  "
        "Supports natural-language edits: read current contents, update "
        "values, insert or delete rows/columns, and clear cells."
    ),
    instruction=_load_skill_instructions(_SKILL_MD),
    tools=[
        google_auth_status,
        google_connect_account,
        google_exchange_code,
        google_disconnect,
        create_google_sheet,
        add_worksheet_tab,
        read_sheet_contents,
        update_range,
        insert_rows,
        insert_columns,
        delete_rows,
        delete_columns,
        clear_range,
    ],
)
