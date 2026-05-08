from restai.cache import Cache
from restai.models.models import ProjectModel
from restai.vectordb.tools import find_embeddings_path


class Project:

    def __init__(self, model: ProjectModel):
        self.vector = None
        self.props = model
        self.context = None  # Verified context dict (from widget JWT or playground)

        if self.props.options.cache:
            self.cache = Cache(self)
        else:
            self.cache = None

        if self.props.type == "rag":
            find_embeddings_path(self.props.name)

    def with_context(self, context: dict, prepend_block: bool = True) -> "Project":
        """Return a new Project with context injected into the system prompt.

        Used by the playground (raw dict), widget endpoint (verified JWT claims),
        and block interpreter (propagated to sub-projects).
        """
        if not context:
            return self
        from restai.utils.widget_context import apply_context
        modified_props = self.props.model_copy(deep=True)
        modified_props.system = apply_context(
            modified_props.system or "", context, prepend_block=prepend_block,
        )
        new_project = Project(modified_props)
        new_project.vector = self.vector
        new_project.context = context
        return new_project

    def delete(self):
        if self.vector:
            self.vector.delete()
        if self.cache:
            self.cache.delete()

    @classmethod
    def reset_memory_index(cls, project_id: int) -> None:
        """Drop the project's per-project memory_search Chroma
        collection. Used when the project's embedding model changes —
        existing vectors were computed with the old model and aren't
        comparable to anything the new one produces, so the only
        honest answer is to rebuild from scratch on the next cron
        tick. Best-effort; a missing collection is fine.

        Classmethod (not instance method) because the caller — the
        edit-project router — has the SQLAlchemy row, not a runtime
        Project instance, and instantiating one just to call this
        would force a vectorstore load the swap is about to
        invalidate.
        """
        try:
            from restai import memory_search
            memory_search.reset_collection(int(project_id))
        except Exception:
            import logging
            logging.warning(
                "Project.reset_memory_index: memory_search reset failed",
                exc_info=True,
            )
