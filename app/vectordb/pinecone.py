from app.vectordb.base import VectorBase


class PineconeVector(VectorBase):  
    def __init__(self, brain, project):
        self.project = project
        self.index = None


    def save(self):
        pass
      
    def load(self, brain):
        pass

    def list(self):
        pass


    def list_source(self, source):
        pass


    def info(self):
        pass

    def find_source(self, source):
        pass


    def find_id(self, id):
        pass


    def delete(self):
        pass
        

    def delete_source(self, source):
        pass


    def delete_id(self, id):
        pass


    def reset(self, brain):
        pass