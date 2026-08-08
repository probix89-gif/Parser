"""Result formatter — Telegram message formatting + top domains summary."""

from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse


def format_results(
    urls: list[str], label: str, per_page: int = 50
) -> list[str]:
    """Format URLs into Telegram messages (paginated, max 50 URLs per message).

    Args:
        urls: List of clean URLs to format.
        label: Label for the result set (e.g., dork query or "Mass batch (N dorks)").
        per_page: Max URLs per Telegram message.

    Returns:
        List of Telegram message strings (each under 4096 chars).
    """
    domains = Counter(urlparse(u).netloc for u in urls)

    header = (
        f"🎯 {label}\n"
        f"📊 Results: {len(urls)} URLs across {len(domains)} domains\n\n"
    )

    # Top 10 domains
    top_domains = domains.most_common(10)
    if top_domains:
        header += "Top domains:\n"
        for domain, count in top_domains:
            header += f"  {domain}: {count}\n"
        header += "\n"

    messages: list[str] = []
    for i in range(0, len(urls), per_page):
        page = urls[i : i + per_page]
        text = header if i == 0 else f"📊 Page {i // per_page + 2}\n\n"
        for url in page:
            text += f"• {url}\n"
        if len(text) > 4000:
            text = text[:3900] + "\n... (truncated)"
        messages.append(text)

    return messages
