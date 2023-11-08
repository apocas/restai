import os
from fastapi import HTTPException
from modules.loaders import LOADERS


def IndexDocuments(brain, project, documents):
    docs = brain.text_splitter.split_documents(documents)
    
    texts = [doc.page_content for doc in docs]
    metadatas = [doc.metadata for doc in docs]

    for metadata in metadatas:
      for key, value in list(metadata.items()):
        if value is None:
            del metadata[key]
    
    ids = project.db.add_texts(texts=texts, metadatas=metadatas)
    return ids


def FindFileLoader(filepath, ext):
    if ext in LOADERS:
      loader_class, loader_args = LOADERS[ext]
      return loader_class(filepath, **loader_args)
    else:
        raise Exception("Invalid file type.")
      
      
def FindEmbeddingsPath(projectName): 
    embeddings_path = os.environ["EMBEDDINGS_PATH"]
    project_dirs = [d for d in os.listdir(embeddings_path) if os.path.isdir(os.path.join(embeddings_path, d))]

    for dir in project_dirs:
        if dir.startswith(projectName + "_"):
            return os.path.join(embeddings_path, dir)

    raise Exception("Project not found.")