from typing import Any, Dict
def wikipedia(
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
    # The agent framework injects context (_chat_id, _brain, _project_id, _user)
    # into **load_kwargs; strip those before forwarding to the wikipedia library,
    # which rejects unknown keyword args (page() got an unexpected keyword '_chat_id').
    load_kwargs = {k: v for k, v in load_kwargs.items() if not k.startswith("_")}
    try:
        wikipedia_page = wikipedia.page(page, **load_kwargs, auto_suggest=False)
    except wikipedia.PageError:
        return "Unable to load page. Try searching instead."
    except wikipedia.DisambiguationError as e:
        opts = ", ".join(list(getattr(e, "options", []) or [])[:5])
        return f"'{page}' is ambiguous. Try a more specific title, e.g.: {opts}"
    except Exception as e:
        # The `wikipedia` PyPI lib (unmaintained) throws bare JSONDecode/HTTP
        # errors when the upstream API returns empty/changed responses. Return
        # a clean ERROR string so the agent can fall back instead of the raw
        # exception leaking as an uncaught tool error.
        return f"ERROR: wikipedia lookup failed: {e}"

    return wikipedia_page.content