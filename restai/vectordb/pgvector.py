import logging
import re

from sqlalchemy import create_engine, text
from llama_index.core.indices import VectorStoreIndex
from llama_index.core.storage import StorageContext
from llama_index.vector_stores.postgres import PGVectorStore

from restai import config
from restai.brain import Brain
from restai.embedding import Embedding
from restai.vectordb.base import VectorBase
from restai.config import (
    PGVECTOR_HOST,
    PGVECTOR_PORT,
    PGVECTOR_USER,
    PGVECTOR_PASSWORD,
    PGVECTOR_DB,
)

logging.basicConfig(level=config.LOG_LEVEL)


def _sanitize_table_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name).lower()


def _get_sync_connection_string() -> str:
    return (
        f"postgresql+psycopg2://{PGVECTOR_USER}:{PGVECTOR_PASSWORD}"
        f"@{PGVECTOR_HOST}:{PGVECTOR_PORT}/{PGVECTOR_DB}"
    )


def _get_async_connection_string() -> str:
    return (
        f"postgresql+asyncpg://{PGVECTOR_USER}:{PGVECTOR_PASSWORD}"
        f"@{PGVECTOR_HOST}:{PGVECTOR_PORT}/{PGVECTOR_DB}"
    )


class PGVectorDB(VectorBase):
    def __init__(self, brain: Brain, project, embedding: Embedding):
        self.project = project
        self.embedding = embedding
        self.table_name = f"data_{_sanitize_table_name(project.props.name)}"
        self.index = self._vector_init(brain)

    def _vector_init(self, brain: Brain):
        vector_store = PGVectorStore.from_params(
            host=PGVECTOR_HOST,
            port=PGVECTOR_PORT,
            user=PGVECTOR_USER,
            password=PGVECTOR_PASSWORD,
            database=PGVECTOR_DB,
            table_name=self.table_name,
            embed_dim=self.embedding.props.dimension,
        )

        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        return VectorStoreIndex.from_vector_store(
            vector_store,
            storage_context=storage_context,
            embed_model=self.embedding.embedding,
        )

    def _get_engine(self):
        return create_engine(_get_sync_connection_string())

    def save(self):
        pass

    def load(self, brain: Brain):
        pass

    def list(self):
        output = []
        engine = self._get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f'SELECT DISTINCT metadata_->>\'source\' AS source '
                    f'FROM public."{self.table_name}" '
                    f'WHERE metadata_->>\'source\' IS NOT NULL'
                )
            )
            for row in rows:
                output.append(row[0])
        engine.dispose()
        return output

    def list_source(self, source: str):
        output = []
        engine = self._get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f'SELECT metadata_->>\'source\' AS source '
                    f'FROM public."{self.table_name}" '
                    f'WHERE metadata_->>\'source\' = :source'
                ),
                {"source": source},
            )
            for row in rows:
                output.append(row[0])
        engine.dispose()
        return output

    def info(self):
        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text(f'SELECT COUNT(*) FROM public."{self.table_name}"')
            )
            count = result.scalar()
        engine.dispose()
        return count or 0

    def find_source(self, source: str):
        ids = []
        metadatas = []
        documents = []
        engine = self._get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f'SELECT node_id, metadata_, text '
                    f'FROM public."{self.table_name}" '
                    f'WHERE metadata_->>\'source\' = :source'
                ),
                {"source": source},
            )
            for row in rows:
                ids.append(row[0])
                metadatas.append(row[1] if isinstance(row[1], dict) else {})
                documents.append(row[2])
        engine.dispose()
        return {"ids": ids, "metadatas": metadatas, "documents": documents}

    def find_id(self, id: str):
        output = {"id": id}
        engine = self._get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    f'SELECT metadata_, text '
                    f'FROM public."{self.table_name}" '
                    f'WHERE node_id = :node_id'
                ),
                {"node_id": id},
            ).fetchone()
            if row:
                metadata = row[0] if isinstance(row[0], dict) else {}
                output["metadata"] = {
                    k: v for k, v in metadata.items() if not k.startswith("_")
                }
                output["document"] = row[1]
        engine.dispose()
        return output

    def delete(self):
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                conn.execute(
                    text(f'DROP TABLE IF EXISTS public."{self.table_name}"')
                )
                conn.commit()
            engine.dispose()
        except Exception as e:
            logging.exception(e)

    def delete_source(self, source: str):
        engine = self._get_engine()
        ids = []
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f'SELECT node_id FROM public."{self.table_name}" '
                    f'WHERE metadata_->>\'source\' = :source'
                ),
                {"source": source},
            )
            ids = [row[0] for row in rows]
            if ids:
                conn.execute(
                    text(
                        f'DELETE FROM public."{self.table_name}" '
                        f'WHERE metadata_->>\'source\' = :source'
                    ),
                    {"source": source},
                )
                conn.commit()
        engine.dispose()
        return ids

    def delete_id(self, id: str):
        engine = self._get_engine()
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    f'SELECT node_id FROM public."{self.table_name}" '
                    f'WHERE node_id = :node_id'
                ),
                {"node_id": id},
            )
            found = [row[0] for row in rows]
            if found:
                conn.execute(
                    text(
                        f'DELETE FROM public."{self.table_name}" '
                        f'WHERE node_id = :node_id'
                    ),
                    {"node_id": id},
                )
                conn.commit()
        engine.dispose()
        return id

    def reset(self, brain: Brain):
        self.delete()
        self.index = self._vector_init(brain)
