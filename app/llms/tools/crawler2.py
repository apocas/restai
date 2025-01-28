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
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }

    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, "html.parser")
    return soup.get_text()
