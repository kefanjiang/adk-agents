"""LinkedIn API integration: OAuth 2.0 token management + post publishing."""

import json
import os
import pathlib
import time
from dotenv import load_dotenv, find_dotenv
import requests

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
_TOKEN_FILE = pathlib.Path(__file__).resolve().parent / ".linkedin_tokens.json"

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"
LINKEDIN_IMAGES_URL = "https://api.linkedin.com/rest/images"
LINKEDIN_VIDEOS_URL = "https://api.linkedin.com/rest/videos"
LINKEDIN_SOCIAL_ACTIONS_URL = "https://api.linkedin.com/rest/socialActions"

LINKEDIN_API_VERSION = "202601" # need to update every year

MAX_IMAGE_SIZE = 8 * 1024 * 1024   # 8 MB
MAX_VIDEO_SIZE = 200 * 1024 * 1024  # 200 MB
MAX_POST_COMMENTARY_CHARS = 3000
MAX_COMMENT_CHARS = 1250

# LinkedIn Posts API "little text" reserved characters (must be escaped as literals).
# See: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/little-text-format
_LITTLE_TEXT_ESCAPE_CHARS = frozenset("|{}@[]()<>#\\*_~")
# Comments API message.text uses plain text + attributes (not little text). Escape
# structural chars that can break parsing, but keep # and @ for hashtags / mentions.
_COMMENT_ESCAPE_CHARS = frozenset("|{}[]()<>\\*_~")

# Scopes required: openid, profile, w_member_social
DEFAULT_SCOPES = "openid profile w_member_social"

load_dotenv(find_dotenv())

DOMAIN = os.getenv("DOMAIN", "localhost")
PORT = 9020
DEFAULT_REDIRECT_URI = f"http://{DOMAIN}:{PORT}/callback"


# ---------------------------------------------------------------------------
# Token persistence
# ---------------------------------------------------------------------------

def _load_tokens() -> dict | None:
    """Load stored tokens from disk."""
    if _TOKEN_FILE.exists():
        try:
            return json.loads(_TOKEN_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _save_tokens(data: dict) -> None:
    """Persist tokens to disk."""
    _TOKEN_FILE.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# OAuth 2.0 helpers
# ---------------------------------------------------------------------------

def get_authorization_url() -> dict:
    """Build the LinkedIn OAuth authorization URL the user must visit.

    Returns:
        dict with keys:
            - status: "success" or "error"
            - auth_url: the full URL the user should open in their browser
            - redirect_uri: DEFAULT_REDIRECT_URI (user needs it to grab the code)
            - error_message: present only on error
    """
    client_id = os.getenv("LINKEDIN_CLIENT_ID")
    if not client_id:
        return {"status": "error", "error_message": "LINKEDIN_CLIENT_ID is not set."}

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": DEFAULT_REDIRECT_URI,
        "scope": DEFAULT_SCOPES,
        "state": "hybro_linkedin_auth",
    }
    url = requests.Request("GET", LINKEDIN_AUTH_URL, params=params).prepare().url
    return {"status": "success", "auth_url": url, "redirect_uri": DEFAULT_REDIRECT_URI}


def linkedin_exchange_code(authorization_code: str) -> dict:
    """Exchange an authorization code for access + refresh tokens.

    After the user visits the auth URL and authorizes, LinkedIn redirects to
    redirect_uri?code=<CODE>&state=hybro_linkedin_auth.  Pass that code here.

    Args:
        authorization_code: The code from LinkedIn's redirect url.

    Returns:
        dict with status, plus on success the stored token info.
    """
    client_id = os.getenv("LINKEDIN_CLIENT_ID")
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET")
    if not client_id or not client_secret:
        return {
            "status": "error",
            "error_message": "LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET must be set.",
        }

    try:
        resp = requests.post(
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": authorization_code,
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

    # Fetch the member URN (sub claim from userinfo)
    member_urn = _fetch_member_urn(data["access_token"])
    if not member_urn:
        return {
            "status": "error",
            "error_message": "Got access token but failed to fetch LinkedIn member URN.",
        }

    tokens = {
        "access_token": data["access_token"],
        "expires_at": time.time() + data.get("expires_in", 3600),
        "refresh_token": data.get("refresh_token", ""),
        "refresh_token_expires_at": time.time() + data.get("refresh_token_expires_in", 0),
        "member_urn": member_urn,
    }
    _save_tokens(tokens)
    return {
        "status": "success",
        "message": "LinkedIn account connected successfully.",
        "member_urn": member_urn,
    }


def _refresh_access_token() -> dict | None:
    """Attempt to refresh the access token using a stored refresh token."""
    tokens = _load_tokens()
    if not tokens or not tokens.get("refresh_token"):
        return None

    client_id = os.getenv("LINKEDIN_CLIENT_ID")
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    try:
        resp = requests.post(
            LINKEDIN_TOKEN_URL,
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
        tokens["refresh_token_expires_at"] = time.time() + data.get("refresh_token_expires_in", 0)
    _save_tokens(tokens)
    return tokens


def _get_valid_access_token() -> tuple[str | None, str | None, str | None]:
    """Return (access_token, member_urn, error_message)."""
    tokens = _load_tokens()
    if not tokens:
        return None, None, "not_connected"

    # Check expiry (with 60s buffer)
    if tokens.get("expires_at", 0) < time.time() + 60:
        tokens = _refresh_access_token()
        if not tokens:
            return None, None, "token_expired"

    return tokens["access_token"], tokens.get("member_urn"), None


def _fetch_member_urn(access_token: str) -> str | None:
    """Fetch the member's person URN via the userinfo endpoint."""
    try:
        resp = requests.get(
            LINKEDIN_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        resp.raise_for_status()
        sub = resp.json().get("sub")
        if sub:
            return f"urn:li:person:{sub}"
    except requests.RequestException:
        pass
    return None


# ---------------------------------------------------------------------------
# Little text format helpers
# ---------------------------------------------------------------------------

def _escape_little_text(
    text: str,
    escape_chars: frozenset[str],
    *,
    preserve_hashtags: bool,
) -> str:
    if not text:
        return text

    result: list[str] = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        if (
            preserve_hashtags
            and ch == "#"
            and i + 1 < n
            and (text[i + 1].isalnum() or text[i + 1] == "_")
        ):
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            result.append(text[i:j])
            i = j
            continue

        if ch == "\\":
            result.append("\\\\")
        elif ch in escape_chars:
            result.append("\\" + ch)
        else:
            result.append(ch)
        i += 1

    return "".join(result)


def escape_linkedin_commentary(text: str) -> str:
    """Escape plain-text reserved characters for LinkedIn Posts API commentary.

    Unescaped ``(``, ``#``, ``*``, etc. in commentary can cause LinkedIn to
    silently truncate the post while still returning HTTP 201.

    Preserves ``#hashtag`` tokens (``#`` followed by word characters) so tags
    remain clickable. All other reserved characters are backslash-escaped.
    """
    return _escape_little_text(
        text, _LITTLE_TEXT_ESCAPE_CHARS, preserve_hashtags=True
    )


def escape_linkedin_comment_text(text: str) -> str:
    """Escape structural characters for Social Actions comment ``message.text``.

    Comments use plain text with optional mention attributes, not Posts-API
    little text. Parentheses and similar chars can still cause truncation, but
    ``#`` and ``@`` are left unescaped so hashtags and @names stay intact.
    """
    return _escape_little_text(text, _COMMENT_ESCAPE_CHARS, preserve_hashtags=False)


def _length_limit_error(
    *,
    label: str,
    raw_len: int,
    escaped_len: int,
    limit: int,
) -> dict:
    if escaped_len > raw_len:
        detail = (
            f"{label} is {raw_len} characters ({escaped_len} after LinkedIn "
            f"escaping); LinkedIn allows at most {limit}."
        )
    else:
        detail = f"{label} is {raw_len} characters; LinkedIn allows at most {limit}."
    return {"status": "error", "error_message": detail}


def _check_length_after_escape(
    raw_text: str,
    escaped_text: str,
    limit: int,
    *,
    label: str,
) -> dict | None:
    if len(escaped_text) > limit:
        return _length_limit_error(
            label=label,
            raw_len=len(raw_text),
            escaped_len=len(escaped_text),
            limit=limit,
        )
    return None


# ---------------------------------------------------------------------------
# Media upload helpers
# ---------------------------------------------------------------------------

def _linkedin_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "LinkedIn-Version": LINKEDIN_API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }


def _download_media(url: str, max_size: int) -> tuple[bytes, str]:
    """Download media from a URL. Returns (data, content_type)."""
    resp = requests.get(url, timeout=60, stream=True)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "application/octet-stream")
    data = resp.content
    if len(data) > max_size:
        raise ValueError(
            f"File too large: {len(data)} bytes (max {max_size // (1024*1024)} MB)"
        )
    return data, content_type


def _upload_image(access_token: str, member_urn: str, image_url: str) -> dict:
    """Upload an image to LinkedIn and return its URN."""
    headers = _linkedin_headers(access_token)

    init_resp = requests.post(
        f"{LINKEDIN_IMAGES_URL}?action=initializeUpload",
        json={"initializeUploadRequest": {"owner": member_urn}},
        headers=headers,
        timeout=30,
    )
    if init_resp.status_code != 200:
        return {"status": "error", "error_message": f"Image init failed: {init_resp.text[:300]}"}

    value = init_resp.json().get("value", {})
    upload_url = value.get("uploadUrl")
    image_urn = value.get("image")
    if not upload_url or not image_urn:
        return {"status": "error", "error_message": "Missing uploadUrl or image URN in init response."}

    try:
        image_data, content_type = _download_media(image_url, MAX_IMAGE_SIZE)
    except (requests.RequestException, ValueError) as e:
        return {"status": "error", "error_message": f"Failed to download image: {e}"}

    upload_resp = requests.put(
        upload_url,
        data=image_data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": content_type,
        },
        timeout=60,
    )
    if upload_resp.status_code not in (200, 201):
        return {"status": "error", "error_message": f"Image upload failed: {upload_resp.status_code}"}

    return {"status": "success", "image_urn": image_urn}


def _upload_video(access_token: str, member_urn: str, video_url: str) -> dict:
    """Upload a video to LinkedIn (chunked) and return its URN."""
    try:
        video_data, content_type = _download_media(video_url, MAX_VIDEO_SIZE)
    except (requests.RequestException, ValueError) as e:
        return {"status": "error", "error_message": f"Failed to download video: {e}"}

    headers = _linkedin_headers(access_token)

    init_resp = requests.post(
        f"{LINKEDIN_VIDEOS_URL}?action=initializeUpload",
        json={
            "initializeUploadRequest": {
                "owner": member_urn,
                "fileSizeBytes": len(video_data),
                "uploadCaptions": False,
                "uploadThumbnail": False,
            },
        },
        headers=headers,
        timeout=30,
    )
    if init_resp.status_code != 200:
        return {"status": "error", "error_message": f"Video init failed: {init_resp.text[:300]}"}

    value = init_resp.json().get("value", {})
    video_urn = value.get("video")
    upload_token = value.get("uploadToken", "")
    upload_instructions = value.get("uploadInstructions", [])
    if not video_urn or not upload_instructions:
        return {"status": "error", "error_message": "Missing video URN or upload instructions."}

    for instruction in upload_instructions:
        chunk_url = instruction.get("uploadUrl")
        first_byte = instruction.get("firstByte", 0)
        last_byte = instruction.get("lastByte", len(video_data) - 1)
        chunk = video_data[first_byte : last_byte + 1]

        chunk_resp = requests.put(
            chunk_url,
            data=chunk,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": content_type,
            },
            timeout=120,
        )
        if chunk_resp.status_code not in (200, 201):
            return {
                "status": "error",
                "error_message": f"Video chunk upload failed at byte {first_byte}: {chunk_resp.status_code}",
            }

    finalize_resp = requests.post(
        f"{LINKEDIN_VIDEOS_URL}?action=finalizeUpload",
        json={
            "finalizeUploadRequest": {
                "video": video_urn,
                "uploadToken": upload_token,
            },
        },
        headers=headers,
        timeout=30,
    )
    if finalize_resp.status_code not in (200, 201):
        return {"status": "error", "error_message": f"Video finalize failed: {finalize_resp.text[:300]}"}

    return {"status": "success", "video_urn": video_urn}


# ---------------------------------------------------------------------------
# Agent tools (exposed to the ADK agent)
# ---------------------------------------------------------------------------

def linkedin_disconnect() -> dict:
    """Disconnect the LinkedIn account by deleting the stored tokens.

    Returns:
        dict with:
            - status: "success" | "not_connected"
            - message: human-readable explanation
    """
    if not _TOKEN_FILE.exists():
        return {"status": "not_connected", "message": "No LinkedIn account is connected."}
    try:
        _TOKEN_FILE.unlink()
        return {"status": "success", "message": "LinkedIn account disconnected successfully."}
    except OSError as e:
        return {"status": "error", "message": f"Failed to disconnect: {e}"}


def linkedin_auth_status() -> dict:
    """Check whether the user's LinkedIn account is currently connected. Takes NO arguments.

    Use this only to CHECK state. It does NOT start the authorization flow.
    If the result is "not_connected" or "token_expired" and the user wants to
    connect or publish, follow up by calling `linkedin_connect_account()`
    immediately — do not stop to ask the user for information first.

    Returns:
        dict with:
            - status: "connected" | "not_connected" | "token_expired"
            - auth_url: (only when not connected) the URL the user should visit
            - message: human-readable explanation
    """
    token, urn, err = _get_valid_access_token()
    if token and urn:
        return {
            "status": "connected",
            "member_urn": urn,
            "message": "LinkedIn account is connected and ready to publish.",
        }

    # Not connected — generate an auth URL to guide the user
    auth = get_authorization_url()
    if err == "token_expired":
        return {
            "status": "token_expired",
            "message": (
                "Your LinkedIn token has expired. Please re-authorize by visiting "
                "the auth_url below."
            ),
            "auth_url": auth.get("auth_url", ""),
        }
    return {
        "status": "not_connected",
        "message": (
            "LinkedIn is not connected. To publish posts, the user needs to visit "
            "the auth_url below and provide the authorization code."
        ),
        "auth_url": auth.get("auth_url", ""),
    }


def linkedin_connect_account() -> dict:
    """Start the LinkedIn account connection flow. Takes NO arguments.

    Call this tool whenever the user wants to connect, link, authorize, sign in,
    or log in their LinkedIn account, OR whenever the account is not connected
    and the user wants to publish. It returns a LinkedIn authorization URL.

    After calling this tool, reply to the user with:
      1. The exact `auth_url` so they can click it to authorize.
      2. A short instruction asking them to paste back the authorization code
         they see on the callback page after authorizing.

    Then wait for the user's next message. When they send the code, call
    `linkedin_exchange_code(authorization_code=<code>)` to finalize the
    connection.

    Do NOT ask the user for email, password, username, client ID, redirect URI,
    scopes, or anything else before calling this tool.

    Returns:
        dict with:
            - status: "success" on success, "error" on failure
            - auth_url: the LinkedIn authorization URL (on success)
            - message: human-readable instruction that includes the URL
            - error_message: present only on error
    """
    auth = get_authorization_url()
    if auth["status"] == "error":
        return auth
    return {
        "status": "success",
        "auth_url": auth["auth_url"],
        "message": (
            "Click the link below to authorize this app to post on your "
            "LinkedIn, then paste the authorization code from the callback "
            "page back into this chat.\n\n"
            f"{auth['auth_url']}"
        ),
    }


def publish_to_linkedin(
    post_text: str,
    visibility: str = "PUBLIC",
    article_url: str = "",
    article_title: str = "",
    article_description: str = "",
    image_url: str = "",
    image_title: str = "",
    video_url: str = "",
    video_title: str = "",
) -> dict:
    """Publish a post to the authenticated user's LinkedIn profile.

    The user must be connected (see linkedin_auth_status) before calling this.
    Only one content attachment per post: image, video, or article link.

    Args:
        post_text: The main text/commentary of the LinkedIn post.
        visibility: "PUBLIC" (default) or "CONNECTIONS" (1st-degree only).
        article_url: Optional URL to attach as a link preview / article share.
        article_title: Optional title for the attached article.
        article_description: Optional description for the attached article.
        image_url: Optional URL of an image to upload and attach.
        image_title: Optional alt-text / title for the image.
        video_url: Optional URL of a video to upload and attach.
        video_title: Optional title for the video.

    Returns:
        dict with:
            - status: "success" or "error"
            - post_url: link to the published post (on success)
            - message: human-readable result
            - error_message: present only on error
    """
    token, member_urn, _ = _get_valid_access_token()
    if not token or not member_urn:
        auth = get_authorization_url()
        return {
            "status": "error",
            "error_message": (
                "LinkedIn is not connected. The user must authorize first. "
                "Auth URL: " + auth.get("auth_url", "(could not generate)")
            ),
        }

    if len(post_text) > MAX_POST_COMMENTARY_CHARS:
        return _length_limit_error(
            label="Post text",
            raw_len=len(post_text),
            escaped_len=len(post_text),
            limit=MAX_POST_COMMENTARY_CHARS,
        )

    commentary = escape_linkedin_commentary(post_text)
    length_err = _check_length_after_escape(
        post_text,
        commentary,
        MAX_POST_COMMENTARY_CHARS,
        label="Post text",
    )
    if length_err:
        return length_err

    body: dict = {
        "author": member_urn,
        "commentary": commentary,
        "visibility": visibility,
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
    }

    # Attach media — priority: image > video > article (only one allowed)
    if image_url:
        result = _upload_image(token, member_urn, image_url)
        if result["status"] != "success":
            return result
        body["content"] = {
            "media": {"id": result["image_urn"], "title": image_title or ""},
        }
    elif video_url:
        result = _upload_video(token, member_urn, video_url)
        if result["status"] != "success":
            return result
        body["content"] = {
            "media": {"id": result["video_urn"], "title": video_title or ""},
        }
    elif article_url:
        body["content"] = {
            "article": {
                "source": article_url,
                "title": article_title or "",
                "description": article_description or "",
            },
        }

    headers = _linkedin_headers(token)

    try:
        resp = requests.post(LINKEDIN_POSTS_URL, json=body, headers=headers, timeout=60)
        if resp.status_code == 201:
            post_urn = resp.headers.get("x-restli-id", "")
            post_url = f"https://www.linkedin.com/feed/update/{post_urn}" if post_urn else ""
            return {
                "status": "success",
                "post_url": post_url,
                "post_urn": post_urn,
                "message": (
                    "Post published to LinkedIn successfully! "
                    "Pass `post_urn` to comment_on_linkedin_post to comment on this post."
                ),
            }
        try:
            data = resp.json() if resp.content else {}
        except ValueError:
            data = {}
        return {
            "status": "error",
            "error_message": (
                f"LinkedIn API returned {resp.status_code}: "
                f"{data.get('message', resp.text[:300])}"
            ),
        }
    except requests.RequestException as e:
        return {"status": "error", "error_message": f"Request to LinkedIn failed: {e}"}


def comment_on_linkedin_post(post_urn: str, comment_text: str) -> dict:
    """Post a comment on a LinkedIn post, share, or UGC post.

    The user must be connected (see linkedin_auth_status) before calling this.

    Note: Standard `w_member_social` access only reliably permits commenting on
    posts the authenticated user authored. Commenting on other users' or
    organizations' posts requires LinkedIn's Community Management API
    (Marketing Developer Platform) partnership; without it, LinkedIn returns
    403 ACCESS_DENIED.

    Args:
        post_urn: The full URN of the post to comment on. Accepts:
            - `urn:li:share:<id>`
            - `urn:li:ugcPost:<id>`
            - `urn:li:activity:<id>`
            Or a LinkedIn feed URL (e.g.
            `https://www.linkedin.com/feed/update/urn:li:activity:123`),
            in which case the URN is extracted.
        comment_text: The text of the comment to post.

    Returns:
        dict with:
            - status: "success" or "error"
            - comment_urn: URN of the created comment (on success)
            - message: human-readable result
            - error_message: present only on error
    """
    token, member_urn, _ = _get_valid_access_token()
    if not token or not member_urn:
        auth = get_authorization_url()
        return {
            "status": "error",
            "error_message": (
                "LinkedIn is not connected. The user must authorize first. "
                "Auth URL: " + auth.get("auth_url", "(could not generate)")
            ),
        }

    if "urn:li:" in post_urn and "/" in post_urn:
        post_urn = post_urn[post_urn.find("urn:li:"):].rstrip("/")

    if not post_urn.startswith("urn:li:"):
        return {
            "status": "error",
            "error_message": (
                f"Invalid post URN: {post_urn!r}. Expected urn:li:share:<id>, "
                "urn:li:ugcPost:<id>, or urn:li:activity:<id>."
            ),
        }

    if len(comment_text) > MAX_COMMENT_CHARS:
        return _length_limit_error(
            label="Comment text",
            raw_len=len(comment_text),
            escaped_len=len(comment_text),
            limit=MAX_COMMENT_CHARS,
        )

    escaped_comment = escape_linkedin_comment_text(comment_text)
    length_err = _check_length_after_escape(
        comment_text,
        escaped_comment,
        MAX_COMMENT_CHARS,
        label="Comment text",
    )
    if length_err:
        return length_err

    encoded_urn = requests.utils.quote(post_urn, safe="")
    url = f"{LINKEDIN_SOCIAL_ACTIONS_URL}/{encoded_urn}/comments"
    body = {
        "actor": member_urn,
        "object": post_urn,
        "message": {"text": escaped_comment},
    }

    try:
        resp = requests.post(url, json=body, headers=_linkedin_headers(token), timeout=30)
        if resp.status_code in (200, 201):
            data = resp.json() if resp.content else {}
            return {
                "status": "success",
                "comment_urn": data.get("$URN") or data.get("id", ""),
                "message": "Comment posted to LinkedIn successfully!",
            }
        try:
            data = resp.json() if resp.content else {}
        except ValueError:
            data = {}
        hint = ""
        if resp.status_code == 403:
            hint = (
                " Note: commenting on posts you don't own requires LinkedIn's "
                "Community Management API partnership."
            )
        return {
            "status": "error",
            "error_message": (
                f"LinkedIn API returned {resp.status_code}: "
                f"{data.get('message', resp.text[:300])}{hint}"
            ),
        }
    except requests.RequestException as e:
        return {"status": "error", "error_message": f"Request to LinkedIn failed: {e}"}
