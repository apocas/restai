from datetime import datetime
from uuid import uuid4
from llama_index.core.memory import ChatSummaryMemoryBuffer
from llama_index.core.storage.chat_store import BaseChatStore
from restai.models.models import ChatModel

CONTEXT_WINDOW_RATIO = 0.75  # Reserve 25% of context window for response


class Chat:
    def __init__(self, model: ChatModel, chat_store: BaseChatStore, token_limit: int = 3900,
                 llm=None, *, project_id: int, user_id: int):
        from restai.projects.agent_shared import sandbox_chat_id

        self.model: ChatModel = model

        if not model.id:
            self.chat_id = str(uuid4())
        else:
            self.chat_id = model.id

        # The store key is DERIVED from (project, user, chat_id), never the raw
        # `ChatModel.id` — that is attacker-chosen, and keying the shared chat
        # store on it directly meant posting someone else's conversation id
        # (trivially guessable for the integrations, which use
        # `telegram_<chat>` / `slack_<channel>` / `whatsapp_<phone>`) read back
        # their history and let you poison it. The scoping arguments are
        # required so no caller can reintroduce the global namespace by
        # omitting them.
        self.memory = ChatSummaryMemoryBuffer.from_defaults(
            token_limit=token_limit,
            llm=llm,
            chat_store=chat_store,
            chat_store_key=f"memory_{sandbox_chat_id(project_id, user_id, self.chat_id)}",
        )

        self.created: datetime = datetime.now()

    def clear_history(self):
        self.memory.reset()

    def __eq__(self, other: "Chat"):
        return self.chat_id == other.chat_id
