from langchain_community.embeddings import VertexAIEmbeddings, HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings

EMBEDDINGS = {
    #"name": (LOADER, {"args": "here"}, "Privacy (public/private)", "Description..."),
    "openai_3_small": (OpenAIEmbeddings, {"model": "text-embedding-3-small"}, "public", "https://platform.openai.com/docs/guides/embeddings", 1536),
    "openai_3_large": (OpenAIEmbeddings, {"model": "text-embedding-3-large"}, "public", "https://platform.openai.com/docs/guides/embeddings", 3072),
    "openai_ada_002": (OpenAIEmbeddings, {"model": "text-embedding-ada-002"}, "public", "https://platform.openai.com/docs/guides/embeddings", 1536),
    "google_vertexai": (VertexAIEmbeddings, {}, "public", "https://cloud.google.com/vertex-ai/docs/generative-ai/learn/overview", 1408),
    "all-mpnet-base-v2": (HuggingFaceEmbeddings, {"model_name": "all-mpnet-base-v2"}, "private", "all-mpnet-base-v2 - https://www.sbert.net/docs/pretrained_models.html - https://huggingface.co/sentence-transformers/all-mpnet-base-v2", 768),
    "paraphrase-multilingual-mpnet-base-v2": (HuggingFaceEmbeddings, {"model_name": "paraphrase-multilingual-mpnet-base-v2"}, "private", "paraphrase-multilingual-mpnet-base-v2 - https://www.sbert.net/docs/pretrained_models.html - https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2", 768),
}
