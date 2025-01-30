from datetime import datetime
import inspect
import json
import logging
import os
import pkgutil
from llama_index.core.tools import FunctionTool

import tiktoken

from app.database import DBWrapper
from app.models.databasemodels import OutputDatabase

DEFAULT_LLMS = {
    # "name": (LOADER, {"args": "here"}, "Privacy (public/private)", "Description...", "vision/chat/qa"),
    "openai_gpt4o": ("OpenAI", {"temperature": 0, "model": "gpt-4o"}, "public", "OpenAI GPT-4o", "chat"),
    "openai_gpt4o_mini": ("OpenAI", {"temperature": 0, "model": "gpt-4o-mini"}, "public", "OpenAI GPT-4o Mini", "chat"),
    "llama31_8b": ("Ollama", {"model": "llama3.1", "temperature": 0.0001, "keep_alive": 0, "request_timeout": 120}, "private", "https://ollama.com/library/llama3.1", "chat"),
    "llama33_70b": ("Ollama", {"model": "llama3.3", "temperature": 0.0001, "keep_alive": 0, "request_timeout": 120}, "private", "https://ollama.com/library/llama3.3", "chat"),
    "deepseek-r1_70b": ("Ollama", {"model": "deepseek-r1:70b", "temperature": 0.0001, "keep_alive": 0, "request_timeout": 120}, "private", "https://ollama.com/library/deepseek-r1:70b", "chat"),
    "deepseek-r1_14b": ("Ollama", {"model": "deepseek-r1:14b", "temperature": 0.0001, "keep_alive": 0, "request_timeout": 120}, "private", "https://ollama.com/library/deepseek-r1:14b", "chat"),
    "deepseek-r1_32b": ("Ollama", {"model": "deepseek-r1:32b", "temperature": 0.0001, "keep_alive": 0, "request_timeout": 120}, "private", "https://ollama.com/library/deepseek-r1:32b", "chat"),
    "llava16_13b": ("OllamaMultiModal", {"model": "llava:13b-v1.6", "temperature": 0.0001, "keep_alive": 0, "request_timeout": 120}, "private", "https://ollama.com/library/llava", "vision"),
    "llava_13b": ("OllamaMultiModal", {"model": "llava:13b", "temperature": 0.0001, "keep_alive": 0, "request_timeout": 120}, "private", "https://ollama.com/library/llava", "vision"),
    "llava_34b": ("OllamaMultiModal", {"model": "llava:34b", "temperature": 0.0001, "keep_alive": 0, "request_timeout": 120}, "private", "https://ollama.com/library/llava", "vision"),
    "minicpm-v": ("OllamaMultiModal", {"model": "minicpm-v", "temperature": 0.0001, "keep_alive": 0, "request_timeout": 120}, "private", "https://ollama.com/library/minicpm-v", "vision"),
    "llama32_11b_vision": ("OllamaMultiModal", {"model": "llama3.2-vision", "temperature": 0.0001, "keep_alive": 0, "request_timeout": 120}, "private", "https://ollama.com/library/llama3.2-vision", "vision"),
}

DEFAULT_EMBEDDINGS = {
    # "name": (LOADER, {"args": "here"}, "Privacy (public/private)", "Description...", dimension),
    "nomic-embed-text": ("OllamaEmbeddings", {"model_name": "nomic-embed-text", "keep_alive": 0, "mirostat": 0}, "private",
                         "https://ollama.com/library/nomic-embed-text", 768),
    "mxbai-embed-large": ("OllamaEmbeddings", {"model_name": "mxbai-embed-large", "keep_alive": 0, "mirostat": 0}, "private",
                         "https://ollama.com/library/mxbai-embed-large", 768),
}


def get_embedding_class(embedding_class_name: str):
    match embedding_class_name:
        case "OllamaEmbeddings":
            from llama_index.embeddings.ollama import OllamaEmbedding
            return OllamaEmbedding, {}
        case _:
            raise Exception("Invalid embedding class name.")


def get_llm_class(llm_class_name: str):
    match llm_class_name:
        case "Ollama":
            from app.llms.ollama import Ollama
            return Ollama, {"request_timeout": 120.0}
        case "OllamaMultiModal":
            from llama_index.multi_modal_llms.ollama import OllamaMultiModal
            return OllamaMultiModal, {"request_timeout": 120.0}
        case "OllamaMultiModal2":
            from app.llms.ollamamultimodal import OllamaMultiModalInternal
            return OllamaMultiModalInternal, {"request_timeout": 120.0}
        case "OpenAI":
            from llama_index.llms.openai import OpenAI
            return OpenAI, {}
        case "Grok":
            from llama_index.llms.anthropic import Anthropic
            return Anthropic, {"base_url": "https://api.x.ai/", "api_key": os.environ.get("XAI_API_KEY"),
                               "model": "grok-beta"}
        case "Groq":
            from llama_index.llms.groq import Groq
            return Groq, {}
        case "Anthropic":
            from llama_index.llms.anthropic import Anthropic
            return Anthropic, {}
        case "LiteLLM":
            from llama_index.llms.litellm import LiteLLM
            return LiteLLM, {}
        case "vLLM":
            from llama_index.llms.vllm import Vllm
            return Vllm, {}
        case "Gemini":
            from llama_index.llms.gemini import Gemini
            from vertexai.generative_models import (
                SafetySetting,
                HarmCategory,
                HarmBlockThreshold
            )
            return Gemini, {"generate_kwargs": {"safety_settings": [
                SafetySetting(
                    category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH,
                )
            ]}}
        case "AzureOpenAI":
            from llama_index.llms.azure_openai import AzureOpenAI
            return AzureOpenAI, {}
        case _:
            raise Exception("Invalid LLM class name.")


def load_generators() -> list[FunctionTool]:
    generators = []
    directory = os.path.dirname(os.path.abspath(__file__))

    print(f"Loading image generators...")
    for importer, modname, _ in pkgutil.iter_modules(path=[directory + '/image/workers']):
        module = __import__(f'app.image.workers.{modname}', fromlist='dummy')
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and name == "worker":
                generators.append(obj)

    print(f"Loading userland image generators...")
    for importer, modname, _ in pkgutil.iter_modules(path=['./generators']):
        module = __import__(f'generators.{modname}', fromlist='dummy')
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and name == "worker":
                replaced = False
                for i, existing_tool in enumerate(generators):
                    if existing_tool.__module__.split(".")[-1] == obj.__module__.split(".")[-1]:
                        print(
                            f"WARNING: Duplicate generator '{obj.__module__}' found in generators! OVERWRITTEN!")
                        generators[i] = obj
                        replaced = True
                        break
                if not replaced:
                    generators.append(obj)

    return generators


def load_audio_generators() -> list[FunctionTool]:
    generators = []
    directory = os.path.dirname(os.path.abspath(__file__))

    print(f"Loading audio generators...")
    for importer, modname, _ in pkgutil.iter_modules(path=[directory + '/audio/workers']):
        module = __import__(f'app.audio.workers.{modname}', fromlist='dummy')
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and name == "worker":
                generators.append(obj)

    print(f"Loading userland audio generators...")
    for importer, modname, _ in pkgutil.iter_modules(path=['./audio']):
        module = __import__(f'audio.{modname}', fromlist='dummy')
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and name == "worker":
                replaced = False
                for i, existing_tool in enumerate(generators):
                    if existing_tool.__module__.split(".")[-1] == obj.__module__.split(".")[-1]:
                        print(
                            f"WARNING: Duplicate generator '{obj.__module__}' found in generators! OVERWRITTEN!")
                        generators[i] = obj
                        replaced = True
                        break
                if not replaced:
                    generators.append(obj)

    return generators


def load_tools() -> list[FunctionTool]:
    tools = []
    directory = os.path.dirname(os.path.abspath(__file__))

    print(f"Loading core tools...")
    for importer, modname, _ in pkgutil.iter_modules(path=[directory + '/llms/tools']):
        module = __import__(f'app.llms.tools.{modname}', fromlist='dummy')
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj):
                tools.append(FunctionTool.from_defaults(fn=obj))

    print(f"Loading userland tools...")
    for importer, modname, _ in pkgutil.iter_modules(path=['./tools']):
        module = __import__(f'tools.{modname}', fromlist='dummy')
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj):
                tool = FunctionTool.from_defaults(fn=obj)
                replaced = False
                for i, existing_tool in enumerate(tools):
                    if existing_tool.metadata.name == tool.metadata.name:
                        print(
                            f"WARNING: Duplicate tool '{tool.metadata.name}' found in tools! OVERWRITTEN!")
                        tools[i] = tool
                        replaced = True
                        break
                if not replaced:
                    tools.append(tool)

    return tools


def tokens_from_string(string: str, encoding_name: str = "cl100k_base") -> int:
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens


def get_logger(name, level=logging.INFO):
    """To set up as many loggers as you want"""

    handler = logging.FileHandler("./logs/" + name + ".log")
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger


def log_inference(user, output, db: DBWrapper):
    db.db.add(OutputDatabase(user=user.username, question=output["question"], answer=output["answer"],
                             data=json.dumps(output), date=datetime.now(), project=output["project"]))
    db.db.commit()
