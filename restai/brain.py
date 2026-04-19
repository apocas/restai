import json
import logging
import traceback
from typing import Optional, Iterable
from restai.database import DBWrapper
from restai.models.databasemodels import ProjectDatabase
from restai.vectordb import tools as vector_tools
from restai import tools
from restai.llm import LLM
from restai.embedding import Embedding
from restai.models.models import LLMModel, ProjectModel, ClassifierModel, EmbeddingModel
from restai.project import Project
from transformers import pipeline
from llama_index.core.tools import FunctionTool
from restai import config
from llama_index.storage.chat_store.redis import RedisChatStore
from llama_index.core.storage.chat_store import SimpleChatStore
from llama_index.core.storage.chat_store.base import BaseChatStore
import tiktoken
from llama_index.core import Settings
from llama_index.core.callbacks import CallbackManager, TokenCountingHandler
import re


class Brain:
    def __init__(self, lightweight=False):
        self.defaultCensorship: str = "I'm sorry, I don't know the answer to that."
        self.defaultSystem: str = ""

        self.tokenizer = tiktoken.get_encoding("cl100k_base").encode
        self.token_counter = TokenCountingHandler(tokenizer=self.tokenizer)
        Settings.callback_manager = CallbackManager([self.token_counter])

        self.embeddings_cache = {}
        self._classifier_cache = {}
        self._ner_cache = {}
        # agent2 in-memory session store: chat_id -> list[message dict]
        self._agent2_sessions: dict[str, list[dict]] = {}
        self.docker_manager = None

        # Tools are lazy-loaded when first requested via get_tools(). The
        # full app sets them eagerly below so the first chat is fast; cron
        # processes (which use lightweight=True) only pay the load cost if
        # they actually fire an agent that needs tools.
        self.tools: list[FunctionTool] | None = None

        if not lightweight:
            self.tools = tools.load_tools()

            if config.RESTAI_GPU == True:
                self.generators: list[FunctionTool] = tools.load_generators()
                self.audio_generators: list[FunctionTool] = tools.load_audio_generators()

            self.chat_store: BaseChatStore
            self.reinit_chat_store()
            self.init_docker_manager()

    def init_docker_manager(self):
        """Create or recreate the Docker manager from current config."""
        # Shut down existing manager if any
        if self.docker_manager is not None:
            self.docker_manager.shutdown()
            self.docker_manager = None

        if not getattr(config, "DOCKER_ENABLED", False):
            return

        docker_url = getattr(config, "DOCKER_URL", "") or ""
        if not docker_url.strip():
            return

        try:
            from restai.docker_manager import DockerManager
            self.docker_manager = DockerManager(
                docker_url=docker_url,
                docker_image=getattr(config, "DOCKER_IMAGE", "python:3.12-slim"),
                container_timeout=int(getattr(config, "DOCKER_TIMEOUT", 900)),
                network_mode=getattr(config, "DOCKER_NETWORK", "none"),
                read_only=bool(getattr(config, "DOCKER_READ_ONLY", True)),
            )
        except Exception as e:
            logging.warning("Failed to initialize Docker manager: %s", e)
            self.docker_manager = None

    def shutdown_docker_manager(self):
        """Gracefully shut down the Docker manager and remove all containers."""
        if self.docker_manager is not None:
            self.docker_manager.shutdown()
            self.docker_manager = None

    # ------------------------------------------------------------------
    # Tool-generated image cache (Redis when available, in-memory fallback)
    # ------------------------------------------------------------------

    _IMAGE_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h
    _IMAGE_CACHE_KEY_PREFIX = "restai_image_cache:"
    _MIME_TO_EXT = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/webp": "webp",
        "image/gif": "gif",
    }
    _EXT_TO_MIME = {v: k for k, v in _MIME_TO_EXT.items()}

    def _image_cache_redis(self):
        """Lazily build a sync Redis client for the image cache. Self-healing
        like the agent2 session store — drops the cached client when the
        configured URL changes so admin Settings updates take effect on the
        next call. Returns None when Redis isn't configured."""
        url = config.build_redis_url()
        if not url:
            cached = getattr(self, "_image_cache_redis_client", None)
            if cached is not None:
                try:
                    cached.close()
                except Exception:
                    pass
                self._image_cache_redis_client = None
                self._image_cache_redis_url = None
            return None
        cached = getattr(self, "_image_cache_redis_client", None)
        cached_url = getattr(self, "_image_cache_redis_url", None)
        if cached is not None and cached_url == url:
            return cached
        try:
            import redis  # sync client; the image cache call sites are sync
            client = redis.Redis.from_url(url)
        except Exception as e:
            logging.warning("image cache: failed to build Redis client (%s); using in-process fallback", e)
            return None
        self._image_cache_redis_client = client
        self._image_cache_redis_url = url
        return client

    def _image_cache_local(self) -> dict:
        """In-process fallback when Redis isn't configured. Single-worker only —
        data is invisible to other workers / nodes, but better than failing in
        a dev setup."""
        store = getattr(self, "_image_cache_local_store", None)
        if store is None:
            store = {}
            self._image_cache_local_store = store
        return store

    def cache_image(self, data: bytes, mime_type: str = "image/png") -> str:
        """Stash an image and return ``"<id>.<ext>"`` for the URL.

        Redis-backed when configured, so every worker / node sees the same
        cache. Falls back to an in-process dict otherwise (works for single-
        worker dev only — multi-worker without Redis will 404 on cross-worker
        reads, same caveat as the chat store)."""
        import secrets
        import time as _time

        ext = self._MIME_TO_EXT.get((mime_type or "").lower(), "png")
        image_id = secrets.token_hex(16)  # 32-char unguessable id
        filename = f"{image_id}.{ext}"

        client = self._image_cache_redis()
        if client is not None:
            try:
                client.set(
                    self._IMAGE_CACHE_KEY_PREFIX + filename,
                    data,
                    ex=self._IMAGE_CACHE_TTL_SECONDS,
                )
                return filename
            except Exception as e:
                logging.warning("image cache: Redis write failed (%s); using in-process fallback", e)

        # In-process fallback
        store = self._image_cache_local()
        # Lazy sweep of expired entries so the dict can't grow forever.
        now = _time.time()
        expired = [k for k, (_d, _m, exp) in store.items() if exp < now]
        for k in expired:
            store.pop(k, None)
        store[filename] = (data, mime_type, now + self._IMAGE_CACHE_TTL_SECONDS)
        return filename

    def get_cached_image(self, filename: str):
        """Return ``(bytes, mime_type)`` for a cached image, or ``None`` when
        the file is missing or older than the TTL."""
        import time as _time

        # Defense in depth against URL traversal — endpoint already validates
        # but we double-check here.
        if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
            return None

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
        mime = self._EXT_TO_MIME.get(ext, "application/octet-stream")

        client = self._image_cache_redis()
        if client is not None:
            try:
                data = client.get(self._IMAGE_CACHE_KEY_PREFIX + filename)
                if data is not None:
                    return data, mime
            except Exception as e:
                logging.warning("image cache: Redis read failed (%s); falling back to in-process", e)

        store = self._image_cache_local()
        entry = store.get(filename)
        if entry is None:
            return None
        data, stored_mime, expires_at = entry
        if expires_at < _time.time():
            store.pop(filename, None)
            return None
        return data, stored_mime or mime

    def reinit_chat_store(self):
        redis_url = config.build_redis_url()
        if redis_url:
            self.chat_store = RedisChatStore(redis_url=redis_url)
        else:
            self.chat_store = SimpleChatStore()
        # Also invalidate the agent2 Redis client cache so the next session
        # operation rebuilds it against the new settings.
        self.reinit_agent2_redis()

    def reinit_agent2_redis(self):
        """Drop any cached agent2 Redis client + URL.

        Called from the settings router whenever Redis config changes via the
        admin GUI. Safe to call even if no client was ever built.
        """
        client = getattr(self, "_agent2_redis", None)
        if client is not None:
            try:
                # redis.asyncio clients expose aclose(); fall back to close()
                aclose = getattr(client, "aclose", None) or getattr(client, "close", None)
                if aclose is not None:
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(aclose())  # fire-and-forget
                    except RuntimeError:
                        # No running loop — ignore; GC will reclaim it
                        pass
            except Exception:
                pass
        self._agent2_redis = None
        self._agent2_redis_url = None

    def get_llm(self, llmName: str, db: DBWrapper) -> Optional[LLM]:
        llm: Optional[LLM] = self.load_llm(llmName, db)

        if llm is None:
            return None

        if hasattr(llm.llm, "system_prompt"):
            llm.llm.system_prompt = None
        return llm

    def get_system_llm(self, db: DBWrapper) -> Optional[LLM]:
        """Return the configured internal/housekeeping LLM, or None if not configured.

        Reads from DB directly (not config cache) so it picks up changes
        immediately, even in multi-worker deployments.
        """
        setting = db.get_setting("system_llm")
        name = (setting.value if setting and setting.value else "").strip()
        if not name:
            return None
        return self.get_llm(name, db)

    def post_processing_reasoning(self, output):
        think_content = None
        think_pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)
        match = think_pattern.search(output["answer"])
        if match:
            think_content = match.group(1).strip()
            output["answer"] = think_pattern.sub("", output["answer"]).strip()
            if think_content and "reasoning" not in output:
                output["reasoning"] = {
                    "output": think_content,
                    "steps": [
                        {
                            "actions": [
                                {"output": think_content, "action": "reasoning"}
                            ],
                            "output": think_content,
                        }
                    ],
                }
        return output

    def post_processing_counting(self, output):
        counting_event_found = None

        for i in range(len(self.token_counter.llm_token_counts) - 1, -1, -1):
            counting_event = self.token_counter.llm_token_counts[i]
            if (
                hasattr(counting_event, "prompt")
                and counting_event.prompt
                and counting_event.prompt.endswith(output["question"])
            ):
                counting_event_found = counting_event
                break

        if counting_event_found is not None:
            self.token_counter.llm_token_counts = self.token_counter.llm_token_counts[i+1:]
            output["tokens"] = {
                "input": counting_event_found.prompt_token_count,
                "output": counting_event_found.completion_token_count,
                "accuracy": "medium",
            }
        else:
            output["tokens"] = {
                "input": tools.tokens_from_string(output["question"]),
                "output": tools.tokens_from_string(output["answer"]),
                "accuracy": "low",
            }

    @staticmethod
    def load_llm(llmName: str, db: DBWrapper) -> Optional[LLM]:
        llm_db = db.get_llm_by_name(llmName)

        if llm_db is not None:
            llm_model = LLMModel.model_validate(llm_db)

            llm_class, llm_default_params = tools.get_llm_class(llm_model.class_name)
            llm_params = {**(llm_default_params or {}), **llm_model.options}
            llm = llm_class(**llm_params)

            return LLM(llmName, llm_model, llm)
        else:
            return None

    def get_embedding(self, embeddingName: str, db: DBWrapper) -> Optional[Embedding]:
        embedding_db = db.get_embedding_by_name(embeddingName)

        if self.embeddings_cache.get(embeddingName):
            return self.embeddings_cache[embeddingName]
        else:
            if embedding_db is not None:
                embedding_model = EmbeddingModel.model_validate(embedding_db)

                embedding_class, embedding_default_params = tools.get_embedding_class(
                    embedding_model.class_name
                )
                llm_params = json.loads(embedding_model.options)
                if embedding_default_params is not None:
                    llm_params.update(embedding_default_params)
                embedding = embedding_class(**llm_params)

                embedding_final = Embedding(embeddingName, embedding_model, embedding)
                self.embeddings_cache[embeddingName] = embedding_final
                return embedding_final

    def find_project(self, id: int, db: DBWrapper) -> Optional[Project]:
        p: Optional[ProjectDatabase] = db.get_project_by_id(id)
        if p is None:
            return None

        proj: ProjectModel = ProjectModel.model_validate(p)
        if proj is None:
            return None
        proj.creator_username = p.creator_user.username if p.creator_user else None

        project: Project = Project(proj)
        project.props = proj
        if project.props.type == "rag":
            try:
                project.vector = vector_tools.find_vector_db(project)(
                    self, project, self.get_embedding(project.props.embeddings, db)
                )
            except Exception as e:
                logging.error(e)
                traceback.print_tb(e.__traceback__)
                project.vector = None
        return project

    VALID_CLASSIFIERS = {
        "facebook/bart-large-mnli": "BART Large MNLI (default)",
        "MoritzLaurer/deberta-v3-large-zeroshot-v2.0": "DeBERTa v3 Large (best accuracy)",
        "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli": "DeBERTa v3 Base (balanced)",
        "joeddav/xlm-roberta-large-xnli": "XLM-RoBERTa (multilingual, 100+ languages)",
        "typeform/distilbert-base-uncased-mnli": "DistilBERT MNLI (fastest)",
    }
    DEFAULT_CLASSIFIER = "facebook/bart-large-mnli"

    def classify(self, classifier_model: ClassifierModel):
        model_name = classifier_model.model or self.DEFAULT_CLASSIFIER
        if model_name not in self.VALID_CLASSIFIERS:
            raise ValueError(f"Invalid classifier: '{model_name}'. Must be one of: {', '.join(self.VALID_CLASSIFIERS.keys())}")
        if model_name not in self._classifier_cache:
            self._classifier_cache[model_name] = pipeline("zero-shot-classification", model=model_name)
        clf = self._classifier_cache[model_name]
        result = clf(classifier_model.sequence, classifier_model.labels, multi_label=True)
        result["model"] = model_name
        return result

    DEFAULT_NER_MODEL = "dslim/bert-base-NER"

    def extract_entities_from_text(self, text: str, model_name: Optional[str] = None) -> list[dict]:
        """Run named-entity recognition on text. Returns list of {word, entity_group, score, ...}."""
        model = model_name or self.DEFAULT_NER_MODEL
        if model not in self._ner_cache:
            logging.info("Loading NER model '%s' (first use, may download from HuggingFace)...", model)
            self._ner_cache[model] = pipeline("ner", model=model, aggregation_strategy="simple")
            logging.info("NER model '%s' loaded.", model)
        ner = self._ner_cache[model]
        # Process in 2000-char windows to fit BERT's token limits comfortably
        entities = []
        for i in range(0, len(text), 2000):
            window = text[i:i + 2000]
            try:
                entities.extend(ner(window))
            except Exception as e:
                logging.warning("NER failed on window: %s", e)
        logging.info("NER on %d chars produced %d raw entities", len(text), len(entities))
        return entities

    def get_tools(self, names: Optional[Iterable[str]] = None) -> list[FunctionTool]:
        # Lazy-load tools on first use — covers the cron path where Brain
        # was constructed with lightweight=True and now needs tools because
        # a routine / Telegram / Slack message fired an agent.
        if self.tools is None:
            self.tools = tools.load_tools()

        if names is None:
            names = []
        _tools = []

        if len(names) > 0:
            for tool in self.tools:
                if tool.metadata.name in names:
                    # Skip terminal tool when Docker is not configured
                    if tool.metadata.name == "terminal" and self.docker_manager is None:
                        continue
                    _tools.append(tool)
        else:
            _tools = self.tools

        return _tools

    def get_generators(
        self, names: Optional[Iterable[str]] = None
    ) -> list[FunctionTool]:
        if names is None:
            names = []
        _generators = []

        if names:
            for generator in self.generators:
                if generator.__module__.split(".")[-1] in names:
                    _generators.append(generator)
        else:
            _generators = self.generators

        return _generators

    def get_audio_generators(
        self, names: Optional[Iterable[str]] = None
    ) -> list[FunctionTool]:
        if names is None:
            names = []
        _generators = []

        if names:
            for generator in self.audio_generators:
                if generator.__module__.split(".")[-1] in names:
                    _generators.append(generator)
        else:
            _generators = self.audio_generators

        return _generators
