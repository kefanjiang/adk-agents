import os

import requests
from apify_client import ApifyClient


NEWS_API_EVERYTHING_URL = "https://newsapi.org/v2/everything"
NEWS_API_TOP_HEADLINES_URL = "https://newsapi.org/v2/top-headlines"


def search_news(
    q: str,
    search_in: str = "",
    sources: str = "",
    domains: str = "",
    exclude_domains: str = "",
    from_date: str = "",
    to_date: str = "",
    language: str = "en",
    sort_by: str = "publishedAt",
    page_size: int = 5,
    page: int = 1,
) -> dict:
    """Search for news articles using the News API.

    Args:
        q: Keywords or phrases to search for. Supports advanced syntax:
            - Surround phrases with quotes for exact match (e.g. "climate change")
            - Use + to require a word (e.g. +bitcoin)
            - Use - to exclude a word (e.g. -bitcoin)
            - Use AND / OR / NOT with optional parentheses
              (e.g. crypto AND (ethereum OR litecoin) NOT bitcoin)
        search_in: Restrict search to specific fields. Comma-separated combination
            of: title, description, content. Leave empty to search all fields.
        sources: Comma-separated source identifiers (max 20).
            Example: "bbc-news,cnn,the-verge"
        domains: Comma-separated domain names to restrict results.
            Example: "bbc.co.uk,techcrunch.com"
        exclude_domains: Comma-separated domain names to exclude.
            Example: "example.com,anotherdomain.com"
        from_date: Oldest article date in ISO 8601 format (e.g. "2026-03-01").
        to_date: Newest article date in ISO 8601 format (e.g. "2026-03-28").
        language: 2-letter ISO-639-1 language code. Options: ar, de, en, es, fr,
            he, it, nl, no, pt, ru, sv, ud, zh. Defaults to "en".
        sort_by: Sort order for results. Options:
            - "relevancy": articles closely related to q come first
            - "popularity": articles from popular sources come first
            - "publishedAt": newest articles come first (default)
        page_size: Number of results to return (1-100). Defaults to 5.
        page: Page number for pagination. Defaults to 1.

    Returns:
        dict with keys:
            - status: "success" or "error"
            - total_results: total number of matching articles
            - articles: list of dicts with title, url, source, published_at
            - error_message: present only when status is "error"
    """
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return {"status": "error", "error_message": "NEWS_API_KEY is not set."}

    params = {"apiKey": api_key, "q": q}

    if search_in:
        params["searchIn"] = search_in
    if sources:
        params["sources"] = sources
    if domains:
        params["domains"] = domains
    if exclude_domains:
        params["excludeDomains"] = exclude_domains
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if language:
        params["language"] = language
    if sort_by:
        params["sortBy"] = sort_by
    if page_size:
        params["pageSize"] = page_size
    if page:
        params["page"] = page

    try:
        response = requests.get(NEWS_API_EVERYTHING_URL, params=params, timeout=30)
        data = response.json()
    except requests.RequestException as e:
        return {"status": "error", "error_message": f"Request failed: {e}"}

    if data.get("status") != "ok":
        return {
            "status": "error",
            "error_message": data.get("message", "Unknown API error"),
        }

    articles = [
        {
            "title": article.get("title", ""),
            "url": article.get("url", ""),
            "source": article.get("source", {}).get("name", ""),
            "published_at": article.get("publishedAt", ""),
        }
        for article in data.get("articles", [])
    ]

    return {
        "status": "success",
        "total_results": data.get("totalResults", 0),
        "articles": articles,
    }


def get_top_headlines(
    country: str = "us",
    category: str = "",
    sources: str = "",
    q: str = "",
    page_size: int = 5,
    page: int = 1,
) -> dict:
    """Get top breaking news headlines by country, category, or source.

    Note: the `sources` parameter cannot be mixed with `country` or `category`.
    If `sources` is provided, `country` and `category` are ignored.

    Args:
        country: 2-letter ISO 3166-1 country code (e.g. "us", "gb", "au").
            Cannot be used together with sources. Defaults to "us".
        category: News category. Options: business, entertainment, general,
            health, science, sports, technology.
            Cannot be used together with sources.
        sources: Comma-separated source identifiers (e.g. "bbc-news,cnn").
            When provided, country and category are ignored.
        q: Optional keywords or phrase to narrow headlines.
        page_size: Number of results to return (1-100). Defaults to 5.
        page: Page number for pagination. Defaults to 1.

    Returns:
        dict with keys:
            - status: "success" or "error"
            - total_results: total number of matching headlines
            - articles: list of dicts with title, url, source, published_at
            - error_message: present only when status is "error"
    """
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        return {"status": "error", "error_message": "NEWS_API_KEY is not set."}

    params = {"apiKey": api_key}

    if sources:
        params["sources"] = sources
    else:
        if country:
            params["country"] = country
        if category:
            params["category"] = category

    if q:
        params["q"] = q
    if page_size:
        params["pageSize"] = page_size
    if page:
        params["page"] = page

    try:
        response = requests.get(NEWS_API_TOP_HEADLINES_URL, params=params, timeout=30)
        data = response.json()
    except requests.RequestException as e:
        return {"status": "error", "error_message": f"Request failed: {e}"}

    if data.get("status") != "ok":
        return {
            "status": "error",
            "error_message": data.get("message", "Unknown API error"),
        }

    headlines = [
        {
            "title": article.get("title", ""),
            "url": article.get("url", ""),
            "source": article.get("source", {}).get("name", ""),
            "published_at": article.get("publishedAt", ""),
        }
        for article in data.get("articles", [])
    ]

    return {
        "status": "success",
        "total_results": data.get("totalResults", 0),
        "articles": headlines,
    }


APIFY_WEB_SCRAPER_ACTOR_ID = "moJRLRc85AitArpNN"

PAGE_FUNCTION = """
async function pageFunction(context) {
    const { request } = context;
    const title = document.title || '';
    const content = document.body.innerText || '';
    return { url: request.url, title, content };
}
"""


def scrape_article(url: str) -> dict:
    """Scrape the full content of a web page given its URL.

    Uses the Apify Web Scraper actor to load the page (including JavaScript-
    rendered content) and extract the page title and body text.

    Args:
        url: The full URL of the article to scrape.

    Returns:
        dict with keys:
            - status: "success" or "error"
            - url: the scraped URL
            - title: the page title
            - content: the full body text of the page
            - error_message: present only when status is "error"
    """
    api_token = os.getenv("APIFY_API_TOKEN")
    if not api_token:
        return {"status": "error", "error_message": "APIFY_API_TOKEN is not set."}

    client = ApifyClient(token=api_token)
    actor_client = client.actor(APIFY_WEB_SCRAPER_ACTOR_ID)

    run_input = {
        "startUrls": [{"url": url}],
        "pageFunction": PAGE_FUNCTION,
        "maxPagesPerCrawl": 1,
    }

    try:
        run = actor_client.call(
            run_input=run_input,
            timeout_secs=120,
        )
    except Exception as e:
        return {"status": "error", "error_message": f"Apify actor run failed: {e}"}

    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        return {"status": "error", "error_message": "No dataset returned from actor run."}

    items = list(client.dataset(dataset_id).iterate_items())
    if not items:
        return {"status": "error", "error_message": "No data extracted from the page."}

    item = items[0]
    return {
        "status": "success",
        "url": item.get("url", url),
        "title": item.get("title", ""),
        "content": item.get("content", ""),
    }


JINA_READER_BASE_URL = "https://r.jina.ai/"


def read_article(url: str) -> dict:
    """Read the full content of a web page using Jina Reader API.

    Converts the URL into clean, LLM-friendly text via Jina's Reader service.
    This is a lightweight alternative to scrape_article -- no browser rendering,
    faster response, and returns clean markdown content.

    Args:
        url: The full URL of the article to read.

    Returns:
        dict with keys:
            - status: "success" or "error"
            - url: the article URL
            - title: the page title
            - content: the article content in clean markdown
            - error_message: present only when status is "error"
    """
    headers = {"Accept": "application/json"}

    jina_key = os.getenv("JINA_API_KEY")
    if jina_key:
        headers["Authorization"] = f"Bearer {jina_key}"

    try:
        response = requests.get(
            f"{JINA_READER_BASE_URL}{url}",
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        return {"status": "error", "error_message": f"Jina Reader request failed: {e}"}

    content_data = data.get("data", {})
    return {
        "status": "success",
        "url": content_data.get("url", url),
        "title": content_data.get("title", ""),
        "content": content_data.get("content", ""),
    }
