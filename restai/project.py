from restai.cache import Cache
from restai.models.models import ProjectModel
from restai.vectordb.tools import find_embeddings_path
class Project:

    def __init__(self, model: ProjectModel):
        self.vector = None
        self.props = model

        if self.props.options.cache:
            self.cache = Cache(self)
        else:
            self.cache = None

        if self.props.type == "rag":
            find_embeddings_path(self.props.name)

    def delete(self):
        if self.vector:
            self.vector.delete()
        if self.cache:
            self.cache.delete()
