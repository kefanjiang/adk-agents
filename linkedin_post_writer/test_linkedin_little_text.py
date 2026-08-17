"""Tests for LinkedIn little text commentary escaping."""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

_module_path = Path(__file__).resolve().parent / "linkedin_api.py"
_spec = importlib.util.spec_from_file_location("linkedin_api_under_test", _module_path)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

escape_linkedin_commentary = _mod.escape_linkedin_commentary
escape_linkedin_comment_text = _mod.escape_linkedin_comment_text
MAX_COMMENT_CHARS = _mod.MAX_COMMENT_CHARS
MAX_POST_COMMENTARY_CHARS = _mod.MAX_POST_COMMENTARY_CHARS
publish_to_linkedin = _mod.publish_to_linkedin
comment_on_linkedin_post = _mod.comment_on_linkedin_post


def test_escapes_parentheses_that_cause_silent_truncation():
    text = "The introduction of ASSERT (Adaptive Spec-driven Scoring for Evaluation)"
    assert escape_linkedin_commentary(text) == (
        "The introduction of ASSERT \\(Adaptive Spec-driven Scoring for Evaluation\\)"
    )


def test_preserves_hashtag_tokens():
    text = "Great news today.\n\n#AI #ResponsibleAI #Innovation"
    assert escape_linkedin_commentary(text) == text


def test_escapes_hash_outside_hashtag_tokens():
    assert escape_linkedin_commentary("Use C# and (parens)") == "Use C\\# and \\(parens\\)"


def test_escapes_backslash_first():
    assert escape_linkedin_commentary("path\\to\\file (note)") == "path\\\\to\\\\file \\(note\\)"


def test_escapes_bullet_asterisks():
    text = "Highlights:\n\n* Point one\n* Point two"
    assert escape_linkedin_commentary(text) == (
        "Highlights:\n\n\\* Point one\n\\* Point two"
    )


def test_comment_escape_preserves_hash_and_at():
    text = "Nice post @Jane! See #AI (details inside)"
    assert escape_linkedin_comment_text(text) == (
        "Nice post @Jane! See #AI \\(details inside\\)"
    )


def test_comment_escape_still_escapes_parentheses():
    assert escape_linkedin_comment_text("ASSERT (Adaptive)") == "ASSERT \\(Adaptive\\)"


def test_publish_rejects_raw_over_limit(monkeypatch):
    monkeypatch.setattr(
        _mod,
        "_get_valid_access_token",
        lambda: ("token", "urn:li:person:1", None),
    )
    result = publish_to_linkedin("x" * (MAX_POST_COMMENTARY_CHARS + 1))
    assert result["status"] == "error"
    assert "3000" in result["error_message"]


def test_publish_rejects_when_escaped_length_exceeds_limit(monkeypatch):
    monkeypatch.setattr(
        _mod,
        "_get_valid_access_token",
        lambda: ("token", "urn:li:person:1", None),
    )
    # 3000 raw chars, 6000 after escaping each '(' -> '\('
    result = publish_to_linkedin("(" * MAX_POST_COMMENTARY_CHARS)
    assert result["status"] == "error"
    assert "after LinkedIn escaping" in result["error_message"]
    assert "6000" in result["error_message"]


def test_publish_sends_escaped_commentary(monkeypatch):
    monkeypatch.setattr(
        _mod,
        "_get_valid_access_token",
        lambda: ("token", "urn:li:person:1", None),
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.headers = {"x-restli-id": "urn:li:share:123"}
    mock_resp.content = b""
    with patch.object(_mod.requests, "post", return_value=mock_resp) as mock_post:
        result = publish_to_linkedin("ASSERT (Adaptive)")
    assert result["status"] == "success"
    body = mock_post.call_args.kwargs["json"]
    assert body["commentary"] == "ASSERT \\(Adaptive\\)"


def test_comment_rejects_when_escaped_length_exceeds_limit(monkeypatch):
    monkeypatch.setattr(
        _mod,
        "_get_valid_access_token",
        lambda: ("token", "urn:li:person:1", None),
    )
    result = comment_on_linkedin_post(
        "urn:li:share:123",
        "(" * MAX_COMMENT_CHARS,
    )
    assert result["status"] == "error"
    assert "after LinkedIn escaping" in result["error_message"]


def test_constants_match_linkedin_limits():
    assert MAX_POST_COMMENTARY_CHARS == 3000
    assert MAX_COMMENT_CHARS == 1250
