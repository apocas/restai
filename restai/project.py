from restai.models.models import ProjectModel
from restai.vectordb.tools import find_embeddings_path


class Project:

    def __init__(self, model: ProjectModel):
        self.vector = None
        self.props = model
        self.context = None  # Verified context dict (from widget JWT or playground)

        if self.props.type == "rag":
            find_embeddings_path(self.props.name)

    def with_context(self, context: dict, prepend_block: bool = True) -> "Project":
        """Return a new Project with context injected into the system prompt."""
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

    @classmethod
    def reset_memory_index(cls, project_id: int) -> None:
        """Drop memory_search collection on embedding model change.

        Classmethod so the edit-project router can call it without instantiating
        a Project (which would load a vectorstore the swap is about to invalidate).
        """
        try:
            from restai.memory import search as memory_search
            memory_search.reset_collection(int(project_id))
        except Exception:
            import logging
            logging.warning(
                "Project.reset_memory_index: memory_search reset failed",
                exc_info=True,
            )
