import requests
from bs4 import BeautifulSoup

def crawler2(
    url: str
) -> str:
    """
    Retrieve a web page content. Useful to get content from a specific URL.

    Args:
        url (str): URL to be crawled.
    """

    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")
    return soup.get_text()
