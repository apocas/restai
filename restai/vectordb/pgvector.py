import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from llama_index.core.indices import VectorStoreIndex
from llama_index.core.storage import StorageContext
from llama_index.vector_stores.postgres import PGVectorStore

from restai import config
import restai.config as _cfg
from restai.brain import Brain
from restai.embedding import Embedding
from restai.vectordb.base import VectorBase

logging.basicConfig(level=config.LOG_LEVEL)


def _get_sync_connection_string() -> str:
    # Resolve through `_cfg.X` each call so GUI changes apply without worker restart.
    return (
        f"postgresql+psycopg2://{_cfg.PGVECTOR_USER}:{_cfg.PGVECTOR_PASSWORD}"
        f"@{_cfg.PGVECTOR_HOST}:{_cfg.PGVECTOR_PORT}/{_cfg.PGVECTOR_DB}"
    )


def _get_async_connection_string() -> str:
    return (
        f"postgresql+asyncpg://{_cfg.PGVECTOR_USER}:{_cfg.PGVECTOR_PASSWORD}"
        f"@{_cfg.PGVECTOR_HOST}:{_cfg.PGVECTOR_PORT}/{_cfg.PGVECTOR_DB}"
    )


class PGVectorDB(VectorBase):
    def __init__(self, brain: Brain, project, embedding: Embedding):
        super().__init__(brain, project, embedding)
        # Name handed to `PGVectorStore.from_params(table_name=...)`.
        self.table_name = f"data_{self.store_key}"
        # ...and the name of the table it ACTUALLY creates. llama-index
        # prefixes another `data_` of its own (`get_data_model`:
        # `tablename = "data_%s" % index_name`), so the physical table is
        # `data_data_p{id}`.
        #
        # Every raw-SQL method below used `table_name` and therefore queried a
        # relation that has never existed: `info`, `list`, `list_source`,
        # `find_source`, `find_id`, `delete_source`, `delete_id` and
        # `list_all_chunks` all raised UndefinedTable, and `delete()` — a
        # `DROP TABLE IF EXISTS` — silently dropped nothing, so removing a
        # project leaked its whole vector table. Only the llama-index-mediated
        # paths (ingest, retrieval) ever worked.
        #
        # The double prefix is preserved rather than "cleaned up" because it is
        # the on-disk name in every existing pgvector deployment; renaming it
        # would orphan their data.
        self.physical_table = f"data_{self.table_name}"
        self.index = self._vector_init(brain)

    def _vector_init(self, brain: Brain):
        vector_store = PGVectorStore.from_params(
            host=_cfg.PGVECTOR_HOST,
            port=_cfg.PGVECTOR_PORT,
            user=_cfg.PGVECTOR_USER,
            password=_cfg.PGVECTOR_PASSWORD,
            database=_cfg.PGVECTOR_DB,
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

    @contextmanager
    def _conn(self):
        """Connection whose engine is always disposed.

        Every method used to call `engine.dispose()` on the success path only,
        so any raised query leaked its pool — which mattered a great deal while
        the table name was wrong and *every* call raised."""
        engine = self._get_engine()
        try:
            with engine.connect() as conn:
                yield conn
        finally:
            engine.dispose()

    def save(self):
        pass

    def load(self, brain: Brain):
        pass

    def list(self):
        output = []
        with self._conn() as conn:
            rows = conn.execute(
                text(
                    f'SELECT DISTINCT metadata_->>\'source\' AS source '
                    f'FROM public."{self.physical_table}" '
                    f'WHERE metadata_->>\'source\' IS NOT NULL'
                )
            )
            for row in rows:
                output.append(row[0])
        return output

    def list_source(self, source: str):
        output = []
        with self._conn() as conn:
            rows = conn.execute(
                text(
                    f'SELECT metadata_->>\'source\' AS source '
                    f'FROM public."{self.physical_table}" '
                    f'WHERE metadata_->>\'source\' = :source'
                ),
                {"source": source},
            )
            for row in rows:
                output.append(row[0])
        return output

    def info(self):
        with self._conn() as conn:
            result = conn.execute(
                text(f'SELECT COUNT(*) FROM public."{self.physical_table}"')
            )
            count = result.scalar()
        return count or 0

    def find_source(self, source: str):
        ids = []
        metadatas = []
        documents = []
        with self._conn() as conn:
            rows = conn.execute(
                text(
                    f'SELECT node_id, metadata_, text '
                    f'FROM public."{self.physical_table}" '
                    f'WHERE metadata_->>\'source\' = :source'
                ),
                {"source": source},
            )
            for row in rows:
                ids.append(row[0])
                metadatas.append(row[1] if isinstance(row[1], dict) else {})
                documents.append(row[2])
        return {"ids": ids, "metadatas": metadatas, "documents": documents}

    def find_id(self, id: str):
        output = {"id": id}
        with self._conn() as conn:
            row = conn.execute(
                text(
                    f'SELECT metadata_, text '
                    f'FROM public."{self.physical_table}" '
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
        return output

    def delete(self):
        try:
            with self._conn() as conn:
                conn.execute(
                    text(f'DROP TABLE IF EXISTS public."{self.physical_table}"')
                )
                conn.commit()
        except Exception as e:
            logging.exception(e)

    def delete_source(self, source: str):
        ids = []
        with self._conn() as conn:
            rows = conn.execute(
                text(
                    f'SELECT node_id FROM public."{self.physical_table}" '
                    f'WHERE metadata_->>\'source\' = :source'
                ),
                {"source": source},
            )
            ids = [row[0] for row in rows]
            if ids:
                conn.execute(
                    text(
                        f'DELETE FROM public."{self.physical_table}" '
                        f'WHERE metadata_->>\'source\' = :source'
                    ),
                    {"source": source},
                )
                conn.commit()
        return ids

    def delete_id(self, id: str):
        with self._conn() as conn:
            rows = conn.execute(
                text(
                    f'SELECT node_id FROM public."{self.physical_table}" '
                    f'WHERE node_id = :node_id'
                ),
                {"node_id": id},
            )
            found = [row[0] for row in rows]
            if found:
                conn.execute(
                    text(
                        f'DELETE FROM public."{self.physical_table}" '
                        f'WHERE node_id = :node_id'
                    ),
                    {"node_id": id},
                )
                conn.commit()
        return id

    def reset(self, brain: Brain):
        self.delete()
        self.index = self._vector_init(brain)

    def list_all_chunks(self, limit=50000):
        output = []
        with self._conn() as conn:
            rows = conn.execute(
                text(
                    f"SELECT node_id, metadata_->>'source' AS source, text "
                    f'FROM public."{self.physical_table}" '
                    f"LIMIT {int(limit)}"
                )
            )
            for row in rows:
                output.append({"id": row[0], "source": row[1] or "", "text": row[2] or ""})
        return output

    def list_all_nodes(self, limit=1000, offset=0):
        import json as _json

        output = []
        with self._conn() as conn:
            # ORDER BY node_id so paging is stable — without it Postgres may
            # return rows in a different order per call and OFFSET would skip
            # and duplicate chunks across pages.
            rows = conn.execute(
                text(
                    f"SELECT node_id, metadata_, text "
                    f'FROM public."{self.physical_table}" '
                    f"ORDER BY node_id "
                    f"LIMIT {int(limit)} OFFSET {int(offset)}"
                )
            )
            for row in rows:
                meta = row[1]
                if isinstance(meta, str):
                    try:
                        meta = _json.loads(meta)
                    except ValueError:
                        meta = {}
                output.append({
                    "id": row[0],
                    "text": row[2] or "",
                    "metadata": dict(meta or {}),
                })
        return output
