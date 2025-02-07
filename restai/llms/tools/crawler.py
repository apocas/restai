from restai.loaders.url import SeleniumWebReader


def crawler(
        url: str
) -> str:
    """
    Retrieve a web page content. Useful to get content from a specific URL.

    Args:
        url (str): URL to be crawled.
    """

    reader: SeleniumWebReader = SeleniumWebReader()
    docs = reader.load_data([url])

    return docs[0].text
