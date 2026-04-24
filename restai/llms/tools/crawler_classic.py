import logging
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from restai.helper import _is_private_ip

logger = logging.getLogger(__name__)


def crawler_classic(url: str) -> str:
    """
    Retrieve a web page content. Useful to get content from a specific URL.

    Args:
        url (str): URL to be crawled.
    """
    try:
        hostname = urlparse(url).hostname
    except Exception:
        return f"ERROR: invalid URL: {url}"
    if not hostname:
        return f"ERROR: URL has no hostname: {url}"

    # Same SSRF guard used by resolve_image() — refuse anything that
    # resolves to a loopback / private / link-local address so the
    # agent can't be jailbroken into hitting the cloud metadata
    # service or any internal LAN host.
    try:
        if _is_private_ip(hostname):
            logger.warning("Blocked SSRF attempt in crawler_classic: %s", hostname)
            return f"ERROR: refusing to fetch private/internal address: {hostname}"
    except ValueError as e:
        return f"ERROR: {e}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException as e:
        return f"ERROR: fetch failed: {e}"

    soup = BeautifulSoup(response.content, "html.parser")
    return soup.get_text()
