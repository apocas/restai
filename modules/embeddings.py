from langchain_community.embeddings import VertexAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings
import os

EMBEDDINGS = {
    #"name": (LOADER, {"args": "here"}, "Privacy (public/private)", "Description..."),
    "all-mpnet-base-v2": (HuggingFaceEmbeddings, {"model_name": "all-mpnet-base-v2"}, "private", "all-mpnet-base-v2 - https://www.sbert.net/docs/pretrained_models.html - https://huggingface.co/sentence-transformers/all-mpnet-base-v2", 768),
    "paraphrase-multilingual-mpnet-base-v2": (HuggingFaceEmbeddings, {"model_name": "paraphrase-multilingual-mpnet-base-v2"}, "private", "paraphrase-multilingual-mpnet-base-v2 - https://www.sbert.net/docs/pretrained_models.html - https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2", 768),
}

if os.environ.get("OPENAI_API_KEY"):
    EMBEDDINGS["openai_3_small"] = (OpenAIEmbeddings, {"model": "text-embedding-3-small"}, "public", "https://platform.openai.com/docs/guides/embeddings", 1536)
    EMBEDDINGS["openai_3_large"] = (OpenAIEmbeddings, {"model": "text-embedding-3-large"}, "public", "https://platform.openai.com/docs/guides/embeddings", 3072)
    EMBEDDINGS["openai_ada_002"] = (OpenAIEmbeddings, {"model": "text-embedding-ada-002"}, "public", "https://platform.openai.com/docs/guides/embeddings", 1536)
if os.environ.get("GOOGLE_API_KEY"):
    EMBEDDINGS["google_vertexai"] = (VertexAIEmbeddings, {}, "public", "https://cloud.google.com/vertex-ai/docs/generative-ai/learn/overview", 1408)