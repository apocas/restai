from datetime import datetime, timezone
import inspect
import logging
import os
import pkgutil
import re
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
        case "Bedrock":
            from llama_index.llms.bedrock_converse import BedrockConverse

            return BedrockConverse, {}
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
            if inspect.isfunction(obj) and not name.startswith("_"):
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


_SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bxox[abp]-[A-Za-z0-9\-]{10,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.=]{20,}\b", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9]{32,}\b"),
    re.compile(r"\b[A-Za-z0-9._%+\-]+:[^\s@]{4,}@", re.IGNORECASE),
]


def _redact_secrets(text):
    if not text or not isinstance(text, str):
        return text
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def log_inference(project: Project, user: User, output, db: DBWrapper, latency_ms=None, system_prompt=None, context=None):
    import json as _json

    input_cost = 0.0
    output_cost = 0.0
    if project.props.llm:
        llm_db = db.get_llm_by_name(project.props.llm)
        if llm_db is not None:
            llm = LLMModel.model_validate(llm_db)
            input_cost = (output["tokens"]["input"] * llm.input_cost) / 1000000
            output_cost = (output["tokens"]["output"] * llm.output_cost) / 1000000

    redact = bool(getattr(project.props.options, "redact_inference_logs", False))
    log_question = output["question"] if project.props.options.logging else None
    log_answer = output["answer"] if project.props.options.logging else None
    log_system = system_prompt if project.props.options.logging else None
    log_context = _json.dumps(context) if context and project.props.options.logging else None

    if redact:
        log_question = _redact_secrets(log_question)
        log_answer = _redact_secrets(log_answer)
        log_system = _redact_secrets(log_system)
        log_context = _redact_secrets(log_context)

    output_db_entry = OutputDatabase(
        user_id=user.id,
        team_id=project.props.team.id if project.props.team else None,
        llm=project.props.llm,
        question=log_question,
        answer=log_answer,
        date=datetime.now(timezone.utc),
        project_id=project.props.id,
        input_tokens=output["tokens"]["input"],
        output_tokens=output["tokens"]["output"],
        input_cost=input_cost,
        output_cost=output_cost,
        latency_ms=latency_ms,
        system_prompt=log_system,
        context=log_context,
    )

    if "id" in output:
        output_db_entry.chat_id = output["id"]

    db.db.add(output_db_entry)
    db.db.commit()


def log_retrieval_events(project, sources, db):
    """Log retrieval events for RAG source analytics."""
    from restai.models.databasemodels import RetrievalEventDatabase

    now = datetime.now(timezone.utc)
    for src in sources:
        source_name = src.get("source", "") if isinstance(src, dict) else str(src)
        score = src.get("score") if isinstance(src, dict) else None
        chunk_id = src.get("id") if isinstance(src, dict) else None
        chunk_text = src.get("text", "") if isinstance(src, dict) else ""

        chunk_text_length = len(chunk_text) if chunk_text else None
        chunk_token_length = None
        if chunk_text:
            try:
                chunk_token_length = tokens_from_string(chunk_text)
            except Exception:
                pass

        if source_name:
            db.db.add(RetrievalEventDatabase(
                project_id=project.props.id,
                source=source_name,
                score=score,
                chunk_id=chunk_id,
                chunk_token_length=chunk_token_length,
                chunk_text_length=chunk_text_length,
                date=now,
            ))
    db.db.commit()


def log_guard_event(project, guard_project_name, user, phase, action, mode, text_checked, guard_response, db):
    from restai.models.databasemodels import GuardEventDatabase

    event = GuardEventDatabase(
        project_id=project.props.id,
        guard_project=guard_project_name,
        user_id=user.id if user else None,
        phase=phase,
        action=action,
        mode=mode,
        text_checked=text_checked if project.props.options.logging else None,
        guard_response=guard_response,
        date=datetime.now(timezone.utc),
    )
    db.db.add(event)
    db.db.commit()
