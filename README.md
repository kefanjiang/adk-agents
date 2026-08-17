# ADK Agents

A2A-exposed agents built on [Google ADK](https://google.github.io/adk-docs/). Each agent is a standalone Python package that serves an A2A endpoint via `to_a2a()` and uvicorn. These agents are running at [Hybro.ai](https://hybro.ai/)

## Agents

| Agent | Port | What it does |
| --- | --- | --- |
| `news_hunter` | 9011 | Searches news, fetches top headlines, and reads full article content (NewsAPI + Jina Reader / Apify). |
| `linkedin_post_writer` | 9020 | Drafts LinkedIn posts from a brief or article URL, and publishes them to the user's profile over LinkedIn OAuth 2.0. |
| `google_sheet_generator` | 19012 | Creates and edits Google Sheets in the user's own Drive via Google OAuth 2.0. |

Shared tooling (article reading, news search, scraping) lives in `tools.py`. Each agent's prompt lives in its `SKILL.md`.

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env   # then fill in the values
```

### Environment variables

See `.env.example`. Summary:

- `GOOGLE_API_KEY` — Gemini model access for all agents.
- `NEWS_API_KEY`, `APIFY_API_TOKEN`, `JINA_API_KEY` — news search and article reading.
- `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET` — LinkedIn publishing.
- `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_SHEET_GENERATOR_PUBLIC_URL`, `GOOGLE_SHEET_REDIRECT_URI` — Google Sheets access.
- `HOST`, `DOMAIN` — bind address and the hostname advertised in the agent card.

## Running an agent

```bash
uv run python -m news_hunter
uv run python -m linkedin_post_writer
uv run python -m google_sheet_generator
```

Each serves its A2A agent card at `http://$DOMAIN:$PORT/.well-known/agent-card.json`.

## OAuth flow

`linkedin_post_writer` and `google_sheet_generator` both use an interactive OAuth 2.0 code exchange: the agent returns an authorization URL, the user authorizes and pastes the code back into the conversation, and the agent exchanges it for tokens. Tokens are stored locally (`.linkedin_tokens.json`, `.google_sheets_tokens.json`) and are gitignored.

## Tests

```bash
uv run pytest
```
