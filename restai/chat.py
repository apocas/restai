from datetime import datetime
from uuid import uuid4
from llama_index.core.memory import ChatSummaryMemoryBuffer
from llama_index.core.storage.chat_store import BaseChatStore
from restai.models.models import ChatModel

CONTEXT_WINDOW_RATIO = 0.75  # Reserve 25% of context window for response


class Chat:
    def __init__(self, model: ChatModel, chat_store: BaseChatStore, token_limit: int = 3900,
                 llm=None, project_id=None, user_id=None):
        self.model: ChatModel = model

        if not model.id:
            self.chat_id = str(uuid4())
        else:
            self.chat_id = model.id

        # The store key is DERIVED from (project, user, chat_id), never the raw
        # client-supplied id. `ChatModel.id` is attacker-chosen, and it used to
        # key the chat store directly in one global namespace — so posting a
        # chat with someone else's conversation id (trivially guessable for the
        # integrations, which use `telegram_<chat>` / `slack_<channel>` /
        # `whatsapp_<phone>`) read back their history and let you poison it.
        # Same derivation the agent loops already use for their sandbox/session.
        if project_id is not None and user_id is not None:
            from restai.projects.agent_shared import sandbox_chat_id

            store_key = f"memory_{sandbox_chat_id(project_id, user_id, self.chat_id)}"
        else:
            store_key = f"memory_{self.chat_id}"

        self.memory = ChatSummaryMemoryBuffer.from_defaults(
            token_limit=token_limit,
            llm=llm,
            chat_store=chat_store,
            chat_store_key=store_key,
        )

        self.created: datetime = datetime.now()

    def clear_history(self):
        self.memory.reset()

    def __eq__(self, other: "Chat"):
        return self.chat_id == other.chat_id
