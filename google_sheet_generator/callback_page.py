"""OAuth callback page handler for Google authorization."""

from starlette.responses import HTMLResponse

CALLBACK_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Google Sheets Authorization</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #f0f2f5; color: #1a1a1a;
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh; padding: 1rem;
  }
  .card {
    background: #fff; border-radius: 12px; box-shadow: 0 4px 24px rgba(0,0,0,.08);
    max-width: 520px; width: 100%; padding: 2.5rem; text-align: center;
  }
  .icon { font-size: 3rem; margin-bottom: 1rem; }
  h1 { font-size: 1.4rem; font-weight: 600; margin-bottom: .5rem; }
  .subtitle { color: #666; font-size: .95rem; margin-bottom: 1.5rem; line-height: 1.5; }
  .code-box {
    background: #f7f8fa; border: 2px dashed #d0d7de; border-radius: 8px;
    padding: 1rem; margin-bottom: 1.25rem; word-break: break-all;
    font-family: "SF Mono", Monaco, Consolas, monospace; font-size: .95rem;
    user-select: all; cursor: text; min-height: 2.5rem;
    color: #137333;
  }
  .btn {
    display: inline-flex; align-items: center; gap: .5rem;
    background: #1a73e8; color: #fff; border: none; border-radius: 24px;
    padding: .75rem 2rem; font-size: 1rem; font-weight: 600;
    cursor: pointer; transition: background .15s;
  }
  .btn:hover { background: #155cb0; }
  .btn.copied { background: #137333; }
  .error-card .code-box { border-color: #d93025; color: #d93025; }
  .error-card h1 { color: #d93025; }
  .hint { color: #888; font-size: .82rem; margin-top: 1.25rem; line-height: 1.5; }
</style>
</head>
<body>
<div class="card" id="card">
  <div class="icon" id="icon">📊</div>
  <h1 id="title">Google Sheets Authorization</h1>
  <p class="subtitle" id="subtitle">Loading...</p>
  <div class="code-box" id="code-box"></div>
  <button class="btn" id="copy-btn" style="display:none" onclick="copyCode()">
    Copy Code
  </button>
  <p class="hint" id="hint" style="display:none"></p>
</div>
<script>
(function() {
  var params = new URLSearchParams(window.location.search);
  var code = params.get("code");
  var error = params.get("error");
  var card = document.getElementById("card");
  var icon = document.getElementById("icon");
  var title = document.getElementById("title");
  var subtitle = document.getElementById("subtitle");
  var codeBox = document.getElementById("code-box");
  var copyBtn = document.getElementById("copy-btn");
  var hint = document.getElementById("hint");

  if (error) {
    card.classList.add("error-card");
    icon.textContent = "❌";
    title.textContent = "Authorization Failed";
    subtitle.textContent = params.get("error_description") || "The authorization was denied or an error occurred.";
    codeBox.textContent = "Error: " + error;
  } else if (code) {
    icon.textContent = "✅";
    title.textContent = "Authorization Successful!";
    subtitle.textContent = "Copy the code below and paste it into the chat to connect your Google account.";
    codeBox.textContent = code;
    copyBtn.style.display = "inline-flex";
    hint.style.display = "block";
    hint.textContent = "You can close this tab after copying the code.";
  } else {
    card.classList.add("error-card");
    icon.textContent = "⚠️";
    title.textContent = "No Authorization Code";
    subtitle.textContent = "This page didn't receive an authorization code. Please try the authorization flow again.";
    codeBox.textContent = "No code parameter found in the URL.";
  }
})();

function copyCode() {
  var code = document.getElementById("code-box").textContent;
  var btn = document.getElementById("copy-btn");
  navigator.clipboard.writeText(code).then(function() {
    btn.innerHTML = "✅ Copied!";
    btn.classList.add("copied");
    setTimeout(function() {
      btn.innerHTML = "Copy Code";
      btn.classList.remove("copied");
    }, 2000);
  });
}
</script>
</body>
</html>
"""


async def oauth_callback(_request):
    return HTMLResponse(CALLBACK_HTML)
