from fastapi import HTTPException
from langchain.text_splitter import CharacterTextSplitter

from app.project import Project

class Brain:
    def __init__(self):
       self.projects = []

       self.text_splitter = CharacterTextSplitter(separator=" ", chunk_size=1024, chunk_overlap=0)

    def listProjects(self):
        return [project.model.name for project in self.projects]

    def createProject(self, projectModel):
        project = Project()
        project.boot(projectModel)
        project.save()
        self.projects.append(project)

    def loadProject(self, name):
        for project in self.projects:
          if project.model.name == name:
            return project

        project = Project()
        project.load(name)
        self.projects.append(project)
        return project
        
    
    def deleteProject(self, name):
        for project in self.projects:
          if project.model.name == name:
            project.delete()
            self.projects.remove(project)

