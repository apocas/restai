import os
import shutil
from time import sleep

import chromadb
from app.brain import Brain
from app.tools import FindFileLoader, IndexDocuments

if "EMBEDDINGS_PATH" not in os.environ:
    os.environ["EMBEDDINGS_PATH"] = "./embeddings/"

if "UPLOADS_PATH" not in os.environ:
    os.environ["UPLOADS_PATH"] = "./uploads/"

if "PROJECTS_PATH" not in os.environ:
    os.environ["PROJECTS_PATH"] = "./projects/"

os.environ["ALLOW_RESET"] = "true"

brain = Brain()

projectName = "test_openai"
project = brain.loadProject(projectName)


project_path = os.path.join(os.environ["UPLOADS_PATH"], project.model.name)

brain.initializeEmbeddings(project)

debug = os.path.join(os.environ["EMBEDDINGS_PATH"], project.model.name)
if os.path.exists(os.path.join(os.environ["EMBEDDINGS_PATH"], project.model.name)):
    print("Deleting old embeddings...")
    project.db._client.reset()

if os.path.isdir(project_path):
    for file in os.listdir(project_path):
        file_path = os.path.join(project_path, file)
        if os.path.isfile(file_path):
            _, ext = os.path.splitext(file or '')
            print('Creating embeddings for ' + file_path + '...')
            loader = FindFileLoader(file_path, ext)
            documents = loader.load()

            texts = IndexDocuments(brain, project, documents)
            project.db.persist()
else:
    print("UPLOADS_PATH is not a valid directory")
