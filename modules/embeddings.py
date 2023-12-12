from langchain.embeddings import OpenAIEmbeddings
from langchain.embeddings import HuggingFaceEmbeddings

EMBEDDINGS = {
    "openai": (OpenAIEmbeddings, {}, "public", "https://platform.openai.com/docs/guides/embeddings"),  # type: ignore
    "huggingface": (HuggingFaceEmbeddings, {"model_name": "all-mpnet-base-v2"}, "private", "all-mpnet-base-v2 - https://www.sbert.net/docs/pretrained_models.html"),
}
