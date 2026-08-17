"""Google OAuth 2.0 integration for Sheets/Drive access.

Chat-driven authorization flow (mirrors the LinkedIn Post Writer pattern):

  1. Agent calls `google_connect_account()` -> returns an auth URL.
  2. User opens the URL, signs in to Google, grants the requested scopes.
  3. Google redirects to /oauth/callback hosted by this agent's uvicorn server.
     The HTML page (callback_page.py) shows the authorization code with a
     copy button.
  4. User copies the code and pastes it into the chat.
  5. Agent calls `google_exchange_code(authorization_code=<code>)` to swap
     the code for access + refresh tokens; tokens persist to disk.
  6. Subsequent Sheets tool calls reuse the saved tokens (with automatic
     refresh on expiry).

Required env vars:
  GOOGLE_OAUTH_CLIENT_ID
  GOOGLE_OAUTH_CLIENT_SECRET

Optional:
  GOOGLE_OAUTH_REDIRECT_URI    Defaults to http://{DOMAIN}:9012/oauth/callback
                               where DOMAIN comes from .env (or "localhost").
                               In production, set this to the public https URL,
                               e.g. https://agent.hybro.ai/oauth/callback, and
                               register that URI in Cloud Console too.
"""

import json
import os
import pathlib
import time
from functools import lru_cache

import gspread
import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Load examples/adk/.env regardless of cwd, before any os.getenv at module scope.
_ADK_ENV = pathlib.Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ADK_ENV, override=False)


# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

_TOKEN_FILE = pathlib.Path(__file__).resolve().parent / ".google_sheets_tokens.json"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

DOMAIN = os.getenv("DOMAIN", "localhost")
PORT = 9012
DEFAULT_REDIRECT_URI = os.getenv(
    "GOOGLE_SHEET_REDIRECT_URI",
    f"http://{DOMAIN}:{PORT}/oauth/callback",
)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _client_creds() -> tuple[str | None, str | None]:
    return (
        os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
        os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
    )


# ---------------------------------------------------------------------------
# Token persistence
# ---------------------------------------------------------------------------

def _load_tokens() -> dict | None:
    if _TOKEN_FILE.exists():
        try:
            return json.loads(_TOKEN_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _save_tokens(data: dict) -> None:
    _TOKEN_FILE.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# OAuth helpers
# ---------------------------------------------------------------------------

def get_authorization_url() -> dict:
    """Build the Google OAuth authorization URL the user must visit."""
    client_id, _ = _client_creds()
    if not client_id:
        return {"status": "error", "error_message": "GOOGLE_OAUTH_CLIENT_ID is not set."}

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": DEFAULT_REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": "hybro_google_sheets_auth",
    }
    url = requests.Request("GET", GOOGLE_AUTH_URL, params=params).prepare().url
    return {"status": "success", "auth_url": url, "redirect_uri": DEFAULT_REDIRECT_URI}


def _fetch_user_email(access_token: str) -> str | None:
    try:
        resp = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("email")
    except requests.RequestException:
        return None


def _refresh_access_token() -> dict | None:
    tokens = _load_tokens()
    if not tokens or not tokens.get("refresh_token"):
        return None

    client_id, client_secret = _client_creds()
    if not client_id or not client_secret:
        return None

    try:
        resp = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return None

    if "access_token" not in data:
        return None

    tokens["access_token"] = data["access_token"]
    tokens["expires_at"] = time.time() + data.get("expires_in", 3600)
    if data.get("refresh_token"):
        tokens["refresh_token"] = data["refresh_token"]
    _save_tokens(tokens)
    _gspread_client_cache.cache_clear()
    return tokens


def _get_valid_access_token() -> tuple[str | None, str | None, str | None]:
    """Return (access_token, user_email, error_message)."""
    tokens = _load_tokens()
    if not tokens:
        return None, None, "not_connected"

    if tokens.get("expires_at", 0) < time.time() + 60:
        tokens = _refresh_access_token()
        if not tokens:
            return None, None, "token_expired"

    return tokens["access_token"], tokens.get("email"), None


# ---------------------------------------------------------------------------
# Runtime client (used by sheets_api.py)
# ---------------------------------------------------------------------------

def _build_credentials() -> Credentials:
    tokens = _load_tokens()
    if not tokens:
        raise RuntimeError(
            "Google account is not connected.  Ask the agent to call "
            "google_connect_account() first."
        )
    client_id, client_secret = _client_creds()
    if not client_id or not client_secret:
        raise RuntimeError(
            "GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET are not set."
        )

    creds = Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri=GOOGLE_TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        tokens["access_token"] = creds.token
        if creds.expiry:
            tokens["expires_at"] = creds.expiry.timestamp()
        _save_tokens(tokens)
    return creds


@lru_cache(maxsize=1)
def _gspread_client_cache() -> gspread.Client:
    return gspread.authorize(_build_credentials())


def get_gspread_client() -> gspread.Client:
    """Return an authorized gspread client.  Raises if not connected."""
    return _gspread_client_cache()


# ---------------------------------------------------------------------------
# Agent tools
# ---------------------------------------------------------------------------

def google_auth_status() -> dict:
    """Check whether the user's Google account is currently connected. Takes NO arguments.

    Use this only to CHECK state.  It does NOT start the authorization flow.
    If the result is "not_connected" or "token_expired" and the user wants
    to perform any Sheets action, follow up by calling
    `google_connect_account()` immediately -- do not stop to ask the user
    for information first.

    Returns:
        dict with:
            - status: "connected" | "not_connected" | "token_expired"
            - email: connected account email (only when connected)
            - auth_url: (only when not connected) URL the user should visit
            - message: human-readable explanation
    """
    token, email, err = _get_valid_access_token()
    if token:
        return {
            "status": "connected",
            "email": email or "(unknown)",
            "message": f"Google account ({email or 'unknown'}) is connected.",
        }

    auth = get_authorization_url()
    if err == "token_expired":
        return {
            "status": "token_expired",
            "message": (
                "Your Google token has expired.  Please re-authorize by "
                "visiting the auth_url below."
            ),
            "auth_url": auth.get("auth_url", ""),
        }
    return {
        "status": "not_connected",
        "message": (
            "Google is not connected.  To create or edit Sheets, the user "
            "needs to visit the auth_url below and paste back the "
            "authorization code."
        ),
        "auth_url": auth.get("auth_url", ""),
    }


def google_connect_account() -> dict:
    """Start the Google account connection flow. Takes NO arguments.

    Call this tool whenever the user wants to connect, link, authorize,
    sign in, or log in their Google account, OR whenever the account is
    not connected and the user wants to create or edit a Sheet.  It
    returns a Google authorization URL.

    After calling this tool, reply to the user with:
      1. The exact `auth_url` so they can click it to authorize.
      2. A short instruction asking them to paste back the authorization
         code they see on the callback page after authorizing.

    Then wait for the user's next message.  When they send the code, call
    `google_exchange_code(authorization_code=<code>)` to finalize the
    connection.

    Do NOT ask the user for email, password, client ID, redirect URI,
    scopes, or anything else before calling this tool.

    Returns:
        dict with:
            - status: "success" on success, "error" on failure
            - auth_url: the Google authorization URL (on success)
            - message: human-readable instruction including the URL
            - error_message: present only on error
    """
    auth = get_authorization_url()
    if auth["status"] == "error":
        return auth
    return {
        "status": "success",
        "auth_url": auth["auth_url"],
        "message": (
            "Click the link below to authorize this app to manage Google "
            "Sheets on your behalf, then paste the authorization code from "
            "the callback page back into this chat.\n\n"
            f"{auth['auth_url']}"
        ),
    }


def google_exchange_code(authorization_code: str) -> dict:
    """Exchange a Google authorization code for access + refresh tokens.

    Call this after the user pastes the code shown on the /oauth/callback page.

    Args:
        authorization_code: The code from Google's callback URL.

    Returns:
        dict with status, message, email (on success), error_message (on error).
    """
    client_id, client_secret = _client_creds()
    if not client_id or not client_secret:
        return {
            "status": "error",
            "error_message": (
                "GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set."
            ),
        }

    code = (authorization_code or "").strip()
    if not code:
        return {"status": "error", "error_message": "authorization_code is empty."}

    try:
        resp = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": DEFAULT_REDIRECT_URI,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return {"status": "error", "error_message": f"Token exchange failed: {e}"}

    if "access_token" not in data:
        return {
            "status": "error",
            "error_message": data.get("error_description", "No access_token in response."),
        }

    email = _fetch_user_email(data["access_token"])

    tokens = {
        "access_token": data["access_token"],
        "expires_at": time.time() + data.get("expires_in", 3600),
        "refresh_token": data.get("refresh_token", ""),
        "id_token": data.get("id_token", ""),
        "email": email or "",
        "scope": data.get("scope", ""),
    }
    if not tokens["refresh_token"]:
        return {
            "status": "error",
            "error_message": (
                "Google returned an access token but no refresh token.  "
                "This usually means the user previously authorized without "
                "prompt=consent.  Call google_disconnect() and retry."
            ),
        }

    _save_tokens(tokens)
    _gspread_client_cache.cache_clear()

    return {
        "status": "success",
        "message": (
            f"Google account ({email or 'unknown'}) connected successfully. "
            "You can now create and edit Sheets."
        ),
        "email": email or "",
    }


def google_disconnect() -> dict:
    """Disconnect the Google account by deleting the stored tokens.

    Returns:
        dict with status ("success" | "not_connected" | "error") and message.
    """
    if not _TOKEN_FILE.exists():
        return {"status": "not_connected", "message": "No Google account is connected."}
    try:
        _TOKEN_FILE.unlink()
        _gspread_client_cache.cache_clear()
        return {"status": "success", "message": "Google account disconnected successfully."}
    except OSError as e:
        return {"status": "error", "message": f"Failed to disconnect: {e}"}
