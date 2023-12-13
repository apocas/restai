from langchain.embeddings import OpenAIEmbeddings, VertexAIEmbeddings, HuggingFaceEmbeddings

EMBEDDINGS = {
    "openai": (OpenAIEmbeddings, {}, "public", "https://platform.openai.com/docs/guides/embeddings"),
    "google_vertexai": (VertexAIEmbeddings, {}, "public", "https://cloud.google.com/vertex-ai/docs/generative-ai/learn/overview"),
    "huggingface": (HuggingFaceEmbeddings, {"model_name": "all-mpnet-base-v2"}, "private", "all-mpnet-base-v2 - https://www.sbert.net/docs/pretrained_models.html"),
}
