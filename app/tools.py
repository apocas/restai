from fastapi import HTTPException
from modules.loaders import LOADERS


def IndexDocuments(brain, project, documents):
    texts = brain.text_splitter.split_documents(documents)
    texts_final = [doc.page_content for doc in texts]
    metadatas = [doc.metadata for doc in texts]

    for metadata in metadatas:
      for key, value in list(metadata.items()):
        if value is None:
            del metadata[key]
    
    project.db.add_texts(texts=texts_final, metadatas=metadatas)
    return texts_final


def FindFileLoader(temp, ext):
    if ext in LOADERS:
      loader_class, loader_args = LOADERS[ext]
      return loader_class(temp.name, **loader_args)
    else:
        raise HTTPException(status_code=500, detail='{"error": "Invalid file type."}')