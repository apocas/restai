import logging
import os
from llama_index.core.text_splitter import TokenTextSplitter, SentenceSplitter
from llama_index.core.schema import Document
from llama_index.core.readers.download import download_loader
from modules.loaders import LOADERS
import yake
import re
import time

DEFAULT_LLMS = {
    #"name": (LOADER, {"args": "here"}, "Privacy (public/private)", "Description...", "vision/chat/qa"),
    "openai_gpt3.5_turbo": ("OpenAI", {"temperature": 0, "model": "gpt-3.5-turbo"}, "public", "OpenAI GPT-3.5 Turbo", "chat"),
    "openai_gpt4": ("OpenAI", {"temperature": 0, "model": "gpt-4"}, "public", "OpenAI GPT-4 ", "chat"),
    "openai_gpt4_turbo": ("OpenAI", {"temperature": 0, "model": "gpt-4-turbo-preview"}, "public", "OpenAI GPT-4 Turbo", "chat"),
    "mistral_7b": ("Ollama", {"model": "mistral", "temperature": 0.0001, "keep_alive": 0}, "private", "https://ollama.com/library/mistral", "qa"),
    "llama2_13b": ("Ollama", {"model": "llama2:13b-chat", "temperature": 0.0001, "keep_alive": 0}, "private", "https://ollama.com/library/llama2", "chat"),
    "llama2_7b": ("Ollama", {"model": "llama2:7b-chat", "temperature": 0.0001, "keep_alive": 0}, "private", "https://ollama.com/library/llama2", "chat"),
    "llava16_13b": ("OllamaMultiModal2", {"model": "llava:13b-v1.6", "temperature": 0.0001, "keep_alive": 0}, "private", "https://ollama.com/library/llava", "vision"),
    "bakllava_7b": ("OllamaMultiModal2", {"model": "bakllava", "temperature": 0.0001, "keep_alive": 0}, "private", "https://ollama.com/library/bakllava", "vision"),
    "mixtral_8x7b": ("Ollama", {"model": "mixtral", "temperature": 0.0001, "keep_alive": 0}, "private", "https://ollama.com/library/mixtral", "chat"),
    "llama2_70b": ("Ollama", {"model": "llama2:70b-chat", "temperature": 0.0001, "keep_alive": 0}, "private", "https://ollama.com/library/llama2", "chat"),
}

def getLLMClass(llm_classname):
    if llm_classname == "Ollama":
        from app.llms.ollama import Ollama
        return Ollama
    elif llm_classname == "OllamaMultiModal2":
        from app.llms.ollamamultimodal import OllamaMultiModal2
        return OllamaMultiModal2
    elif llm_classname == "OpenAI":
        from llama_index.llms.openai import OpenAI
        return OpenAI
    elif llm_classname == "Groq":
        from llama_index.llms.groq import Groq
        return Groq
    elif llm_classname == "Anthropic":
        from llama_index.llms.anthropic import Anthropic
        return Anthropic
    else:
        raise Exception("Invalid LLM class name.")

def IndexDocuments(project, documents, splitter="sentence", chunks=256):
    if splitter == "sentence":
        splitter_o = TokenTextSplitter(
            separator=" ", chunk_size=chunks, chunk_overlap=30)
    elif splitter == "token":
        splitter_o = SentenceSplitter(
            separator=" ", paragraph_separator="\n", chunk_size=chunks, chunk_overlap=30)

    for document in documents:
        text_chunks = splitter_o.split_text(document.text)

        doc_chunks = [Document(text=t, metadata=document.metadata)
                      for t in text_chunks]

        for doc_chunk in doc_chunks:
            project.db.insert(doc_chunk)

    return len(doc_chunks)


def ExtractKeywordsForMetadata(documents):
    max_ngram_size = 4
    numOfKeywords = 15
    kw_extractor = yake.KeywordExtractor(n=max_ngram_size, top=numOfKeywords)
    for document in documents:
        metadataKeywords = ""
        keywords = kw_extractor.extract_keywords(document.text)
        for kw in keywords:
            metadataKeywords = metadataKeywords + kw[0] + ", "
        document.metadata["keywords"] = metadataKeywords

    return documents


def FindFileLoader(ext, eargs={}):
    if ext in LOADERS:
        loader_name, loader_args = LOADERS[ext]
        loader = download_loader(loader_name)()
        return loader
    else:
        raise Exception("Invalid file type.")


def FindEmbeddingsPath(projectName):
    embeddings_path = os.environ["EMBEDDINGS_PATH"]
    embeddingsPathProject = None

    if not os.path.exists(embeddings_path):
        os.makedirs(embeddings_path)

    project_dirs = [d for d in os.listdir(
        embeddings_path) if os.path.isdir(os.path.join(embeddings_path, d))]

    for dir in project_dirs:
        if re.match(f'^{projectName}_[0-9]+$', dir):
            embeddingsPathProject = os.path.join(embeddings_path, dir)

    if embeddingsPathProject is None:
        embeddingsPathProject = os.path.join(
            embeddings_path, projectName + "_" + str(int(time.time())))
        os.mkdir(embeddingsPathProject)

    return embeddingsPathProject


def loadEnvVars():
    if "EMBEDDINGS_PATH" not in os.environ:
        os.environ["EMBEDDINGS_PATH"] = "./embeddings/"

    if "ANONYMIZED_TELEMETRY" not in os.environ:
        os.environ["ANONYMIZED_TELEMETRY"] = "False"

    if "LOG_LEVEL" not in os.environ:
        os.environ["LOG_LEVEL"] = "INFO"

    os.environ["ALLOW_RESET"] = "true"


def get_logger(name, level=logging.INFO):
    """To setup as many loggers as you want"""

    handler = logging.FileHandler("./logs/" + name + ".log")
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger
