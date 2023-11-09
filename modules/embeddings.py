from langchain.embeddings import OpenAIEmbeddings
from langchain.embeddings import HuggingFaceEmbeddings

EMBEDDINGS = {
    "openai": (OpenAIEmbeddings, {}),  # type: ignore
    "huggingface": (HuggingFaceEmbeddings, {"model_name": "all-mpnet-base-v2"}),
}
