from typing import Any, Dict
def wikpedia(
    page: str, lang: str = "en", **load_kwargs: Dict[str, Any]
) -> str:
    """
    Retrieve a Wikipedia page. Useful for learning about a particular concept that isn't private information.

    Args:
        page (str): Title of the page to read.
        lang (str): Language of Wikipedia to read. (default: English)
    """
    import wikipedia

    wikipedia.set_lang(lang)
    try:
        wikipedia_page = wikipedia.page(page, **load_kwargs, auto_suggest=False)
    except wikipedia.PageError:
        return "Unable to load page. Try searching instead."
      
    return wikipedia_page.content