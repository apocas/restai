from datetime import datetime
import inspect
import logging
import os
import pkgutil
from llama_index.core.tools import FunctionTool

import tiktoken

from restai.database import DBWrapper
from restai.models.databasemodels import OutputDatabase
from restai.models.models import LLMModel, User
from restai.project import Project

DEFAULT_LLMS = {}

DEFAULT_EMBEDDINGS = {}


def get_embedding_class(embedding_class_name: str):
    match embedding_class_name:
        case "LangChain" | "LangChain.Openai":
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings, {}
        case "LangChain.HuggingFace":
            from langchain_huggingface import HuggingFaceEmbeddings

            return HuggingFaceEmbeddings, {}
        case "OllamaEmbeddings" | "Ollama":
            from llama_index.embeddings.ollama import OllamaEmbedding

            return OllamaEmbedding, {}
        case _:
            raise Exception("Invalid embedding class name.")


def get_llm_class(llm_class_name: str):
    match llm_class_name:
        case "Ollama":
            from llama_index.llms.ollama import Ollama

            return Ollama, {"request_timeout": 120.0}
        case "OllamaMultiModal":
            from llama_index.multi_modal_llms.ollama import OllamaMultiModal

            return OllamaMultiModal, {"request_timeout": 120.0}
        case "OllamaMultiModal2":
            from restai.llms.ollamamultimodal import OllamaMultiModalInternal

            return OllamaMultiModalInternal, {"request_timeout": 120.0}
        case "OpenAI":
            from llama_index.llms.openai import OpenAI

            return OpenAI, {}
        case "OpenAILike":
            from llama_index.llms.openai_like import OpenAILike

            return OpenAILike, {}
        case "Grok":
            from llama_index.llms.anthropic import Anthropic

            return Anthropic, {
                "base_url": "https://api.x.ai/",
                "api_key": os.environ.get("XAI_API_KEY"),
                "model": "grok-beta",
            }
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

        case "GeminiMultiModal":
            from llama_index.multi_modal_llms.gemini import GeminiMultiModal

            return GeminiMultiModal, {}
        case "Gemini":
            from llama_index.llms.gemini import Gemini
            from vertexai.generative_models import (
                SafetySetting,
                HarmCategory,
                HarmBlockThreshold,
            )

            return Gemini, {
                "generate_kwargs": {
                    "safety_settings": [
                        SafetySetting(
                            category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                            threshold=HarmBlockThreshold.BLOCK_ONLY_HIGH,
                        )
                    ]
                }
            }
        case "AzureOpenAI":
            from llama_index.llms.azure_openai import AzureOpenAI

            return AzureOpenAI, {}
        case _:
            raise Exception("Invalid LLM class name.")


def load_generators() -> list[FunctionTool]:
    generators = []
    directory = os.path.dirname(os.path.abspath(__file__))

    print(f"Loading image generators...")
    for importer, modname, _ in pkgutil.iter_modules(
        path=[directory + "/image/workers"]
    ):
        module = __import__(f"restai.image.workers.{modname}", fromlist="dummy")
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and name == "worker":
                generators.append(obj)

    print(f"Loading userland image generators...")
    for importer, modname, _ in pkgutil.iter_modules(path=["./generators"]):
        module = __import__(f"generators.{modname}", fromlist="dummy")
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and name == "worker":
                replaced = False
                for i, existing_tool in enumerate(generators):
                    if (
                        existing_tool.__module__.split(".")[-1]
                        == obj.__module__.split(".")[-1]
                    ):
                        print(
                            f"WARNING: Duplicate generator '{obj.__module__}' found in generators! OVERWRITTEN!"
                        )
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
    for importer, modname, _ in pkgutil.iter_modules(
        path=[directory + "/audio/workers"]
    ):
        module = __import__(f"restai.audio.workers.{modname}", fromlist="dummy")
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and name == "worker":
                generators.append(obj)

    print(f"Loading userland audio generators...")
    for importer, modname, _ in pkgutil.iter_modules(path=["./audio"]):
        module = __import__(f"audio.{modname}", fromlist="dummy")
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and name == "worker":
                replaced = False
                for i, existing_tool in enumerate(generators):
                    if (
                        existing_tool.__module__.split(".")[-1]
                        == obj.__module__.split(".")[-1]
                    ):
                        print(
                            f"WARNING: Duplicate generator '{obj.__module__}' found in generators! OVERWRITTEN!"
                        )
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
    for importer, modname, _ in pkgutil.iter_modules(path=[directory + "/llms/tools"]):
        module = __import__(f"restai.llms.tools.{modname}", fromlist="dummy")
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj):
                tools.append(FunctionTool.from_defaults(fn=obj))

    print(f"Loading userland tools...")
    for importer, modname, _ in pkgutil.iter_modules(path=["./tools"]):
        module = __import__(f"tools.{modname}", fromlist="dummy")
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj):
                tool = FunctionTool.from_defaults(fn=obj)
                replaced = False
                for i, existing_tool in enumerate(tools):
                    if existing_tool.metadata.name == tool.metadata.name:
                        print(
                            f"WARNING: Duplicate tool '{tool.metadata.name}' found in tools! OVERWRITTEN!"
                        )
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


def get_logger(name: str, level=logging.INFO):
    """To set up as many loggers as you want"""

    handler = logging.FileHandler("./logs/" + name + ".log")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger


def log_inference(project: Project, user: User, output, db: DBWrapper):
    llm = LLMModel.model_validate(db.get_llm_by_name(project.props.llm))

    output_db_entry = OutputDatabase(
        user_id=user.id,
        llm=project.props.llm,
        question=output["question"] if project.props.options.logging else None,
        answer=output["answer"] if project.props.options.logging else None,
        date=datetime.now(),
        project_id=project.props.id,
        input_tokens=output["tokens"]["input"],
        output_tokens=output["tokens"]["output"],
        input_cost=(output["tokens"]["input"] * llm.input_cost) / 1000000,
        output_cost=(output["tokens"]["output"] * llm.output_cost) / 1000000,
    )

    if "id" in output:
        output_db_entry.chat_id = output["id"]

    db.db.add(output_db_entry)
    db.db.commit()
