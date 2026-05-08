import logging
from urllib.parse import urlparse

from restai.helper import _is_private_ip
from restai.loaders.url import SeleniumWebReader

logger = logging.getLogger(__name__)


# Same caps used by the (lighter) `crawler_classic` tool — keep the
# two crawlers aligned so the agent can't get a wider attack surface
# by switching from one to the other.
_PAGE_LOAD_TIMEOUT_S = 30
_MAX_OUTPUT_CHARS = 200_000


def crawler_selenium(url: str) -> str:
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

    # SSRF guard. Mirrors `crawler_classic` — refuses anything that
    # resolves to loopback / private / link-local / cloud-metadata
    # ranges so the agent can't be jailbroken into hitting AWS IMDS
    # (`169.254.169.254`), an internal admin panel, or a sibling
    # service on the LAN. Without this, Selenium drives a real
    # browser to whatever URL the agent picks — every internal HTTP
    # surface inside the cluster is reachable.
    try:
        if _is_private_ip(hostname):
            logger.warning("Blocked SSRF attempt in crawler_selenium: %s", hostname)
            return f"ERROR: refusing to fetch private/internal address: {hostname}"
    except ValueError as e:
        return f"ERROR: {e}"

    reader = SeleniumWebReader(page_load_timeout=_PAGE_LOAD_TIMEOUT_S)
    try:
        docs = reader.load_data([url])
    except Exception as e:
        return f"ERROR: fetch failed: {e}"

    if not docs:
        return "ERROR: no content returned"

    text = docs[0].text or ""
    if len(text) > _MAX_OUTPUT_CHARS:
        text = text[: _MAX_OUTPUT_CHARS - 1] + "…[truncated]"
    return text
