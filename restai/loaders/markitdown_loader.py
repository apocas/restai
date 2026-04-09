"""MarkItDown file loader — converts files to Markdown using Microsoft's
markitdown library, then wraps the result in LlamaIndex Document objects.

Also provides `auto_ingest()` which tries docling → markitdown → classic
in order, returning the first that succeeds.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from llama_index.core.schema import Document

logger = logging.getLogger(__name__)


def load_with_markitdown(
    file_path: str,
    source: Optional[str] = None,
) -> list[Document]:
    """Convert a file to Markdown via MarkItDown and return as Documents."""
    from markitdown import MarkItDown

    md = MarkItDown()
    result = md.convert(file_path)
    text = result.text_content if hasattr(result, "text_content") else str(result)
    if not text or not text.strip():
        return []
    metadata = {"source": source or Path(file_path).name}
    return [Document(text=text, metadata=metadata)]


def load_url_with_markitdown(
    url: str,
    source: Optional[str] = None,
) -> list[Document]:
    """Fetch a URL and convert to Markdown via MarkItDown."""
    from markitdown import MarkItDown

    md = MarkItDown()
    result = md.convert_url(url)
    text = result.text_content if hasattr(result, "text_content") else str(result)
    if not text or not text.strip():
        return []
    metadata = {"source": source or url}
    return [Document(text=text, metadata=metadata)]


def _has_content(docs: list[Document]) -> bool:
    return bool(docs) and any(d.text.strip() for d in docs)


def auto_ingest(
    file_path: str,
    source: str,
    *,
    manager=None,
    opts: Optional[dict] = None,
) -> tuple[list[Document], str]:
    """Try docling → markitdown → classic in order. Return (documents, method_used).

    `manager` is the multiprocessing Manager needed by docling's subprocess runner.
    `opts` is passed to the classic loader for format-specific options.
    """
    # 1. Docling — best quality for PDF/DOCX (layout-aware)
    if manager is not None:
        try:
            from restai.document.runner import load_documents

            docs = load_documents(manager, file_path)
            if _has_content(docs):
                logger.info("auto_ingest: docling succeeded for %s", source)
                return docs, "docling"
        except Exception as e:
            logger.info("auto_ingest: docling failed for %s (%s), trying markitdown", source, e)

    # 2. MarkItDown — broad format support, lightweight
    try:
        docs = load_with_markitdown(file_path, source=source)
        if _has_content(docs):
            logger.info("auto_ingest: markitdown succeeded for %s", source)
            return docs, "markitdown"
    except Exception as e:
        logger.info("auto_ingest: markitdown failed for %s (%s), trying classic", source, e)

    # 3. Classic — LlamaIndex file readers (always works for supported formats)
    try:
        from restai.vectordb.tools import find_file_loader

        ext = Path(file_path).suffix.lower()
        loader = find_file_loader(ext, opts or {})
        try:
            docs = loader.load_data(file=Path(file_path))
        except TypeError:
            docs = loader.load_data(input_file=Path(file_path))
        if _has_content(docs):
            logger.info("auto_ingest: classic succeeded for %s", source)
            return docs, "classic"
    except Exception as e:
        logger.warning("auto_ingest: classic also failed for %s (%s)", source, e)

    return [], "classic"
